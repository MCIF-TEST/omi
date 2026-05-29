"""Unit tests for the extracted coordination-elevation logic.

This logic was inline in the orchestrator's full-scan path (Phase 4); it now
lives in ``app.detection.coordination.elevate`` so it's pure and unit-testable.
The orchestrator and the rescue benchmark both call it, so these tests pin the
exact contract both rely on.
"""

from __future__ import annotations

from app.detection.coordination._types import CoordinationCluster
from app.detection.coordination.elevate import (
    COORDINATION_SIGNAL_NAME,
    apply_coordination,
    build_coordination_signal,
    coordination_membership,
)
import pytest

from app.detection.scoring import aggregate
from app.schemas import SignalResult


def _cluster(method: str, members: list[str], score: float, evidence=None) -> CoordinationCluster:
    return CoordinationCluster(method=method, members=members, score=score,
                               evidence=evidence or [f"{method} evidence"])


def test_membership_inverts_clusters():
    clusters = [
        _cluster("temporal_semantic_clique", ["a", "b", "c"], 0.8),
        _cluster("fingerprint_cluster", ["b", "c", "d"], 0.7),
    ]
    by_member = coordination_membership(clusters)
    assert [c.method for c in by_member["a"]] == ["temporal_semantic_clique"]
    assert {c.method for c in by_member["b"]} == {"temporal_semantic_clique", "fingerprint_cluster"}
    assert "e" not in by_member


def test_build_signal_none_when_no_clusters():
    assert build_coordination_signal([]) is None


def test_build_signal_uses_max_score_and_scales_confidence_by_method_count():
    one = build_coordination_signal([_cluster("age_cohort", ["a"], 0.6)])
    assert one is not None
    assert one.name == COORDINATION_SIGNAL_NAME
    assert one.probability == 0.6
    assert one.confidence == pytest.approx(0.75)  # 0.55 + 0.20 * 1

    # Two distinct methods, take the strongest probability, higher confidence.
    two = build_coordination_signal([
        _cluster("age_cohort", ["a"], 0.6),
        _cluster("fingerprint_cluster", ["a"], 0.9),
    ])
    assert two.probability == 0.9
    assert two.confidence == pytest.approx(0.95)  # 0.55 + 0.20 * 2
    assert two.sub_signals["detector_count"] == 2.0


def test_confidence_is_capped_at_one():
    clusters = [_cluster(f"m{i}", ["a"], 0.7) for i in range(5)]
    sig = build_coordination_signal(clusters)
    assert sig.confidence == 1.0  # 0.55 + 0.20*5 = 1.55 -> capped


def test_apply_coordination_is_noop_without_clusters():
    base = aggregate([SignalResult(name="temporal", probability=0.3, confidence=0.4)])
    out = apply_coordination(base, [])
    assert out is base  # identity: untouched


def test_apply_coordination_lifts_score():
    base = aggregate([SignalResult(name="temporal", probability=0.3, confidence=0.4)])
    lifted = apply_coordination(base, [
        _cluster("temporal_semantic_clique", ["a", "b", "c"], 0.85),
        _cluster("fingerprint_cluster", ["a", "b", "c"], 0.8),
    ])
    assert lifted.overall_probability > base.overall_probability
    assert any(s.name == COORDINATION_SIGNAL_NAME for s in lifted.signals)


def test_evidence_is_truncated_to_five():
    clusters = [_cluster("m", ["a"], 0.7, evidence=[f"e{i}" for i in range(10)])]
    sig = build_coordination_signal(clusters)
    assert len(sig.evidence) == 5
