"""Co-tag network detector — the first IO-native coordination signal.

Phase 2 showed the engine's aggregate score could not separate a state campaign
from unrelated professionals, and that the *missing capability* was a network
signal (``co_engagement`` has no analog outside YouTube). This is that signal,
ported to the disclosure data Omi owns.

A "tag" is a shared **target or topic** lifted from a tweet: a ``#hashtag`` or an
``@mention`` (which also captures ``RT @account`` amplification). Coordinated
operations push the same hashtags and amplify the same handles; unrelated
legitimate accounts do not. Measured on the real corpus, the fraction of account
pairs sharing tags (Jaccard ≥ 0.1) was **Iran 75% / Xinjiang 51% / GRU 21% vs
legitimate humans 0%** — the cleanest IO-vs-human separation of any signal.

Structurally identical to :mod:`co_engagement` (pairwise Jaccard over a per-account
set → Union-Find components), so it inherits that detector's calibration shape and
is a *discriminative* lens in :mod:`aggregate`. I/O-free: the caller supplies the
already-extracted tag set per account.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field

from app.detection.coordination._types import (
    CoordinationCluster,
    CoordinationFinding,
    _UnionFind,
)

# #hashtag or @mention (incl. the "@x" inside "RT @x:"). Case-folded by the caller.
_TAG_RE = re.compile(r"[#@]\w{2,}")


def extract_tags(texts: list[str]) -> set[str]:
    """Lift the hashtag/mention tag set from an account's posts (lower-cased)."""
    tags: set[str] = set()
    for t in texts:
        if t:
            tags.update(m.lower() for m in _TAG_RE.findall(t))
    return tags


@dataclass
class CoTagEntry:
    external_id: str
    handle: str
    tags: set[str] = field(default_factory=set)


def detect_co_tag(
    entries: list[CoTagEntry],
    *,
    min_shared_tags: int = 2,
    min_jaccard: float = 0.15,
    min_cluster_size: int = 2,
) -> CoordinationFinding:
    """Cluster accounts that push the same hashtags / amplify the same handles.

    Two accounts are linked when they share at least ``min_shared_tags`` tags
    *and* their tag-set Jaccard is ≥ ``min_jaccard`` (the absolute count stops a
    pair of prolific accounts from linking on one ubiquitous tag; the Jaccard
    stops large sets from over-linking). Connected components ≥
    ``min_cluster_size`` are coordination clusters.
    """
    eligible = [e for e in entries if len(e.tags) >= min_shared_tags]
    if len(eligible) < 2:
        return CoordinationFinding(
            method="co_tag", overall_score=0.5, confidence=0.0, clusters=[],
            evidence=["Not enough accounts with hashtag/mention tags to compare."],
        )

    uf = _UnionFind(range(len(eligible)))
    pairs: list[tuple[int, int, int, float]] = []  # (i, j, |∩|, J)
    for i in range(len(eligible)):
        ti = eligible[i].tags
        for j in range(i + 1, len(eligible)):
            tj = eligible[j].tags
            inter = ti & tj
            if len(inter) < min_shared_tags:
                continue
            jac = len(inter) / len(ti | tj)
            if jac < min_jaccard:
                continue
            uf.union(i, j)
            pairs.append((i, j, len(inter), jac))

    clusters: list[CoordinationCluster] = []
    for _, idxs in uf.components().items():
        if len(idxs) < min_cluster_size:
            continue
        member_set = set(idxs)
        intra = [p for p in pairs if p[0] in member_set and p[1] in member_set]
        if not intra:
            continue
        max_shared = max(p[2] for p in intra)
        mean_jac = sum(p[3] for p in intra) / len(intra)
        score = min(1.0, 0.65 + 0.20 * min(1.0, (len(idxs) - 2) / 3.0)
                    + 0.15 * min(1.0, mean_jac / 0.3))
        clusters.append(CoordinationCluster(
            method="co_tag",
            members=sorted(eligible[i].external_id for i in idxs),
            score=score,
            evidence=[
                f"{len(idxs)} accounts push the same hashtags / amplify the same "
                f"handles (max shared tags in a pair: {max_shared}, mean Jaccard "
                f"{mean_jac:.2f}) — shared-target coordination."
            ],
            metadata={"size": float(len(idxs)), "max_shared_tags": float(max_shared),
                      "mean_jaccard": mean_jac},
        ))

    flagged = {m for c in clusters for m in c.members}
    share = len(flagged) / len(eligible) if eligible else 0.0
    overall = 1.0 / (1.0 + math.exp(-(share - 0.10) * 12))
    confidence = min(1.0, len(eligible) / 15.0)
    evidence = (
        [f"Identified {len(clusters)} shared-target network(s) covering {len(flagged)} account(s)."]
        if clusters else
        ["No shared-target networks: accounts' hashtag/mention sets don't overlap suspiciously."]
    )
    return CoordinationFinding(
        method="co_tag", overall_score=float(overall),
        confidence=confidence, clusters=clusters, evidence=evidence,
    )
