"""The waitlist: /v1/waitlist and the admin views over it.

Public while the product is locked (see app/core/lockdown.py). This is the one thing a visitor can
actually DO before launch, so it has to work without an account, without a credit, and without
anything that can fail: a campaign drives people here once, and a form that errors is a backer lost.

Three decisions worth keeping:

* **Idempotent per address.** Re-submitting returns success rather than an error. A duplicate is not
  a mistake the visitor made, and telling somebody "you are already on the list" as an ERROR reads
  as rejection at the exact moment you want them to feel welcomed.
* **The email is normalised before it is stored**, so ``Foo@Bar.com`` and ``foo@bar.com`` are one
  person and the launch blast mails them once.
* **Nothing here reveals the list.** The public route never says whether an address was already
  present, because that would turn the endpoint into an oracle for checking whether a given person
  signed up.
"""

from __future__ import annotations

import logging
import re

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.core.auth import CurrentUser, require_user
from app.core.config import get_settings
from app.core.ip import client_ip, hash_ip
from app.core.rate_limit import WAITLIST_LIMITER, enforce
from app.storage.db import get_session
from app.storage.models import WaitlistEntry

log = logging.getLogger("omi.waitlist")


def _now() -> datetime:
    return datetime.now(timezone.utc)

router = APIRouter(prefix="/v1/waitlist", tags=["waitlist"])
admin_router = APIRouter(prefix="/v1/admin/waitlist", tags=["admin-waitlist"])

#: Deliberately permissive. This is a mailing list, not an authentication boundary: the cost of
#: rejecting a real address that happens to look unusual (a long TLD, a plus tag, a non-Latin local
#: part) is a lost backer, while the cost of accepting a junk one is a row somebody deletes.
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s.]+\.[^@\s]+$")

MAX_EMAIL_LEN = 320          # the RFC maximum, and what the column holds
VALID_SOURCES = {"landing", "coming_soon", "signup", "report"}


def normalise_email(raw: str | None) -> str | None:
    """Lowercased, stripped, and validated. None when it is not usable."""
    email = (raw or "").strip().lower()
    if not email or len(email) > MAX_EMAIL_LEN or not _EMAIL_RE.match(email):
        return None
    return email


def join_waitlist(session, email: str, *, source: str = "coming_soon",
                  ip_hash: str | None = None) -> bool:
    """Add an address if it is not already there. Returns whether a row was created. Never raises.

    Shared by the public route and by signup, so an account created during lockdown lands on the
    same list and gets the same launch email. The insert races on the unique index rather than
    checking first, because a check-then-insert loses that race under concurrent submits and the
    duplicate would surface as a 500 on a form a visitor is watching.
    """
    email = normalise_email(email) or ""
    if not email:
        return False
    try:
        with session.begin_nested():
            session.add(WaitlistEntry(
                email=email,
                source=source if source in VALID_SOURCES else "coming_soon",
                ip_hash=ip_hash,
            ))
        return True
    except IntegrityError:
        return False                     # already on the list; not an error
    except Exception:                    # noqa: BLE001
        log.warning("waitlist insert failed", exc_info=True)
        return False


class JoinRequest(BaseModel):
    email: str
    source: str | None = None


class JoinResponse(BaseModel):
    joined: bool
    #: What to show the visitor. Identical whether or not they were already on the list.
    message: str


@router.post("", response_model=JoinResponse)
def join(
    body: JoinRequest,
    request: Request,
    response: Response,
) -> JoinResponse:
    """Join the waitlist. No auth, no credits, and safe to call twice."""
    enforce(WAITLIST_LIMITER, f"ip:{client_ip(request)}", what="waitlist")

    email = normalise_email(body.email)
    if email is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="That does not look like an email address.",
        )

    with get_session() as session:
        join_waitlist(session, email, source=body.source or "coming_soon",
                      ip_hash=hash_ip(client_ip(request)))

    # 200 either way. The response is the same whether the row was new or already present, so this
    # endpoint cannot be used to check whether a particular person is on the list.
    response.status_code = status.HTTP_200_OK
    return JoinResponse(
        joined=True,
        message="You are on the list. We will email you the moment OmiSphere opens.",
    )


# --------------------------------------------------------------------------------------------- #
# Admin
# --------------------------------------------------------------------------------------------- #
def _require_admin(current: CurrentUser) -> None:
    """Local mode resolves to is_admin=True, so a test that means to prove this gate must set
    OMI_REQUIRE_AUTH=true and sign up a real user."""
    if not current.is_admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admins only.")


class WaitlistRow(BaseModel):
    id: int
    email: str
    source: str
    created_at: str
    notified: bool


class WaitlistPage(BaseModel):
    entries: list[WaitlistRow]
    total: int
    pending: int          # still owed a launch email
    notified: int


@admin_router.get("", response_model=WaitlistPage)
def list_waitlist(
    limit: int = 200,
    offset: int = 0,
    current: CurrentUser = Depends(require_user),
) -> WaitlistPage:
    _require_admin(current)
    limit = max(1, min(1000, limit))

    with get_session() as session:
        total = int(session.execute(
            select(func.count()).select_from(WaitlistEntry)
        ).scalar_one())
        notified = int(session.execute(
            select(func.count()).select_from(WaitlistEntry)
            .where(WaitlistEntry.notified_at.is_not(None))
        ).scalar_one())
        rows = session.execute(
            select(WaitlistEntry)
            .order_by(WaitlistEntry.created_at.desc())
            .limit(limit).offset(max(0, offset))
        ).scalars().all()

        return WaitlistPage(
            entries=[
                WaitlistRow(
                    id=r.id, email=r.email, source=r.source,
                    created_at=r.created_at.isoformat() if r.created_at else "",
                    notified=r.notified_at is not None,
                )
                for r in rows
            ],
            total=total,
            pending=total - notified,
            notified=notified,
        )


