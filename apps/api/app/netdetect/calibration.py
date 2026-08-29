"""What the accumulated judgements would move, and whether there are yet enough of them.

EVERY CONSTANT IN THIS PACKAGE IS REASONED, NOT FITTED. No labelled corpus of coordinated accounts
exists and none can be bought, so the thresholds were argued from what a real population looks like
and then pinned by synthetic controls. That is defensible and it is not calibration: a control proves
the SHAPE of a guard, never its setting.

`NetdetectFinding.status` is the only ground truth this detector will ever accumulate. This module
reads it back and answers one question: **if a threshold had been set differently, which of the
findings a person has already judged would have changed?**

---------------------------------------------------------------------------------------------------
IT REPORTS. IT NEVER MOVES ANYTHING.
---------------------------------------------------------------------------------------------------

No constant in `app/netdetect` is read from the database, and none may become so. Three reasons, and
the first is the one that matters:

* **A threshold that moves itself can be steered by whoever clicks.** This detector reports groups of
  named real people as running together. A self-tuning gate turns "dismiss" into a write on the
  system's accusation policy, available to anyone with an admin session, with no review and no diff.
* **A constant in code has a commit, a reviewer and a reason beside it.** A constant in a row has a
  number. The next session inherits the second one with no way to know what argument produced it.
* **The synthetic controls pin the current values.** A value that changed at runtime would drift away
  from the tests that justify it, and the suite would keep passing because it tests the code.

So the output of this module is a recommendation with its arithmetic attached, for a person to read
and then to edit `significance.py` or `detect.py` by hand if they agree.

---------------------------------------------------------------------------------------------------
WHY THE ROW CARRIES `by_family_json` AND NOT JUST A SCORE
---------------------------------------------------------------------------------------------------

Every threshold swept here is recomputable from the stored row: hard evidence, the number of
families carrying real weight and the top family's share all fall out of `by_family_json`, and the
search correction is `corrected_p`. So a sweep replays a threshold against findings judged months
ago **without re-running the detector**, which matters because the corpus those findings were made
in is not kept and re-deriving it would risk deriving it differently.

---------------------------------------------------------------------------------------------------
WHAT A JUDGEMENT IS AND IS NOT
---------------------------------------------------------------------------------------------------

A dismissal is a labelled negative about **the finding**, not about the accounts. "These are
reporters on one beat" says the group is not an operation; it says nothing about whether any member
is automated. `AccountLabel` is the other reservoir and it labels botness, which this package
deliberately never reads. The two are orthogonal axes and averaging them would be a category error.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import select

from app.netdetect.detect import MIN_FAMILIES, MIN_HARD_EVIDENCE
from app.netdetect.shuffle import DEFAULT_QUANTILE
from app.netdetect.significance import MAX_SINGLE_FAMILY_SHARE, MIN_FAMILY_CONTRIBUTION
from app.netdetect.types import FAMILY_WEIGHT, HARD_FAMILIES
from app.storage.models import NetdetectFinding

#: Judgements needed before this module will name a recommendation at all, and the minimum of the
#: rarer class among them.
#:
#: Four tunable constants fitted against a dozen labels is not calibration, it is memorising the
#: last dozen posts somebody happened to look at. The floor is deliberately blunt: a sweep is still
#: printed below it, because watching the reservoir fill is useful, but nothing is recommended.
MIN_JUDGEMENTS = 30
MIN_PER_CLASS = 8

#: A recommendation has to be worth the churn. A move that reclassifies fewer findings than this is
#: inside the noise of who happened to be reviewing that week.
MIN_NET_IMPROVEMENT = 3


@dataclass(slots=True)
class Judged:
    """One judged finding, reduced to the quantities a threshold is expressed in."""

    id: int
    confirmed: bool
    score: float
    corrected_p: float | None
    hard_evidence: float
    families_contributing: int
    top_family_share: float
    member_count: int
    corpus_size: int
    needs_adjudication: bool


@dataclass(slots=True)
class SweepRow:
    value: float
    #: Confirmed findings this setting would still have reported. Recall, on the judged set.
    confirmed_kept: int
    #: Dismissed findings this setting would still have reported. Every one is a false positive a
    #: person had to spend attention on.
    dismissed_kept: int

    @property
    def dismissed_removed(self) -> int:
        return self._total_dismissed - self.dismissed_kept

    _total_dismissed: int = 0


@dataclass(slots=True)
class Sweep:
    constant: str
    where: str
    current: float
    #: "raise" if larger values are stricter, "lower" if smaller ones are. Stated because a reader
    #: cannot infer it from the numbers and reading it backwards inverts every recommendation.
    stricter_direction: str
    rows: list[SweepRow] = field(default_factory=list)
    recommendation: str | None = None
    proposed: float | None = None


@dataclass(slots=True)
class FamilySplit:
    family: str
    weight: float
    hard: bool
    mean_in_confirmed: float
    mean_in_dismissed: float
    present_in_confirmed: int
    present_in_dismissed: int

    @property
    def separation(self) -> float:
        """Positive means the family argues FOR an operation on this evidence, negative against."""
        return self.mean_in_confirmed - self.mean_in_dismissed


@dataclass(slots=True)
class CalibrationReport:
    confirmed: int
    dismissed: int
    open: int
    #: False while the reservoir is too thin to fit anything. The sweeps are still returned.
    sufficient: bool
    #: Why not, when it is not. Empty when it is.
    insufficient_reason: str
    sweeps: list[Sweep] = field(default_factory=list)
    families: list[FamilySplit] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)
    #: Open findings whose judgement would teach the most, nearest boundary first.
    next_to_judge: list["NextToJudge"] = field(default_factory=list)
    #: How many more judgements, and of which class, before anything can be recommended.
    still_needed: str = ""
    caveats: list[str] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class Axis:
    """One tunable constant: where it lives, what it is now, and what would flip a finding.

    DECLARED ONCE AND USED TWICE, by the sweep that replays it against judged findings and by the
    ranking that asks which unjudged finding sits nearest it. Two copies of these predicates is
    exactly the drift this file would not notice: the sweep would fit one rule while the ranking
    sent an operator to judge findings selected by another.
    """

    constant: str
    where: str
    current: float
    values: tuple[float, ...]
    stricter_direction: str
    #: (judged, value) -> would this finding still have been reported at that setting.
    keeps: object
    #: (judged) -> the finding's own position on this axis, or None when it has none.
    position: object


#: How many open findings to name as worth judging next. A queue nobody can finish is a queue
#: nobody starts, and the point of this list is that thirty judgements should feel reachable.
MAX_NEXT_TO_JUDGE = 10


@dataclass(slots=True)
class NextToJudge:
    """One open finding, and why judging IT would teach more than judging another.

    NOT A SUSPICION RANKING, AND THE DISTINCTION IS THE WHOLE POINT. `distance` says this finding
    sits near a threshold boundary, so a verdict on it would change what the sweeps recommend. It
    says nothing whatever about how likely the group is to be an operation, and the two orderings
    are close to unrelated: a finding far above every threshold is the most obviously coordinated
    and the least informative, because nobody needed a label to know how it would be classified.

    An operator who read this as "most suspicious first" would work through the borderline cases
    believing them to be the strongest, which is exactly backwards.
    """

    finding_id: int
    context_id: str | None
    member_count: int
    #: The constant this finding sits nearest to.
    nearest_constant: str
    #: Distance to that boundary as a fraction of the constant's own sweep range, so the four are
    #: comparable. Zero means the finding sits exactly on the line.
    distance: float
    #: The finding's value on that axis, and the setting in force.
    value: float
    current: float
    #: How many of the fitted constants this finding would flip. The primary ordering: a finding
    #: sitting on two boundaries teaches about both.
    flips_constants: int
    why: str


def _axes() -> list[Axis]:
    """The four constants this module fits, and the only place their rules are written."""
    alpha = round(1.0 - DEFAULT_QUANTILE, 4)
    return [
        Axis(
            constant="MIN_HARD_EVIDENCE", where="app/netdetect/detect.py",
            current=MIN_HARD_EVIDENCE,
            values=(0.0, 1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 8.0),
            stricter_direction="raise",
            keeps=lambda j, v: j.hard_evidence >= v,
            position=lambda j: j.hard_evidence,
        ),
        Axis(
            constant="MIN_FAMILIES", where="app/netdetect/detect.py",
            current=float(MIN_FAMILIES),
            values=(1.0, 2.0, 3.0, 4.0),
            stricter_direction="raise",
            keeps=lambda j, v: j.families_contributing >= v,
            position=lambda j: float(j.families_contributing),
        ),
        Axis(
            constant="MAX_SINGLE_FAMILY_SHARE", where="app/netdetect/significance.py",
            current=MAX_SINGLE_FAMILY_SHARE,
            values=(0.50, 0.60, 0.70, 0.80, 0.90, 1.0),
            stricter_direction="lower",
            keeps=lambda j, v: j.top_family_share <= v,
            position=lambda j: j.top_family_share,
        ),
        Axis(
            constant="alpha (1 - DEFAULT_QUANTILE)", where="app/netdetect/shuffle.py",
            current=alpha,
            values=(0.005, 0.01, 0.02, 0.05, 0.10),
            stricter_direction="lower",
            # A finding with no corrected p was never compared against the shuffled search, and
            # "not corrected" must never be read as "significant".
            keeps=lambda j, v: j.corrected_p is not None and j.corrected_p <= v,
            position=lambda j: j.corrected_p,
        ),
    ]


def _next_to_judge(session, axes: list[Axis]) -> list[NextToJudge]:
    """Which unjudged findings sit closest to a threshold that is being fitted.

    The reservoir needs thirty judgements with eight of each class before anything is recommended,
    and it fills one operator click at a time. Judging thirty well-chosen findings is worth more
    than judging several hundred arbitrary ones, because a finding far from every boundary cannot
    change a recommendation whichever way it goes.

    THE MEASURE IS HOW MANY SETTINGS WOULD FLIP IT, not how near a number it is. Distance alone
    degenerates on the integer constants: `MIN_FAMILIES` is 2 and most findings contribute exactly
    two families, so they all sit at distance zero and the ranking says nothing. Asking instead
    whether a finding is kept at some candidate settings and refused at others answers the question
    directly, and works the same on a continuous axis as on a discrete one.
    """
    rows = list(session.execute(
        select(NetdetectFinding).where(NetdetectFinding.status == "open")
    ).scalars())
    if not rows or not axes:
        return []

    out: list[NextToJudge] = []
    for row in rows:
        judged = _reduce(row)
        flips: list[tuple[str, float, float, float]] = []
        for axis in axes:
            verdicts = {bool(axis.keeps(judged, v)) for v in axis.values}
            if len(verdicts) < 2:
                # Kept at every candidate setting, or refused at every one. A label here cannot
                # move this constant, however close the raw number happens to look.
                continue
            position = axis.position(judged)
            if position is None:
                continue
            spread = max(axis.values) - min(axis.values)
            distance = abs(float(position) - axis.current) / spread if spread > 0 else 0.0
            flips.append((axis.constant, distance, float(position), axis.current))

        if not flips:
            continue
        flips.sort(key=lambda f: f[1])
        constant, distance, value, current = flips[0]
        out.append(NextToJudge(
            finding_id=row.id,
            context_id=row.context_id,
            member_count=int(row.member_count or 0),
            nearest_constant=constant,
            distance=round(distance, 4),
            value=round(value, 4),
            current=round(current, 4),
            flips_constants=len(flips),
            why=(
                f"kept at some candidate settings of {constant} and refused at others, sitting at "
                f"{value:.2f} against the current {current:.2f}. A verdict here moves that fit; a "
                f"finding classified the same way at every setting cannot."
            ),
        ))

    # Most constants moved first, then nearest the line. A finding sitting on two boundaries teaches
    # about both.
    out.sort(key=lambda n: (-n.flips_constants, n.distance, n.finding_id))
    return out[:MAX_NEXT_TO_JUDGE]


def _reduce(row: NetdetectFinding) -> Judged:
    by_family = {k: float(v) for k, v in (row.by_family_json or {}).items()}
    hard = sum(v * FAMILY_WEIGHT.get(k, 0.5) for k, v in by_family.items() if k in HARD_FAMILIES)
    weighted_total = sum(v * FAMILY_WEIGHT.get(k, 0.5) for k, v in by_family.items())
    top = max((v * FAMILY_WEIGHT.get(k, 0.5) for k, v in by_family.items()), default=0.0)
    return Judged(
        id=row.id,
        confirmed=row.status == "confirmed",
        score=float(row.score or 0.0),
        corrected_p=row.corrected_p,
        hard_evidence=hard,
        families_contributing=sum(1 for v in by_family.values() if v >= MIN_FAMILY_CONTRIBUTION),
        top_family_share=(top / weighted_total) if weighted_total > 0 else 0.0,
        member_count=int(row.member_count or 0),
        corpus_size=int(row.corpus_size or 0),
        needs_adjudication=bool(row.needs_adjudication),
    )


def load_judged(session) -> list[Judged]:
    rows = session.execute(
        select(NetdetectFinding).where(NetdetectFinding.status.in_(("confirmed", "dismissed")))
    ).scalars()
    return [_reduce(r) for r in rows]


def _sweep(
    judged: list[Judged],
    *,
    constant: str,
    where: str,
    current: float,
    values: list[float],
    keeps,
    stricter_direction: str,
) -> Sweep:
    """One constant, replayed at each candidate value against every judged finding.

    ``keeps(j, value)`` answers "would this finding still have been reported". A sweep says nothing
    about findings nobody judged, which is most of them, and that limitation is in the caveats
    rather than smoothed over here.
    """
    total_dismissed = sum(1 for j in judged if not j.confirmed)
    out = Sweep(constant=constant, where=where, current=current,
                stricter_direction=stricter_direction)
    for v in values:
        row = SweepRow(
            value=v,
            confirmed_kept=sum(1 for j in judged if j.confirmed and keeps(j, v)),
            dismissed_kept=sum(1 for j in judged if not j.confirmed and keeps(j, v)),
        )
        row._total_dismissed = total_dismissed
        out.rows.append(row)
    return out


def _recommend(sweep: Sweep, *, confirmed_total: int) -> None:
    """Name the strictest value that costs no confirmed finding, if it beats the current one.

    THE ASYMMETRY IS DELIBERATE AND IS THE WHOLE RULE. A false positive here is a published-looking
    claim that named real people are running an operation together, checked by a person who then has
    to decide it is a newsroom. A false negative is a lead nobody got. So a recommendation may
    never trade away a confirmed finding: the search is over settings that keep ALL of them and
    refuse the most dismissals.
    """
    at_current = next((r for r in sweep.rows if r.value == sweep.current), None)
    if at_current is None:
        return

    viable = [r for r in sweep.rows if r.confirmed_kept == confirmed_total]
    if not viable:
        return
    # Among settings that refuse the SAME number of dismissed findings, take the LEAST strict one.
    # The extra strictness buys nothing on the evidence in hand and costs recall on the findings
    # nobody has judged, which are most of them. Which end is least strict depends on the constant,
    # hence `stricter_direction` rather than a hardcoded sign.
    least_strict = (lambda r: r.value) if sweep.stricter_direction == "raise" else (lambda r: -r.value)
    best = min(viable, key=lambda r: (r.dismissed_kept, least_strict(r)))
    gain = at_current.dismissed_kept - best.dismissed_kept
    if best.value == sweep.current or gain < MIN_NET_IMPROVEMENT:
        return

    sweep.proposed = best.value
    sweep.recommendation = (
        f"{sweep.constant} {sweep.current:g} -> {best.value:g} in {sweep.where}: refuses "
        f"{gain} of the {at_current.dismissed_kept} dismissed findings this setting still reports, "
        f"and keeps all {confirmed_total} confirmed ones. Edit it by hand if you agree."
    )


def _families(judged: list[Judged], rows: list[NetdetectFinding]) -> list[FamilySplit]:
    conf = [r for r in rows if r.status == "confirmed"]
    dism = [r for r in rows if r.status == "dismissed"]

    def stats(group, family):
        vals = [float((r.by_family_json or {}).get(family, 0.0)) for r in group]
        present = sum(1 for v in vals if v > 0)
        mean = (sum(vals) / len(vals)) if vals else 0.0
        return mean, present

    out = []
    for family, weight in sorted(FAMILY_WEIGHT.items(), key=lambda kv: -kv[1]):
        cm, cp = stats(conf, family)
        dm, dp = stats(dism, family)
        out.append(FamilySplit(
            family=family, weight=weight, hard=family in HARD_FAMILIES,
            mean_in_confirmed=round(cm, 3), mean_in_dismissed=round(dm, 3),
            present_in_confirmed=cp, present_in_dismissed=dp,
        ))
    return out


def build_report(session) -> CalibrationReport:
    """Read the reservoir and say what it would move. Writes nothing, anywhere."""
    rows = list(session.execute(select(NetdetectFinding)).scalars())
    judged_rows = [r for r in rows if r.status in ("confirmed", "dismissed")]
    judged = [_reduce(r) for r in judged_rows]

    confirmed = sum(1 for j in judged if j.confirmed)
    dismissed = len(judged) - confirmed
    open_count = sum(1 for r in rows if r.status == "open")

    report = CalibrationReport(
        confirmed=confirmed, dismissed=dismissed, open=open_count,
        sufficient=False, insufficient_reason="",
    )

    axes = _axes()
    report.sweeps = [
        _sweep(judged, constant=a.constant, where=a.where, current=a.current,
               values=list(a.values), keeps=a.keeps, stricter_direction=a.stricter_direction)
        for a in axes
    ]
    report.families = _families(judged, judged_rows)
    report.next_to_judge = _next_to_judge(session, axes)

    # What the reservoir still needs, stated as work rather than as a refusal. The floor is the
    # thing standing between this deployment and a fitted threshold, so an operator should be able
    # to see how far off it is without doing the arithmetic.
    missing_total = max(0, MIN_JUDGEMENTS - len(judged))
    missing_confirmed = max(0, MIN_PER_CLASS - confirmed)
    missing_dismissed = max(0, MIN_PER_CLASS - dismissed)
    if missing_total or missing_confirmed or missing_dismissed:
        parts = []
        if missing_total:
            parts.append(f"{missing_total} more judgement{'s' if missing_total != 1 else ''}")
        if missing_confirmed:
            parts.append(f"{missing_confirmed} more confirmed")
        if missing_dismissed:
            parts.append(f"{missing_dismissed} more dismissed")
        report.still_needed = ", ".join(parts)

    if len(judged) < MIN_JUDGEMENTS:
        report.insufficient_reason = (
            f"{len(judged)} judged findings; {MIN_JUDGEMENTS} are needed before any threshold is "
            f"fitted. Four constants against a dozen labels memorises the last dozen posts somebody "
            f"looked at rather than calibrating anything."
        )
    elif min(confirmed, dismissed) < MIN_PER_CLASS:
        report.insufficient_reason = (
            f"{confirmed} confirmed and {dismissed} dismissed; at least {MIN_PER_CLASS} of each are "
            f"needed. A reservoir of one class can only ever teach the detector to be quieter, or "
            f"louder, and neither is the same as teaching it to be right."
        )
    else:
        report.sufficient = True
        for sweep in report.sweeps:
            _recommend(sweep, confirmed_total=confirmed)
            if sweep.recommendation:
                report.recommendations.append(sweep.recommendation)

    report.caveats = [
        "Nothing here changes a threshold. Every constant lives in code with a reviewer and a "
        "reason beside it, and a gate that retunes itself on operator clicks can be steered by "
        "whoever clicks.",
        "A sweep replays a setting against JUDGED findings only. Findings nobody looked at are not "
        "in these numbers, and a stricter setting also refuses findings that were never reviewed.",
        "The reservoir is whatever an operator chose to open, so it is not a sample of anything. "
        "Precision computed here is precision on that selection, not on the deployment.",
        "A dismissal labels the FINDING, not the accounts. It says this group is not an operation, "
        "not that any member is or is not automated.",
        "`next_to_judge` is NOT a suspicion ranking. It names the findings whose verdict would "
        "change what a threshold is fitted to, which is close to the opposite of the findings most "
        "likely to be operations: a group far above every threshold is the most obviously "
        "coordinated and teaches the least, because nobody needed a label to know how it would be "
        "classified. Judging that list in order is efficient; reading it as strongest-first is "
        "backwards.",
        "A recommendation never trades away a confirmed finding. Calling real people coordinated "
        "when they are not is the expensive error, so the search is only over settings that keep "
        "every confirmed finding and refuse more of the dismissed ones.",
    ]
    return report
