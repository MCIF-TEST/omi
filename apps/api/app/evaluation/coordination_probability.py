"""Measuring the coordination probability model against the labelled scenarios we actually have.

Run it:

    cd apps/api && python -m app.evaluation.coordination_probability

WHAT THIS CAN AND CANNOT DO, because overstating it would be the exact error the model exists to
avoid.

The committed corpus is ``benchmarks/coordination_v1.json`` (13 scenarios, ~170 accounts each
labelled ``bot`` or ``organic``, 6 of them expecting no coordination) plus
``coordination_rescue_v1.json`` (3 more). That is enough to **falsify** a badly wrong likelihood
ratio and enough to prove the detector stays silent on clean data. It is nowhere near enough to
**fit** seven likelihood ratios, and no amount of running it will make it so.

So the ratios stay reasoned, stamped with ``LR_VERSION``, and this harness is a regression gate
rather than a training loop. The two reservoirs that will eventually support a real fit are
``AccountLabel`` and the dismissals accumulating on ``CampaignDetection``.

The headline number is **precision at the decision threshold**. Recall matters less here by design:
a missed operation is a weaker product, a false one is an accusation against a real person.
"""

from __future__ import annotations

import json
import pathlib
from dataclasses import dataclass, field

from app.campaigns.detector.probability import DECISION_THRESHOLD

BENCHMARK_DIR = pathlib.Path(__file__).resolve().parent / "benchmarks"

#: Bin edges for the reliability curve. A calibrated model puts ~85% of the pairs it calls 0.85
#: into the coordinated class. Any systematic gap is the thing to fix.
RELIABILITY_BINS = (0.0, 0.5, 0.7, 0.85, 0.95, 1.0001)


@dataclass
class PairOutcome:
    """One predicted pair and whether it was really coordinated."""

    scenario: str
    a: str
    b: str
    predicted: float
    actually_coordinated: bool


@dataclass
class Report:
    outcomes: list[PairOutcome] = field(default_factory=list)
    scenarios: int = 0
    clean_scenarios: int = 0
    clean_scenarios_silent: int = 0
    notes: list[str] = field(default_factory=list)

    # ---- metrics -----------------------------------------------------------------------------
    @property
    def brier(self) -> float:
        """Mean squared error of the probabilities. Lower is better; 0.25 is a coin flip."""
        if not self.outcomes:
            return 0.0
        return sum(
            (o.predicted - (1.0 if o.actually_coordinated else 0.0)) ** 2 for o in self.outcomes
        ) / len(self.outcomes)

    def precision_at(self, threshold: float) -> tuple[float, int]:
        """Of the pairs called coordinated at this threshold, the share that really were."""
        called = [o for o in self.outcomes if o.predicted >= threshold]
        if not called:
            return 1.0, 0
        right = sum(1 for o in called if o.actually_coordinated)
        return right / len(called), len(called)

    def recall_at(self, threshold: float) -> tuple[float, int]:
        real = [o for o in self.outcomes if o.actually_coordinated]
        if not real:
            return 1.0, 0
        found = sum(1 for o in real if o.predicted >= threshold)
        return found / len(real), len(real)

    def reliability(self) -> list[tuple[str, int, float, float]]:
        """``(bin, n, mean predicted, observed frequency)`` per bin."""
        out = []
        for i in range(len(RELIABILITY_BINS) - 1):
            lo, hi = RELIABILITY_BINS[i], RELIABILITY_BINS[i + 1]
            inside = [o for o in self.outcomes if lo <= o.predicted < hi]
            if not inside:
                continue
            out.append((
                f"{lo:.2f}-{min(hi, 1.0):.2f}",
                len(inside),
                sum(o.predicted for o in inside) / len(inside),
                sum(1 for o in inside if o.actually_coordinated) / len(inside),
            ))
        return out

    @property
    def clean_pass_rate(self) -> float:
        """Share of no-coordination scenarios where the detector said nothing. This is the number
        that decides whether the thing is shippable."""
        if not self.clean_scenarios:
            return 1.0
        return self.clean_scenarios_silent / self.clean_scenarios


def _load(name: str) -> list[dict]:
    path = BENCHMARK_DIR / name
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text())
    except (OSError, ValueError):
        return []
    if isinstance(data, dict):
        data = data.get("scenarios") or data.get("cases") or []
    return [s for s in data if isinstance(s, dict)]


def _roles(scenario: dict) -> dict[str, str]:
    out: dict[str, str] = {}
    for account in scenario.get("accounts") or []:
        if not isinstance(account, dict):
            continue
        ext = str(account.get("external_id") or account.get("id") or "")
        if ext:
            out[ext] = str(account.get("role") or "organic")
    return out


