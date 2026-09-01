"""When the section is small enough for one group to poison its own null.

THE BLIND SPOT THIS EXISTS FOR, AND IT IS INVERTED FROM INTUITION.

`RARITY_CEILING` drops any feature held by more than a quarter of the corpus, on the reasoning that
a common feature carries no information. That reasoning holds only while the corpus is a fair
background. A comment section is not: it is exactly the thing an operation can flood.

An operation of k accounts shares its hard-family tells (one signup week, one set of outside
targets) across ALL k members by construction, so those features sit at prevalence k/n. Once
k/n passes the ceiling they are discarded before any arithmetic runs, and they are discarded FIRST,
because per-account features like text shingles vary between members and stay rare.

Measured on a planted operation in an organic background, holding the operation at 8 accounts and
shrinking the background:

    op share   hard-family features surviving as rare   recall
      12%                    5                           8/8
      24%                    5                           8/8
      32%                    0                           0
      39%                    0                           0
      50%                    0                           0

The candidate generator still finds the group perfectly: at 39% the largest community is 11 of 11
operation accounts. It is the significance test that then throws it away, because `hard_evidence`
has fallen to 0.00 and only text and timing carry weight, so the structural refusal fires with
"only 1 family carried real weight". `detect` returns no findings, which is indistinguishable from
a clean comment section.

That is the failure this package calls the worst kind, and the most dangerous place to have it: a
heavily brigaded post is the single most likely thing a customer scans, and the more of it an
operation owns, the safer the operation is.

---------------------------------------------------------------------------------------------------
WHAT THIS MODULE CLAIMS, AND WHAT IT REFUSES TO CLAIM
---------------------------------------------------------------------------------------------------

It does NOT say an operation is present. It cannot: a null built from a section one group dominates
cannot resolve that group in EITHER direction. Measured, the statistic fires on a planted operation
at 32% and above, and it fires harder (12 against 5) on a fan community filling 44% of a small
section, because fans converging on one artist's posts is real network evidence too.

Both are the same true statement: this section is too small, relative to that group, to price what
the group shares. So the finding is a REFUSAL TO RESOLVE, worded as one, and it names the tool that
still works. `assign.sweep` weighs accounts against formations catalogued from OTHER investigations,
so it does not depend on rarity within this corpus at all.

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
            f"community that simply turned up together. This scan cannot tell them apart. Sweep "
            f"these accounts against the formation catalogue, which weighs them against other "
            f"investigations rather than against this one, or read them by hand."
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
