"""Report + sharing endpoints — Phase 6.

Two router groups in one file:

* Authenticated: mint/revoke a share token on an investigation.
* Public: render the report by token. No auth, no credits, no rate
  limiting for now — adding that is Phase 9 work.

Public routes live under ``/r/...`` (short URLs); the Next.js public
page mirrors that at ``/r/{token}``.
"""

from __future__ import annotations

import logging
import secrets
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, Response, status
from pydantic import BaseModel, Field

from app.core.auth import CurrentUser, require_user
from app.reports.templates import build_report_view, render_markdown
from app.storage.db import get_session
from app.storage.repository import AccountRepository
from app.storage.models import Investigation

log = logging.getLogger("omi.reports")


# ---------------------------------------------------------------------------
# Auth-required: mint / revoke share token
# ---------------------------------------------------------------------------

share_router = APIRouter(prefix="/v1/investigations", tags=["reports"])


class ShareResponse(BaseModel):
    slug: str
    share_token: str
    is_public: bool
    published_at: datetime | None
    public_url: str


@share_router.post("/{slug}/share", response_model=ShareResponse)
def create_share_token(
    slug: str,
    current: CurrentUser = Depends(require_user),
) -> ShareResponse:
    """Mint (or reuse) a share token for this investigation.

    The investigation becomes publicly readable at /r/{token}. Idempotent:
    calling twice returns the existing token rather than rotating.
    """
    with get_session() as session:
        repo = AccountRepository(session)
        inv = repo.get_investigation(
            slug=slug, user_id=current.id if current.id != 0 else None,
        )
        if inv is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                                detail="Investigation not found.")
        if not inv.share_token:
            inv.share_token = "rpt_" + secrets.token_urlsafe(16)
        inv.is_public = 1
        inv.published_at = inv.published_at or datetime.now(timezone.utc)
        return ShareResponse(
            slug=inv.slug,
            share_token=inv.share_token,
            is_public=bool(inv.is_public),
            published_at=inv.published_at,
            public_url=f"/r/{inv.share_token}",
        )


@share_router.delete("/{slug}/share")
def revoke_share_token(
    slug: str,
    current: CurrentUser = Depends(require_user),
) -> dict:
    """Revoke the share token. Public URL immediately 404s afterward."""
    with get_session() as session:
        repo = AccountRepository(session)
        inv = repo.get_investigation(
            slug=slug, user_id=current.id if current.id != 0 else None,
        )
        if inv is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                                detail="Investigation not found.")
        inv.share_token = None
        inv.is_public = 0
        return {"ok": True}


# ---------------------------------------------------------------------------
# Public: report data + markdown / json exports
# ---------------------------------------------------------------------------

from app.core.rate_limit import public_report_rate_limit  # noqa: E402

public_router = APIRouter(
    prefix="/r", tags=["public-reports"],
    dependencies=[Depends(public_report_rate_limit)],
)


class PublicReportResponse(BaseModel):
    view: dict


def _resolve(token: str) -> Investigation:
    from sqlalchemy import select
    with get_session() as session:
        inv = session.execute(
            select(Investigation).where(
                Investigation.share_token == token,
                Investigation.is_public == 1,
            )
        ).scalar_one_or_none()
    if inv is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="Report not found or no longer public.")
    return inv


def _read_count(token: str) -> int | None:
    """How many distinct readers this shared report has had, from the existing deduped view log.

    Real social proof or none: returns None on any failure rather than a zero that would read as
    "nobody has looked at this". The presentation layer also hides it below a threshold, because a
    report read three times makes the product look dead.
    """
    from sqlalchemy import func, select as _select

    from app.storage.models import EventLog

    # The token lives INSIDE payload_json; EventLog has no token column. The JSON path comparison
    # renders as json_extract on SQLite and ->> on Postgres, so one query covers both.
    try:
        with get_session() as session:
            return int(session.execute(
                _select(func.count()).select_from(EventLog).where(
                    EventLog.kind == "public_report_view",
                    EventLog.payload_json["token"].as_string() == token,
                )
            ).scalar_one() or 0)
    except Exception:
        return None


