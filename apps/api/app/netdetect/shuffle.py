"""The falsification harness, and the correction for having searched.

THIS IS THE MOST IMPORTANT FILE IN THE PACKAGE. It exists before the detector trusts a threshold,
because building a detector before the test that can refute it is how a system ends up confidently
publishing noise, and this product's findings are claims about named real people.

THE PROBLEM IT SOLVES
---------------------
``significance.score_candidate`` answers "how improbable is this set" for ONE set. The pipeline does
not test one set. It searches a very large space of possible sets and reports the best ones. In a
corpus of any size, SOMETHING improbable is always shared by SOME subset: that is a property of the
search, not of the data. Reporting the extreme of a large search as though it were a single
pre-registered test is the classic way to manufacture findings, and it is exactly what a threshold
like "P >= 0.95" does when it is applied to the winner of a search.

THE CORRECTION
--------------
Compare against the distribution of the MAXIMUM, not the distribution of a single score.

    1. Shuffle the account-feature graph while preserving BOTH degree sequences.
    2. Run the entire real pipeline on the shuffled graph.
    3. Record the highest score it finds.
    4. Repeat K times. Those K maxima are the null distribution of "the best thing a search like
       ours finds in data like ours with the structure removed".

A real candidate is significant only when it beats that distribution. This is a max-statistic
permutation test and it controls the family-wise error rate: it answers "I searched and took the
best" with "here is what taking the best gets you when there is nothing there".

WHY DEGREE-PRESERVING
---------------------
A shuffle that ignored degrees would destroy the very structure the null is supposed to keep:
prolific accounts would stop being prolific and popular features would stop being popular, so
everything real would look significant against it. Double-edge swap preserves both sequences
exactly, which means the only thing removed is the ASSOCIATION between particular accounts and
particular features. That association is precisely what coordination is.

WHAT IT STILL CANNOT DO
-----------------------
The null removes association but keeps the corpus's shape, so it cannot price in a confound that IS
structural: if the corpus is dominated by one topic because customers scanned one topic, the shuffle
inherits that. See ``detect.py``'s refusal rules, which are the non-statistical half of the answer.
"""

from __future__ import annotations

import random
from dataclasses import dataclass

from app.netdetect.significance import Corpus
from app.netdetect.types import AccountProfile, Feature

#: Swap attempts per edge. The standard rule of thumb for double-edge swap mixing is a small
#: multiple of the edge count; 10 is comfortably past the point where the chain has mixed for
#: graphs of this density, and the cost is linear.
SWAPS_PER_EDGE = 10

#: How many shuffled corpora make the null distribution of the maximum. Small on purpose: we need a
#: high quantile of the maximum, not a precise p-value, and each shuffle re-runs the whole pipeline.
DEFAULT_SHUFFLES = 24

#: Quantile of the shuffled maxima a real candidate must beat. 0.95 here is a family-wise claim
#: across the entire search, which is a far stronger statement than 0.95 on one hypothesis.
DEFAULT_QUANTILE = 0.95


