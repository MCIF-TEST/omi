"""Content intelligence endpoints — Phase 10."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.content.service import ContentIntelligenceService
from app.core.auth import CurrentUser, require_user
from app.schemas import (
    CommentBatchOut,
    ContentCommentsResponse,
    ContentCommentOut,
    ContentEntityDetail,
    ContentEntityListResponse,
    ContentEntitySummary,
)
from app.storage.db import get_session

router = APIRouter(prefix="/v1/content", tags=["content"])


def _entity_to_summary(e) -> ContentEntitySummary:
    return ContentEntitySummary(
        id=e.id,
        platform=e.platform,
        content_id=e.content_id,
        kind=e.kind,
        title=e.title,
        author_external_id=e.author_external_id,
        author_handle=e.author_handle,
        canonical_url=e.canonical_url,
        thumbnail_url=e.thumbnail_url,
        total_batches=e.total_batches or 0,
        total_comments_collected=e.total_comments_collected or 0,
        total_distinct_authors=e.total_distinct_authors or 0,
        contributor_count=e.contributor_count or 0,
        latest_coordination_score=e.latest_coordination_score or 0.0,
        latest_risk_tier=e.latest_risk_tier or "low",
        latest_tier_distribution=e.latest_tier_distribution or {},
        first_scanned_at=e.first_scanned_at,
        last_scanned_at=e.last_scanned_at,
    )


def _batch_to_out(b) -> CommentBatchOut:
    return CommentBatchOut(
        id=b.id,
        fetched_at=b.fetched_at,
        comments_fetched=b.comments_fetched or 0,
        new_comments=b.new_comments or 0,
        duplicates=b.duplicates or 0,
        distinct_authors=b.distinct_authors or 0,
        new_authors=b.new_authors or 0,
        coordination_score=b.coordination_score or 0.0,
        risk_tier=b.risk_tier or "low",
        tier_distribution=b.tier_distribution or {},
        summary=b.summary,
    )


def _comment_to_out(c) -> ContentCommentOut:
    return ContentCommentOut(
        id=c.id,
        external_comment_id=c.external_comment_id,
        author_external_id=c.author_external_id,
        author_handle=c.author_handle,
        text=c.text,
        like_count=c.like_count,
        reply_count=c.reply_count,
        observed_at=c.observed_at,
        first_batch_id=c.first_batch_id,
    )


@router.get("", response_model=ContentEntityListResponse)
def list_content_entities(
    platform: str | None = Query(None),
    min_risk_tier: str = Query("low", pattern="^(low|moderate|high|extreme)$"),
    limit: int = Query(40, ge=1, le=100),
    offset: int = Query(0, ge=0),
    _: CurrentUser = Depends(require_user),
) -> ContentEntityListResponse:
    """List all tracked content entities, sorted by most recently scanned."""
    # Map public tier names to internal storage names
    internal_tier = {"low": "low", "moderate": "moderate", "high": "elevated", "extreme": "high"}.get(
        min_risk_tier, "low"
    )
    with get_session() as session:
        svc = ContentIntelligenceService(session)
        total, entities = svc.list_entities(
            platform=platform,
            min_risk_tier=internal_tier,
            limit=limit,
            offset=offset,
        )
    return ContentEntityListResponse(
        total=total,
        platform=platform,
        entities=[_entity_to_summary(e) for e in entities],
    )


@router.get("/{platform}/{content_id}", response_model=ContentEntityDetail)
def get_content_entity(
    platform: str,
    content_id: str,
    _: CurrentUser = Depends(require_user),
) -> ContentEntityDetail:
    """Full intelligence detail for one piece of content."""
    with get_session() as session:
        svc = ContentIntelligenceService(session)
        entity = svc.get_entity_by_platform_id(platform, content_id)
        if entity is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No content entity found for {platform}/{content_id}.",
            )
        batches = svc.get_batches(entity.id, limit=50)
        total_comments, recent = svc.get_comments(entity.id, limit=20)
        summary = _entity_to_summary(entity)

    return ContentEntityDetail(
        entity=summary,
        batches=[_batch_to_out(b) for b in batches],
        recent_comments=[_comment_to_out(c) for c in recent],
        total_comments=total_comments,
    )


@router.get("/{platform}/{content_id}/batches", response_model=list[CommentBatchOut])
def get_content_batches(
    platform: str,
    content_id: str,
    limit: int = Query(50, ge=1, le=200),
    _: CurrentUser = Depends(require_user),
) -> list[CommentBatchOut]:
    """Batch history for one piece of content."""
    with get_session() as session:
        svc = ContentIntelligenceService(session)
        entity = svc.get_entity_by_platform_id(platform, content_id)
        if entity is None:
            raise HTTPException(status_code=404, detail="Content entity not found.")
        batches = svc.get_batches(entity.id, limit=limit)
    return [_batch_to_out(b) for b in batches]


@router.get("/{platform}/{content_id}/comments", response_model=ContentCommentsResponse)
def get_content_comments(
    platform: str,
    content_id: str,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    batch_id: int | None = Query(None),
    _: CurrentUser = Depends(require_user),
) -> ContentCommentsResponse:
    """Paginated comment feed for one piece of content, optionally filtered to one batch."""
    with get_session() as session:
        svc = ContentIntelligenceService(session)
        entity = svc.get_entity_by_platform_id(platform, content_id)
        if entity is None:
            raise HTTPException(status_code=404, detail="Content entity not found.")
        total, comments = svc.get_comments(
            entity.id, limit=limit, offset=offset, batch_id=batch_id
        )
    return ContentCommentsResponse(
        total=total,
        comments=[_comment_to_out(c) for c in comments],
    )
