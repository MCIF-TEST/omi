"""Narrative observatory endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.core.auth import CurrentUser, require_user
from app.narrative.embeddings import get_embedder
from app.narrative.service import NarrativeService
from app.schemas import (
    NarrativeActivityPoint,
    NarrativeDetail,
    NarrativeOut,
    NarrativeSample,
    NarrativesResponse,
    NarrativeTopAccount,
)
from app.storage.db import get_session


router = APIRouter(prefix="/v1/narratives", tags=["narratives"])


@router.get("", response_model=NarrativesResponse)
def list_narratives(
    window_days: int = Query(7, ge=1, le=90),
    limit: int = Query(20, ge=1, le=100),
    current: CurrentUser = Depends(require_user),
) -> NarrativesResponse:
    """Trending narratives across the corpus, enriched with risk scores."""
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
                inauthenticity_score=t.inauthenticity_score,
                risk_label=t.risk_label,
                platforms=t.platforms,
            )
            for t in trending
        ],
    )
    cache.set(cache_key, result, ttl_seconds=60)
    return result


@router.get("/{narrative_id}", response_model=NarrativeDetail)
def get_narrative(
    narrative_id: int,
    current: CurrentUser = Depends(require_user),
) -> NarrativeDetail:
    """Full detail for one narrative cluster — accounts, samples, activity, AI analysis."""
    with get_session() as session:
        service = NarrativeService(session)
        detail = service.get_detail(narrative_id)

    if detail is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Narrative {narrative_id} not found.",
        )

    # Generate LLM analysis
    from app.reasoning.commentary import synthesize_narrative_analysis
    sample_texts = [s.text for s in detail.samples[:6]]
    analysis_result = synthesize_narrative_analysis(
        label=detail.label,
        member_count=detail.member_count,
        distinct_authors=detail.distinct_authors,
        spread_ratio=detail.spread_ratio,
        inauthenticity_score=detail.inauthenticity_score,
        risk_label=detail.risk_label,
        platforms=detail.platforms,
        sample_texts=sample_texts,
    )

    return NarrativeDetail(
        id=detail.id,
        label=detail.label,
        member_count=detail.member_count,
        distinct_authors=detail.distinct_authors,
        spread_ratio=detail.spread_ratio,
        first_seen_at=detail.first_seen_at,
        last_seen_at=detail.last_seen_at,
        inauthenticity_score=detail.inauthenticity_score,
        risk_label=detail.risk_label,
        platforms=detail.platforms,
        platform_breakdown=detail.platform_breakdown,
        activity=[NarrativeActivityPoint(**a) for a in detail.activity],
        top_accounts=[
            NarrativeTopAccount(
                external_id=a.external_id,
                handle=a.handle,
                display_name=a.display_name,
                platform=a.platform,
                comment_count=a.comment_count,
                tier=a.tier,
            )
            for a in detail.top_accounts
        ],
        samples=[
            NarrativeSample(
                text=s.text,
                account_external_id=s.account_external_id,
                handle=s.handle,
                platform=s.platform,
                parent_id=s.parent_id,
                observed_at=s.observed_at,
            )
            for s in detail.samples
        ],
        ai_analysis=analysis_result.text,
        ai_provider=analysis_result.provider,
    )
