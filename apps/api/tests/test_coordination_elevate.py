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
from app.schemas import SignalResult, Tier


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


def test_build_signal_one_discriminative_runs_at_full_strength():
    """A single discriminative detector (fingerprint / co_engagement / co_tag)
    can carry a maximal member signal alone — these are the lenses that
    measured a real IO-vs-human gap. Mirrors the video-level gate."""
    sig = build_coordination_signal([_cluster("fingerprint_cluster", ["a"], 0.9)])
    assert sig is not None
    assert sig.name == COORDINATION_SIGNAL_NAME
    assert sig.probability == 0.9                             # uncapped
    assert sig.confidence == pytest.approx(0.75)              # 0.55 + 0.20 * 1
    assert sig.sub_signals["corroborated"] == 1.0
    assert sig.sub_signals["discriminative_count"] == 1.0


def test_build_signal_two_distinct_methods_run_at_full_strength():
    """A discriminative + supporting cluster on the same member: take the
    strongest probability and lift confidence with the extra method."""
    sig = build_coordination_signal([
        _cluster("age_cohort", ["a"], 0.6),
        _cluster("fingerprint_cluster", ["a"], 0.9),
    ])
    assert sig.probability == 0.9
    assert sig.confidence == pytest.approx(0.95)              # 0.55 + 0.20 * 2
    assert sig.sub_signals["detector_count"] == 2.0
    assert sig.sub_signals["corroborated"] == 1.0


def test_build_signal_lone_supporting_is_capped_at_moderate():
    """The Phase-4 member-level gate: a lone non-discriminative detector
    (style_match / temporal_semantic / age_cohort) cannot push a member to
    HIGH. This is the fix for the ~0.73 member-FPR on Known-Mixed controls
    where style_match-only clusters were elevating legitimate professional
    writers via a 0.80+ coordination signal injected into the per-account
    re-aggregate. Mirrors aggregate.aggregate_coordination's gate exactly."""
    sig = build_coordination_signal([_cluster("style_match", ["a"], 0.85)])
    assert sig is not None
    assert sig.probability == pytest.approx(0.49)             # capped at SUPPORTING_CEILING
    assert sig.confidence == pytest.approx(0.50)              # capped at supporting confidence ceiling
    assert sig.sub_signals["corroborated"] == 0.0
    assert sig.sub_signals["discriminative_count"] == 0.0


def test_build_signal_two_supporting_methods_corroborate():
    """Two independent supporting detectors agreeing IS corroboration —
    matches the aggregator's ``len(fired) >= 2`` rule. The composed signal
    runs at full strength even without a discriminative lens."""
    sig = build_coordination_signal([
        _cluster("style_match", ["a"], 0.85),
        _cluster("age_cohort", ["a"], 0.70),
    ])
    assert sig.probability == 0.85                            # uncapped
    assert sig.confidence == pytest.approx(0.95)              # 0.55 + 0.20 * 2
    assert sig.sub_signals["corroborated"] == 1.0


def test_confidence_is_capped_at_one():
    # Five unknown methods — treated as supporting (not in DISCRIMINATIVE_DETECTORS)
    # but corroborated by count (>=2 distinct), so the signal runs at full
    # strength and confidence saturates at 1.0.
    clusters = [_cluster(f"m{i}", ["a"], 0.7) for i in range(5)]
    sig = build_coordination_signal(clusters)
    assert sig.probability == 0.7
    assert sig.confidence == 1.0                              # 0.55 + 0.20*5 = 1.55 -> capped
    assert sig.sub_signals["corroborated"] == 1.0


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


# --- Phase-5 boundary hold --------------------------------------------------
# Phase 4 measured the signal-cap's residual: a capped uncorroborated signal
# still tips BORDERLINE-standalone accounts (0.39-0.49) just across the
# ELEVATED boundary (humans induced elevation 0.324). The hold completes the
# corroboration principle at the verdict boundary: uncorroborated coordination
# may move a score within its tier band but may not cross a boundary upward —
# clamped at the band ceiling with explicit score_adjustments narration,
# mirroring the single-axis HIGH cap idiom in app.detection.scoring.

def _borderline_moderate_base():
    """A borderline-MODERATE standalone scan (~0.40) — the Phase-4 residual
    population (humans at 0.39-0.49 standalone)."""
    return aggregate([
        SignalResult(name="temporal", probability=0.5, confidence=0.4),
        SignalResult(name="semantic", probability=0.45, confidence=0.35),
    ])


def test_boundary_hold_keeps_uncorroborated_borderline_below_elevated():
    base = _borderline_moderate_base()
    assert base.tier is Tier.MODERATE  # precondition: the residual population
    clusters = [_cluster("style_match", ["a"], 0.85)]
    # The capped signal alone would still cross the boundary (the residual).
    raw = aggregate(list(base.signals) + [build_coordination_signal(clusters)])
    assert raw.tier in (Tier.ELEVATED, Tier.HIGH)
    # Production: held at the MODERATE ceiling, never silently.
    out = apply_coordination(base, clusters)
    assert out.tier is Tier.MODERATE
    assert out.overall_probability == pytest.approx(0.49)
    assert any("boundary hold" in a.lower() for a in out.score_adjustments)
    assert "uncorroborated" in out.summary


def test_boundary_hold_allows_movement_within_the_band():
    """An uncorroborated lift that does NOT cross a boundary is untouched —
    the hold is a boundary rule, not a suppression of evidence."""
    low = aggregate([
        SignalResult(name="temporal", probability=0.2, confidence=0.4),
        SignalResult(name="semantic", probability=0.3, confidence=0.3),
        SignalResult(name="profile", probability=0.25, confidence=0.5),
    ])
    out = apply_coordination(low, [_cluster("style_match", ["a"], 0.85)])
    assert out.overall_probability > low.overall_probability  # raise allowed
    assert out.tier is Tier.MODERATE                          # no crossing
    assert not any("boundary hold" in a.lower() for a in out.score_adjustments)


def test_boundary_hold_blocks_uncorroborated_high_from_elevated_base():
    """The same principle one tier up: no uncorroborated path to HIGH —
    consistent with the single-axis HIGH cap (clamped at 0.74/ELEVATED)."""
    base = aggregate([
        SignalResult(name="temporal", probability=0.8, confidence=0.6),
        SignalResult(name="voice", probability=0.75, confidence=0.55),
    ])
    assert base.tier is Tier.ELEVATED
    out = apply_coordination(base, [_cluster("style_match", ["a"], 0.95)])
    assert out.tier is Tier.ELEVATED
    assert out.overall_probability == pytest.approx(0.74)
    assert any("boundary hold" in a.lower() for a in out.score_adjustments)


def test_boundary_hold_never_touches_corroborated_members():
    """Rescue preserved: a discriminative cluster crosses boundaries freely —
    the hold applies only to uncorroborated evidence."""
    base = _borderline_moderate_base()
    out = apply_coordination(base, [_cluster("fingerprint_cluster", ["a"], 0.9)])
    assert out.tier in (Tier.ELEVATED, Tier.HIGH)
    assert not any("boundary hold" in a.lower() for a in out.score_adjustments)
