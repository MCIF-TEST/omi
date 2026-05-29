"""Accuracy gate for memory learning — the "becomes smarter over time" pillar.

Measures the longitudinal claim at the heart of the vision: as the persistent
fingerprint store accumulates previously-scored accounts, a new sparse-history
account that behaves like known-bad accounts gets correctly flagged — when,
scored cold against an empty store, it slips through.

Drives the real production path end-to-end: analyze_account (standalone) ->
extract_fingerprint -> compute_memory_signal (against a store of size N) ->
aggregate. The store is synthesised in-memory at each size, so the benchmark
is DB-free and deterministic.

Baseline (memory_v1):
  * cold_bad_recall      0.000  (empty store: bad accounts slip through)
  * warm_bad_recall      1.000  (full store: all caught)
  * memory_recall_lift  +1.000  (the headline: the engine learned)
  * bad_monotonic_rate   1.000  (the learning curve never goes backwards)
  * mean_warm_prob_lift +0.345
  * good_false_lift      0.000  (clean accounts never escalated by memory)
  * distant_inert_rate   1.000  (unmatched accounts left exactly untouched)

Gates are a ratchet: tighten as the memory path improves.
"""

from __future__ import annotations

from app.evaluation.memory_benchmark import (
    FLAGGED_TIERS,
    evaluate_memory,
    load_memory_benchmark,
    run_memory_scenario,
)
from app.schemas import Tier

# --- Calibration ratchet (tighten as the memory path improves) -------------
GATE_MIN_MEMORY_RECALL_LIFT = 0.50    # current +1.000
GATE_MIN_WARM_BAD_RECALL = 0.85       # current 1.000
GATE_MAX_COLD_BAD_RECALL = 0.25       # current 0.000 (premise: under-flagged cold)
GATE_MIN_BAD_MONOTONIC_RATE = 0.85    # current 1.000
GATE_MIN_MEAN_WARM_PROB_LIFT = 0.12   # current +0.345
GATE_MAX_GOOD_FALSE_LIFT = 0.05       # current 0.000
GATE_MIN_DISTANT_INERT_RATE = 0.99    # current 1.000


def _report() -> dict:
    return evaluate_memory(load_memory_benchmark())


def test_memory_benchmark_is_well_formed():
    scenarios = load_memory_benchmark()
    assert len(scenarios) >= 4
    hoods = {s.neighborhood for s in scenarios}
    assert {"bad", "good", "distant"} <= hoods, (
        f"benchmark must cover bad/good/distant neighborhoods; got {hoods}"
    )
    for s in scenarios:
        assert s.profile, f"{s.label}: needs a profile for the standalone scan"


def test_premise_cold_store_underflags():
    """The benchmark only means something if a cold store misses these bots."""
    r = _report()
    assert r["cold_bad_recall"] <= GATE_MAX_COLD_BAD_RECALL, (
        f"Cold-store bot recall {r['cold_bad_recall']} too high — the benchmark "
        "isn't exercising the learning gap it exists to measure."
    )


def test_memory_strictly_improves_recall_over_time():
    """The core claim: accumulated observations catch what a cold store misses."""
    r = _report()
    assert r["warm_bad_recall"] > r["cold_bad_recall"], (
        f"Memory must improve recall as the store grows: cold "
        f"{r['cold_bad_recall']} -> warm {r['warm_bad_recall']}"
    )


def test_memory_recall_lift_gate():
    r = _report()
    assert r["memory_recall_lift"] >= GATE_MIN_MEMORY_RECALL_LIFT, (
        f"Memory recall lift {r['memory_recall_lift']} below gate {GATE_MIN_MEMORY_RECALL_LIFT}"
    )
    assert r["warm_bad_recall"] >= GATE_MIN_WARM_BAD_RECALL


def test_learning_curve_is_monotonic():
    """Adding observations must never make a bad account look *less* suspicious."""
    r = _report()
    assert r["bad_monotonic_rate"] >= GATE_MIN_BAD_MONOTONIC_RATE, (
        f"Bad-scenario monotonic rate {r['bad_monotonic_rate']} below gate "
        f"{GATE_MIN_BAD_MONOTONIC_RATE} — the learning curve regressed somewhere."
    )


def test_mean_warm_prob_lift_gate():
    r = _report()
    assert r["mean_warm_prob_lift"] >= GATE_MIN_MEAN_WARM_PROB_LIFT


def test_memory_never_escalates_clean_accounts():
    r = _report()
    assert r["good_false_lift"] <= GATE_MAX_GOOD_FALSE_LIFT, (
        f"Memory escalated clean accounts (false-lift {r['good_false_lift']}) — "
        "behaving like previously-cleared accounts must not raise suspicion."
    )


def test_unmatched_accounts_are_left_untouched():
    """An account whose fingerprint matches nothing must score identically at
    every store size — the memory signal is conservative (zero confidence)."""
    r = _report()
    assert r["distant_inert_rate"] >= GATE_MIN_DISTANT_INERT_RATE

    # And assert it exactly, per distant scenario.
    for scenario in load_memory_benchmark():
        if scenario.neighborhood != "distant":
            continue
        res = run_memory_scenario(scenario)
        base = res.cold.adjusted_probability
        for p in res.curve:
            assert p.memory_confidence == 0.0, (
                f"{res.label}: unmatched store should yield zero memory confidence"
            )
            assert abs(p.adjusted_probability - base) < 1e-6, (
                f"{res.label}: score moved despite no fingerprint match"
            )


def test_warm_bad_accounts_reach_flagged_tier():
    """End state: each bad account lands in ELEVATED/HIGH once the store is warm."""
    for scenario in load_memory_benchmark():
        if scenario.neighborhood != "bad":
            continue
        res = run_memory_scenario(scenario)
        assert Tier(res.warm.adjusted_tier) in FLAGGED_TIERS, (
            f"{res.label}: warm-store tier {res.warm.adjusted_tier} is not flagged"
        )