#: Keys inside ``payload_json`` that carry the analyst's internals and must never reach an
#: unauthenticated response. Both hold the admin-only eight-signal breakdown and internal provenance
#: (trace ids, prompt hashes, token counts); the checkpoint additionally holds the RAW per-batch
#: assessments, i.e. exactly what the viewer gate exists to filter, one batch at a time.
_PAYLOAD_KEYS_NEVER_PUBLIC = ("CACHE_KEY", "BATCH_PARTS_KEY")


def _public_payload(payload: dict | None) -> dict:
    """The scan payload with the analyst's internal state removed, for the public JSON export.

    ``payload_json`` carries the analyst entry under its cache key, and an in-flight run's per-batch
    checkpoint under another. Both hold the admin-only eight-signal breakdown plus internal
    provenance (trace ids, prompt hashes, token counts). Dumping the payload raw on an
    UNAUTHENTICATED route bypassed the viewer gate entirely: the page and the markdown export both
    filter, and this one handed over everything.

    The filtered per-account reads are already on ``investigation.account_reads``, so a programmatic
    consumer still gets the analyst's conclusions, just not the unfinished feature or the internals.

    Resolved by NAME from the analyst module, so a key renamed there cannot silently stop being
    stripped here.
    """
    from app.reasoning import analyst as _analyst

    if not isinstance(payload, dict):
        return {}
    drop = {getattr(_analyst, name) for name in _PAYLOAD_KEYS_NEVER_PUBLIC}
    return {k: v for k, v in payload.items() if k not in drop}


def _account_reads(inv: Investigation) -> list[dict]:
    """The model's written read per account, for the public report.

    Filtered through the SAME viewer gate the signed-in routes use, with ``is_admin=False`` hardcoded
    because this route is anonymous. That keeps the eight-signal breakdown (an unfinished, admin-only
    feature) out of a public response without this function needing to know which fields those are.

    Only resolved accounts are carried: an unresolved alias has no identity to attach a public claim
    to, and publishing one would be a statement about nobody.
    """
    from app.reasoning import analyst

    try:
        entry = analyst.cached_assessment(inv)
        if not entry or not analyst.entry_is_model_backed(entry):
            return []
        served = analyst.assessment_for_viewer(entry.get("assessment"), is_admin=False) or {}
        rows = served.get("commenter_assessments") or []
        out: list[dict] = []
        for r in rows:
            if not isinstance(r, dict) or not r.get("resolved"):
                continue
            out.append({
                "external_id": r.get("external_id"),
                "handle": r.get("handle"),
                "omi_score": r.get("omi_score"),
                "suspicion_tier": r.get("suspicion_tier"),
                "assessment": r.get("assessment"),
            })
        return out
    except Exception:
        # A shared report must render even if the analyst entry is malformed. Losing the prose is a
        # degraded page; a 500 is a dead link somebody already posted publicly.
        return []


def _investigation_to_dict(inv: Investigation) -> dict:
    return {
        "slug": inv.slug,
        "label": inv.label,
        "input_url": inv.input_url,
        "kind": inv.kind,
        "created_at": inv.created_at,
        "published_at": inv.published_at,
        "batch_count": inv.batch_count,
        "quota_used": inv.quota_used,
        # Phase 7 — surfaced on the public report when present
        "commentary_text": inv.commentary_text,
        "commentary_provider": inv.commentary_provider,
        "commentary_generated_at": inv.commentary_generated_at,
        # Funnel: how much of the post this report actually covers (see Investigation.commenters_available).
        "commenters_available": getattr(inv, "commenters_available", None),
        # The analyst's per-account reads, built HERE rather than per route. Adding it at one call
        # site is exactly what made the markdown export disagree with the page it exports.
        "account_reads": _account_reads(inv),
    }


@public_router.get("/{token}", response_model=PublicReportResponse)
def public_report_view(
    request: Request,
    token: str = Path(min_length=8),
    template: Literal["executive", "evidence"] = Query("executive"),
) -> PublicReportResponse:
    """Render the report data for the Next.js public page."""
    inv = _resolve(token)
    meta = _investigation_to_dict(inv)
    # Counted BEFORE this request is recorded, so the number a reader sees is other people, not
    # themselves. Off-by-one here would be the kind of small dishonesty this page cannot afford.
    meta["read_count"] = _read_count(token)
    view = build_report_view(
        template=template,
        investigation=meta,
        payload=inv.payload_json or {},
    )
    # Q3 (founder learning): was the shared link actually read? Deduped per
    # (token, ip-hash) per 10 min; token only, user_id NULL, IP never stored.
    from app.analytics.event_log import record_public_view
    from app.core.ip import client_ip
    record_public_view(token, "investigation", ip=client_ip(request))
    return PublicReportResponse(view=view)