def shuffle_corpus(corpus: Corpus, *, seed: int = 0) -> Corpus:
    """A degree-preserving shuffle of the account-feature graph.

    Returns a NEW ``Corpus``; the input is untouched, so a caller can shuffle repeatedly from one
    baseline without the chain drifting further on every call.
    """
    rng = random.Random(seed)

    # Edge list as (account_id, feature). Kept alongside a membership set so a swap can reject a
    # duplicate in O(1): allowing duplicates would silently lower a feature's degree and break the
    # guarantee this function exists to provide.
    edges: list[tuple[str, Feature]] = []
    present: set[tuple[str, Feature]] = set()
    # SORTED, and this is the load-bearing line in the whole file.
    #
    # `features` is a set of dataclasses whose fields are strings, so it iterates in an order that
    # depends on `hash(str)` and is therefore randomised per PROCESS. The swap loop below indexes
    # into this list with a seeded RNG, so an edge list in a different order means a different
    # shuffle from the same seed. Every shuffle in the null is built this way, so the null threshold
    # itself became a function of the interpreter's hash seed rather than of the data.
    #
    # Measured before the fix: one corpus, one seed, thresholds of 8.505 / 8.02 / 0.0 across three
    # hash seeds. A threshold of 0.0 accepts every candidate, which removes the search correction
    # that is the entire justification for this module, and it is why the falsification test failed
    # roughly one run in five and read as flakiness.
    for a in sorted(corpus.accounts, key=lambda a: a.external_id):
        for f in sorted(a.features, key=lambda f: f.token()):
            edges.append((a.external_id, f))
            present.add((a.external_id, f))

    n = len(edges)
    if n < 4:
        return Corpus([AccountProfile(a.external_id, a.platform, set(a.features), a.handle,
                                      a.score, a.tier) for a in corpus.accounts])

    for _ in range(n * SWAPS_PER_EDGE):
        i = rng.randrange(n)
        j = rng.randrange(n)
        if i == j:
            continue
        a1, f1 = edges[i]
        a2, f2 = edges[j]
        if a1 == a2 or f1 == f2:
            continue
        # The swap must not create an edge that already exists, or degrees stop being preserved.
        if (a1, f2) in present or (a2, f1) in present:
            continue
        present.discard((a1, f1))
        present.discard((a2, f2))
        present.add((a1, f2))
        present.add((a2, f1))
        edges[i] = (a1, f2)
        edges[j] = (a2, f1)

    rebuilt: dict[str, set[Feature]] = {a.external_id: set() for a in corpus.accounts}
    for aid, f in edges:
        rebuilt[aid].add(f)

    return Corpus([
        AccountProfile(
            external_id=a.external_id,
            platform=a.platform,
            features=rebuilt[a.external_id],
            handle=a.handle,
            score=a.score,
            tier=a.tier,
        )
        for a in corpus.accounts
    ])


@dataclass(slots=True)
class NullDistribution:
    """What a search like ours finds when there is nothing to find."""

    maxima: list[float]
    shuffles: int
    quantile: float

    @property
    def threshold(self) -> float:
        """The score a real candidate has to beat.

        Returns +inf on an empty sample rather than 0. A missing null must never read as "everything
        is significant"; it must read as "nothing can be reported yet", and infinity is the honest
        encoding of that.
        """
        if not self.maxima:
            return float("inf")
        ordered = sorted(self.maxima)
        idx = min(len(ordered) - 1, int(round(self.quantile * (len(ordered) - 1))))
        return ordered[idx]

    def p_value(self, score: float) -> float:
        """Fraction of shuffled searches that found something at least this good.

        The +1 in numerator and denominator is the standard permutation-test correction: with K
        shuffles the smallest honestly reportable p-value is 1/(K+1), and reporting 0 would claim a
        precision the sample size does not have.
        """
        if not self.maxima:
            return 1.0
        beat = sum(1 for m in self.maxima if m >= score)
        return (beat + 1) / (len(self.maxima) + 1)


def build_null(
    corpus: Corpus,
    search_fn,
    *,
    shuffles: int = DEFAULT_SHUFFLES,
    quantile: float = DEFAULT_QUANTILE,
    seed: int = 1_000,
) -> NullDistribution:
    """Run the WHOLE pipeline on ``shuffles`` degree-preserving shuffles and keep each maximum.

    ``search_fn`` takes a ``Corpus`` and returns the candidates it would report. It must be the
    same function used on real data: a null built from a cheaper approximation of the search would
    be measuring a different search than the one whose output is being corrected, which is worse
    than no correction because it looks like one.
    """
    maxima: list[float] = []
    for i in range(max(1, shuffles)):
        shuffled = shuffle_corpus(corpus, seed=seed + i)
        found = search_fn(shuffled)
        maxima.append(max((c.score for c in found), default=0.0))
    return NullDistribution(maxima=maxima, shuffles=shuffles, quantile=quantile)
