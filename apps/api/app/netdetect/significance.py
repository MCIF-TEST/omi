"""How improbable is it that THESE accounts share THIS much?

The whole design turns on answering that honestly, so this module is written to be argued with.

THE NULL IS DEGREE-PRESERVING, AND THAT IS THE POINT
----------------------------------------------------
The naive null treats every account as equally likely to hold every feature. It is wrong in two
directions at once and both produce false positives:

* a **prolific** account holds many features, so it collides with everyone by chance;
* a **popular** feature is held by many accounts, so sharing it is not a coincidence.

The configuration null fixes both by holding the two degree sequences fixed: each account keeps its
number of features and each feature keeps its number of accounts, and only the wiring is randomised.
Under that null the probability that account *a* holds feature *f* is approximately

    p(a, f) = min(1, d(a) * d(f) / M)                       [Chung-Lu]

with ``d(a)`` the account's feature count, ``d(f)`` the feature's account count, and ``M`` the total
number of edges. A prolific account is expected to collide; a popular feature is expected to be
shared. Only what exceeds that expectation counts.

This is the principled, general form of the score-band-conditional background subtraction that
``campaigns/verdict_coordination.py`` performs by hand for one specific case.

WITHIN A FAMILY, EVIDENCE IS DISCOUNTED
---------------------------------------
Two 5-gram shingles from the same copy-pasted post co-occur perfectly. Summing their surprises
turns one observation into several and is how a detector talks itself into certainty. Contributions
inside a family are therefore sorted and summed with harmonic weights (1, 1/2, 1/3, ...): more
evidence never hurts, but the tenth shingle is worth a tenth of the first. Families are summed
plainly, because the family map IS the claim that they are independent.

NOTHING HERE IS A PROBABILITY OF COORDINATION
---------------------------------------------
The output is a surprise in log10 units: "this would happen about once in 10^s draws from a corpus
shaped like ours." Turning that into P(coordinated) needs a prior and, far more importantly, a
correction for how many candidate sets were searched. That correction lives in ``shuffle.py`` and it
is the reason a number from this module must never be reported on its own.
"""

from __future__ import annotations

import math
from collections import defaultdict

from app.netdetect.types import (
    ALL_FAMILIES,
    AccountProfile,
    Candidate,
    Feature,
    FeatureEvidence,
    weighted,
)

#: Surprise contributed by one feature is capped. A single feature that looks impossible (a rarity
#: estimate from too little data, a provider artifact, an id that leaked into the text) must not be
#: able to carry a finding on its own. This is the same reasoning as the older detector's per-method
#: LR caps: it is where an unmodelled confound is priced in.
MAX_FEATURE_SURPRISE = 6.0

#: Features held by more than this share of the corpus carry no information and are skipped before
#: any arithmetic. Both a statistical statement and the performance strategy: rare features are few
#: and their co-occurrence lists are short.
RARITY_CEILING = 0.25

#: A feature must be shared by at least this many of the group. Two accounts sharing something is
#: the pairwise question this design exists to stop asking.
MIN_SHARED_BY = 2

#: A family contributing less than this is noise, not a second kind of evidence. Used by the caller
#: to decide whether a candidate really rests on two independent things or on one thing plus a
#: rounding error.
MIN_FAMILY_CONTRIBUTION = 2.0

#: No single family may carry more than this share of a finding. One family is ONE KIND OF EVIDENCE,
#: however many times it fires: fifty shared shingles from one copy-pasted post is one observation
#: seen fifty times. A finding dominated by a single family is exactly the shape of a community that
#: shares a vocabulary, or a profession that shares a tool.
MAX_SINGLE_FAMILY_SHARE = 0.70


def internal_reply_ratio(corpus: "Corpus", members: list[str]) -> float:
    """How much of the group's replying is to ITSELF.

    THE STRONGEST EXCULPATORY SIGNAL AVAILABLE, and the one every presence-based detector misses.

    Real communities talk TO each other. A fandom, a professional beat, a diaspora group and a
    friend circle all reply among themselves constantly, and that mutual conversation is the thing
    that makes them a community rather than a formation.

    An operation is a BROADCAST ARRAY. Its accounts point outward at targets; they have little
    reason to talk to each other in public, and doing so would link them. So a high internal reply
    ratio argues *against* coordination, and counting those replies as evidence FOR it (which a
    naive network family does) inverts the signal on precisely the populations most at risk of being
    wrongly accused.
    """
    inside = set(members)
    internal = external = 0
    for m in members:
        for f in corpus.by_id[m].features:
            if f.kind != "reply_to":
                continue
            if f.value in inside:
                internal += 1
            else:
                external += 1
    total = internal + external
    return (internal / total) if total else 0.0


