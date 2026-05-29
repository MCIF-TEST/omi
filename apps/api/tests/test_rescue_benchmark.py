"""Accuracy gate for coordination *rescue* — the end-to-end product thesis.

seed_v1 proves the single-account engine under-flags sparse-history accounts.
coordination_v1 proves the cross-account detectors recover planted clusters.
This benchmark measures the **bridge**: when a bot the single-account engine
scores LOW sits inside a detected coordination cluster, does the coordination
signal lift it into the correct tier?

It drives the real production code end-to-end:
  analyze_account (standalone) -> coordination detectors -> apply_coordination

Baseline (coordination_rescue_v1):
  * standalone_bot_recall  0.000  (the engine alone catches NONE of the bots)
  * adjusted_bot_recall    0.952  (coordination catches 95% of them)
  * recall_lift           +0.952  (the headline: miss -> catch)
  * rescue_rate            1.000  (every under-flagged in-cluster bot lifted)
  * mean_prob_lift        +0.488
  * organic_false_lift     0.000  (zero clean accounts wrongly escalated)

Gates are a ratchet: tighten as the bridge improves. They encode the claim
that coordination *strictly and substantially* rescues recall without
escalating clean accounts.
"""

from __future__ import annotations

import pytest

from app.evaluation.rescue_benchmark import (
    evaluate_rescue,
    load_rescue_benchmark,
    run_rescue_scenario,
)

# --- Calibration ratchet (tighten as the bridge improves) ------------------
GATE_MIN_RECALL_LIFT = 0.50        # current +0.952
GATE_MIN_RESCUE_RATE = 0.85        # current 1.000
GATE_MIN_MEAN_PROB_LIFT = 0.15     # current +0.488
GATE_MAX_ORGANIC_FALSE_LIFT = 0.05 # current 0.000
# The premise: the single-account engine genuinely under-flags these bots.
# If this ever rises, the benchmark stopped exercising the gap it exists for.
GATE_MAX_STANDALONE_BOT_RECALL = 0.25  # current 0.000


@pytest.fixture(scope="module")
def report() -> dict:
    return evaluate_rescue(load_rescue_benchmark())


def test_rescue_benchmark_is_well_formed():
    scenarios = load_rescue_benchmark()
    assert len(scenarios) >= 3, "rescue benchmark should cover several detector paths"
    for s in scenarios:
        roles = {a.role for a in s.accounts}
        assert "bot" in roles, f"{s.label}: needs bot accounts"
        for a in s.accounts:
            assert a.profile, f"{a.external_id}: needs a profile for the standalone scan"


def test_premise_single_account_engine_underflags(report):
    """The benchmark only means something if the standalone engine misses these
    bots. Lock the premise in so the benchmark can't silently stop testing it."""
    assert report["standalone_bot_recall"] <= GATE_MAX_STANDALONE_BOT_RECALL, (
        f"Standalone bot recall {report['standalone_bot_recall']} is too high — "
        "these bots are no longer under-flagged, so the rescue benchmark isn't "
        "exercising the gap it exists to measure."
    )


def test_coordination_strictly_improves_recall(report):
    """The core claim: coordination catches bots the engine alone cannot."""
    assert report["adjusted_bot_recall"] > report["standalone_bot_recall"], (
        f"Coordination must improve bot recall: standalone "
        f"{report['standalone_bot_recall']} -> adjusted {report['adjusted_bot_recall']}"
    )


def test_recall_lift_gate(report):
    assert report["recall_lift"] >= GATE_MIN_RECALL_LIFT, (
        f"Recall lift {report['recall_lift']} fell below gate {GATE_MIN_RECALL_LIFT}"
    )


def test_rescue_rate_gate(report):
    assert report["rescue_rate"] >= GATE_MIN_RESCUE_RATE, (
        f"Rescue rate {report['rescue_rate']} fell below gate {GATE_MIN_RESCUE_RATE}. "
        f"{report['n_rescued']}/{report['n_rescuable']} under-flagged in-cluster bots rescued."
    )


def test_mean_prob_lift_gate(report):
    assert report["mean_prob_lift"] >= GATE_MIN_MEAN_PROB_LIFT, (
        f"Mean probability lift {report['mean_prob_lift']} fell below gate {GATE_MIN_MEAN_PROB_LIFT}"
    )


def test_no_organic_false_escalation(report):
    """Coordination must not escalate clean accounts. The lift must be surgical."""
    assert report["organic_false_lift"] <= GATE_MAX_ORGANIC_FALSE_LIFT, (
        f"Organic false-lift {report['organic_false_lift']} exceeds gate "
        f"{GATE_MAX_ORGANIC_FALSE_LIFT} — coordination is escalating clean accounts."
    )


def test_accounts_outside_clusters_are_unchanged():
    """An account in no cluster must score identically before and after the lift
    (apply_coordination is a no-op without clusters)."""
    for scenario in load_rescue_benchmark():
        for r in run_rescue_scenario(scenario):
            if not r.in_cluster:
                assert r.adjusted_p == r.standalone_p, (
                    f"{r.external_id} is in no cluster but its score changed: "
                    f"{r.standalone_p} -> {r.adjusted_p}"
                )
                assert r.adjusted_tier == r.standalone_tier