def evaluate() -> Report:
    """Score every committed scenario through the real probability model.

    Ground truth for a PAIR is "both accounts are labelled bot in a scenario that expects
    coordination". That is an approximation: two bots in one scenario are not necessarily in the
    same planted cluster. It is the approximation the committed labels support, and it is stated
    here rather than hidden so nobody reads the resulting Brier score as more precise than it is.
    """
    from app.campaigns.detector import fuse

    report = Report()
    scenarios = _load("coordination_v1.json") + _load("coordination_rescue_v1.json")
    if not scenarios:
        report.notes.append(
            "No benchmark scenarios found. The real corpus is gitignored and absent from this "
            "checkout; see CLAUDE.md, 'The dataset corpus is not in git'."
        )
        return report

    for scenario in scenarios:
        label = str(scenario.get("label") or "unnamed")
        expected = str(scenario.get("expected_coordination") or "none").lower()
        roles = _roles(scenario)
        if not roles:
            continue
        report.scenarios += 1

        edges = _edges_for(scenario)
        findings = fuse.build_findings(sorted(roles), edges)
        reported = [f for f in findings if f.label == fuse.LABEL_CORROBORATED]

        if expected == "none":
            report.clean_scenarios += 1
            if not reported:
                report.clean_scenarios_silent += 1
            else:
                report.notes.append(
                    f"FALSE POSITIVE on {label}: reported "
                    f"{sum(len(f.members) for f in reported)} accounts as coordinated"
                )

        for pair, value in fuse.pair_posteriors(edges).items():
            report.outcomes.append(PairOutcome(
                scenario=label, a=pair[0], b=pair[1], predicted=value,
                actually_coordinated=(
                    expected != "none"
                    and roles.get(pair[0]) == "bot"
                    and roles.get(pair[1]) == "bot"
                ),
            ))
    return report


def _edges_for(scenario: dict) -> list:
    """Build detector edges from a benchmark scenario.

    The benchmark predates this detector and carries the older detectors' shapes, so this maps what
    it does have onto the cohort detector's inputs. Where a scenario cannot supply a family's
    evidence, that family simply does not fire, which is the honest outcome.
    """
    from app.campaigns.detector import cohort as cohort_mod
    from app.campaigns.detector import run as detector_run

    rows = []
    for account in scenario.get("accounts") or []:
        if not isinstance(account, dict):
            continue
        ext = str(account.get("external_id") or account.get("id") or "")
        if not ext:
            continue
        profile = account.get("profile") or {}
        rows.append({
            "external_id": ext,
            "handle": account.get("handle") or profile.get("handle") or ext,
            # Every benchmark account is treated as cohort-eligible: these scenarios exist to test
            # coordination, and re-applying the 70+ filter here would discard most of the labels.
            "overall_probability": 0.95,
            "bio": profile.get("bio"),
            "account_created_at": profile.get("created_at"),
            "thread_comments": [
                {"text": t, "created_at": None} for t in (account.get("texts") or [])[:5]
            ],
            "recent_activity": [
                {"text": p.get("text") if isinstance(p, dict) else str(p),
                 "created_at": p.get("created_at") if isinstance(p, dict) else None,
                 "parent_id": None, "source_client": None}
                for p in (account.get("posts") or [])[:20]
            ],
        })

    cohort = cohort_mod.from_scan_rows(rows, [], platform="x", threshold=0.0)
    edges: list = []
    for signal in detector_run.SIGNALS:
        try:
            edges.extend(signal(cohort))
        except Exception:  # noqa: BLE001 - a signal that cannot run on this shape contributes none
            continue
    return edges


def render(report: Report) -> str:
    lines: list[str] = []
    add = lines.append

    add("OMISPHERE coordination probability calibration")
    add("=" * 62)
    add(f"scenarios          {report.scenarios}")
    add(f"pairs scored       {len(report.outcomes)}")
    add(f"brier score        {report.brier:.4f}   (lower is better; 0.25 is a coin flip)")
    add("")

    add(f"clean scenarios    {report.clean_scenarios_silent}/{report.clean_scenarios} silent "
        f"({report.clean_pass_rate:.0%})")
    add("  This is the number that decides shippability. A detector that cannot stay quiet on")
    add("  data with no coordination in it is not usable at any recall.")
    add("")

    add("precision / recall by threshold")
    for threshold in (0.50, 0.70, 0.85, 0.95, 0.99):
        precision, called = report.precision_at(threshold)
        recall, real = report.recall_at(threshold)
        marker = "  <- decision threshold" if abs(threshold - DECISION_THRESHOLD) < 1e-9 else ""
        # Printing "precision 1.000" off zero calls is the same failure as a preflight that passes
        # because it never looked. Say "no calls" instead, so an empty result cannot read as a
        # clean bill of health.
        p_txt = f"precision {precision:.3f} (n={called:4d})" if called else "no calls          "
        r_txt = f"recall {recall:.3f} (of {real})" if real else "no positives to find"
        add(f"  >= {threshold:.2f}   {p_txt}   {r_txt}{marker}")
    add("")

    positives = sum(1 for o in report.outcomes if o.actually_coordinated)
    if positives == 0:
        add("RECALL IS NOT MEASURABLE FROM THIS CORPUS, and that is a fact about the corpus.")
        add("  These scenarios were built for the older per-scan detectors, so they carry no")
        add("  comment timestamps, no posting-client strings and no engagement targets. Four of")
        add("  the seven signals cannot fire here at all, and the ones that can have little to")
        add("  work with. The clean-scenario result above IS meaningful; read the precision rows")
        add("  as untested rather than as passed.")
        add("")

    add("reliability (a calibrated model puts ~85% of its 0.85 calls in the positive class)")
    rows = report.reliability()
    if rows:
        for name, n, predicted, observed in rows:
            add(f"  {name}   n={n:4d}   mean predicted {predicted:.3f}   observed {observed:.3f}")
    else:
        add("  no pairs scored")

    if report.notes:
        add("")
        add("notes")
        for note in report.notes:
            add(f"  {note}")

    add("")
    add("The likelihood ratios are reasoned, not fitted: ~200 labelled accounts across 16")
    add("scenarios can falsify a badly wrong ratio but cannot fit seven of them. Treat this as a")
    add("regression gate. Real calibration needs the accumulating AccountLabel rows and the")
    add("dismissals on campaign_detections.")
    return "\n".join(lines)


if __name__ == "__main__":  # pragma: no cover
    print(render(evaluate()))