class Corpus:
    """The bipartite graph, plus the degree bookkeeping the null needs.

    Built once per detection run and read many times. ``feature_accounts`` is the inverted index
    that makes candidate generation cheap.
    """

    __slots__ = ("accounts", "by_id", "feature_accounts", "account_degree", "total_edges")

    def __init__(self, accounts: list[AccountProfile]) -> None:
        # Deduplicate by id: the same account appearing twice in a payload would otherwise be its
        # own perfect coincidence.
        seen: dict[str, AccountProfile] = {}
        for a in accounts:
            if a.external_id and a.external_id not in seen:
                seen[a.external_id] = a
        self.accounts: list[AccountProfile] = list(seen.values())
        self.by_id: dict[str, AccountProfile] = seen

        self.feature_accounts: dict[Feature, set[str]] = defaultdict(set)
        self.account_degree: dict[str, int] = {}
        for a in self.accounts:
            self.account_degree[a.external_id] = len(a.features)
            # SORTED, and this is not cosmetic. `features` is a set of dataclasses whose fields are
            # strings, so its iteration order depends on `hash(str)`, which Python randomises per
            # process. That order set the insertion order of `feature_accounts`, which set the order
            # of the candidate search, which changed which communities Louvain found, which changed
            # the null threshold. Measured: the same corpus with the same seeds produced thresholds
            # of 8.505, 8.02 and 0.0 under three hash seeds, and a threshold of 0 removes the
            # search correction entirely. That is why the falsification test failed about one run
            # in five and looked like flakiness.
            for f in sorted(a.features, key=lambda f: f.token()):
                self.feature_accounts[f].add(a.external_id)
        self.total_edges = sum(self.account_degree.values())

    @property
    def size(self) -> int:
        return len(self.accounts)

    def feature_degree(self, f: Feature) -> int:
        return len(self.feature_accounts.get(f, ()))

    def is_rare(self, f: Feature) -> bool:
        n = self.size
        return n > 0 and (self.feature_degree(f) / n) <= RARITY_CEILING

    def rare_features(self) -> list[Feature]:
        return [f for f in self.feature_accounts if self.is_rare(f)]


def _p_edge(corpus: Corpus, account_id: str, f: Feature) -> float:
    """Chung-Lu probability that this account holds this feature under the configuration null."""
    if corpus.total_edges <= 0:
        return 0.0
    da = corpus.account_degree.get(account_id, 0)
    df = corpus.feature_degree(f)
    return min(1.0, (da * df) / corpus.total_edges)


def _poisson_binomial_tail(probs: list[float], k: int) -> float:
    """P(X >= k) where X is the number of successes among independent Bernoulli(``probs``).

    Exact by dynamic programming. The group sizes here are small (tens), so the O(n^2) cost is
    nothing, and an exact tail avoids the usual trap of a normal approximation being wildly wrong in
    precisely the far tail this whole system reads.
    """
    if k <= 0:
        return 1.0
    n = len(probs)
    if k > n:
        return 0.0

    # dist[j] = P(exactly j successes so far)
    dist = [1.0] + [0.0] * n
    for p in probs:
        p = min(1.0, max(0.0, p))
        for j in range(n, 0, -1):
            dist[j] = dist[j] * (1.0 - p) + dist[j - 1] * p
        dist[0] *= (1.0 - p)
    return max(0.0, min(1.0, sum(dist[k:])))


