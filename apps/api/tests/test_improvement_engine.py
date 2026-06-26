"""Continuous Improvement Engine — recommendation tests (Sprint 011).

Exercises every detector deterministically with synthetic snapshots: prompt/context/evidence
improvement + regression, control-FPR increase, calibration drift, latency, citation,
hallucination, and Governor regressions — plus determinism, reproducible ids, mandatory
supporting metrics, and the no-actionable-difference case.
"""
from __future__ import annotations

from app.reasoning.improvement import recommend


def _snap(config: dict, **over) -> dict:
    base = {
        "config": config, "label": str(config), "agreement_rate": 0.80, "control_fpr": 0.0,
        "number_preserved_rate": 1.0, "avg_latency_ms": 100.0, "citation_failure_rate": 0.0,
        "governor_permit_rate": 1.0, "governor_floor_rate": 0.0, "citation_retention": 1.0,
    }
    base.update(over)
    return base


# --- lever improvement / regression ----------------------------------------- #
def test_prompt_improvement():
    recs = recommend(_snap({"prompt_version": "v1"}), _snap({"prompt_version": "v2"}, agreement_rate=0.88))
    assert [r.kind for r in recs] == ["prompt_improvement"]
    r = recs[0]
    assert r.action == "promote" and r.severity == "improvement" and r.state == "recommended"
    assert r.metrics["agreement_gain"] == 0.08


def test_prompt_regression():
    recs = recommend(_snap({"prompt_version": "v1"}), _snap({"prompt_version": "v2"}, agreement_rate=0.70))
    assert any(r.kind == "prompt_regression" and r.action == "rollback" for r in recs)


def test_context_and_evidence_levers():
    assert any(r.kind == "context_improvement"
               for r in recommend(_snap({"context_mode": "raw"}), _snap({"context_mode": "structured"}, agreement_rate=0.9)))
    assert any(r.kind == "evidence_improvement"
               for r in recommend(_snap({"enrich": False}), _snap({"enrich": True}, agreement_rate=0.9)))


# --- critical regressions (precision + constitution) ------------------------ #
def test_control_fpr_increase_is_critical_and_sorts_first():
    recs = recommend(_snap({"prompt_version": "v1"}),
                     _snap({"prompt_version": "v2"}, agreement_rate=0.95, control_fpr=0.2))
    assert recs[0].kind == "control_fpr_increase"
    assert recs[0].severity == "critical" and recs[0].action == "rollback"


def test_calibration_drift_is_critical():
    recs = recommend(_snap({"prompt_version": "v1"}),
                     _snap({"prompt_version": "v2"}, number_preserved_rate=0.9))
    assert any(r.kind == "calibration_drift" and r.severity == "critical" for r in recs)


# --- cross-cutting regressions ---------------------------------------------- #
def test_latency_regression():
    recs = recommend(_snap({"prompt_version": "v1"}), _snap({"prompt_version": "v2"}, avg_latency_ms=200.0))
    assert any(r.kind == "latency_regression" and r.action == "hold" for r in recs)


def test_citation_regression():
    recs = recommend(_snap({"prompt_version": "v1"}), _snap({"prompt_version": "v2"}, citation_retention=0.8))
    assert any(r.kind == "citation_regression" for r in recs)


def test_hallucination_increase():
    recs = recommend(_snap({"prompt_version": "v1"}), _snap({"prompt_version": "v2"}, citation_failure_rate=0.1))
    assert any(r.kind == "hallucination_increase" and r.action == "rollback" for r in recs)


def test_governor_violation_increase():
    recs = recommend(_snap({"prompt_version": "v1"}), _snap({"prompt_version": "v2"}, governor_permit_rate=0.9))
    assert any(r.kind == "governor_violation_increase" for r in recs)


# --- discipline: evidence required, deterministic, reproducible ------------- #
def test_no_actionable_difference_yields_no_recommendation():
    assert recommend(_snap({"prompt_version": "v1"}), _snap({"prompt_version": "v2"})) == []


def test_every_recommendation_carries_metrics_and_is_severity_ordered():
    recs = recommend(_snap({"prompt_version": "v1"}),
                     _snap({"prompt_version": "v2"}, agreement_rate=0.5, control_fpr=0.3,
                           citation_failure_rate=0.2, avg_latency_ms=300.0, governor_permit_rate=0.8))
    assert recs and all(r.metrics for r in recs)            # never without evidence
    assert recs[0].severity == "critical"                   # most severe first


def test_determinism_and_reproducible_ids():
    b, c = _snap({"prompt_version": "v1"}), _snap({"prompt_version": "v2"}, agreement_rate=0.88)
    r1, r2 = recommend(b, c), recommend(b, c)
    assert [r.to_dict() for r in r1] == [r.to_dict() for r in r2]
    assert r1[0].id == r2[0].id and r1[0].id.startswith("rec:")
