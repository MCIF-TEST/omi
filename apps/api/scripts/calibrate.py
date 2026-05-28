"""Calibration harness for the omi detection engine.

Runs the engine over a labeled fixture set and reports:

* Brier score (lower is better; 0 = perfect calibration)
* Per-tier accuracy (how often we put accounts in the right bucket)
* A per-detector influence breakdown
* Suggested weight adjustments (heuristic — not auto-applied)

Usage:

    cd apps/api
    python -m scripts.calibrate                          # uses bundled fixture
    python -m scripts.calibrate --fixture path/to.json   # custom fixture

Fixture format (JSON list):

    [
      {
        "label": "ai_content_high",       # human readable category
        "expected_tier": "high",          # "low" | "moderate" | "elevated" | "high"
        "expected_probability": 0.85,     # target probability (optional)
        "profile": {                      # Profile schema
          "platform": "youtube",
          "handle": "...",
          ...
        },
        "posts": [                        # list of Post-shaped dicts
          {"id": "...", "author_handle": "...", "text": "...", "created_at": "ISO..."},
          ...
        ]
      },
      ...
    ]
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

# Allow `python -m scripts.calibrate` when run from apps/api/
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.detection.engine import analyze_account  # noqa: E402
from app.schemas import Post, Profile, Tier  # noqa: E402


_TIER_MIDPOINT = {Tier.LOW: 0.12, Tier.MODERATE: 0.37, Tier.ELEVATED: 0.62, Tier.HIGH: 0.87}


def _load_fixture(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError("Fixture must be a JSON array.")
    return data


def _parse_post(d: dict[str, Any]) -> Post:
    # Tolerate ISO strings for created_at
    if isinstance(d.get("created_at"), str):
        d = {**d, "created_at": datetime.fromisoformat(d["created_at"].replace("Z", "+00:00"))}
    return Post(**d)


def _parse_profile(d: dict[str, Any]) -> Profile:
    if isinstance(d.get("created_at"), str):
        d = {**d, "created_at": datetime.fromisoformat(d["created_at"].replace("Z", "+00:00"))}
    return Profile(**d)


def _expected_prob(case: dict[str, Any]) -> float:
    if "expected_probability" in case and case["expected_probability"] is not None:
        return float(case["expected_probability"])
    tier = Tier(case.get("expected_tier", "low"))
    return _TIER_MIDPOINT[tier]


def _load_cases_from_db(min_confidence: str) -> list[dict[str, Any]]:
    """Hydrate a calibration fixture from labelled accounts in the DB.

    Strategy: for each labelled account we have a persisted Scan row from
    a previous /v1/scan/* call. The Scan row carries the resulting tier
    + probability — i.e. what the engine *did* return for this account.
    We use that as the prediction and the AccountLabel.expected_tier as
    the target.

    Note: we don't re-run the detectors. The point of --from-db is to
    measure how the engine *was* calibrated at the time of each scan, not
    to re-evaluate every account. Detector-by-detector influence stats are
    therefore empty in this mode.
    """
    from sqlalchemy import select
    from app.storage.db import get_session
    from app.storage.models import Account, AccountLabel, Scan

    out: list[dict[str, Any]] = []
    filt = []
    if min_confidence == "high":
        filt.append(AccountLabel.confidence == "high")

    with get_session() as session:
        rows = session.execute(
            select(AccountLabel, Account).join(
                Account, AccountLabel.account_id == Account.id
            ).where(*filt)
        ).all()
        for label_row, account in rows:
            scan = session.execute(
                select(Scan).where(Scan.account_id == account.id)
                .order_by(Scan.scanned_at.desc())
                .limit(1)
            ).scalar_one_or_none()
            if scan is None:
                continue
            # We hand back a case shape that includes a `_db_prediction`
            # block so main() can short-circuit the detector pipeline and
            # use the stored result directly.
            out.append({
                "label": f"{label_row.label}/{label_row.source}",
                "expected_tier": label_row.expected_tier,
                "expected_probability": None,
                "profile": {
                    "platform": account.platform,
                    "handle": account.handle,
                    "display_name": account.display_name,
                    "bio": account.bio,
                    "follower_count": account.follower_count,
                    "following_count": account.following_count,
                    "created_at": account.account_created_at.isoformat()
                    if account.account_created_at else None,
                },
                "posts": [],
                "_db_prediction": {
                    "tier": scan.tier,
                    "probability": scan.overall_probability,
                    "confidence": scan.confidence,
                    "signals": scan.signals_json or [],
                },
            })
    return out


def _per_tier_metrics(
    expected: list[str], predicted: list[str]
) -> dict[str, dict[str, float]]:
    """Per-tier precision / recall / F1, classic micro-style.

    We treat each tier as a separate one-vs-rest classification. This lets
    us see, for example, "the engine is fine at flagging HIGH but tends to
    miss MODERATE" — a fact the global Brier score hides.
    """
    tiers = ("low", "moderate", "elevated", "high")
    out: dict[str, dict[str, float]] = {}
    for t in tiers:
        tp = sum(1 for e, p in zip(expected, predicted) if e == t and p == t)
        fp = sum(1 for e, p in zip(expected, predicted) if e != t and p == t)
        fn = sum(1 for e, p in zip(expected, predicted) if e == t and p != t)
        precision = tp / (tp + fp) if (tp + fp) else 0.0
        recall = tp / (tp + fn) if (tp + fn) else 0.0
        f1 = (
            2 * precision * recall / (precision + recall)
            if (precision + recall) else 0.0
        )
        support = sum(1 for e in expected if e == t)
        out[t] = {
            "precision": round(precision, 3),
            "recall": round(recall, 3),
            "f1": round(f1, 3),
            "support": support,
        }
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Calibrate the omi detection engine.")
    default_fixture = Path(__file__).parent / "fixtures" / "calibration.json"
    ap.add_argument("--fixture", type=Path, default=default_fixture)
    ap.add_argument("--json", action="store_true", help="Emit machine-readable JSON only.")
    ap.add_argument(
        "--check",
        metavar="BASELINE.json",
        type=Path,
        help=(
            "Compare this run against a previously-saved baseline (also in "
            "--json format). Exits non-zero if Brier worsens by >0.01 or "
            "tier accuracy drops by >0.02 — wire this into CI to catch "
            "calibration regressions when detector weights change."
        ),
    )
    ap.add_argument(
        "--from-db",
        action="store_true",
        help=(
            "Load cases from the local AccountLabel table instead of the JSON "
            "fixture. Uses the production DB (OMI_DATABASE_URL); evaluates "
            "labelled accounts against their most recent persisted Scan row "
            "so no extra YouTube quota is consumed."
        ),
    )
    ap.add_argument(
        "--min-confidence",
        choices=("high", "medium"),
        default="medium",
        help="With --from-db, restrict to labels of at least this confidence.",
    )
    args = ap.parse_args()

    if args.from_db:
        cases = _load_cases_from_db(args.min_confidence)
        if not cases:
            print(
                "No labeled accounts with a persisted Scan row found. "
                "Label a few from the dashboard and re-run.",
                file=sys.stderr,
            )
            return 1
    else:
        cases = _load_fixture(args.fixture)
        if not cases:
            print("No cases in fixture.", file=sys.stderr)
            return 1

    results: list[dict[str, Any]] = []
    signal_contributions: dict[str, list[float]] = defaultdict(list)
    brier_terms: list[float] = []
    tier_correct = 0
    tier_confusion: dict[tuple[str, str], int] = Counter()

    for case in cases:
        expected_p = _expected_prob(case)
        expected_tier = case.get("expected_tier", "low")

        # --- DB-backed cases: use the persisted scan result directly ---
        db_pred = case.get("_db_prediction")
        if db_pred:
            predicted_tier = db_pred["tier"]
            predicted_p = db_pred["probability"]
            predicted_conf = db_pred["confidence"]
            stored_signals = db_pred.get("signals") or []
            for s in stored_signals:
                if not isinstance(s, dict):
                    continue
                signal_contributions[s.get("name", "?")].append(
                    abs((s.get("probability", 0.5)) - 0.5) * (s.get("confidence", 0.0))
                )
            weak = []
        else:
            # --- Fixture cases: re-run the detector pipeline ---
            profile = _parse_profile(case["profile"])
            posts = [_parse_post(p) for p in case.get("posts", [])]
            scan_res = analyze_account(profile, posts)
            predicted_tier = scan_res.tier.value
            predicted_p = scan_res.overall_probability
            predicted_conf = scan_res.confidence
            for s in scan_res.signals:
                signal_contributions[s.name].append(
                    abs(s.probability - 0.5) * s.confidence
                )
            weak = list(scan_res.weak_signals or [])

        err = (predicted_p - expected_p) ** 2
        brier_terms.append(err)
        if predicted_tier == expected_tier:
            tier_correct += 1
        tier_confusion[(expected_tier, predicted_tier)] += 1

        results.append({
            "label": case.get("label", "?"),
            "expected_tier": expected_tier,
            "expected_p": round(expected_p, 3),
            "predicted_tier": predicted_tier,
            "predicted_p": round(predicted_p, 3),
            "confidence": round(predicted_conf, 3),
            "abs_error": round(abs(predicted_p - expected_p), 3),
            "weak_signals": weak,
        })

    n = len(results)
    brier = sum(brier_terms) / n
    accuracy = tier_correct / n

    # Per-detector "average influence" (lever = how strongly that detector
    # moved its sub-probability away from 0.5, weighted by its confidence).
    detector_influence = {
        name: round(sum(vals) / max(1, len(vals)), 4)
        for name, vals in signal_contributions.items()
    }

    # Heuristic suggestions: if a detector's average influence is way below
    # the mean, its weight could probably be raised; if it's way above,
    # consider whether it's overfitting.
    avg = sum(detector_influence.values()) / max(1, len(detector_influence))
    suggestions: list[str] = []
    for name, lvl in detector_influence.items():
        if lvl < 0.5 * avg:
            suggestions.append(f"{name}: very low influence ({lvl:.3f}) — fixture may not exercise it, or weight could be raised.")
        elif lvl > 2.0 * avg:
            suggestions.append(f"{name}: very high influence ({lvl:.3f}) — check for overfit or label leakage.")

    expected_tiers = [r["expected_tier"] for r in results]
    predicted_tiers = [r["predicted_tier"] for r in results]
    per_tier = _per_tier_metrics(expected_tiers, predicted_tiers)
    macro_f1 = (
        sum(m["f1"] for m in per_tier.values()) / len(per_tier)
        if per_tier else 0.0
    )

    report = {
        "n_cases": n,
        "brier_score": round(brier, 4),
        "tier_accuracy": round(accuracy, 3),
        "macro_f1": round(macro_f1, 3),
        "per_tier": per_tier,
        "per_detector_influence": detector_influence,
        "tier_confusion": {f"{e}→{p}": c for (e, p), c in sorted(tier_confusion.items())},
        "weight_suggestions": suggestions,
        "per_case": results,
    }

    # Regression check against a saved baseline — for CI integration.
    if args.check:
        try:
            baseline = json.loads(args.check.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"Failed to read baseline {args.check}: {e}", file=sys.stderr)
            return 2
        regressions: list[str] = []
        if report["brier_score"] > baseline.get("brier_score", 1.0) + 0.01:
            regressions.append(
                f"Brier worsened: {baseline['brier_score']:.4f} → {report['brier_score']:.4f}"
            )
        if report["tier_accuracy"] < baseline.get("tier_accuracy", 0.0) - 0.02:
            regressions.append(
                f"Tier accuracy dropped: {baseline['tier_accuracy']:.3f} → {report['tier_accuracy']:.3f}"
            )
        if report["macro_f1"] < baseline.get("macro_f1", 0.0) - 0.02:
            regressions.append(
                f"Macro-F1 dropped: {baseline['macro_f1']:.3f} → {report['macro_f1']:.3f}"
            )
        if regressions:
            print("CALIBRATION REGRESSION DETECTED:", file=sys.stderr)
            for r in regressions:
                print(f"  · {r}", file=sys.stderr)
            return 1
        print(
            f"OK · brier {report['brier_score']:.4f} "
            f"acc {report['tier_accuracy']:.1%} "
            f"macro-F1 {report['macro_f1']:.3f}",
            file=sys.stderr,
        )

    if args.json:
        print(json.dumps(report, indent=2))
        return 0

    # Pretty print
    print("=" * 72)
    print(f" OMI CALIBRATION REPORT — {n} cases")
    print("=" * 72)
    print()
    print(f"  Brier score:       {brier:.4f}   (lower is better; 0 = perfect)")
    print(f"  Tier accuracy:     {accuracy:.1%}   ({tier_correct}/{n})")
    print(f"  Macro-F1:          {macro_f1:.3f}   (average F1 across 4 tiers)")
    print()
    print("  Per-tier precision / recall / F1:")
    for tier_name in ("low", "moderate", "elevated", "high"):
        m = per_tier[tier_name]
        if m["support"] == 0:
            print(f"    {tier_name:<10}  (no cases)")
            continue
        print(
            f"    {tier_name:<10}  P={m['precision']:.2f}  "
            f"R={m['recall']:.2f}  F1={m['f1']:.2f}  "
            f"(n={m['support']})"
        )
    print()
    print("  Per-detector influence (avg |p-0.5| × confidence):")
    for name, lvl in sorted(detector_influence.items(), key=lambda kv: -kv[1]):
        bar = "█" * int(lvl * 40)
        print(f"    {name:<14} {lvl:.3f}  {bar}")
    print()
    print("  Tier confusion (expected → predicted):")
    for k, c in sorted(tier_confusion.items()):
        flag = " " if k[0] == k[1] else "✗"
        print(f"    {flag} {k[0]:>10} → {k[1]:<10} ×{c}")
    print()
    if suggestions:
        print("  Suggestions:")
        for s in suggestions:
            print(f"    · {s}")
    else:
        print("  No strong tuning suggestions — calibration looks balanced.")
    print()
    print("  Per-case detail:")
    print(f"    {'label':<28} {'exp':<10} {'got':<10} {'err':>6}  weak")
    for r in results:
        weak = f" ({len(r['weak_signals'])} weak)" if r['weak_signals'] else ""
        flag = " " if r['expected_tier'] == r['predicted_tier'] else "✗"
        print(f"  {flag} {r['label'][:28]:<28} {r['expected_tier']:<10} "
              f"{r['predicted_tier']:<10} {r['abs_error']:>6}{weak}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
