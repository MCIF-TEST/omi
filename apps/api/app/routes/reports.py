"""Report + sharing endpoints — Phase 6.

Two router groups in one file:

* Authenticated: mint/revoke a share token on an investigation.
* Public: render the report by token. No auth, no credits, no rate
  limiting for now — adding that is Phase 9 work.

Public routes live under ``/r/...`` (short URLs); the Next.js public
page mirrors that at ``/r/{token}``.
"""

from __future__ import annotations

import secrets
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, Response, status
from pydantic import BaseModel

from app.core.auth import CurrentUser, require_user
from app.reports.templates import build_report_view, render_markdown
from app.storage.db import get_session
from app.storage.repository import AccountRepository
from app.storage.models import Investigation


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
            "payload": inv.payload_json or {},
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
