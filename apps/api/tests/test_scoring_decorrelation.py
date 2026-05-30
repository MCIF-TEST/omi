"""Signal decorrelation in the log-odds aggregator (GAP-02).

These pin the overconfidence fix: correlated detectors must not be combined as
if they were independent likelihood sources, and "convergence" must be measured
across independent axes rather than raw detector counts.
"""

from __future__ import annotations

import math

import pytest

from app.core.config import Settings
from app.detection.scoring import _axis_of, _redundancy_factors, aggregate
from app.schemas import SignalResult, Tier


def _sig(name, p, c):
    return SignalResult(name=name, probability=p, confidence=c, evidence=[])


def _settings(**over):
    return Settings(**over)


# --- axis model ----------------------------------------------------------

def test_correlated_detectors_share_an_axis():
    assert _axis_of("semantic") == _axis_of("ai_writing")
    assert _axis_of("temporal") == _axis_of("engagement") == _axis_of("coordination")
    # Independent detectors are their own axis.
    assert _axis_of("profile") == "profile"
    assert _axis_of("voice") == "voice"
    assert _axis_of("memory") == "memory"
    assert _axis_of("profile") != _axis_of("voice")


# --- redundancy factors --------------------------------------------------

def test_redundancy_discounts_weaker_member_of_a_group():
    s = _settings()
    prior_logit = math.log(s.prior_probability / (1 - s.prior_probability))
    signals = [_sig("semantic", 0.8, 0.9), _sig("ai_writing", 0.7, 0.6)]
    factors, notes = _redundancy_factors(signals, {"semantic": 1.2, "ai_writing": 0.8},
                                         s, prior_logit)
    # Strongest contributor keeps full weight; the other is discounted.
    assert factors["semantic"] == 1.0
    assert factors["ai_writing"] == pytest.approx(s.decorrelation_redundancy_content)
    assert notes and "text-pattern" in notes[0]


def test_redundancy_compounds_for_third_member():
    s = _settings()
    prior_logit = math.log(s.prior_probability / (1 - s.prior_probability))
    signals = [_sig("temporal", 0.9, 0.9), _sig("engagement", 0.85, 0.8),
               _sig("coordination", 0.8, 0.7)]
    w = {"temporal": 1.0, "engagement": 0.9, "coordination": 0.9}
    factors, _ = _redundancy_factors(signals, w, s, prior_logit)
    r = s.decorrelation_redundancy_timing
    ranked = sorted(factors, key=lambda n: factors[n], reverse=True)
    assert factors[ranked[0]] == 1.0
    assert factors[ranked[1]] == pytest.approx(r)
    assert factors[ranked[2]] == pytest.approx(r ** 2)


def test_redundancy_noop_for_single_member_and_independent_detectors():
    s = _settings()
    prior_logit = math.log(s.prior_probability / (1 - s.prior_probability))
    signals = [_sig("semantic", 0.8, 0.9), _sig("profile", 0.8, 0.9)]
    factors, notes = _redundancy_factors(signals, {"semantic": 1.2, "profile": 0.7},
                                         s, prior_logit)
    assert factors == {"semantic": 1.0, "profile": 1.0}
    assert notes == []


def test_disabling_decorrelation_restores_independent_factors():
    s = _settings(decorrelation_redundancy_content=1.0)
    prior_logit = math.log(s.prior_probability / (1 - s.prior_probability))
    signals = [_sig("semantic", 0.8, 0.9), _sig("ai_writing", 0.7, 0.6)]
    factors, notes = _redundancy_factors(signals, {"semantic": 1.2, "ai_writing": 0.8},
                                         s, prior_logit)
    assert factors == {"semantic": 1.0, "ai_writing": 1.0}
    assert notes == []


# --- end-to-end aggregation behavior -------------------------------------

def test_correlated_pair_scores_lower_than_independent_pair():
    """Two correlated detectors firing identically must yield a LOWER overall
    than two independent detectors firing identically — that is the whole point
    of decorrelation."""
    # Use the timing group (temporal+engagement share an axis and are both
    # scored). The content group's second member, ai_writing, is supplemental
    # (GAP-03) and no longer participates in the composite, so it can't be used
    # to demonstrate the decorrelation of two *scored* detectors.
    correlated = aggregate([_sig("temporal", 0.85, 0.8), _sig("engagement", 0.85, 0.8)])
    independent = aggregate([_sig("semantic", 0.85, 0.8), _sig("profile", 0.85, 0.8)])
    assert correlated.overall_probability < independent.overall_probability
    assert correlated.confidence < independent.confidence
    assert any("Discounted overlapping" in a for a in correlated.score_adjustments)
    assert independent.score_adjustments == [] or all(
        "Discounted" not in a for a in independent.score_adjustments)


def test_three_correlated_signals_do_not_earn_convergence_bonus():
    """temporal+engagement+coordination are one axis; they must NOT trigger the
    3-axis convergence bonus that three genuinely independent detectors would."""
    correlated = aggregate([
        _sig("temporal", 0.7, 0.7),
        _sig("engagement", 0.7, 0.7),
        _sig("coordination", 0.7, 0.7),
    ])
    independent = aggregate([
        _sig("temporal", 0.7, 0.7),
        _sig("semantic", 0.7, 0.7),
        _sig("profile", 0.7, 0.7),
    ])
    assert not any("Convergence bonus" in a for a in correlated.score_adjustments)
    assert any("Convergence bonus" in a for a in independent.score_adjustments)
    # The independent triad converges across 3 axes → strictly stronger verdict.
    assert independent.overall_probability > correlated.overall_probability


def test_two_correlated_confident_signals_cannot_reach_high():
    """Two detectors on the same axis are not independent corroboration, so even
    at high probability they are capped below HIGH."""
    # temporal+engagement share the behavioral_timing axis (both scored).
    res = aggregate([_sig("temporal", 0.97, 0.95), _sig("engagement", 0.97, 0.95)])
    assert res.tier != Tier.HIGH
    assert any("Capped below HIGH" in a for a in res.score_adjustments)


def test_two_independent_confident_signals_may_reach_high():
    """Two detectors on different axes ARE corroboration and may reach HIGH."""
    res = aggregate([_sig("semantic", 0.95, 0.95), _sig("profile", 0.95, 0.95)])
    assert res.tier == Tier.HIGH
    assert not any("Capped below HIGH" in a for a in res.score_adjustments)


def test_clean_account_has_no_adjustments():
    res = aggregate([_sig("semantic", 0.1, 0.8), _sig("profile", 0.1, 0.8)])
    assert res.tier == Tier.LOW
    assert res.score_adjustments == []


def test_decorrelation_setting_changes_only_the_score_not_the_signals():
    """Toggling decorrelation must not mutate the detector outputs themselves —
    only the aggregate score/confidence and the adjustment notes.

    Both signals here share one axis, so the single-axis cap pins overall at the
    ELEVATED ceiling in both runs; the decorrelation effect is therefore visible
    in reported *confidence* (shared evidence no longer inflates it)."""
    # Timing group (both scored); toggle its redundancy factor.
    sigs = [_sig("temporal", 0.85, 0.8), _sig("engagement", 0.85, 0.8)]
    on = aggregate(sigs, _settings())
    off = aggregate(sigs, _settings(decorrelation_redundancy_timing=1.0))
    assert off.confidence > on.confidence
    assert [s.probability for s in on.signals] == [s.probability for s in off.signals]
