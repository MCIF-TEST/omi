"""Persistent investigation endpoints — Phase 5.

A user's scan history. Each investigation has a stable URL-safe slug,
the merged ComprehensiveScanResult payload, and metadata for the
dashboard.
"""

from __future__ import annotations

import re
import secrets
from datetime import datetime, timezone
from urllib.parse import parse_qs, urlparse

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from app.core.auth import CurrentUser, require_user
from app.schemas import (
    INVESTIGATION_VERDICTS,
    InvestigationDetailResponse,
    InvestigationsListResponse,
    InvestigationSummary,
    Tier,
    VerdictUpdate,
)
from app.storage.db import get_session
from app.storage.models import Investigation
from app.storage.repository import AccountRepository


router = APIRouter(prefix="/v1/investigations", tags=["investigations"])

# YouTube video IDs are 11 chars; also accept from youtu.be / shorts / live.
_YT_ID_RE = re.compile(
    r"(?:youtube\.com/(?:watch\?v=|embed/|shorts/|live/|v/)|youtu\.be/)"
    r"([A-Za-z0-9_-]{11})",
    re.IGNORECASE,
)
_YT_ID_BARE = re.compile(r"^[A-Za-z0-9_-]{11}$")


@router.get("", response_model=InvestigationsListResponse)
def list_investigations(
    limit: int = Query(50, ge=1, le=200),
    current: CurrentUser = Depends(require_user),
) -> InvestigationsListResponse:
    """Recent investigations for the logged-in user, newest first.

    In local mode (``OMI_REQUIRE_AUTH=false``, ``current.id == 0``) this lists
    the local-install user's history instead of returning nothing — a solo
    install keeps a real investigation history just like an authenticated one.
    """
    with get_session() as session:
        repo = AccountRepository(session)
        user_id = repo.local_user_id() if current.id == 0 else current.id
        if user_id is None:
            # Local mode but no scans saved yet.
            return InvestigationsListResponse(investigations=[])
        rows = repo.list_user_investigations(user_id, limit=limit)
        return InvestigationsListResponse(
            investigations=[_to_summary(r) for r in rows]
        )


@router.get("/{slug}", response_model=InvestigationDetailResponse)
def get_investigation(
    slug: str,
    current: CurrentUser = Depends(require_user),
) -> InvestigationDetailResponse:
    with get_session() as session:
        repo = AccountRepository(session)
        # Local mode: scope to the local user so a saved local investigation is
        # retrievable. Authenticated: scope to the owner.
        user_id = repo.local_user_id() if current.id == 0 else current.id
        inv = repo.get_investigation(slug=slug, user_id=user_id)
        if inv is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No investigation '{slug}'.",
            )
        return _to_detail(inv)


@router.patch("/{slug}", response_model=InvestigationDetailResponse)
def update_investigation(
    slug: str,
    body: VerdictUpdate,
    current: CurrentUser = Depends(require_user),
) -> InvestigationDetailResponse:
    """Set or clear the analyst verdict and/or personal notes on an investigation.

    Send ``{"verdict": null}`` to clear a verdict. ``notes`` is a free-text
    field visible only to the owner — never included in public shares.
    """
    if body.verdict is not None and body.verdict not in INVESTIGATION_VERDICTS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid verdict '{body.verdict}'. Must be one of: {', '.join(INVESTIGATION_VERDICTS)}",
        )

    with get_session() as session:
        repo = AccountRepository(session)
        user_id = repo.local_user_id() if current.id == 0 else current.id
        inv = repo.get_investigation(slug=slug, user_id=user_id)
        if inv is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No investigation '{slug}'.",
            )

        now = datetime.now(timezone.utc)
        if body.verdict is not None:
            inv.verdict = body.verdict if body.verdict != "pending" else None
            inv.concluded_at = now if body.verdict not in ("pending", None) else None
        if body.notes is not None:
            inv.notes = body.notes or None
        inv.updated_at = now
        session.flush()
        return _to_detail(inv)


