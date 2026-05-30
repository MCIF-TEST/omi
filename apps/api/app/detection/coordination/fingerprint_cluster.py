"""Fingerprint-based clustering of suspicious commenters.

Re-uses the 17-dim behavioral fingerprint that every scan already produces.
Within a single video, accounts that score *individually* unremarkable can
still betray themselves as a family if their fingerprints sit on top of
each other — same posting cadence, same writing rhythm, same profile
shape. That's the "we came from the same recipe" tell of bot farms.

Greedy single-linkage at euclidean distance ≤ 0.30. Clusters of ≥ 3
members whose mean individual probability is also elevated get flagged.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from app.detection.coordination._types import (
    CoordinationCluster,
    CoordinationFinding,
    _UnionFind,
)
from app.memory.fingerprint import euclidean


@dataclass
class FingerprintEntry:
    external_id: str
    handle: str
    fingerprint: list[float]
    individual_probability: float


_MAX_ENTRIES = 300  # O(n²) Euclidean loop — cap to stay bounded for huge scans


def detect_fingerprint_clusters(
    entries: list[FingerprintEntry],
    *,
    distance_threshold: float = 0.30,
    min_cluster_size: int = 3,
    min_mean_probability: float = 0.45,
) -> CoordinationFinding:
    # Subsample: sort by descending individual_probability so the highest-risk
    # accounts are always checked even when the total exceeds the cap.
    if len(entries) > _MAX_ENTRIES:
        entries = sorted(entries, key=lambda e: e.individual_probability, reverse=True)[:_MAX_ENTRIES]

    if len(entries) < min_cluster_size:
        return CoordinationFinding(
            method="fingerprint_cluster",
            overall_score=0.5,
            confidence=0.0,
            clusters=[],
            evidence=[
                f"Need ≥ {min_cluster_size} fingerprints to cluster; have {len(entries)}."
            ],
        )

    uf = _UnionFind(range(len(entries)))
    edge_count = 0
    for i in range(len(entries)):
        for j in range(i + 1, len(entries)):
            try:
                d = euclidean(entries[i].fingerprint, entries[j].fingerprint)
            except ValueError:
                continue
            if d <= distance_threshold:
                uf.union(i, j)
                edge_count += 1

    clusters: list[CoordinationCluster] = []
    for _, member_idxs in uf.components().items():
        if len(member_idxs) < min_cluster_size:
            continue
        mean_prob = sum(entries[i].individual_probability for i in member_idxs) / len(member_idxs)
        if mean_prob < min_mean_probability:
            continue
        members = [entries[i].external_id for i in member_idxs]
        # Intra-cluster mean distance — tightness diagnostic.
        dists = []
        for x in range(len(member_idxs)):
            for y in range(x + 1, len(member_idxs)):
                dists.append(euclidean(
                    entries[member_idxs[x]].fingerprint,
                    entries[member_idxs[y]].fingerprint,
                ))
        mean_dist = sum(dists) / len(dists) if dists else 0.0

        size_factor = 1.0 / (1.0 + math.exp(-(len(member_idxs) - min_cluster_size)))
        prob_factor = (mean_prob - min_mean_probability) / (1.0 - min_mean_probability)
        tight_factor = 1.0 - mean_dist / distance_threshold
        score = max(0.4, min(1.0, 0.5 + 0.25 * size_factor + 0.15 * prob_factor + 0.1 * tight_factor))

        clusters.append(
            CoordinationCluster(
                method="fingerprint_cluster",
                members=sorted(members),
                score=score,
                evidence=[
                    f"{len(member_idxs)} accounts share an unusually similar behavioral "
                    f"fingerprint (mean intra-cluster distance {mean_dist:.2f}) and "
                    f"individually scored a mean probability of {mean_prob:.2f} — "
                    f"patterns consistent with a bot family produced from the same template."
                ],
                metadata={
                    "size": float(len(member_idxs)),
                    "mean_individual_probability": mean_prob,
                    "mean_intra_distance": mean_dist,
                },
            )
        )

    flagged = {m for c in clusters for m in c.members}
    share = len(flagged) / len(entries) if entries else 0.0
    overall = 1.0 / (1.0 + math.exp(-(share - 0.10) * 10))

    confidence = min(1.0, len(entries) / 25.0)
    evidence: list[str] = []
    if clusters:
        evidence.append(
            f"Detected {len(clusters)} fingerprint cluster(s) covering "
            f"{len(flagged)} account(s)."
        )
    else:
        evidence.append("No suspicious fingerprint clusters found across this batch.")

    return CoordinationFinding(
        method="fingerprint_cluster",
        overall_score=float(overall),
        confidence=confidence,
        clusters=clusters,
        evidence=evidence,
    )
