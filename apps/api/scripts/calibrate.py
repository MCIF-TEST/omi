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


def main() -> int:
    ap = argparse.ArgumentParser(description="Calibrate the omi detection engine.")
    default_fixture = Path(__file__).parent / "fixtures" / "calibration.json"
    ap.add_argument("--fixture", type=Path, default=default_fixture)
    ap.add_argument("--json", action="store_true", help="Emit machine-readable JSON only.")
    args = ap.parse_args()

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
        profile = _parse_profile(case["profile"])
        posts = [_parse_post(p) for p in case.get("posts", [])]
        scan = analyze_account(profile, posts)

        expected_p = _expected_prob(case)
        expected_tier = case.get("expected_tier", "low")
        err = (scan.overall_probability - expected_p) ** 2
        brier_terms.append(err)
        if scan.tier.value == expected_tier:
            tier_correct += 1
        tier_confusion[(expected_tier, scan.tier.value)] += 1

        for s in scan.signals:
            signal_contributions[s.name].append(abs(s.probability - 0.5) * s.confidence)

        results.append({
            "label": case.get("label", "?"),
            "expected_tier": expected_tier,
            "expected_p": round(expected_p, 3),
            "predicted_tier": scan.tier.value,
            "predicted_p": round(scan.overall_probability, 3),
            "confidence": round(scan.confidence, 3),
            "abs_error": round(abs(scan.overall_probability - expected_p), 3),
            "weak_signals": list(scan.weak_signals or []),
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

    report = {
        "n_cases": n,
        "brier_score": round(brier, 4),
        "tier_accuracy": round(accuracy, 3),
        "per_detector_influence": detector_influence,
        "tier_confusion": {f"{e}→{p}": c for (e, p), c in sorted(tier_confusion.items())},
        "weight_suggestions": suggestions,
        "per_case": results,
    }

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