def _to_detail(inv) -> InvestigationDetailResponse:
    return InvestigationDetailResponse(
        slug=inv.slug,
        label=inv.label,
        input_url=inv.input_url,
        kind=inv.kind,
        overall_probability=inv.overall_probability,
        overall_tier=Tier(inv.overall_tier),
        summary=inv.summary,
        quota_used=inv.quota_used,
        batch_count=inv.batch_count,
        created_at=inv.created_at,
        updated_at=inv.updated_at,
        payload=inv.payload_json or {},
        share_token=inv.share_token,
        is_public=bool(inv.is_public),
        published_at=inv.published_at,
        commentary_text=inv.commentary_text,
        commentary_provider=inv.commentary_provider,
        commentary_generated_at=inv.commentary_generated_at,
        verdict=inv.verdict,
        concluded_at=inv.concluded_at,
        notes=inv.notes,
    )


def _to_summary(inv) -> InvestigationSummary:
    platform = _platform_of(inv)
    return InvestigationSummary(
        slug=inv.slug,
        label=inv.label,
        input_url=inv.input_url,
        kind=inv.kind,
        overall_probability=inv.overall_probability,
        overall_tier=Tier(inv.overall_tier),
        confidence=inv.confidence,
        summary=inv.summary,
        quota_used=inv.quota_used,
        batch_count=inv.batch_count,
        created_at=inv.created_at,
        updated_at=inv.updated_at,
        target_id=inv.target_id,
        verdict=inv.verdict,
        platform=platform,
        thumbnail_url=_thumbnail_of(inv, platform),
    )


def _platform_of(inv) -> str:
    """Resolve platform WITHOUT touching payload_json.

    Reads the denormalised ``platform`` column, falling back to URL / target_id heuristics for rows
    written before that column existed. The payload is deliberately not consulted: this runs once per
    row in the archive list, and with ``load_only()`` on that query, reading ``inv.payload_json`` here
    would lazy-load a multi-megabyte blob per row — turning one query into an N+1 and undoing exactly
    the problem the column was added to solve. New rows get an accurate value at write time
    (``derive_list_fields``), where the payload is already in memory and costs nothing extra.
    """
    stored = (getattr(inv, "platform", None) or "").strip().lower()
    if stored in ("x", "twitter"):
        return "x"
    if stored == "youtube":
        return "youtube"
    url = (inv.input_url or "").lower()
    if "youtube.com" in url or "youtu.be" in url:
        return "youtube"
    if "twitter.com" in url or "x.com" in url or "t.co/" in url:
        return "x"
    # A bare 11-char target_id is a YouTube video id; X ids are numeric.
    if inv.target_id and _YT_ID_BARE.match(inv.target_id):
        return "youtube"
    return "unknown"


def _youtube_video_id(inv) -> str | None:
    """Video id from target_id / input_url only — never the payload (see _platform_of)."""
    candidates: list[str] = []
    if inv.target_id:
        candidates.append(inv.target_id)
    for c in candidates:
        if _YT_ID_BARE.match(c):
            return c
    url = inv.input_url or ""
    m = _YT_ID_RE.search(url)
    if m:
        return m.group(1)
    # watch?v= with extra params
    try:
        parsed = urlparse(url)
        if "youtube.com" in (parsed.netloc or "").lower():
            qs = parse_qs(parsed.query or "")
            v = (qs.get("v") or [None])[0]
            if v and _YT_ID_BARE.match(v):
                return v
    except Exception:
        pass
    return None


def _thumbnail_of(inv, platform: str) -> str | None:
    """Public thumbnail URL when we can derive one without paid APIs.

    YouTube: hqdefault on i.ytimg.com (no API key).
    X: no reliable public post thumb without auth — return None so the UI
    can show a branded X placeholder.
    """
    stored = getattr(inv, "thumbnail_url", None)
    if isinstance(stored, str) and stored.startswith(("http://", "https://")):
        return stored
    if platform == "youtube":
        vid = _youtube_video_id(inv)
        if vid:
            return f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg"
    return None


