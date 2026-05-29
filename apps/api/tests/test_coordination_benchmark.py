"""Accuracy gate for the multi-account coordination detectors.

Complements ``test_evaluation_benchmark.py`` (single-account accuracy) by
measuring the detectors that are invisible to that benchmark: age_cohort,
co_engagement, style_match, temporal_semantic, fingerprint_cluster.  Those
detectors all require a *batch* of peer accounts to produce any signal; a
single-account fixture exercises them at exactly zero influence.

Metrics gated here:
  * cluster_recall  — fraction of planted coordination clusters that are
    detected (Jaccard ≥ 0.50 match required). Measures true positives.
  * member_precision — of all accounts flagged in detected clusters, what
    fraction were actually labeled bot. Measures false-positive cost.
  * member_recall   — of all bot accounts, what fraction were caught.
  * clean_pass_rate — in scenarios expected to have no coordination, how
    often did the detectors correctly stay silent.

Baseline (coordination_v1):
  * cluster_recall   0.857  (6/7 planted clusters matched; the 7th sits
                             inside organic noise at 23% share, 2 pts below
                             the 25% cohort threshold — expected miss)
  * member_precision 1.000  (zero false positives on the current fixture)
  * member_recall    0.837  (one burst-bot member at the cluster edge)
  * clean_pass_rate  1.000  (all 6 clean scenarios correctly silent)

The gates are deliberately a ratchet: tighten them as the detectors improve.
"""

from __future__ import annotations

import pytest

from app.evaluation.coordination_benchmark import (
    CoordinationEvalRow,
    compute_coordination_report,
    evaluate_coordination,
    load_coordination_benchmark,
    run_coordination_scenario,
)

# --- Calibration ratchet (tighten as the detectors improve) ----------------
GATE_MIN_CLUSTER_RECALL = 0.70     # current 0.857
GATE_MIN_MEMBER_PRECISION = 0.85   # current 1.000
GATE_MIN_MEMBER_RECALL = 0.70      # current 0.837
GATE_MIN_CLEAN_PASS_RATE = 0.85    # current 1.000


@pytest.fixture(scope="module")
def report() -> dict:
    """Evaluate the coordination benchmark once for the whole module."""
    return evaluate_coordination(load_coordination_benchmark())


@pytest.fixture(scope="module")
def rows() -> list[CoordinationEvalRow]:
    scenarios = load_coordination_benchmark()
    return [run_coordination_scenario(s) for s in scenarios]


# ---------------------------------------------------------------------------
# Structural tests (no engine needed)
# ---------------------------------------------------------------------------

def test_coordination_benchmark_is_well_formed():
    scenarios = load_coordination_benchmark()
    assert len(scenarios) >= 10, "coordination benchmark should have at least 10 scenarios"

    types = {s.scenario_type for s in scenarios}
    assert len(types) >= 4, f"should cover at least 4 detector types; got {types}"

    expected_coords = {s.expected_coordination for s in scenarios}
    assert "none" in expected_coords, "must include clean control scenarios (expected_coordination=none)"
    assert "high" in expected_coords, "must include clearly-coordinated scenarios"

    planted_scenarios = [s for s in scenarios if s.planted_clusters]
    assert len(planted_scenarios) >= 5, "must have ≥5 scenarios with planted clusters"

    for s in scenarios:
        roles = {a.role for a in s.accounts}
        if s.planted_clusters:
            assert "bot" in roles, f"{s.label}: scenarios with planted clusters must have bot accounts"


def test_compute_coordination_report_math():
    """The metric layer computes cluster_recall and member_precision correctly."""
    from app.evaluation.coordination_benchmark import (
        AccountEntry, CoordinationEvalRow, PlantedCluster,
        compute_coordination_report,
    )
    from app.detection.coordination._types import CoordinationCluster

    # Row 1: planted cluster fully matched, all flagged accounts are bots
    r1 = CoordinationEvalRow(
        label="test1", scenario_type="age_cohort",
        expected_coordination="high",
        n_accounts=5, n_bots=3, n_organic=2,
        planted_clusters=[PlantedCluster("age_cohort", ["a", "b", "c"])],
        detected_clusters=[CoordinationCluster("age_cohort", ["a", "b", "c"], 0.9)],
        cluster_recall=1.0, member_precision=1.0, member_recall=1.0, matched_planted=1,
    )
    # Row 2: clean scenario, no clusters planted, no clusters detected
    r2 = CoordinationEvalRow(
        label="test2", scenario_type="age_cohort",
        expected_coordination="none",
        n_accounts=5, n_bots=0, n_organic=5,
        planted_clusters=[],
        detected_clusters=[],
        cluster_recall=1.0, member_precision=1.0, member_recall=1.0, matched_planted=0,
    )
    report = compute_coordination_report([r1, r2])
    assert report["n_scenarios"] == 2
    assert report["n_with_planted"] == 1
    assert report["n_clean"] == 1
    assert report["cluster_recall"] == pytest.approx(1.0)
    assert report["clean_pass_rate"] == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# Accuracy gates
