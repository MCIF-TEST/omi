"""Accuracy gate for the detection engine.

This is the test that makes "is the engine any good?" a tracked number CI
enforces, rather than an assumption. It runs the live engine over the seed
benchmark and asserts:

* backend-independent invariants that must always hold (engine beats the
  trivial majority-class baseline; ranks bot archetypes above human ones),
* calibration floors/ceilings that lock in the CURRENT measured accuracy so
  any regression fails the build.

The floors below are deliberately set to current measured values (with a
small margin). They are a RATCHET: when calibration improves the numbers,
tighten them so the new accuracy can't silently regress. They are NOT a
statement that current accuracy is good — see the per-tier recall, which is
poor today and is exactly what this harness exists to drive up.

Runs against the hashing-embedder fallback (sentence-transformers is an
optional extra), which is deterministic and matches CI.
"""

from __future__ import annotations

import pytest

from app.evaluation import (
    EvalRow,
    compute_report,
    evaluate,
    load_benchmark,
    majority_class_rate,
)

# --- Calibration ratchet (tighten as the engine improves) ------------------
# GAP-03 demoted ai_writing to a supplemental (non-scoring) signal, which removed
# its harmful false positives but also unmasked an elevated/high recall gap
# (macro-F1 had fallen to 0.182). The GAP-03 *remaining-risk* pass then rebuilt
# that recall the RIGHT way — through legitimate behavioral detection rather than
# stylometric AI tells:
#   • engagement detector overhaul — disjunctive (noisy-OR) combination over
#     correlation-grouped axes so a single blatant spam behavior (100% links,
#     emoji-bombing, follow-bait, self-promo, crypto-shill) actually registers
#     instead of being averaged away; strength-aware confidence so unambiguous
#     spam on a handful of posts is a confident call; link-precision so
#     journalists/researchers citing sources are NOT flagged.
#   • semantic detector — a 3-gram template-skeleton supplement + strength-aware
#     confidence so fill-in-the-blank template spam is detected even on the
#     fallback embedder.
# Net effect on the seed benchmark: Brier 0.1107 → 0.0588, tier accuracy
# 0.415 → 0.646, macro-F1 0.182 → 0.583 — with ZERO new false positives on the
# clean/ESL/edge archetypes. The residual misses are temporal/profile/
# coordination archetypes owned by the confidence-calibration / community-anchor
# gaps, not by content-style detection.
GATE_MAX_BRIER = 0.070      # current 0.0588
GATE_MIN_ACCURACY = 0.60    # current 0.646; majority baseline 0.338
GATE_MIN_MACRO_F1 = 0.52    # current 0.583


@pytest.fixture(scope="module")
def report() -> dict:
    """Evaluate the seed benchmark once for the whole module."""
    return evaluate(load_benchmark())


def test_seed_benchmark_is_well_formed():
    cases = load_benchmark()
    assert len(cases) >= 50, "seed benchmark should be a meaningful size"
    tiers = {c.expected_tier for c in cases}
    assert tiers == {"low", "moderate", "elevated", "high"}, "all tiers represented"


def test_compute_report_math():
    """The pure metric layer computes Brier/accuracy correctly."""
    rows = [
        EvalRow("a", "high", 0.9, "high", 0.8, 0.7),   # err 0.01, tier correct
        EvalRow("b", "low", 0.1, "low", 0.2, 0.5),     # err 0.01, tier correct
        EvalRow("c", "high", 0.9, "low", 0.1, 0.5),    # err 0.64, tier wrong
    ]
    r = compute_report(rows)
    assert r["n_cases"] == 3
    assert r["tier_accuracy"] == round(2 / 3, 3)
    assert r["brier_score"] == round((0.01 + 0.01 + 0.64) / 3, 4)
    assert r["majority_class_rate"] == round(2 / 3, 3)  # two of three are "high"


def test_engine_beats_majority_baseline(report):
    """An engine that loses to 'always guess the most common tier' is useless."""
    assert report["tier_accuracy"] > report["majority_class_rate"], (
        f"engine accuracy {report['tier_accuracy']} must beat majority-class "
        f"baseline {report['majority_class_rate']}"
    )


def test_engine_ranks_suspicious_above_clean(report):
    """Backend-independent: expected-HIGH cases must, on average, score well
    above expected-LOW cases. Ordering is the floor of any useful detector."""
    by_tier: dict[str, list[float]] = {}
    for c in report["per_case"]:
        by_tier.setdefault(c["expected_tier"], []).append(c["predicted_p"])
    mean_high = sum(by_tier["high"]) / len(by_tier["high"])
    mean_low = sum(by_tier["low"]) / len(by_tier["low"])
    assert mean_high > mean_low + 0.15, (
        f"HIGH archetypes (mean p={mean_high:.3f}) should clearly outrank "
        f"LOW archetypes (mean p={mean_low:.3f})"
    )


def test_accuracy_gate_no_regression(report):
    """Lock in current calibration. Tighten the constants when it improves."""
    assert report["brier_score"] <= GATE_MAX_BRIER, (
        f"Brier {report['brier_score']} regressed past gate {GATE_MAX_BRIER}"
    )
    assert report["tier_accuracy"] >= GATE_MIN_ACCURACY, (
        f"Tier accuracy {report['tier_accuracy']} fell below gate {GATE_MIN_ACCURACY}"
    )
    assert report["macro_f1"] >= GATE_MIN_MACRO_F1, (
        f"Macro-F1 {report['macro_f1']} fell below gate {GATE_MIN_MACRO_F1}"
    )


def test_majority_class_rate_helper():
    assert majority_class_rate(["low", "low", "high"]) == pytest.approx(2 / 3)
    assert majority_class_rate([]) == 0.0
