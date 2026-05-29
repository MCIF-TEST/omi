"""Calibration CLI for the omi detection engine.

Thin wrapper over :mod:`app.evaluation` — the metric computation lives in
the package (so the pytest accuracy gate, the admin scoreboard endpoint, and
this CLI all share one implementation and can never disagree). This script
adds the operator conveniences: pretty terminal output, the ``--from-db``
path that scores real labeled accounts against their persisted scans, and the
``--check`` regression guard for CI.

Usage:

    cd apps/api
    python -m scripts.calibrate                          # seed benchmark
    python -m scripts.calibrate --fixture path/to.json   # custom benchmark
    python -m scripts.calibrate --from-db                # real labeled accounts
    python -m scripts.calibrate --json                   # machine-readable
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

# Allow `python -m scripts.calibrate` when run from apps/api/
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.evaluation import (  # noqa: E402
    DEFAULT_BENCHMARK,
    EvalRow,
    compute_report,
    evaluate,
    expected_prob,
    load_benchmark,
)


def _rows_from_db(min_confidence: str) -> list[EvalRow]:
    """Build eval rows from labeled accounts' most recent persisted scans.

    No detectors re-run and no YouTube quota is spent — this measures how the
    engine *was* calibrated at scan time. Per-detector influence comes from the
    stored signals_json. Use the fixture path to re-evaluate live.
    """
    from sqlalchemy import select
    from app.storage.db import get_session
    from app.storage.models import Account, AccountLabel, Scan

    filt = []
    if min_confidence == "high":
        filt.append(AccountLabel.confidence == "high")

    rows: list[EvalRow] = []
    with get_session() as session:
        labeled = session.execute(
            select(AccountLabel, Account).join(
                Account, AccountLabel.account_id == Account.id
            ).where(*filt)
        ).all()
        for label_row, account in labeled:
            scan = session.execute(
                select(Scan).where(Scan.account_id == account.id)
                .order_by(Scan.scanned_at.desc()).limit(1)
            ).scalar_one_or_none()
            if scan is None:
                continue
            rows.append(EvalRow(
                label=f"{label_row.label}/{label_row.source}",
                expected_tier=label_row.expected_tier,
                expected_p=expected_prob(label_row.expected_tier, None),
                predicted_tier=scan.tier,
                predicted_p=scan.overall_probability,
                confidence=scan.confidence,
                signals=scan.signals_json or [],
                weak_signals=[],
            ))
    return rows


def main() -> int:
    ap = argparse.ArgumentParser(description="Calibrate the omi detection engine.")
    ap.add_argument("--fixture", type=Path, default=DEFAULT_BENCHMARK)
    ap.add_argument("--json", action="store_true", help="Emit machine-readable JSON only.")
    ap.add_argument(
        "--check", metavar="BASELINE.json", type=Path,
        help="Compare against a saved baseline; exit non-zero if Brier worsens "
             ">0.01 or tier accuracy / macro-F1 drop >0.02. Wire into CI.",
    )
    ap.add_argument(
        "--from-db", action="store_true",
        help="Score labeled accounts (AccountLabel) against their persisted "
             "scans instead of the JSON benchmark. No YouTube quota.",
    )
    ap.add_argument("--min-confidence", choices=("high", "medium"), default="medium")
    args = ap.parse_args()

    if args.from_db:
        rows = _rows_from_db(args.min_confidence)
        if not rows:
            print("No labeled accounts with a persisted Scan row found. "
                  "Label a few from the dashboard and re-run.", file=sys.stderr)
            return 1
        report = compute_report(rows)
    else:
        cases = load_benchmark(args.fixture)
        if not cases:
            print("No cases in benchmark.", file=sys.stderr)
            return 1
        report = evaluate(cases)

    n = report["n_cases"]
    brier = report["brier_score"]
    accuracy = report["tier_accuracy"]
    macro_f1 = report["macro_f1"]
    per_tier = report["per_tier"]
    detector_influence = report["per_detector_influence"]
    suggestions = report["weight_suggestions"]
    results = report["per_case"]

    # Regression check against a saved baseline — for CI integration.
    if args.check:
        try:
            baseline = json.loads(args.check.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"Failed to read baseline {args.check}: {e}", file=sys.stderr)
            return 2
        regressions: list[str] = []
        if brier > baseline.get("brier_score", 1.0) + 0.01:
            regressions.append(f"Brier worsened: {baseline['brier_score']:.4f} -> {brier:.4f}")
        if accuracy < baseline.get("tier_accuracy", 0.0) - 0.02:
            regressions.append(f"Tier accuracy dropped: {baseline['tier_accuracy']:.3f} -> {accuracy:.3f}")
        if macro_f1 < baseline.get("macro_f1", 0.0) - 0.02:
            regressions.append(f"Macro-F1 dropped: {baseline['macro_f1']:.3f} -> {macro_f1:.3f}")
        if regressions:
            print("CALIBRATION REGRESSION DETECTED:", file=sys.stderr)
            for r in regressions:
                print(f"  - {r}", file=sys.stderr)
            return 1
        print(f"OK - brier {brier:.4f} acc {accuracy:.1%} macro-F1 {macro_f1:.3f}", file=sys.stderr)

    if args.json:
        print(json.dumps(report, indent=2))
        return 0

    # Pretty print
    print("=" * 72)
    print(f" OMI CALIBRATION REPORT - {n} cases")
    print("=" * 72)
    print()
    print(f"  Brier score:       {brier:.4f}   (lower is better; 0 = perfect)")
    print(f"  Tier accuracy:     {accuracy:.1%}   (majority-class baseline: {report['majority_class_rate']:.1%})")
    print(f"  Macro-F1:          {macro_f1:.3f}   (average F1 across 4 tiers)")
    print()
    print("  Per-tier precision / recall / F1:")
    for tier_name in ("low", "moderate", "elevated", "high"):
        m = per_tier[tier_name]
        if m["support"] == 0:
            print(f"    {tier_name:<10}  (no cases)")
            continue
        print(f"    {tier_name:<10}  P={m['precision']:.2f}  R={m['recall']:.2f}  "
              f"F1={m['f1']:.2f}  (n={m['support']})")
    print()
    print("  Per-detector influence (avg |p-0.5| x confidence):")
    for name, lvl in sorted(detector_influence.items(), key=lambda kv: -kv[1]):
        bar = "#" * int(lvl * 40)
        print(f"    {name:<14} {lvl:.3f}  {bar}")
    print()
    print("  Tier confusion (expected -> predicted):")
    for k, c in sorted(report["tier_confusion"].items()):
        e, p = k.split("->")
        flag = " " if e == p else "x"
        print(f"    {flag} {e:>10} -> {p:<10} x{c}")
    print()
    if suggestions:
        print("  Suggestions:")
        for s in suggestions:
            print(f"    - {s}")
    else:
        print("  No strong tuning suggestions - calibration looks balanced.")
    print()
    print("  Per-case detail:")
    for r in results:
        weak = f" ({len(r['weak_signals'])} weak)" if r["weak_signals"] else ""
        flag = " " if r["expected_tier"] == r["predicted_tier"] else "x"
        print(f"  {flag} {r['label'][:28]:<28} {r['expected_tier']:<10} "
              f"{r['predicted_tier']:<10} {r['abs_error']:>6}{weak}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
