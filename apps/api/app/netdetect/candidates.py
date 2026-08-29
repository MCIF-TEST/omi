"""Proposing sets of accounts worth testing.

Deliberately cheap and over-inclusive. This stage is tuned for RECALL, because the expensive stage
after it (``significance`` plus the shuffled null) is what removes false positives. A candidate
generator that tried to be precise would be making the significance decision with worse information
and no correction, which is how a hand-tuned threshold ends up being the real detector.

THE SHAPE OF THE SEARCH
-----------------------
1. Keep only RARE features. Common ones carry no information under the null anyway, so dropping
   them costs nothing and shrinks the graph enormously. This is what makes the whole thing tractable.
2. Build the account-account graph, weighting each shared rare feature by how surprising it is.
   Only pairs that share at least one rare feature get an edge, so the graph is sparse.
3. Community-detect on that graph.

Step 3 uses the Louvain implementation already in ``app/graph/algorithms``, which is wired for the
saved-graph surface. Reusing it means one community algorithm in the codebase rather than two that
can disagree about the same accounts.
"""

from __future__ import annotations

import math
from collections import defaultdict

from app.netdetect.significance import Corpus

#: A feature held by more accounts than this contributes no pair edges. Quadratic in the holder
#: count, so this is both the performance bound and a statement that a widely-shared feature is not
#: evidence about any particular pair.
MAX_HOLDERS_FOR_PAIRING = 40

#: Smallest reportable group. Two accounts sharing something is the pairwise question this design
#: exists to stop asking, and three is the smallest set for which "these are running together" is a
#: different claim from "these two coincided".
MIN_GROUP = 3

#: A community larger than this share of the corpus is the corpus, not a cohort. Learned elsewhere
#: in this codebase: a DBSCAN blob covering most of a batch is the batch.
MAX_GROUP_SHARE = 0.40


def pair_weights(corpus: Corpus) -> dict[tuple[str, str], float]:
    """Account-account weights over shared rare features.

    The weight is the summed log-rarity of what a pair shares, which is only a heuristic for
    proposing groups. It is NOT the score: the real statistic is computed set-wise later, under the
    degree-preserving null. Using this number as a verdict would reintroduce exactly the pairwise
    reasoning the redesign removed.
    """
    n = corpus.size
    if n < MIN_GROUP:
        return {}

    weights: dict[tuple[str, str], float] = defaultdict(float)
    # Sorted: the corpus now inserts features deterministically, and stating it here too means a
    # future change to that construction cannot silently reintroduce hash-order dependence in the
    # search. The pair weights feed Louvain, whose answer depends on the order edges arrive in.
    for f, holders in sorted(corpus.feature_accounts.items(), key=lambda kv: kv[0].token()):
        d = len(holders)
        if d < 2 or d > MAX_HOLDERS_FOR_PAIRING or not corpus.is_rare(f):
            continue
        # Rarity in log10 units. A feature two accounts out of 500 share is worth more than one
        # thirty of them share, and the log keeps a single very rare feature from dominating.
        w = math.log10(n / d)
        if w <= 0:
            continue
        ordered = sorted(holders)
        for i, a in enumerate(ordered):
            for b in ordered[i + 1:]:
                weights[(a, b)] += w
    return dict(weights)


def communities(corpus: Corpus) -> list[list[str]]:
    """Candidate groups, before any significance testing.

    Returns member-disjoint sets. Disjointness matters downstream: overlapping candidates would be
    tested repeatedly, inflating the search space the null has to correct for without adding any
    information.
    """
    weights = pair_weights(corpus)
    if not weights:
        return []

    from app.graph.algorithms import _louvain

    nodes = sorted({a for pair in weights for a in pair})
    # Sorted too. Louvain is seeded, but a seeded Louvain still depends on the order edges are
    # inserted into the graph, so an unsorted edge list makes the community structure a function of
    # dict iteration order rather than of the data.
    edges = sorted((a, b, w) for (a, b), w in weights.items())
    assignment = _louvain(nodes, edges)

    groups: dict[int, list[str]] = defaultdict(list)
    for node, comm in assignment.items():
        groups[comm].append(node)

    ceiling = max(MIN_GROUP, int(corpus.size * MAX_GROUP_SHARE))
    out: list[list[str]] = []
    for members in groups.values():
        if len(members) < MIN_GROUP:
            continue
        if len(members) > ceiling:
            # Too big to be a cohort. Rather than discarding it (a real operation can be large in a
            # small corpus), keep only its densest core: the members with the most internal weight.
            members = _densest_core(members, weights, ceiling)
            if len(members) < MIN_GROUP:
                continue
        out.append(sorted(members))
    return out


def _densest_core(members: list[str], weights: dict[tuple[str, str], float], keep: int) -> list[str]:
    """The ``keep`` members carrying the most internal weight.

    A blunt trim, and honest about being one: it is a way to salvage a candidate from an
    over-merged community, not a claim that the discarded members are innocent. The significance
    test still has to pass on whatever survives.
    """
    inside = set(members)
    strength: dict[str, float] = {m: 0.0 for m in members}
    for (a, b), w in weights.items():
        if a in inside and b in inside:
            strength[a] += w
            strength[b] += w
    return sorted(sorted(members, key=lambda m: strength[m], reverse=True)[:keep])
