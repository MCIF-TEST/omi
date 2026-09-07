"""When the section is small enough for one group to poison its own null.

THE BLIND SPOT THIS EXISTS FOR, AND IT IS INVERTED FROM INTUITION: a section can be too CROWDED
by one group for this scan to price what that group shares, and the run then reports nothing at all.

`RARITY_CEILING` drops any feature held by more than a quarter of the corpus, on the reasoning that
a common feature carries no information. That reasoning holds only while the corpus is a fair
background. A comment section is not: it is exactly the thing an operation can flood.

An operation of k accounts shares its hard-family tells (one signup week, one set of outside
targets) across ALL k members by construction, so those features sit at prevalence k/n. Once
k/n passes the ceiling they are discarded before any arithmetic runs, and they are discarded FIRST,
because per-account features like text shingles vary between members and stay rare.

IT IS A BAND, NOT A SLOPE, AND MEASURING IT PROPERLY REQUIRES HOLDING THE CORPUS SIZE FIXED.

The first measurement here raised the operation's share by SHRINKING the background, which drove the
corpus under `detect.MIN_CORPUS` (25) at the top of the range. Those runs were refused for corpus
size, which is a STATED refusal on `RunOut.refused` and a different thing entirely from being
silenced by the ceiling. Three mechanisms can empty a dominated section and only one is silent:

    RARITY_CEILING suppression   silent, reads exactly like a clean scan.  THIS MODULE'S SUBJECT.
    MIN_CORPUS (25)              a stated refusal. The caller is told.
    MAX_GROUP_SHARE (0.40)       the generator caps a community at 40% of the corpus.

Measured with the corpus held at n = 50, so share is isolated from size and the floor never fires:

    op share   suppressed hard features   recall        recall with the ceiling lifted
      12%               0                  6 / 6                 6 / 6
      24%               0                12 / 12               12 / 12
      32%               5                 0 / 16               16 / 16
      40%               4                16 / 20               20 / 20
      50%               5                18 / 25               20 / 25

**The worst point is near a third, and recall partially RETURNS above it.** At 32% the loss is
total and silent: the corpus is well above the floor, the candidate generator still produces a
19-account community under a cap of 20, and the significance test throws the whole thing away
because `hard_evidence` has fallen to 0.00 and only text and timing carry weight. Above that the
operation is large enough that even its diluted evidence carries some members, and by 50% the
binding constraint is `MAX_GROUP_SHARE` rather than the ceiling (20 of 25 is the cap, not a loss).

So the honest claim is a BAND centred near a third of the section, not "the more of a post an
operation owns the safer it is". That earlier wording was a real overstatement and it was produced
by the shrinking-background construction rather than by the data.

**Lifting the ceiling restores full recall everywhere the group cap allows**, which is what proves
the ceiling is the whole mechanism here and that the Chung-Lu null is NOT also poisoned. That
matters for the eventual fix: judging rarity against an outside background would work, because the
null underneath it is still sound. It is also why the ceiling must not simply be raised, since the
same lift is what lets generic shared behaviour into every other finding.

---------------------------------------------------------------------------------------------------
WHAT THIS MODULE CLAIMS, AND WHAT IT REFUSES TO CLAIM
---------------------------------------------------------------------------------------------------

It does NOT say an operation is present. It cannot: a null built from a section one group dominates
cannot resolve that group in EITHER direction. Measured, the statistic fires on a planted operation
at 32% and above, and it fires harder (12 against 5) on a fan community filling 44% of a small
section, because fans converging on one artist's posts is real network evidence too.

Both are the same true statement: this section is too small, relative to that group, to price what
the group shares. So the finding is a REFUSAL TO RESOLVE, worded as one.

---------------------------------------------------------------------------------------------------
THE CATALOGUE RESOLVES WHAT THE SECTION CANNOT, AND THAT IS MEASURED RATHER THAN ASSERTED
---------------------------------------------------------------------------------------------------

`assign.sweep` weighs an account against formations catalogued from OTHER investigations, using the
surprise each feature carried in the corpus where it was learned. So it does not read this corpus's
rarity at all, and a group large enough to poison its own background here cannot poison a profile
built somewhere it was a minority.

That was stated in this docstring for a while as reasoning. It is now a measurement. Catalogue the
stadium operator from a section where it holds 8 of 68, then rotate it onto accounts sharing no id
with anything stored and vary how much of the NEW section it owns:

    op share   detect finds it   suppressed here   sweep places   organic placed
      12%            yes               0              8 / 8          0 / 56
      24%            yes               0              8 / 8          0 / 25
      32%            NO                5              8 / 8          0 / 17
      40%            no*               5              8 / 8          0 / 12
      50%            no*               5              8 / 8          0 /  8

* This construction shrinks the background, so at 40% and 50% the corpus is 20 and 16 accounts,
  under MIN_CORPUS: those runs were refused for SIZE rather than silenced by the ceiling. The
  section-side claim rests on the 32% row and on the n = 50 band above. What the two starred rows
  still show is worth having on its own: the catalogue places a rotated operation even in a section
  too small for the detector to run on at all.

Recall through the catalogue is FLAT across the whole range, including where recall through this
section collapses. That is the point: the two are blind to different things, so the fallback is worth
running exactly where the primary path fails.

IT IS ALSO SAFE, WHICH MATTERS MORE, because the statistic that sends us here fires on innocent
groups too and a fallback that answered them with names would turn a refusal into an accusation:

    corpus                              suppressed   sweep places
    fan community, 12 of 27 (44%)           12            0
    fan community, 12 of 20 (60%)           12            0
    professional beat, 10 of 25 (40%)        0            0
    UNCATALOGUED ring, 8 of 25 (32%)         3            0
    organic only, 25                         0            0

The uncatalogued row is the honest limit and must be stated wherever this is surfaced: the catalogue
can only recognise an operation somebody has already recorded, so an empty fallback means "no match
in the catalogue", never "nobody here is coordinated". `assign.NOT_A_CLEARANCE` carries that wording
already and this path reuses it rather than writing a second one.

Restricting the statistic to the HARD families is what keeps it honest, and it is measured: the
professional-beat control fills 40% of a 25-account section and scores ZERO here, because a newsroom
shares text, timing and a publishing tool rather than provisioning and targets. The same hard/soft
split that decides whether a finding is publishable is what decides whether a section is
unresolvable.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.netdetect.significance import Corpus
from app.netdetect.types import HARD_FAMILIES

#: How many suppressed hard-family features a group must share before the section is called
#: unresolvable. MEASURED, and the gap it sits in is wide: every corpus with no dominant group
#: scored exactly 0 (organic at 25 and 60, the newsroom at 14% and at 40% of its section, the fan
#: community at 14%, a viral thread), and every dominated one scored 5 or more. A threshold in an
#: empty gap is the only kind worth having.
MIN_SUPPRESSED_HARD = 3

#: A feature must be shared by at least this fraction of the group to count as the group's own.
#: Half, so one member's stray attribute cannot make a section look unresolvable.
GROUP_SHARE = 0.5


@dataclass(slots=True)
class Domination:
    """Whether one group is large enough here that this section cannot price what it shares."""

    #: Suppressed hard-family features shared by the worst group. Zero when nothing was suppressed.
    suppressed: int = 0
    #: That group's size, and the largest share of the corpus any of its suppressed features reached.
    group_size: int = 0
    top_prevalence: float = 0.0
    #: Families whose evidence was suppressed, so the notice can name what was lost.
    families: list[str] = field(default_factory=list)
    #: False when the check did not run. NEVER read a zero as "the section is resolvable" without
    #: this, the same rule `attachment_checked` and `corroboration.checked` follow.
    checked: bool = False

    @property
    def unresolvable(self) -> bool:
        return self.checked and self.suppressed >= MIN_SUPPRESSED_HARD

    def sentence(self) -> str:
        if not self.checked:
            return "This section was not checked for a dominant group."
        if not self.unresolvable:
            return ""
        fams = " and ".join(sorted(self.families)) or "the operator's own acts"
        return (
            f"{self.group_size} accounts here share {self.suppressed} behaviours in "
            f"{fams} that this section is too small to price: each is held by up to "
            f"{self.top_prevalence:.0%} of everyone who commented, so it was dropped as ordinary "
            f"before any statistics ran. That is what a group large enough to shape its own "
            f"background looks like, and it reads the same whether the group is an operation or a "
            f"community that simply turned up together. This scan cannot tell them apart. What "
            f"still works is the formation catalogue, which weighs these accounts against other "
            f"investigations rather than against this one: the run does that automatically and "
            f"reports how many placed."
        )


def assess(corpus: Corpus, groups: list[list[str]]) -> Domination:
    """Did the rarity ceiling swallow a group's hard evidence?

    ``groups`` are the candidate communities, which is where a dominant group already shows up
    intact: the generator finds it, and only the significance test loses it.
    """
    out = Domination(checked=True)
    if corpus.size <= 0:
        return out

    for members in groups:
        inside = set(members)
        if len(inside) < 2:
            continue
        need = max(2, int(len(inside) * GROUP_SHARE))
        count, top, fams = 0, 0.0, set()
        for f, holders in corpus.feature_accounts.items():
            if f.family not in HARD_FAMILIES:
                continue
            if len(holders & inside) < need:
                continue
            # Only features the ceiling actually threw away. A rare one was priced normally and
            # is already in the finding, or already in the refusal, either way not suppressed.
            if corpus.is_rare(f):
                continue
            count += 1
            top = max(top, len(holders) / corpus.size)
            fams.add(f.family)
        if count > out.suppressed:
            out.suppressed = count
            out.group_size = len(inside)
            out.top_prevalence = top
            out.families = sorted(fams)
    return out
