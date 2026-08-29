"""Does this account belong in this set?

THE QUESTION THE SET-LEVEL STATISTIC DOES NOT ANSWER. `detect` asks how improbable it is that THESE
k accounts share this much. Candidate generation is community detection, and Louvain pulls in
boundary accounts, so a finding can name somebody who borders the group without belonging to it.
Measured across a systematic grid: recall 8/8, and about 7% of all named members were bystanders.

That rate was pinned as a ceiling and otherwise unaddressed, because a finding names real people and
the obvious per-member number does not work. `persist.pair_evidence_from` knows how much of the
shared evidence each member participates in, and publishing THAT ranks some bystanders above genuine
operation members (pinned by a test in `test_netdetect.py`). A number beside a person's name is read
as a judgement about them, so the wrong number is worse than none.

---------------------------------------------------------------------------------------------------
WHAT WORKS: WHAT DID THIS MEMBER ADD?
---------------------------------------------------------------------------------------------------

Not "how much does it share" but "how much less improbable is this set without it". Score the set,
then score the set minus one member, in the finding's own weighted log10 units.

The arithmetic gives the sign for free. Removing a genuine member drops the shared count `k` across
many rare features, so the Poisson-binomial tail widens and the score falls: a large POSITIVE delta.
Removing a bystander leaves `k` alone on the features that carry the finding while shrinking `n`, so
the tail gets SMALLER and the score can rise: a delta at or below zero.

Measured on the contaminated corpora, every bystander landed at or below zero while every operation
member sat well above it.

---------------------------------------------------------------------------------------------------
THE THRESHOLD IS RELATIVE, AND THAT IS A MEASUREMENT RATHER THAN A PREFERENCE
---------------------------------------------------------------------------------------------------

A fixed global cut does not work, and the numbers say so plainly. Across the grid the weakest genuine
operation member scored **-0.134** and the strongest bystander **+0.116**, so any absolute threshold
misclassifies one or the other. Within a single finding they separate cleanly, because the scale of a
delta is set by how much evidence that particular finding rests on.

So a member is weak relative to the TYPICAL member of its own finding.

---------------------------------------------------------------------------------------------------
IT ABSTAINS, AND THE ABSTENTION IS THE HONEST PART
---------------------------------------------------------------------------------------------------

In a homogeneous operation every member holds the same features, so removing any one of them barely
moves the score and the median contribution sits near zero. There is no weak member to find, and a
rule that went looking anyway would flag whoever happened to round lowest. The professional-beat
control lands here too, correctly: a real community IS everybody contributing alike.

Below `MIN_MEDIAN_CONTRIBUTION` this returns no verdict and says why, the same discipline as
`corrected_p = None` meaning "not compared" and never "not significant".

---------------------------------------------------------------------------------------------------
IT REPORTS. IT NEVER DROPS A MEMBER.
---------------------------------------------------------------------------------------------------

Removing a flagged account would change the finding's membership, its score and its stored identity,
which is a detection decision taken on a heuristic. It would also make the mirror error unrecoverable:
a wrongly flagged member is a real participant quietly deleted from an operation. The flag goes to a
reader beside the evidence, and the reader decides.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field

from app.netdetect.significance import Corpus, score_candidate

#: A member contributing less than this share of what the typical member contributes is not carrying
#: the finding. Measured separation on the contaminated corpora is wide: the tightest case put the
#: bystander at 0.07 of the median against a weakest genuine member at 0.78, so this sits between
#: them with room on both sides rather than being fitted to either.
WEAK_FRACTION = 0.25

#: Below this median contribution the question is not answerable and the answer is no answer.
#:
#: A homogeneous group (every member holding the same features) gives every member a delta near zero,
#: because the evidence survives whoever you remove. Measured: such findings ran medians of 0.04 to
#: 0.18 while every finding with a real bystander ran 1.57 to 3.92. The gap is an order of magnitude,
#: which is why a blunt gate is enough and a fitted one would be false precision.
MIN_MEDIAN_CONTRIBUTION = 0.5

#: Above this many members the test abstains rather than running.
#:
#: MEASURED, not guessed. Leave-one-out costs one scoring per member and each scoring walks a
#: feature union that itself grows with the member count, so the curve is steep. On a 220-account
#: corpus: n=20 took 0.21s, n=30 1.0s, n=40 2.8s, n=50 7.2s, n=60 15.4s. This runs inside an admin
#: request that has already spent tens of seconds detecting, so 40 is where the answer stops being
#: worth the wait.
#:
#: It agrees with `persist.MAX_MEMBERS_FOR_PAIRS` by coincidence of the same underlying judgement,
#: that a finding this large is a subject rather than a formation. They are kept separate because
#: the cost models are different (pairs grow quadratically, this closer to n^3.5), and collapsing
#: them would tie one bound to the other's measurement.
MAX_MEMBERS = 40


@dataclass(slots=True)
class Attachment:
    """Per-member leave-one-out contributions, and who (if anyone) is weakly attached."""

    #: member -> how much the set's weighted log10 surprise falls when that member is removed.
    contribution: dict[str, float] = field(default_factory=dict)
    #: Members contributing far less than the typical one. Empty when nobody is, or when abstaining.
    weak: list[str] = field(default_factory=list)
    #: Median contribution, the scale the threshold is relative to.
    median: float = 0.0
    #: Non-null when no verdict was reached. Never read this as "nobody is weakly attached".
    abstained: str | None = None

    @property
    def answered(self) -> bool:
        return self.abstained is None


def leave_one_out(corpus: Corpus, members: list[str]) -> dict[str, float]:
    """How much the set's weighted surprise falls when each member is removed.

    Positive means the member carried evidence the rest of the set does not have. Zero or negative
    means the finding is no less improbable without them.
    """
    ordered = sorted(dict.fromkeys(members))
    if len(ordered) < 3:
        return {}
    full = score_candidate(corpus, ordered, collect_evidence=False).score
    out: dict[str, float] = {}
    for m in ordered:
        rest = [x for x in ordered if x != m]
        out[m] = full - score_candidate(corpus, rest, collect_evidence=False).score
    return out


def assess(corpus: Corpus, members: list[str]) -> Attachment:
    """Who in this finding is not carrying it, or why that cannot be said."""
    ordered = sorted(dict.fromkeys(members))
    if len(ordered) < 3:
        return Attachment(abstained="a finding this small has no typical member to compare against")
    if len(ordered) > MAX_MEMBERS:
        return Attachment(
            abstained=f"{len(ordered)} members is above the {MAX_MEMBERS} this test is run for"
        )

    contribution = leave_one_out(corpus, ordered)
    if not contribution:
        return Attachment(abstained="the set could not be re-scored without a member")

    median = statistics.median(contribution.values())
    result = Attachment(contribution={k: round(v, 4) for k, v in contribution.items()},
                        median=round(median, 4))

    if median < MIN_MEDIAN_CONTRIBUTION:
        # NOT "nobody is weakly attached". The evidence is spread evenly enough that removing any one
        # member barely moves the score, which is what a real community looks like as well as what a
        # tight operation looks like. Singling anybody out here would be picking a rounding error.
        result.abstained = (
            "every member contributes about equally to this finding, so none can be singled out "
            "as weakly attached"
        )
        return result

    threshold = WEAK_FRACTION * median
    result.weak = sorted(m for m, v in contribution.items() if v < threshold)
    return result
