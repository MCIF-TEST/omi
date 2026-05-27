"""Incremental online clustering for the narrative store.

For each new comment:

1. Embed it.
2. Find the nearest existing narrative centroid (cosine).
3. If similarity >= ``match_threshold``: assign, update centroid as a
   running average weighted by member count.
4. Else: spawn a new narrative.

The centroid update is a streaming mean:

    new_centroid = (old_centroid * n + new_vec) / (n + 1)

then renormalized so cosine = dot product stays valid.

This is O(N_narratives) per comment. Fine for the early-scale phase
where N is in the hundreds. Phase 9 swaps this for an ANN index
(hnswlib / pgvector) when N gets large.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass
class ClusterDecision:
    narrative_id: int | None    # None = spawn new
    similarity: float           # best cosine match
    new_centroid: list[float]   # post-update centroid (for store)


def _normalize(vec: list[float]) -> list[float]:
    n = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / n for v in vec]


def cosine(a: list[float], b: list[float]) -> float:
    if len(a) != len(b):
        return 0.0
    return sum(x * y for x, y in zip(a, b))


def update_centroid(old: list[float], member_count: int, new_vec: list[float]) -> list[float]:
    """Streaming-mean centroid update + renormalize."""
    if not old:
        return list(new_vec)
    if len(old) != len(new_vec):
        return list(new_vec)
    n = max(1, member_count)
    out = [(o * n + v) / (n + 1) for o, v in zip(old, new_vec)]
    return _normalize(out)


def best_match(
    new_vec: list[float],
    candidates: list[tuple[int, list[float], int]],
    match_threshold: float = 0.78,
) -> ClusterDecision:
    """Find the closest centroid; return assignment decision.

    ``candidates`` is a list of (narrative_id, centroid, member_count).
    """
    if not candidates:
        return ClusterDecision(narrative_id=None, similarity=0.0, new_centroid=_normalize(new_vec))

    best_id = -1
    best_sim = -2.0
    best_centroid: list[float] = []
    best_count = 0
    for nid, c, mc in candidates:
        s = cosine(new_vec, c)
        if s > best_sim:
            best_sim, best_id, best_centroid, best_count = s, nid, c, mc

    if best_sim >= match_threshold:
        updated = update_centroid(best_centroid, best_count, new_vec)
        return ClusterDecision(
            narrative_id=best_id,
            similarity=best_sim,
            new_centroid=updated,
        )
    return ClusterDecision(
        narrative_id=None,
        similarity=best_sim,
        new_centroid=_normalize(new_vec),
    )
