"""Persistent investigation endpoints — Phase 5.

A user's scan history. Each investigation has a stable URL-safe slug,
the merged ComprehensiveScanResult payload, and metadata for the
dashboard.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from urllib.parse import parse_qs, urlparse

from fastapi import APIRouter, Depends, HTTPException, Query, status

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
    """Resolve platform from payload first, then input URL heuristics."""
    payload = inv.payload_json or {}
    raw = (payload.get("platform") or "").strip().lower()
    if raw in ("x", "twitter"):
        return "x"
    if raw == "youtube":
        return "youtube"
    url = (inv.input_url or "").lower()
    if "youtube.com" in url or "youtu.be" in url:
        return "youtube"
    if "twitter.com" in url or "x.com" in url or "t.co/" in url:
        return "x"
    # kind is rarely platform-specific; comprehensive scans on YT still carry
    # video_id in the payload.
    if payload.get("video_id") and not raw:
        return "youtube"
    return "unknown"


def _youtube_video_id(inv) -> str | None:
    payload = inv.payload_json or {}
    candidates: list[str] = []
    for key in ("video_id", "content_id", "target_id"):
        val = payload.get(key)
        if isinstance(val, str) and val:
            candidates.append(val)
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
    payload = inv.payload_json or {}
    for key in ("thumbnail_url", "thumb_url", "image_url"):
        val = payload.get(key)
        if isinstance(val, str) and val.startswith(("http://", "https://")):
            return val
    if platform == "youtube":
        vid = _youtube_video_id(inv)
        if vid:
            return f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg"
    return None
