"""Tier-2B coordination calibration — aggregate_coordination().

Pins the behavior that lifted real-world recall 0.333 -> 0.500 while holding
precision 1.0 / FPR 0.0 / controls 0/3. The findings here mirror the exact
per-detector numbers observed in the state-IO evaluation, so the test doubles
as documentation of *why* the calibration exists and guards against a
regression back to the diluting confidence-weighted mean.
"""

from __future__ import annotations

from app.detection.coordination._types import CoordinationFinding
from app.detection.coordination.aggregate import (
    DETECTOR_RELIABILITY,
    aggregate_coordination,
)

# Detection threshold used throughout the evaluation: tier >= elevated <=> >= 0.50.
ELEVATED = 0.50


def _f(method: str, score: float, conf: float, n_clusters: int = 0) -> CoordinationFinding:
    return CoordinationFinding(
        method=method, overall_score=score, confidence=conf, clusters=[None] * n_clusters
    )


def _legacy_mean(findings):
    """The pre-Tier-2B aggregation, for an explicit before/after assertion."""
    w = sum(f.confidence for f in findings)
    return sum(f.overall_score * f.confidence for f in findings) / w if w else 0.0


def test_rescues_diluted_corroboration():
    """Russia-IRA #1 shape: fingerprint + style both fire with real clusters,
    but cohort/temporal sit at their no-signal floor. The legacy mean buried it
    (0.42); the calibrated score must clear ELEVATED via the corroboration OR."""
    findings = [
        _f("temporal_semantic_clique", 0.23, 1.0, 0),
        _f("fingerprint_cluster", 0.82, 0.96, 1),
        _f("age_cohort", 0.05, 0.96, 0),
        _f("style_match", 0.77, 0.5, 1),
    ]
    assert _legacy_mean(findings) < ELEVATED        # legacy: missed
    agg = aggregate_coordination(findings)
    assert agg.score >= ELEVATED                    # calibrated: caught
    # The lift comes from corroboration (disjunctive evidence), not the mean.
    assert agg.corroboration > agg.weighted_mean


def test_confident_negative_detector_cannot_dilute():
    """A detector pinned at its no-signal floor with full confidence must add
    ZERO positive evidence — it can't drag a strong corroborated signal down."""
    strong = [_f("fingerprint_cluster", 0.95, 1.0, 2), _f("style_match", 0.9, 1.0, 1)]
    with_floor = strong + [
        _f("temporal_semantic_clique", 0.23, 1.0, 0),
        _f("age_cohort", 0.10, 1.0, 0),
    ]
    a, b = aggregate_coordination(strong), aggregate_coordination(with_floor)
    # Adding two confident-but-floored detectors leaves the OR identical and
    # only mildly moves the (now reliability-weighted) mean — never a collapse.
    assert b.corroboration == a.corroboration
    assert b.score >= ELEVATED


def test_mixed_op_control_stays_below_threshold():
    """Mixed-IO control #2 shape: a weak fingerprint cluster (0.46) + a
    moderate, low-confidence style match. Distinct operations, not one op —
    must NOT reach ELEVATED (precision guard)."""
    findings = [
        _f("temporal_semantic_clique", 0.23, 1.0, 0),
        _f("fingerprint_cluster", 0.46, 1.0, 1),
        _f("age_cohort", 0.35, 1.0, 0),
        _f("style_match", 0.73, 0.55, 1),
    ]
    assert aggregate_coordination(findings).score < ELEVATED


def test_human_profiles_stay_low():
    """Cresci human shape: text detectors abstain (conf 0), structural detectors
    sit low. Score must stay well under the ELEVATED line (FPR guard)."""
    findings = [
        _f("temporal_semantic_clique", 0.5, 0.0, 0),   # abstain (no text)
        _f("fingerprint_cluster", 0.27, 1.0, 0),
        _f("age_cohort", 0.16, 1.0, 0),
        _f("style_match", 0.5, 0.0, 0),                 # abstain (no text)
    ]
    assert aggregate_coordination(findings).score < 0.30


def test_all_abstain_is_zero():
    findings = [
        _f("fingerprint_cluster", 0.5, 0.0, 0),
        _f("style_match", 0.5, 0.0, 0),
    ]
    agg = aggregate_coordination(findings)
    assert agg.score == 0.0 and agg.corroboration == 0.0
    assert aggregate_coordination([]).score == 0.0


def test_reliability_priors_favor_discriminative_detectors():
    """The proven discriminators (fingerprint, style) must out-weight the weak/
    data-shape-sensitive ones (cohort, temporal)."""
    assert DETECTOR_RELIABILITY["fingerprint_cluster"] == 1.0
    assert DETECTOR_RELIABILITY["style_match"] == 1.0
    assert DETECTOR_RELIABILITY["age_cohort"] < 1.0
    assert DETECTOR_RELIABILITY["temporal_semantic_clique"] < 1.0
    # A single strong fingerprint signal corroborates more strongly than a
    # cohort signal of the same score/confidence (the reliability prior bites
    # in the evidence/OR term; a lone detector's mean is just its own score).
    fp = aggregate_coordination([_f("fingerprint_cluster", 0.9, 1.0, 1)])
    co = aggregate_coordination([_f("age_cohort", 0.9, 1.0, 1)])
    assert fp.corroboration > co.corroboration
    # And in a head-to-head mix, the fingerprint-led batch wins outright.
    fp_led = aggregate_coordination([
        _f("fingerprint_cluster", 0.8, 1.0, 1), _f("age_cohort", 0.3, 1.0, 0)])
    co_led = aggregate_coordination([
        _f("fingerprint_cluster", 0.3, 1.0, 0), _f("age_cohort", 0.8, 1.0, 1)])
    assert fp_led.score > co_led.score