@public_router.get("/{token}/markdown")
def public_report_markdown(
    token: str = Path(min_length=8),
    template: Literal["executive", "evidence"] = Query("evidence"),
) -> Response:
    """Download the report as Markdown text."""
    inv = _resolve(token)
    md = render_markdown(
        template=template,
        investigation=_investigation_to_dict(inv),
        payload=inv.payload_json or {},
    )
    return Response(
        content=md,
        media_type="text/markdown; charset=utf-8",
        headers={
            "Content-Disposition": (
                f'attachment; filename="{inv.slug}-{template}.md"'
            ),
        },
    )


@public_router.get("/{token}/json")
def public_report_json(token: str = Path(min_length=8)) -> Response:
    """Raw payload export. Useful for archival or programmatic consumers."""
    import json
    inv = _resolve(token)
    body = json.dumps(
        {
            "investigation": _investigation_to_dict(inv),
            "payload": _public_payload(inv.payload_json),
        },
        default=str,
        indent=2,
    )
    return Response(
        content=body,
        media_type="application/json",
        headers={
            "Content-Disposition": (
                f'attachment; filename="{inv.slug}.json"'
            ),
        },
    )


# ---------------------------------------------------------------------------
# Disputes: the recourse an accused account has
#
# OmiSphere publishes scored claims about named real people who never agreed to be analysed. A person
# who believes a report is wrong about them needs a way to say so that does not require creating an
# account with the product accusing them. This is that route.
#
# It is also the operational answer to a data-protection objection or erasure request from someone
# whose data was collected indirectly, and the reason an operator can say "reviewed and acted within a
# day" instead of "there was no way to reach us".
# ---------------------------------------------------------------------------
DISPUTE_STATUSES = ("open", "reviewing", "upheld", "rejected")


class DisputeIn(BaseModel):
    subject_handle: str | None = Field(default=None, max_length=255)
    contact: str | None = Field(default=None, max_length=320)
    reason: str = Field(min_length=10, max_length=4000)


class DisputeOut(BaseModel):
    id: int
    share_token: str
    subject_handle: str | None
    contact: str | None
    reason: str
    status: str
    resolution_note: str | None
    created_at: str | None
    resolved_at: str | None
    report_still_public: bool


@public_router.post("/{token}/dispute", status_code=status.HTTP_201_CREATED)
def submit_dispute(
    body: DisputeIn,
    request: Request,
    token: str = Path(min_length=8),
) -> dict:
    """Object to a public report. UNAUTHENTICATED by design.

    The person disputing a report is, by definition, not a customer. Requiring them to sign up to the
    product that published a claim about them would make the recourse theatre.

    Submitting does NOT unpublish anything. That would let anyone silence any report by claiming to be
    named in it, which is its own abuse vector, and the token is guessable to precisely nobody but
    shareable by everyone. The mitigation is on the other side: an admin can unpublish in one call and
    sees the queue.

    Accepted even when the token no longer resolves. Someone objecting to a report that was just
    unshared still deserves a record of having objected, and a 404 here would read as stonewalling.
    """
    from sqlalchemy import select as _select

    from app.core.ip import client_ip, hash_ip
    from app.storage.models import ReportDispute

    reason = (body.reason or "").strip()
    if len(reason) < 10:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Tell us what is wrong with the report so we can check it.",
        )
    ip_hash = None
    try:
        ip_hash = hash_ip(client_ip(request))
    except Exception:
        pass

    with get_session() as session:
        inv = session.execute(
            _select(Investigation).where(Investigation.share_token == token)
        ).scalar_one_or_none()

        # One open dispute per (token, subject) is enough. A person hitting submit twice should not
        # produce two queue entries an operator has to reconcile.
        handle = (body.subject_handle or "").strip() or None
        existing = session.execute(
            _select(ReportDispute).where(
                ReportDispute.share_token == token,
                ReportDispute.subject_handle == handle,
                ReportDispute.status.in_(("open", "reviewing")),
            )
        ).scalars().first()
        if existing is not None:
            return {"recorded": True, "id": existing.id, "already_open": True}

        row = ReportDispute(
            share_token=token,
            investigation_id=inv.id if inv is not None else None,
            subject_handle=handle,
            contact=(body.contact or "").strip() or None,
            reason=reason,
            status="open",
            ip_hash=ip_hash,
        )
        session.add(row)
        session.flush()
        log.warning(
            "report dispute filed: token=%s subject=%s dispute_id=%s (report %s)",
            token, handle or "?", row.id,
            "exists" if inv is not None else "already unshared",
        )
        return {"recorded": True, "id": row.id, "already_open": False}