# ---------------------------------------------------------------------------
# Funnel: claim a shared report into your own archive
# ---------------------------------------------------------------------------
class ClaimRequest(BaseModel):
    share_token: str = Field(min_length=8, max_length=48)


class ClaimResponse(BaseModel):
    slug: str                 # the CALLER'S copy, not the original
    label: str
    input_url: str            # the post to scan more of, for /investigate?url=
    platform: str | None
    already_claimed: bool     # True when this token was claimed by this user before


@router.post("/claim", response_model=ClaimResponse)
def claim_shared_investigation(
    body: ClaimRequest,
    current: CurrentUser = Depends(require_user),
) -> ClaimResponse:
    """Copy a publicly shared investigation into the caller's own archive.

    This is the top of the funnel. A visitor lands on someone else's ``/r/<token>`` report, signs up
    from it, and the report they were reading becomes the first thing in THEIR archive, with the
    source URL ready to scan more of. Without this the signup is a dead end: they arrive at an empty
    dashboard and have to find the post again themselves.

    What a claim does NOT do:

    * It does not move or change the original. The owner keeps their investigation, their share token,
      and their history untouched. This is a copy.
    * **It does not copy ``share_token``.** That column is unique and drives the ``/r/<token>`` lookup,
      so two rows carrying one token would either fail the insert or make the public report ambiguous.
      The copy is private until its new owner shares it themselves.
    * It grants no credits and spends none. Reading someone's report is free; scanning is what costs.

    Idempotent per (user, token) via ``claimed_from_token``: claiming twice returns the existing copy
    rather than duplicating a ``payload_json`` that is routinely megabytes. That matters because the
    web app fires this on a page load it cannot guarantee happens only once (a refresh, a double
    mount in development, a retried request).
    """
    from sqlalchemy import select

    token = body.share_token.strip()
    with get_session() as session:
        repo = AccountRepository(session)
        owner_id = repo.local_user_id() if current.id == 0 else current.id
        if owner_id is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                                detail="Sign in to save this report.")

        # Already claimed by this user? Hand back the copy they already have.
        existing = session.execute(
            select(Investigation).where(
                Investigation.user_id == owner_id,
                Investigation.claimed_from_token == token,
            ).order_by(Investigation.id.asc())
        ).scalars().first()
        if existing is not None:
            return ClaimResponse(
                slug=existing.slug, label=existing.label, input_url=existing.input_url,
                platform=_platform_of(existing), already_claimed=True,
            )

        source = session.execute(
            select(Investigation).where(
                Investigation.share_token == token,
                Investigation.is_public == 1,
            )
        ).scalar_one_or_none()
        if source is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="That report is no longer shared, so it cannot be saved.",
            )
        # Claiming your own report would put a duplicate in your archive for no reason.
        if source.user_id == owner_id:
            return ClaimResponse(
                slug=source.slug, label=source.label, input_url=source.input_url,
                platform=_platform_of(source), already_claimed=True,
            )

        payload = source.payload_json or {}
        copy = repo.create_investigation(
            user_id=owner_id,
            slug="inv_" + secrets.token_hex(4),
            label=source.label,
            input_url=source.input_url,
            target_id=source.target_id,
            kind=source.kind,
            overall_probability=source.overall_probability or 0.0,
            overall_tier=source.overall_tier or "low",
            summary=source.summary or "",
            quota_used=0,                       # the caller paid no quota for this
            payload_json=payload,
        )
        copy.confidence = source.confidence
        # The copy is the same investigation of the same post, so it knows the same thing about how
        # much of that post was left unchecked. Without this the claimer's own report forgets the gap,
        # and so does any link they later share themselves.
        copy.commenters_available = source.commenters_available
        copy.claimed_from_token = token
        session.flush()
        return ClaimResponse(
            slug=copy.slug, label=copy.label, input_url=copy.input_url,
            platform=_platform_of(copy), already_claimed=False,
        )
