"""Temporal-semantic clique detection.

Bot bursts have a distinct signature: many accounts post nearly-identical
text within seconds of each other. That's the moment a Discord/Telegram
amplification room fires off a wave.

We model it as a graph: each comment is a node; an undirected edge connects
two comments if they're both semantically similar (cosine ≥ threshold) AND
were posted within a tight time window. Connected components that span
multiple authors are coordinated bursts.

Single accounts can fake "humanness" individually but cannot fake out
being a clique on this graph — it requires multiple cooperating accounts
producing similar content at coordinated times.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from app.detection.coordination._types import (
    CoordinationCluster,
    CoordinationFinding,
    _UnionFind,
)


@dataclass
class CommentEntry:
    """One top-level comment under the video."""

    comment_id: str
    author_external_id: str
    text: str
    created_at: datetime


def detect_temporal_semantic_cliques(
    comments: list[CommentEntry],
    *,
    similarity_threshold: float = 0.65,
    time_window_seconds: float = 120.0,
    min_cluster_authors: int = 3,
) -> CoordinationFinding:
    """Find dense same-content-same-time cliques across multiple authors."""
    if len(comments) < min_cluster_authors:
        return CoordinationFinding(
            method="temporal_semantic_clique",
            overall_score=0.5,
            confidence=0.0,
            clusters=[],
            evidence=[
                f"Need ≥ {min_cluster_authors} comments to detect coordination; "
                f"have {len(comments)}."
            ],
        )

    texts = [c.text or "" for c in comments]
    # TF-IDF over uni+bigrams; sublinear_tf so a single repeated word doesn't dominate.
    try:
        vectorizer = TfidfVectorizer(
            lowercase=True,
            ngram_range=(1, 2),
            min_df=1,
            max_df=1.0,
            max_features=4096,
            sublinear_tf=True,
        )
        matrix = vectorizer.fit_transform(texts)
    except ValueError:
        return CoordinationFinding(
            method="temporal_semantic_clique",
            overall_score=0.5,
            confidence=0.0,
            clusters=[],
            evidence=["Comment text was unusable for similarity analysis."],
        )

    vectors = matrix.toarray().astype(np.float32)
    sim = cosine_similarity(vectors)

    n = len(comments)
    uf = _UnionFind(range(n))
    edge_pairs: list[tuple[int, int, float]] = []
    for i in range(n):
        ti = comments[i].created_at.timestamp()
        for j in range(i + 1, n):
            tj = comments[j].created_at.timestamp()
            if abs(ti - tj) > time_window_seconds:
                continue
            s = float(sim[i, j])
            if s < similarity_threshold:
                continue
            uf.union(i, j)
            edge_pairs.append((i, j, s))

    clusters: list[CoordinationCluster] = []
    for _, member_idxs in uf.components().items():
        if len(member_idxs) < 2:
            continue
        authors = {comments[i].author_external_id for i in member_idxs}
        if len(authors) < min_cluster_authors:
            continue

        # Strength: combine number of authors with mean similarity inside the
        # cluster and tightness of the time window.
        member_set = set(member_idxs)
        cluster_edges = [(s, abs(comments[i].created_at.timestamp()
                                  - comments[j].created_at.timestamp()))
                         for (i, j, s) in edge_pairs
                         if i in member_set and j in member_set]
        if not cluster_edges:
            continue
        mean_sim = sum(s for s, _ in cluster_edges) / len(cluster_edges)
        mean_dt = sum(dt for _, dt in cluster_edges) / len(cluster_edges)

        size_factor = 1.0 / (1.0 + math.exp(-(len(authors) - min_cluster_authors)))
        sim_factor = max(0.0, (mean_sim - similarity_threshold) / (1.0 - similarity_threshold))
        time_factor = max(0.0, 1.0 - mean_dt / time_window_seconds)
        score = min(1.0, 0.4 + 0.3 * size_factor + 0.2 * sim_factor + 0.1 * time_factor)

        clusters.append(
            CoordinationCluster(
                method="temporal_semantic_clique",
                members=sorted(authors),
                score=score,
                evidence=[
                    f"{len(authors)} accounts posted semantically similar comments "
                    f"(mean cosine={mean_sim:.2f}) within an average of "
                    f"{mean_dt:.0f}s of each other — patterns consistent with a "
                    f"coordinated burst."
                ],
                metadata={
                    "n_authors": float(len(authors)),
                    "n_comments": float(len(member_idxs)),
                    "mean_similarity": mean_sim,
                    "mean_time_gap_seconds": mean_dt,
                },
            )
        )

    # Global score: share of distinct authors caught in any cluster.
    flagged_authors = {m for c in clusters for m in c.members}
    all_authors = {c.author_external_id for c in comments}
    if all_authors:
        share = len(flagged_authors) / len(all_authors)
    else:
        share = 0.0
    # Smooth + lift: 30% flagged share already signals a heavy operation.
    overall = 1.0 / (1.0 + math.exp(-(share - 0.15) * 8))

    confidence = min(1.0, len(comments) / 30.0)
    evidence: list[str] = []
    if clusters:
        evidence.append(
            f"Detected {len(clusters)} coordinated comment burst(s) involving "
            f"{len(flagged_authors)} distinct account(s) "
            f"({share:.0%} of commenters in this scan)."
        )
    else:
        evidence.append(
            "No coordinated comment bursts detected within the configured time/similarity windows."
        )

    return CoordinationFinding(
        method="temporal_semantic_clique",
        overall_score=float(overall),
        confidence=confidence,
        clusters=clusters,
        evidence=evidence,
    )
