"""Co-engagement / "fellow travelers" detector.

The novel one. Random YouTube users almost never co-appear on multiple
videos by chance — YouTube hosts billions of videos and a typical user
comments on maybe 5-50. But coordinated network accounts *do* co-appear,
because they're tasked with the same amplification campaigns. Two
sock-puppets that share three or more videos in their recent comment
histories are vanishingly unlikely to be independent.

We compute pairwise overlap of recent-engagement video sets across all
commenters in the current scan. Pairs above a strict shared-video count
form edges in a graph; connected components become coordination
clusters. Because the engagement edges persist in the DB, this signal
gets *stronger* across scans — when the same network shows up on a
different video tomorrow, we recognize them.

This detector is I/O-free: the caller pre-loads
``{external_id: set[video_id]}`` from the persistent ``CommenterEngagement``
table and passes it in.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from app.detection.coordination._types import (
    CoordinationCluster,
    CoordinationFinding,
    _UnionFind,
)


@dataclass
class EngagementEntry:
    external_id: str
    handle: str
    engaged_video_ids: set[str]


def detect_co_engagement(
    entries: list[EngagementEntry],
    *,
    min_shared_videos: int = 3,
    min_jaccard: float = 0.10,
    min_cluster_size: int = 2,
) -> CoordinationFinding:
    eligible = [e for e in entries if len(e.engaged_video_ids) >= 2]
    if len(eligible) < 2:
        return CoordinationFinding(
            method="co_engagement",
            overall_score=0.5,
            confidence=0.0,
            clusters=[],
            evidence=[
                "Not enough commenters with persisted engagement history to compare."
            ],
        )

    uf = _UnionFind(range(len(eligible)))
    flagged_pairs: list[tuple[int, int, int, float]] = []  # (i, j, |∩|, J)
    for i in range(len(eligible)):
        vi = eligible[i].engaged_video_ids
        for j in range(i + 1, len(eligible)):
            vj = eligible[j].engaged_video_ids
            inter = vi & vj
            if len(inter) < min_shared_videos:
                continue
            j_score = len(inter) / len(vi | vj)
            if j_score < min_jaccard:
                continue
            uf.union(i, j)
            flagged_pairs.append((i, j, len(inter), j_score))

    clusters: list[CoordinationCluster] = []
    for _, idxs in uf.components().items():
        if len(idxs) < min_cluster_size:
            continue
        members = [eligible[i].external_id for i in idxs]
        # Intra-cluster: largest shared video set across any pair.
        member_set = set(idxs)
        intra = [p for p in flagged_pairs if p[0] in member_set and p[1] in member_set]
        if not intra:
            continue
        max_shared = max(p[2] for p in intra)
        mean_jaccard = sum(p[3] for p in intra) / len(intra)
        score = min(
            1.0,
            0.65 + 0.20 * min(1.0, (len(idxs) - 2) / 3.0) + 0.15 * min(1.0, mean_jaccard / 0.3),
        )
        clusters.append(
            CoordinationCluster(
                method="co_engagement",
                members=sorted(members),
                score=score,
                evidence=[
                    f"{len(idxs)} accounts have appeared together on multiple other "
                    f"videos (max shared videos in a pair: {max_shared}, mean Jaccard "
                    f"overlap {mean_jaccard:.2f}) — patterns consistent with a "
                    f"coordinated amplification network."
                ],
                metadata={
                    "size": float(len(idxs)),
                    "max_shared_videos": float(max_shared),
                    "mean_jaccard": mean_jaccard,
                },
            )
        )

    flagged = {m for c in clusters for m in c.members}
    share = len(flagged) / len(eligible) if eligible else 0.0
    overall = 1.0 / (1.0 + math.exp(-(share - 0.10) * 12))
    confidence = min(1.0, len(eligible) / 15.0)
    evidence = (
        [
            f"Identified {len(clusters)} fellow-traveler network(s) covering "
            f"{len(flagged)} account(s)."
        ]
        if clusters
        else [
            "No fellow-traveler networks detected; commenters' recent video "
            "engagement histories don't overlap suspiciously."
        ]
    )

    return CoordinationFinding(
        method="co_engagement",
        overall_score=float(overall),
        confidence=confidence,
        clusters=clusters,
        evidence=evidence,
    )
