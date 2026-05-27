"""Persistent investigation endpoints — Phase 5.

A user's scan history. Each investigation has a stable URL-safe slug,
the merged ComprehensiveScanResult payload, and metadata for the
dashboard.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.core.auth import CurrentUser, require_user
from app.schemas import (
    InvestigationDetailResponse,
    InvestigationsListResponse,
    InvestigationSummary,
    Tier,
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
        # Local mode (require_auth=false) — return empty list; investigations
        # are a multi-tenant concept.
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
    )