# ---------------------------------------------------------------------------

def test_cluster_recall_gate(report):
    """Planted clusters must be recovered above the ratchet floor."""
    cr = report["cluster_recall"]
    assert cr >= GATE_MIN_CLUSTER_RECALL, (
        f"Cluster recall {cr:.3f} fell below gate {GATE_MIN_CLUSTER_RECALL}. "
        f"Per-scenario breakdown: "
        + ", ".join(
            f"{s['label']}={s['cluster_recall']:.2f}"
            for s in report["per_scenario"]
        )
    )


def test_member_precision_gate(report):
    """Flagged members must be predominantly real bots (guard against spam FP)."""
    mp = report["member_precision"]
    assert mp >= GATE_MIN_MEMBER_PRECISION, (
        f"Member precision {mp:.3f} fell below gate {GATE_MIN_MEMBER_PRECISION}. "
        "Detectors are flagging organic accounts — check FP rate."
    )


def test_member_recall_gate(report):
    """Bot members should be caught in a detected cluster above the ratchet floor."""
    mr = report["member_recall"]
    assert mr >= GATE_MIN_MEMBER_RECALL, (
        f"Member recall {mr:.3f} fell below gate {GATE_MIN_MEMBER_RECALL}."
    )


def test_clean_pass_rate_gate(report):
    """Scenarios with no coordination must not be falsely flagged."""
    cpr = report["clean_pass_rate"]
    assert cpr >= GATE_MIN_CLEAN_PASS_RATE, (
        f"Clean pass rate {cpr:.3f} fell below gate {GATE_MIN_CLEAN_PASS_RATE}. "
        "Detectors are firing on organic-only scenarios."
    )


# ---------------------------------------------------------------------------
# Invariant tests (backend-independent)
# ---------------------------------------------------------------------------

def test_high_coordination_scenarios_all_fire(rows):
    """Every scenario labeled 'high' expected_coordination must produce ≥1 cluster."""
    high_rows = [r for r in rows if r.expected_coordination == "high"]
    assert high_rows, "benchmark must include 'high' coordination scenarios"
    failures = [r.label for r in high_rows if not r.detected_clusters]
    assert not failures, (
        f"These HIGH-coordination scenarios produced no clusters: {failures}"
    )


def test_clean_scenarios_stay_silent(rows):
    """Every 'none' scenario must produce zero detected clusters."""
    clean_rows = [r for r in rows if r.expected_coordination == "none"]
    assert clean_rows, "benchmark must include 'none' (clean) coordination scenarios"
    failures = [
        (r.label, len(r.detected_clusters)) for r in clean_rows if r.detected_clusters
    ]
    assert not failures, (
        f"These NONE-coordination scenarios falsely detected clusters: {failures}"
    )


def test_no_organic_accounts_falsely_flagged(rows):
    """Organic accounts must not appear in any detected cluster on any scenario."""
    organic_flagged: list[tuple[str, str]] = []
    for r in rows:
        bot_ids = {
            a.external_id
            for s in load_coordination_benchmark()
            if s.label == r.label
            for a in s.accounts
            if a.role == "bot"
        }
        for cluster in r.detected_clusters:
            for member in cluster.members:
                if member not in bot_ids:
                    organic_flagged.append((r.label, member))
    assert not organic_flagged, (
        f"Organic accounts found in detected clusters: {organic_flagged}"
    )


def test_per_detector_coverage():
    """Each coordination detector type is exercised by at least one scenario."""
    scenarios = load_coordination_benchmark()
    types = {s.scenario_type for s in scenarios}
    required = {"age_cohort", "co_engagement", "style_match",
                "temporal_semantic", "fingerprint_cluster"}
    missing = required - types
    assert not missing, f"Detector types not covered by any scenario: {missing}"
