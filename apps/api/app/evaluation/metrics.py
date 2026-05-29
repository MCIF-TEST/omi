"""Pure metric functions for evaluating the detection engine.

Extracted so the *same* computation backs three callers:

* the pytest accuracy gate (``tests/test_evaluation_benchmark.py``),
* the admin scoreboard endpoint (``GET /v1/intelligence/benchmark``),
* the calibration CLI (``scripts/calibrate.py``).

A "row" is the unit of evaluation: one labeled subject plus what the engine
predicted for it. Both the benchmark runner (which calls the engine live) and
the ``--from-db`` calibration path (which reads persisted scans) produce rows
of the same shape, so they share one metric implementation and can never
silently disagree.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Any

TIERS: tuple[str, ...] = ("low", "moderate", "elevated", "high")

# Representative probability at the centre of each tier band. Used as the
# regression target when a case declares only a tier (not an exact target
# probability) — lets Brier score work uniformly across both.
TIER_MIDPOINT: dict[str, float] = {
    "low": 0.12,
    "moderate": 0.37,
    "elevated": 0.62,
    "high": 0.87,
}


@dataclass
class EvalRow:
    """One labeled subject and the engine's prediction for it."""

    label: str
    expected_tier: str
    expected_p: float
    predicted_tier: str
    predicted_p: float
    confidence: float
    # [{"name", "probability", "confidence"}, ...]
    signals: list[dict[str, Any]] = field(default_factory=list)
    weak_signals: list[str] = field(default_factory=list)


def expected_prob(expected_tier: str, expected_probability: float | None) -> float:
    """Target probability for a case: explicit value, else the tier midpoint."""
    if expected_probability is not None:
        return float(expected_probability)
    return TIER_MIDPOINT.get(expected_tier, 0.12)


def per_tier_metrics(expected: list[str], predicted: list[str]) -> dict[str, dict[str, float]]:
    """Per-tier precision / recall / F1, one-vs-rest.

    Surfaces facts the global Brier hides — e.g. "fine at flagging HIGH but
    misses MODERATE entirely".
    """
    out: dict[str, dict[str, float]] = {}
    for t in TIERS:
        tp = sum(1 for e, p in zip(expected, predicted) if e == t and p == t)
        fp = sum(1 for e, p in zip(expected, predicted) if e != t and p == t)
        fn = sum(1 for e, p in zip(expected, predicted) if e == t and p != t)
        precision = tp / (tp + fp) if (tp + fp) else 0.0
        recall = tp / (tp + fn) if (tp + fn) else 0.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
        out[t] = {
            "precision": round(precision, 3),
            "recall": round(recall, 3),
            "f1": round(f1, 3),
            "support": sum(1 for e in expected if e == t),
        }
    return out


def majority_class_rate(expected: list[str]) -> float:
    """Accuracy a trivial 'always predict the most common tier' baseline gets.

    The engine must beat this to be worth anything; the gate asserts it does.
    """
    if not expected:
        return 0.0
    return Counter(expected).most_common(1)[0][1] / len(expected)


def compute_report(rows: list[EvalRow]) -> dict[str, Any]:
    """Aggregate per-row predictions into the full scoreboard report."""
    n = len(rows)
    if n == 0:
        return {"n_cases": 0}

    brier_terms: list[float] = []
    tier_correct = 0
    tier_confusion: Counter[tuple[str, str]] = Counter()
    signal_contributions: dict[str, list[float]] = defaultdict(list)
    per_case: list[dict[str, Any]] = []

    for r in rows:
        brier_terms.append((r.predicted_p - r.expected_p) ** 2)
        if r.predicted_tier == r.expected_tier:
            tier_correct += 1
        tier_confusion[(r.expected_tier, r.predicted_tier)] += 1
        for s in r.signals:
            if not isinstance(s, dict):
                continue
            signal_contributions[s.get("name", "?")].append(
                abs(s.get("probability", 0.5) - 0.5) * s.get("confidence", 0.0)
            )
        per_case.append({
            "label": r.label,
            "expected_tier": r.expected_tier,
            "expected_p": round(r.expected_p, 3),
            "predicted_tier": r.predicted_tier,
            "predicted_p": round(r.predicted_p, 3),
            "confidence": round(r.confidence, 3),
            "abs_error": round(abs(r.predicted_p - r.expected_p), 3),
            "weak_signals": list(r.weak_signals or []),
        })

    brier = sum(brier_terms) / n
    accuracy = tier_correct / n

    detector_influence = {
        name: round(sum(vals) / max(1, len(vals)), 4)
        for name, vals in signal_contributions.items()
    }

    # Heuristic tuning hints: a detector far below the mean influence is
    # under-exercised or under-weighted; far above may be overfit.
    avg = sum(detector_influence.values()) / max(1, len(detector_influence))
    suggestions: list[str] = []
    for name, lvl in detector_influence.items():
        if lvl < 0.5 * avg:
            suggestions.append(
                f"{name}: very low influence ({lvl:.3f}) — fixture may not exercise it, or weight could be raised."
            )
        elif lvl > 2.0 * avg:
            suggestions.append(
                f"{name}: very high influence ({lvl:.3f}) — check for overfit or label leakage."
            )

    expected_tiers = [r.expected_tier for r in rows]
    predicted_tiers = [r.predicted_tier for r in rows]
    per_tier = per_tier_metrics(expected_tiers, predicted_tiers)
    macro_f1 = sum(m["f1"] for m in per_tier.values()) / len(per_tier) if per_tier else 0.0

    return {
        "n_cases": n,
        "brier_score": round(brier, 4),
        "tier_accuracy": round(accuracy, 3),
        "macro_f1": round(macro_f1, 3),
        "majority_class_rate": round(majority_class_rate(expected_tiers), 3),
        "per_tier": per_tier,
        "per_detector_influence": detector_influence,
        "tier_confusion": {f"{e}->{p}": c for (e, p), c in sorted(tier_confusion.items())},
        "weight_suggestions": suggestions,
        "per_case": per_case,
    }
