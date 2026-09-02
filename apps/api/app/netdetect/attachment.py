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
#: the finding. RETAINED FOR REFERENCE AND NO LONGER THE RULE: the weak set is now the group below
#: the widest step (see `MIN_CONTRIBUTION_GAP`), which needs no reference point and so cannot be
#: dragged off by the very members it is trying to identify. The original measurement still reads
#: correctly on findings where bystanders are a minority: the tightest case put the bystander at
#: 0.07 of the median against a weakest genuine member at 0.78.
WEAK_FRACTION = 0.25

#: Below this median contribution the question WAS treated as unanswerable. RETAINED FOR REFERENCE
#: AND NO LONGER THE RULE: see `MIN_CONTRIBUTION_GAP` below for why it was wrong and what replaced
#: it. The original measurement stands on its own terms, which is what made the error hard to see:
#: homogeneous findings ran medians of 0.04 to 0.18 while findings with a real bystander ran 1.57 to
#: 3.92.
MIN_MEDIAN_CONTRIBUTION = 0.5

#: The smallest step between two neighbouring contributions that counts as a REAL BOUNDARY rather
#: than the ordinary spread inside one group.
#:
#: WHY LEVEL CANNOT ANSWER THIS, WHICH IS THE BUG THIS CONSTANT REPLACES. The old rule abstained
#: when the MEDIAN contribution was low, on the reasoning that a homogeneous group gives every
#: member a delta near zero. That reasoning is sound and its converse is false: a finding that is
#: more than half bystanders ALSO has a near-zero median, because the median then falls inside the
#: bystander cluster instead of between the clusters. So the guard switched itself off exactly as
#: contamination got worse. Measured on the amplifier-ring grid, it abstained on every finding where
#: bystanders reached half or more (9 of 17, 15 of 23, 17 of 25) while the two populations were
#: cleanly separated in every one of them: no genuine member below +1.19, no bystander above +0.52.
#:
#: THE MAXIMUM CANNOT ANSWER IT EITHER, and that was measured before it was discarded. Keying on the
#: max classifies every ring finding correctly and then ruins the case the abstention exists for: a
#: PURE 8-member operation with no bystanders measures a max of 0.834, so a max rule checks it and
#: flags about half a clean group. All three homogeneous fixtures behave that way.
#:
#: What separates the two is BIMODALITY. A contaminated finding is two populations with an empty
#: band between them; a homogeneous one is a single continuous spread. Measured largest step:
#:
#:     homogeneous op 50/5    0.568        contaminated ring 40/63    1.406  (splits 9 of 9)
#:     homogeneous op 50/23   0.282        contaminated ring 60/61    1.057  (splits 15 of 15)
#:     homogeneous op 60/23   0.287        contaminated ring 80/63    1.482  (splits 17 of 17)
#:     newsroom control       0.235
#:
#: The band between 0.568 and 1.057 is empty, so this sits in the middle of it rather than being
#: fitted to either side, and in all three contaminated cases the split lands on EXACTLY the
#: bystander count. The RATIO of step to spread was measured too and does not work: homogeneous runs
#: 0.390 to 0.587 against a contaminated 0.379 to 0.579, which overlap completely.
#:
#: IT ALSO ABSTAINS ON SOME CONTAMINATED FINDINGS, AND THAT IS CORRECT RATHER THAN A MISS. The
#: numbers above come from ring corpora built on organic seed 31. Measured on ring corpora whose
#: organic background carries the ring's own seed, the two populations do not separate at all and
#: this abstains, naming nobody:
#:
#:     ring 40/61  8 ring, 1 bystander   ring spans -0.218..0.746, the bystander sits at 0.712
#:     ring 80/63  8 ring, 5 bystanders  ring spans  0.692..1.630, bystanders reach 0.947
#:
#: In the first the single bystander out-contributes SIX of the eight genuine members; in the second
#: the top bystander out-contributes the weakest genuine one. A rule that insisted on producing a
#: verdict there would have flagged real operation members and cleared the bystander, which is the
#: same failure the discarded MAX rule had, arriving from the other direction. So "flagged 0 of 5"
#: on such a corpus is this working: `abstained` is set, `answered` is False, and the surface says
#: no membership verdict was reached rather than showing a clean bill of health.
MIN_CONTRIBUTION_GAP = 0.8

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
    #: The widest step between two neighbouring contributions: the boundary this test looks for.
    #: Set whether or not it cleared `MIN_CONTRIBUTION_GAP`, so a caller holding the Attachment can
    #: see WHY it abstained and not merely that it did.
    #:
    #: IN-PROCESS ONLY, and deliberately so for now. `attachment_note` carries the abstention itself
    #: through `Candidate` to the stored row and out to a reader, so the CONDITION is not lost at
    #: the serialiser; this number is the supporting detail behind it. Surfacing it would mean a
    #: Candidate field, a column, an `_INCREMENTAL_COLUMNS` entry and a route field, which is real
    #: plumbing for a diagnostic. Worth doing if an operator ever has to argue with an abstention,
    #: and worth NOT claiming until then.
    gap: float = 0.0
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

    # THE QUESTION IS WHETHER THERE ARE TWO POPULATIONS HERE, NOT WHETHER THE NUMBERS ARE SMALL.
    #
    # Sort the contributions and look for the widest step between neighbours. A finding carrying
    # bystanders is bimodal: everyone who holds the evidence sits well above everyone who does not,
    # with an empty band between. A homogeneous group is one continuous spread with no such band,
    # whether its members contribute a lot or a little.
    #
    # This replaced a rule that keyed on the median LEVEL and therefore abstained precisely when
    # contamination was worst, because a finding more than half bystanders has its median inside the
    # bystander cluster. See `MIN_CONTRIBUTION_GAP` for that measurement and for why keying on the
    # maximum instead is also wrong.
    ranked = sorted(contribution.items(), key=lambda kv: (kv[1], kv[0]))
    steps = [(ranked[i + 1][1] - ranked[i][1], i) for i in range(len(ranked) - 1)]
    gap, below = max(steps) if steps else (0.0, -1)
    result.gap = round(gap, 4)

    if gap < MIN_CONTRIBUTION_GAP:
        # NOT "nobody is weakly attached". There is no boundary in this finding to draw, which is
        # what a real community looks like as well as what a tight operation looks like. Singling
        # anybody out here would be picking a rounding error.
        result.abstained = (
            "every member contributes about equally to this finding, so none can be singled out "
            "as weakly attached"
        )
        return result

    result.weak = sorted(name for name, _ in ranked[:below + 1])
    return result
