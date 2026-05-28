"""Persistent investigation endpoints — Phase 5.

A user's scan history. Each investigation has a stable URL-safe slug,
the merged ComprehensiveScanResult payload, and metadata for the
dashboard.
"""

from __future__ import annotations

from datetime import datetime, timezone

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


@router.get("", response_model=InvestigationsListResponse)
def list_investigations(
    limit: int = Query(50, ge=1, le=200),
    current: CurrentUser = Depends(require_user),
) -> InvestigationsListResponse:
    """Recent investigations for the logged-in user, newest first."""
    if current.id == 0:
        return InvestigationsListResponse(investigations=[])

    with get_session() as session:
        repo = AccountRepository(session)
        rows = repo.list_user_investigations(current.id, limit=limit)
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
        inv = repo.get_investigation(
            slug=slug, user_id=current.id if current.id != 0 else None
        )
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
        inv = repo.get_investigation(
            slug=slug, user_id=current.id if current.id != 0 else None
        )
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
    return InvestigationSummary(
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
        target_id=inv.target_id,
        verdict=inv.verdict,
    )
