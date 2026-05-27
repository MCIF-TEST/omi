"""Narrative observatory endpoints — Phase 3."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.core.auth import CurrentUser, require_user
from app.narrative.embeddings import get_embedder
from app.narrative.service import NarrativeService
from app.schemas import NarrativeOut, NarrativesResponse
from app.storage.db import get_session


router = APIRouter(prefix="/v1/narratives", tags=["narratives"])


@router.get("", response_model=NarrativesResponse)
def list_narratives(
    window_days: int = Query(7, ge=1, le=90),
    limit: int = Query(20, ge=1, le=100),
    current: CurrentUser = Depends(require_user),
) -> NarrativesResponse:
    """Trending narratives across the corpus.

    A narrative is a cluster of semantically similar comments (across all
    accounts, all videos, all platforms). Trending = high membership in
    the trailing window, weighted by spread (distinct authors).
    """
    if window_days < 1:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="window_days must be >= 1")
    embedder = get_embedder()
    embedder_name = type(embedder).__name__

    from app.core.cache import get_cache
    cache = get_cache()
    cache_key = f"narratives.trending.w{window_days}.l{limit}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    with get_session() as session:
        service = NarrativeService(session, embedder=embedder)
        trending = service.list_trending(window_days=window_days, limit=limit)

    result = NarrativesResponse(
        window_days=window_days,
        embedder=embedder_name,
        narratives=[
            NarrativeOut(
                id=t.id,
                label=t.label,
                member_count=t.member_count,
                distinct_authors=t.distinct_authors,
                recent_members=t.recent_members,
                spread_ratio=t.spread_ratio,
                first_seen_at=t.first_seen_at,
                last_seen_at=t.last_seen_at,
                sample_text=t.sample_text,
            )
            for t in trending
        ],
    )
    cache.set(cache_key, result, ttl_seconds=60)
    return result
