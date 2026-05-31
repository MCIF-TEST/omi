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
# GAP-04 targeted hybrid-operation archetypes (astroturf, broadcast bots, fresh
# sockpuppets, mechanical schedulers) that were under-detected with low-data
# confidence:
#   • narrative detector — new detector scanning for political/disinformation
#     language patterns from IO disclosures (deep-state, media-corruption tropes,
#     amplification CTAs, etc.); primary signal for coordinated narrative ops.
#   • voice broadcast exception — zero first-person across a non-trivial corpus
#     now raises confidence even for short posts (pure amplification bots).
#   • profile fresh-account compound signal — clusters of auto-handle + sparse
#     graph + minimal bio on <90-day accounts now flags sockpuppet setups.
#   • temporal strength-aware confidence — machine-precision scheduling (CoV <
#     5%) gets a confidence boost even on small post histories; typical bots with
#     Gaussian jitter (CoV >> 5%) are NOT boosted.
#   • single-axis cap fix — the "no HIGH without corroboration" cap now only
#     counts *suspicious* confident signals (p > 0.40) as axes, preventing clean
#     detectors from falsely bypassing the cap.
# Net effect on the seed benchmark: Brier 0.0588 → 0.0345 (41% improvement),
# tier accuracy 0.646 → 0.631, macro-F1 0.583 → 0.588. The slight accuracy dip
# is explained by the single-axis cap correctly classifying engagement_farm_high
# as ELEVATED (one suspicious axis only), which is the right policy tradeoff.
# GAP-05 confidence calibration recalibrated the narrative detector's probability
# curve (centre 0.30 → 0.12 — explicit IO-disclosure phrasing is suspicious at
# much lower marker rates than the old curve assumed; a 30%-marker account was
# mapping to a useless 0.50) and expanded its pattern recall to catch common
# real-world astroturf phrasings the original set missed ("they are trying to
# silence us", "before it gets taken down", "(mainstream) media won't cover").
# A 2-axis convergence bonus was tested and REJECTED — it worsened Brier by
# pushing ambiguous over-detected cases higher without cleanly recovering the
# under-detected ones (the residual misses are genuinely signal-ambiguous, e.g.
# clean_ai_verbose_writer vs elevated_broadcast_voice share a near-identical
# signal vector — separating them needs new discriminating features owned by
# GAP-07/GAP-10, not threshold tuning).
# Net effect on the seed benchmark: Brier 0.0345 → 0.0275 (20% further
# improvement), accuracy 0.631 (held), macro-F1 0.588 → 0.585, ZERO new false
# positives (narrative fires only on the two genuine astroturf archetypes).
GATE_MAX_BRIER = 0.032      # current 0.0275; was 0.045 after GAP-04
GATE_MIN_ACCURACY = 0.62    # current 0.631
GATE_MIN_MACRO_F1 = 0.57    # current 0.585


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
