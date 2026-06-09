"""Accuracy gate for coordination *rescue* — the end-to-end product thesis.

seed_v1 proves the single-account engine under-flags sparse-history accounts.
coordination_v1 proves the cross-account detectors recover planted clusters.
This benchmark measures the **bridge**: when a bot the single-account engine
scores LOW sits inside a detected coordination cluster, does the coordination
signal lift it into the correct tier?

It drives the real production code end-to-end:
  analyze_account (standalone) -> coordination detectors -> apply_coordination

**Phase-4 recalibration (member-level corroboration gate).** The benchmark
contains three scenarios — one per detector path: ``temporal_semantic`` (1),
``fingerprint_cluster`` (2), ``age_cohort`` (3). After the Phase-4 fix to
``elevate.build_coordination_signal`` (which mirrors the video-level
corroboration gate at the per-member elevation site), a member is only
lifted to HIGH when its clusters include a *discriminative* detector or
≥2 distinct detectors. Scenarios 1 and 3 are single supporting-detector
constructions — by the new contract their members are intentionally capped
at MODERATE (the same property that drops the ~0.73 member-FPR on
legitimate Known-Mixed coordination controls to ≤0.15). Scenario 2 uses a
discriminative detector and still rescues fully. The aggregate-level gates
below were tightened against the old all-rescue baseline; they are reset
here to the new floor (the discriminative scenario alone), with a new
focused test pinning the supporting-only-capping property explicitly.

Baseline (coordination_rescue_v1, post Phase-4 gate):
  * standalone_bot_recall  0.000  (the engine alone catches NONE of the bots)
  * adjusted_bot_recall    0.238  (fingerprint scenario fully rescued; the
                                   two supporting-only scenarios capped at MODERATE)
  * recall_lift           +0.238
  * rescue_rate            0.250  (5/20 — exactly the fingerprint scenario's bots)
  * mean_prob_lift        +0.230
  * organic_false_lift     0.000  (zero clean accounts wrongly escalated — unchanged)

Gates are a ratchet: tighten as the bridge improves.
"""

from __future__ import annotations

import pytest

from app.evaluation.rescue_benchmark import (
    evaluate_rescue,
    load_rescue_benchmark,
    run_rescue_scenario,
)

# --- Calibration ratchet (tighten as the bridge improves) ------------------
# These reflect the Phase-4 member-level corroboration gate: only the
# discriminative-detector scenario (fingerprint_family_rescue) rescues
# uncorroborated bots; the supporting-only scenarios are intentionally capped
# at MODERATE — that capping is the precision fix and is asserted explicitly
# in ``test_supporting_only_scenarios_are_capped_at_moderate`` below.
GATE_MIN_RECALL_LIFT = 0.15        # current +0.238
GATE_MIN_RESCUE_RATE = 0.20        # current 0.250 (fingerprint scenario alone)
GATE_MIN_MEAN_PROB_LIFT = 0.10     # current +0.230
GATE_MAX_ORGANIC_FALSE_LIFT = 0.05 # current 0.000 (unchanged — the trust gate)
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


# --- Phase-4 corroboration-gate trust properties ----------------------------
# These tests pin the per-member corroboration contract directly, so the
# benchmark measures the right thing (precision via gate) instead of inferring
# it from a lowered global rescue rate.

_DISCRIMINATIVE_SCENARIO = "fingerprint_family_rescue"
_SUPPORTING_ONLY_SCENARIOS = {"temporal_burst_rescue", "age_cohort_rescue"}
# Top of the MODERATE band — must stay in sync with
# app.detection.coordination.aggregate.SUPPORTING_CEILING and
# app.detection.coordination.elevate._SUPPORTING_CONFIDENCE_CEILING.
_MODERATE_CAP = 0.50


def test_discriminative_scenario_still_rescues_fully():
    """The fingerprint_family scenario fires the *discriminative*
    fingerprint_cluster detector. Under the Phase-4 gate this is exactly the
    case that should still lift its members to ELEVATED/HIGH — it is the
    'real-IO-like' construction (one strong discriminator, sparse history).
    If this rescue rate regresses, the gate has become too strict."""
    for scenario in load_rescue_benchmark():
        if scenario.label != _DISCRIMINATIVE_SCENARIO:
            continue
        results = run_rescue_scenario(scenario)
        bots_in_cluster = [r for r in results if r.role == "bot" and r.in_cluster]
        assert bots_in_cluster, "fingerprint_family_rescue should have in-cluster bots"
        rescued = [r for r in bots_in_cluster if r.adjusted_p > r.standalone_p]
        assert len(rescued) == len(bots_in_cluster), (
            f"Discriminative scenario regressed: only "
            f"{len(rescued)}/{len(bots_in_cluster)} fingerprint bots rescued."
        )
        # Each rescued bot should land at the new ELEVATED+ shape, not MODERATE.
        for r in rescued:
            assert r.adjusted_p > _MODERATE_CAP, (
                f"{r.external_id}: discriminative rescue should clear MODERATE, "
                f"got adjusted_p={r.adjusted_p:.3f}"
            )
        return
    pytest.fail(f"benchmark missing the discriminative scenario "
                f"{_DISCRIMINATIVE_SCENARIO!r}")


def test_supporting_only_scenarios_are_capped_at_moderate():
    """The temporal_burst and age_cohort scenarios each fire a single
    *supporting* detector. Under the Phase-4 gate, members in such scenarios
    must be capped at MODERATE — this is the precision fix that takes
    legitimate professional writers / journalists out of the ELEVATED tier
    in the same code path (the original ~0.73 member-FPR on Known-Mixed
    controls is the production symptom this test rules out synthetically)."""
    saw = set()
    for scenario in load_rescue_benchmark():
        if scenario.label not in _SUPPORTING_ONLY_SCENARIOS:
            continue
        saw.add(scenario.label)
        for r in run_rescue_scenario(scenario):
            if not r.in_cluster:
                continue
            assert r.adjusted_p <= _MODERATE_CAP, (
                f"{scenario.label}/{r.external_id}: a lone supporting detector "
                f"must not lift a member above MODERATE, got "
                f"adjusted_p={r.adjusted_p:.3f}. This would re-open the "
                f"member-level FPR Phase-4 closed."
            )
    missing = _SUPPORTING_ONLY_SCENARIOS - saw
    assert not missing, f"benchmark missing supporting-only scenarios: {missing}"