@admin_router.get("/export.csv")
def export_waitlist(current: CurrentUser = Depends(require_user)) -> Response:
    """The whole list as CSV, for importing into whatever you actually send mail from.

    Opens with a BOM: Excel on Windows reads a BOM-less UTF-8 file as the local codepage and mangles
    every non-Latin address, and this is a list of real people's contact details.
    """
    _require_admin(current)
    import csv
    import io

    buf = io.StringIO()
    w = csv.writer(buf, quoting=csv.QUOTE_MINIMAL, lineterminator="\n")
    w.writerow(["email", "source", "created_at", "notified_at"])
    with get_session() as session:
        for r in session.execute(
            select(WaitlistEntry).order_by(WaitlistEntry.created_at.asc())
        ).scalars():
            w.writerow([
                r.email, r.source,
                r.created_at.isoformat() if r.created_at else "",
                r.notified_at.isoformat() if r.notified_at else "",
            ])

    return Response(
        content="﻿" + buf.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="omisphere-waitlist.csv"'},
    )


# --------------------------------------------------------------------------------------------- #
# The launch email
# --------------------------------------------------------------------------------------------- #
LAUNCH_SUBJECT = "OmiSphere is open"

LAUNCH_BODY = """\
OmiSphere is open.

You asked to be told when you could use it, so: you can, right now.

Paste the link to any X or YouTube post and OmiSphere compiles who commented on it, then scores the
accounts you choose. Every score comes with the evidence behind it and a written read you can check
against what the account actually posted.

  {base}

Compiling a comment section is free. You start with {trial} credits, which cover {accounts} accounts.

Thanks for waiting.

- OmiSphere

You are receiving this once, because you joined the waitlist at omisphere.online. There is nothing
to unsubscribe from: this is the only email the waitlist sends.
"""


class NotifyResponse(BaseModel):
    sent: int
    failed: int
    remaining: int
    smtp_configured: bool
    detail: str


@admin_router.post("/notify", response_model=NotifyResponse)
def notify_waitlist(
    limit: int = 500,
    current: CurrentUser = Depends(require_user),
) -> NotifyResponse:
    """Send the launch email to everybody still owed one. SAFE TO RUN TWICE.

    ``notified_at`` is stamped per address as its mail is accepted, and committed as the run goes
    rather than at the end. So a run that dies half way through resumes from where it stopped, and a
    second run mails nobody twice. That property is not decoration: the operator will re-run this,
    either because the first run errored or because they are not sure it worked, and mailing your
    whole waitlist twice on launch day is the most visible possible way to look careless.

    ``limit`` bounds one call so a large list is sent in batches rather than in one request that
    times out behind a proxy. Call it until ``remaining`` is 0.
    """
    _require_admin(current)

    from app.notifications.delivery import send_transactional_email

    settings = get_settings()
    smtp_ok = bool(settings.smtp_host)

    base = (settings.public_base_url or "https://omisphere.online").rstrip("/")
    trial = int(settings.free_trial_credits)
    from app.core.plans import ACCOUNTS_PER_CREDIT

    body = LAUNCH_BODY.format(base=base, trial=trial, accounts=trial * ACCOUNTS_PER_CREDIT)

    sent = failed = 0
    with get_session() as session:
        pending = session.execute(
            select(WaitlistEntry)
            .where(WaitlistEntry.notified_at.is_(None))
            .order_by(WaitlistEntry.created_at.asc())
            .limit(max(1, min(2000, limit)))
        ).scalars().all()

        for row in pending:
            ok, err = send_transactional_email(row.email, LAUNCH_SUBJECT, body)
            if ok:
                # Stamped INSIDE the loop. Marking the whole batch at the end would re-send every
                # address in it if the run died part way, which is the exact failure this exists to
                # prevent.
                row.notified_at = _now()
                sent += 1
            else:
                failed += 1
                log.warning("waitlist launch email failed for one address: %s", err)

        remaining = int(session.execute(
            select(func.count()).select_from(WaitlistEntry)
            .where(WaitlistEntry.notified_at.is_(None))
        ).scalar_one()) - sent

    if not smtp_ok:
        detail = (
            "SMTP is not configured, so nothing was sent and nobody was marked as notified. "
            "Set OMI_SMTP_HOST (plus OMI_SMTP_USER / OMI_SMTP_PASSWORD / OMI_SMTP_FROM) on the API "
            "service and redeploy, then run this again. Until then, export the CSV and send from "
            "your own mail provider."
        )
    elif failed:
        detail = (
            f"{sent} sent, {failed} failed. Failures were NOT marked as notified, so running this "
            f"again retries only them."
        )
    else:
        detail = f"{sent} sent. {max(0, remaining)} still to go."

    return NotifyResponse(
        sent=sent, failed=failed, remaining=max(0, remaining),
        smtp_configured=smtp_ok, detail=detail,
    )