# ---------------------------------------------------------------------------
# Admin: review the queue, and unpublish ANY report
# ---------------------------------------------------------------------------
admin_router = APIRouter(prefix="/v1/admin/disputes", tags=["admin-disputes"])


def _dispute_out(row, still_public: bool) -> DisputeOut:
    return DisputeOut(
        id=row.id, share_token=row.share_token, subject_handle=row.subject_handle,
        contact=row.contact, reason=row.reason, status=row.status,
        resolution_note=row.resolution_note,
        created_at=row.created_at.isoformat() if row.created_at else None,
        resolved_at=row.resolved_at.isoformat() if row.resolved_at else None,
        report_still_public=still_public,
    )


@admin_router.get("", response_model=list[DisputeOut])
def list_disputes(
    status_filter: str = Query("open", alias="status"),
    limit: int = Query(100, ge=1, le=500),
    current: CurrentUser = Depends(require_user),
) -> list[DisputeOut]:
    """The dispute queue. Admin only, because it holds complainants' contact details."""
    from sqlalchemy import select as _select

    from app.storage.models import ReportDispute

    if not current.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admins only.")
    with get_session() as session:
        q = _select(ReportDispute).order_by(ReportDispute.created_at.desc()).limit(limit)
        if status_filter and status_filter != "all":
            q = q.where(ReportDispute.status == status_filter)
        rows = list(session.execute(q).scalars().all())
        live = {
            t for (t,) in session.execute(
                _select(Investigation.share_token).where(
                    Investigation.share_token.in_([r.share_token for r in rows] or [""]),
                    Investigation.is_public == 1,
                )
            ).all()
        }
        return [_dispute_out(r, r.share_token in live) for r in rows]


class DisputeResolution(BaseModel):
    status: str
    note: str | None = Field(default=None, max_length=2000)
    unpublish: bool = False


@admin_router.post("/{dispute_id}", response_model=DisputeOut)
def resolve_dispute(
    dispute_id: int,
    body: DisputeResolution,
    current: CurrentUser = Depends(require_user),
) -> DisputeOut:
    """Resolve a dispute, optionally unpublishing the report in the same call.

    ``unpublish`` works on ANY report, not just one the admin owns. The owner-scoped
    ``DELETE /v1/investigations/{slug}/share`` cannot help here by construction: the person harmed is
    not the owner, and waiting for the owner to act is not a takedown process. Revoking clears the
    token so ``/r/<token>`` 404s immediately, including for links already posted publicly.

    The investigation itself is NOT deleted. The customer keeps their own copy; what is withdrawn is
    the public claim, which is the thing that caused the harm.
    """
    from sqlalchemy import select as _select

    from app.storage.models import ReportDispute

    if not current.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admins only.")
    if body.status not in DISPUTE_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"status must be one of {', '.join(DISPUTE_STATUSES)}.",
        )
    with get_session() as session:
        row = session.get(ReportDispute, dispute_id)
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dispute not found.")
        row.status = body.status
        row.resolution_note = (body.note or "").strip() or None
        if body.status in ("upheld", "rejected"):
            row.resolved_at = datetime.now(timezone.utc)

        still_public = False
        inv = session.execute(
            _select(Investigation).where(Investigation.share_token == row.share_token)
        ).scalar_one_or_none()
        if inv is not None:
            if body.unpublish:
                inv.share_token = None
                inv.is_public = 0
                inv.published_at = None
                log.warning("report unpublished by admin after dispute %s (inv=%s)",
                            row.id, inv.slug)
            else:
                still_public = bool(inv.is_public)
        session.flush()
        return _dispute_out(row, still_public)
