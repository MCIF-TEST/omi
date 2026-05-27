"""Graph service — high-level read API.

Wraps the store + algorithms layers behind a clean interface that the
HTTP routes call into. Adds account-display lookup (joining edges to
the Account table for handle / tier in the visualization).
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.graph.algorithms import (
    Subgraph, build_subgraph, detect_communities, edge_strength,
)
from app.graph.store import GraphStore
from app.storage.models import Account


@dataclass
class NodeAttr:
    external_id: str
    handle: str
    display_name: str | None
    tier: str | None
    last_score: float | None
    community_id: int


@dataclass
class GraphResponse:
    focal: str
    depth: int
    nodes: list[NodeAttr]
    edges: list[dict]
    community_count: int


class GraphService:
    def __init__(self, session: Session):
        self.session = session
        self.store = GraphStore(session)

    # ---- Subgraph around a focal account ------------------------------

    def account_subgraph(
        self, *, platform: str, external_id: str, depth: int = 2,
    ) -> GraphResponse:
        edges = self.store.all_edges(platform)
        if not edges:
            return GraphResponse(focal=external_id, depth=depth,
                                 nodes=[], edges=[], community_count=0)

        sg: Subgraph = build_subgraph(external_id, edges, depth=depth)
        if external_id not in sg.communities:
            sg.communities[external_id] = 0

        # Resolve display attributes for the involved accounts in one query
        node_ids = sg.nodes if sg.nodes else [external_id]
        rows = list(self.session.execute(
            select(Account).where(
                Account.platform == platform,
                Account.external_id.in_(node_ids),
            )
        ).scalars())
        by_id = {r.external_id: r for r in rows}
        nodes = [
            NodeAttr(
                external_id=nid,
                handle=(by_id[nid].handle if nid in by_id else nid),
                display_name=(by_id[nid].display_name if nid in by_id else None),
                tier=(by_id[nid].last_tier if nid in by_id else None),
                last_score=(by_id[nid].last_score if nid in by_id else None),
                community_id=sg.communities.get(nid, 0),
            )
            for nid in sg.nodes or [external_id]
        ]
        # Edges as plain dicts (UI consumes them directly)
        edge_dicts = [
            {"a": a, "b": b, "strength": s}
            for (a, b, s) in sg.edges
        ]
        return GraphResponse(
            focal=external_id,
            depth=depth,
            nodes=nodes,
            edges=edge_dicts,
            community_count=len(set(n.community_id for n in nodes)),
        )

    # ---- Whole-graph community detection ------------------------------

    def communities(
        self, *, platform: str, min_size: int = 3, limit: int = 20,
    ) -> list[dict]:
        edges = self.store.all_edges(platform)
        comms = detect_communities(edges, min_size=min_size)[:limit]
        if not comms:
            return []
        # Resolve handles for community samples
        all_ids = sorted({m for c in comms for m in c.members[:8]})
        rows = list(self.session.execute(
            select(Account).where(
                Account.platform == platform,
                Account.external_id.in_(all_ids),
            )
        ).scalars())
        by_id = {r.external_id: r for r in rows}
        out = []
        for c in comms:
            sample = c.members[:8]
            out.append({
                "id": c.id,
                "size": c.size,
                "avg_strength": c.avg_strength,
                "max_strength": c.max_strength,
                "methods_seen": c.methods_seen,
                "sample_accounts": [
                    {
                        "external_id": eid,
                        "handle": by_id[eid].handle if eid in by_id else eid,
                        "tier": by_id[eid].last_tier if eid in by_id else None,
                    }
                    for eid in sample
                ],
                "total_members": c.size,
            })
        return out

    # ---- Pairwise edge detail ----------------------------------------

    def edge_detail(self, *, platform: str, a: str, b: str) -> dict | None:
        edge = self.store.get_edge(platform, a, b)
        if edge is None:
            return None
        return {
            "platform": edge.platform,
            "account_a": edge.account_a,
            "account_b": edge.account_b,
            "observation_count": edge.observation_count,
            "methods": edge.methods,
            "mean_cluster_score": edge.mean_cluster_score,
            "strength": edge_strength(edge),
            "last_shared_parent": edge.last_shared_parent,
            "first_observed_at": edge.first_observed_at,
            "last_observed_at": edge.last_observed_at,
        }
