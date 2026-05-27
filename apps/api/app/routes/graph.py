"""Graph + coordination intelligence endpoints — Phase 4."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.core.auth import CurrentUser, require_user
from app.graph.service import GraphService
from app.schemas import (
    AccountSubgraphResponse, CommunitiesResponse, CommunityOut,
    CommunitySampleAccount, EdgeDetailResponse, GraphEdge, GraphNode,
)
from app.storage.db import get_session


router = APIRouter(prefix="/v1/graph", tags=["graph"])


@router.get("/account/{platform}/{external_id}", response_model=AccountSubgraphResponse)
def account_subgraph(
    platform: str,
    external_id: str,
    depth: int = Query(2, ge=1, le=3),
    current: CurrentUser = Depends(require_user),
) -> AccountSubgraphResponse:
    """2-hop coordination subgraph around the focused account.

    Edges are the cumulative, cross-scan coordination edges. Nodes are
    colored by Louvain community id; the UI uses these for a coordination-
    cluster visualization.
    """
    with get_session() as session:
        svc = GraphService(session)
        out = svc.account_subgraph(platform=platform, external_id=external_id, depth=depth)

    return AccountSubgraphResponse(
        focal=out.focal,
        depth=out.depth,
        nodes=[GraphNode(**n.__dict__) for n in out.nodes],
        edges=[GraphEdge(**e) for e in out.edges],
        community_count=out.community_count,
    )


@router.get("/communities", response_model=CommunitiesResponse)
def communities(
    platform: str = "youtube",
    min_size: int = Query(3, ge=2, le=50),
    limit: int = Query(20, ge=1, le=100),
    current: CurrentUser = Depends(require_user),
) -> CommunitiesResponse:
    """Detected coordination communities across the persistent graph.

    Sorted by avg_strength × log(size) — biggest, most-coordinated first.

    Cached 5 min — Louvain is the most expensive read in the system.
    """
    from app.core.cache import get_cache
    cache = get_cache()
    cache_key = f"graph.communities.{platform}.ms{min_size}.l{limit}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    with get_session() as session:
        svc = GraphService(session)
        rows = svc.communities(platform=platform, min_size=min_size, limit=limit)

    result = CommunitiesResponse(
        platform=platform,  # type: ignore[arg-type]
        min_size=min_size,
        communities=[
            CommunityOut(
                id=r["id"], size=r["size"],
                avg_strength=r["avg_strength"], max_strength=r["max_strength"],
                methods_seen=r["methods_seen"],
                sample_accounts=[CommunitySampleAccount(**a) for a in r["sample_accounts"]],
                total_members=r["total_members"],
            )
            for r in rows
        ],
    )
    cache.set(cache_key, result, ttl_seconds=300)
    return result


@router.get("/edges/{platform}/{a}/{b}", response_model=EdgeDetailResponse)
def edge_detail(
    platform: str, a: str, b: str,
    current: CurrentUser = Depends(require_user),
) -> EdgeDetailResponse:
    """Edge detail for a specific coordination pair."""
    with get_session() as session:
        svc = GraphService(session)
        edge = svc.edge_detail(platform=platform, a=a, b=b)
    if edge is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No edge between those accounts.")
    return EdgeDetailResponse(**edge)
