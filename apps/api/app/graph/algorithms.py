"""Pure-function graph algorithms.

Wraps networkx with our domain-specific weighting + a stable strength
formula. All inputs are EdgeRecord lists from the GraphStore.

Edge strength is a bounded [0, 1] number combining:
  * observation_count        — how many independent clusters caught the pair
  * methods diversity        — how many distinct detector kinds (out of 5)
  * recency                  — how recently the pair was last seen together
  * mean_cluster_score       — average per-cluster suspicion

This is the central knob for the rest of the graph layer.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timezone

from app.graph.store import EdgeRecord

# All 5 cross-account detector method names. Diversity = |methods ∩ this set| / 5.
_KNOWN_METHODS = {
    "temporal_semantic_clique",
    "fingerprint_cluster",
    "age_cohort",
    "style_match",
    "co_engagement",
}


def edge_strength(edge: EdgeRecord, *, now: datetime | None = None) -> float:
    """Combined coordination strength in [0, 1]. See module docstring."""
    now = now or datetime.now(timezone.utc)
    obs_part = 0.35 * min(1.0, math.log(1 + edge.observation_count) / math.log(8))

    diversity = len(_KNOWN_METHODS.intersection(edge.methods)) / max(1, len(_KNOWN_METHODS))
    div_part = 0.30 * diversity

    last = edge.last_observed_at
    if last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)
    days_ago = (now - last).total_seconds() / 86400.0
    # 1.0 if seen in last 7 days; decays linearly to 0.1 over 90 days.
    if days_ago <= 7:
        recency = 1.0
    elif days_ago >= 90:
        recency = 0.1
    else:
        recency = 1.0 - 0.9 * ((days_ago - 7) / 83)
    rec_part = 0.20 * recency

    sev_part = 0.15 * max(0.0, min(1.0, edge.mean_cluster_score))

    return round(min(1.0, obs_part + div_part + rec_part + sev_part), 4)


@dataclass
class Subgraph:
    focal: str
    nodes: list[str]
    edges: list[tuple[str, str, float]]   # (a, b, strength)
    communities: dict[str, int]           # node -> community id


def build_subgraph(
    focal: str,
    edges: list[EdgeRecord],
    *,
    depth: int = 2,
    max_neighbors_per_hop: int = 50,
) -> Subgraph:
    """BFS the persisted graph from ``focal`` to depth ``depth``.

    Bounded by ``max_neighbors_per_hop`` to keep the response small on
    accounts with thousands of edges. Edges are kept only if both
    endpoints survive the BFS.
    """
    # adjacency
    adj: dict[str, list[tuple[str, EdgeRecord]]] = {}
    for e in edges:
        adj.setdefault(e.account_a, []).append((e.account_b, e))
        adj.setdefault(e.account_b, []).append((e.account_a, e))

    visited = {focal}
    frontier = [focal]
    for _ in range(depth):
        next_frontier: list[str] = []
        for node in frontier:
            neighbors = sorted(
                adj.get(node, []),
                key=lambda pair: -edge_strength(pair[1]),
            )[:max_neighbors_per_hop]
            for nb, _e in neighbors:
                if nb not in visited:
                    visited.add(nb)
                    next_frontier.append(nb)
        frontier = next_frontier

    kept_edges: list[tuple[str, str, float]] = []
    for e in edges:
        if e.account_a in visited and e.account_b in visited:
            kept_edges.append((e.account_a, e.account_b, edge_strength(e)))

    communities = _louvain(list(visited), kept_edges)
    return Subgraph(focal=focal, nodes=sorted(visited),
                    edges=kept_edges, communities=communities)


def _louvain(nodes: list[str], edges: list[tuple[str, str, float]]) -> dict[str, int]:
    """Run Louvain. Returns node → community id. Skips silently if networkx
    isn't installed (community ids all 0)."""
    try:
        import networkx as nx  # type: ignore
    except ImportError:
        return {n: 0 for n in nodes}

    g: nx.Graph = nx.Graph()
    for n in nodes:
        g.add_node(n)
    for a, b, w in edges:
        g.add_edge(a, b, weight=max(0.01, w))

    if g.number_of_edges() == 0:
        return {n: 0 for n in nodes}

    try:
        comms = nx.community.louvain_communities(g, weight="weight", seed=42)
    except Exception:
        return {n: 0 for n in nodes}
    mapping: dict[str, int] = {}
    for i, c in enumerate(comms):
        for node in c:
            mapping[node] = i
    for n in nodes:
        mapping.setdefault(n, 0)
    return mapping


@dataclass
class CommunitySummary:
    id: int
    size: int
    members: list[str]
    avg_strength: float
    max_strength: float
    methods_seen: list[str]


def detect_communities(
    edges: list[EdgeRecord],
    *,
    min_size: int = 3,
) -> list[CommunitySummary]:
    """Run Louvain on the whole edge set; return communities sized ≥ min_size."""
    if not edges:
        return []
    nodes = set()
    weighted: list[tuple[str, str, float]] = []
    for e in edges:
        nodes.add(e.account_a)
        nodes.add(e.account_b)
        weighted.append((e.account_a, e.account_b, edge_strength(e)))
    membership = _louvain(sorted(nodes), weighted)

    by_id: dict[int, list[str]] = {}
    for node, cid in membership.items():
        by_id.setdefault(cid, []).append(node)

    edge_lookup: dict[tuple[str, str], EdgeRecord] = {
        tuple(sorted([e.account_a, e.account_b])): e for e in edges  # type: ignore
    }

    out: list[CommunitySummary] = []
    for cid, members in by_id.items():
        if len(members) < min_size:
            continue
        member_set = set(members)
        strengths: list[float] = []
        methods: set[str] = set()
        for e in edges:
            if e.account_a in member_set and e.account_b in member_set:
                strengths.append(edge_strength(e))
                methods.update(e.methods)
        if not strengths:
            continue
        out.append(CommunitySummary(
            id=cid,
            size=len(members),
            members=sorted(members),
            avg_strength=round(sum(strengths) / len(strengths), 4),
            max_strength=round(max(strengths), 4),
            methods_seen=sorted(methods),
        ))
    # Most "coordinated" first: average strength × log(size)
    out.sort(key=lambda c: c.avg_strength * math.log(1 + c.size), reverse=True)
    return out
