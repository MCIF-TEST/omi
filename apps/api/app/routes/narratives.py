"""Narrative observatory endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.core.auth import CurrentUser, require_user
from app.narrative.embeddings import get_embedder
from app.narrative.service import NarrativeService
from app.schemas import (
    NarrativeActivityPoint,
    NarrativeBurst,
    NarrativeDetail,
    NarrativeGraph,
    NarrativeGraphEdge,
    NarrativeGraphNode,
    NarrativeOriginWindow,
    NarrativeOut,
    NarrativePropagationPoint,
    NarrativeSample,
    NarrativeSignalBreakdown,
    NarrativesResponse,
    NarrativeTopAccount,
)
from app.storage.db import get_session


router = APIRouter(prefix="/v1/narratives", tags=["narratives"])


@router.get("", response_model=NarrativesResponse)
def list_narratives(
    window_days: int = Query(7, ge=1, le=90),
    limit: int = Query(20, ge=1, le=100),
    min_risk_tier: str = Query(
        "low",
        pattern="^(low|moderate|high|extreme)$",
        description=(
            "Filter the list by minimum coordination risk band. "
            "Pass 'moderate' to hide organic clusters."
        ),
    ),
    current: CurrentUser = Depends(require_user),
) -> NarrativesResponse:
    """Trending narratives, ranked by coordination intelligence (not raw volume)."""
    embedder = get_embedder()
    embedder_name = type(embedder).__name__

    from app.core.cache import get_cache
    cache = get_cache()
    cache_key = f"narratives.trending.w{window_days}.l{limit}.r{min_risk_tier}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    with get_session() as session:
        service = NarrativeService(session, embedder=embedder)
        trending = service.list_trending(
            window_days=window_days,
            limit=limit,
            min_risk_tier=min_risk_tier,
        )

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
                risk_tier=t.risk_tier,
                coordination_score=t.coordination_score,
                manipulation_probability=t.manipulation_probability,
                synchronization_intensity=t.synchronization_intensity,
                semantic_cohesion=t.semantic_cohesion,
                cluster_confidence=t.cluster_confidence,
                coordination_label=t.coordination_label,
                qualifying_member_count=t.qualifying_member_count,
                qualifying_author_count=t.qualifying_author_count,
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
    """Full coordination drill-down for one narrative cluster.

    Returns the multi-signal panel, propagation timeline, identified
    bursts, origin lag, and a MODERATE-and-above subgraph.
    """
    try:
        with get_session() as session:
            service = NarrativeService(session)
            detail = service.get_detail(narrative_id)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to load narrative: {exc}",
        ) from exc

    if detail is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Narrative {narrative_id} not found.",
        )

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
                display_tier=a.display_tier,
                distinct_parents=a.distinct_parents,
                influence_score=a.influence_score,
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
        risk_tier=detail.risk_tier,
        coordination_score=detail.coordination_score,
        manipulation_probability=detail.manipulation_probability,
        synchronization_intensity=detail.synchronization_intensity,
        semantic_cohesion=detail.semantic_cohesion,
        cluster_confidence=detail.cluster_confidence,
        coordination_label=detail.coordination_label,
        qualifying_member_count=detail.qualifying_member_count,
        qualifying_author_count=detail.qualifying_author_count,
        signal_breakdown=[NarrativeSignalBreakdown(**s) for s in detail.signal_breakdown],
        propagation=[NarrativePropagationPoint(**p) for p in detail.propagation],
        bursts=[NarrativeBurst(**b) for b in detail.bursts],
        origin=NarrativeOriginWindow(**detail.origin) if detail.origin else None,
        graph=NarrativeGraph(
            nodes=[
                NarrativeGraphNode(
                    external_id=n.external_id,
                    handle=n.handle,
                    platform=n.platform,
                    tier=n.tier,
                    display_tier=n.display_tier,
                    comment_count=n.comment_count,
                    distinct_parents=n.distinct_parents,
                    influence_score=n.influence_score,
                )
                for n in detail.graph.nodes
            ],
            edges=[
                NarrativeGraphEdge(a=e.a, b=e.b, strength=e.strength, methods=e.methods)
                for e in detail.graph.edges
            ],
        ),
    )