def feature_surprise(corpus: Corpus, members: list[str], f: Feature) -> tuple[int, float]:
    """``(shared_by, surprise)`` for one feature across one candidate set."""
    holders = corpus.feature_accounts.get(f, set())
    shared = [m for m in members if m in holders]
    k = len(shared)
    if k < MIN_SHARED_BY:
        return (k, 0.0)

    probs = [_p_edge(corpus, m, f) for m in members]
    tail = _poisson_binomial_tail(probs, k)
    if tail <= 0.0:
        return (k, MAX_FEATURE_SURPRISE)
    return (k, min(MAX_FEATURE_SURPRISE, -math.log10(tail)))


def score_candidate(
    corpus: Corpus,
    members: list[str],
    *,
    collect_evidence: bool = True,
) -> Candidate:
    """Total surprise for a set of accounts, with the per-family breakdown and the audit trail.

    Only RARE features are considered. A common feature contributes nothing under the null anyway
    (its Chung-Lu probability is already high, so its tail is near 1 and its surprise near 0), so
    skipping it early is a performance decision rather than a statistical one.
    """
    members = [m for m in dict.fromkeys(members) if m in corpus.by_id]
    if len(members) < 2:
        return Candidate(members=members, platform="unknown", score=0.0)

    # Union of the members' features, so a feature only some of them hold is still considered.
    union: set[Feature] = set()
    for m in members:
        union |= corpus.by_id[m].features

    # A network target that IS a member of the group is conversation, not convergence. Excluded by
    # name: without this, a community replying among itself hands the detector a perfect feature per
    # member and reports the community as an operation. Same reasoning as excluding the scanned
    # post, which every commenter engages by construction.
    inside = set(members)

    per_family: dict[str, list[float]] = {fam: [] for fam in ALL_FAMILIES}
    evidence: list[FeatureEvidence] = []

    # Sorted for the same reason as the corpus build: a set of Features iterates in hash order.
    for f in sorted(union, key=lambda f: f.token()):
        if not corpus.is_rare(f):
            continue
        if f.kind in ("reply_to", "target_post", "repost_of") and f.value in inside:
            continue
        k, s = feature_surprise(corpus, members, f)
        if s <= 0.0:
            continue
        per_family.setdefault(f.family, []).append(s)
        if collect_evidence:
            evidence.append(FeatureEvidence(
                feature=f,
                shared_by=k,
                corpus_count=corpus.feature_degree(f),
                surprise=s,
                sentence=_sentence(f, k, corpus.feature_degree(f), corpus.size),
            ))

    by_family: dict[str, float] = {}
    for fam, vals in per_family.items():
        if vals:
            by_family[fam] = _harmonic_sum(vals)

    platform = corpus.by_id[members[0]].platform
    evidence.sort(key=lambda e: e.surprise, reverse=True)
    # The headline score is WEIGHTED. The raw sum treats "ten reporters share a topic" as worth the
    # same as "eight accounts were provisioned in one week under one naming convention", and the
    # controls showed exactly that failure. Weighting here rather than at the comparison keeps the
    # shuffled null on the same scale by construction.
    return Candidate(
        members=sorted(members),
        platform=platform,
        score=weighted(by_family),
        by_family=by_family,
        evidence=evidence[:40],
    )


def _harmonic_sum(values: list[float]) -> float:
    """Sorted descending, weighted 1, 1/2, 1/3, ... See the module docstring.

    Monotone (more evidence never lowers the score) but strongly sublinear, which is the honest
    shape for observations that are correlated by an unknown amount.
    """
    return sum(v / (i + 1) for i, v in enumerate(sorted(values, reverse=True)))


def _sentence(f: Feature, shared_by: int, corpus_count: int, corpus_size: int) -> str:
    """One plain line a reviewer can check. Every published claim needs one."""
    where = {
        "shingle": "use the same phrase",
        "bio_shingle": "carry the same profile phrase",
        "gap_class": "post on the same interval rhythm",
        "active_hours": "are active in exactly the same hours",
        "quiet_hours": "share the same daily quiet period",
        "target_post": "engaged the same post",
        "reply_to": "replied to the same account",
        "client": "publish with the same tool",
        "link_domain": "link to the same domain",
        "creation_week": "were created in the same week",
        "handle_template": "share a handle template",
    }.get(f.kind, f.kind.replace("_", " "))
    return (
        f"{shared_by} accounts {where} ({f.value[:60]}), "
        f"held by {corpus_count} of {corpus_size} accounts in the corpus"
    )
