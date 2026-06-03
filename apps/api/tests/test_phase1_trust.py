"""Tier-2 Phase-1 trust fixes.

- Coordination intent corroboration guard: a single coordination method is
  "possible coordination", not an accusatory "campaign"; two+ independent
  methods (or narrative-injection) is the confident call. The score lift is
  unchanged (rescue benchmark unaffected) — only the named intent differs.
- Honest amplification framing: the OmiScore amplification dimension is INFERRED
  from behaviour, not a measurement of actual reach.
"""

from __future__ import annotations

from app.detection.scoring import _infer_intent, aggregate
from app.intelligence.signals import INTELLIGENCE_DIMENSIONS
from app.schemas import SignalResult, Tier


def _coord(p: float, c: float, methods: int) -> SignalResult:
    return SignalResult(
        name="coordination", probability=p, confidence=c,
        sub_signals={"detector_count": float(methods)},
    )


def test_single_method_coordination_is_not_a_campaign():
    code, label = _infer_intent([_coord(0.85, 0.75, 1)], Tier.HIGH)
    assert code == "possible_coordination"
    assert "uncorroborated" in label.lower()


def test_corroborated_coordination_is_a_campaign():
    code, _label = _infer_intent([_coord(0.85, 0.95, 2)], Tier.HIGH)
    assert code == "coordinated_campaign"


def test_coordination_lift_preserved__only_the_intent_label_differs():
    # Both single- and multi-method coordination still lift the score out of LOW
    # (the rescue path is untouched); only the named intent is gated by corroboration.
    r1 = aggregate([_coord(0.85, 0.75, 1)])
    r2 = aggregate([_coord(0.85, 0.95, 2)])
    assert r1.tier != Tier.LOW and r2.tier != Tier.LOW
    assert r1.suspected_intent == "possible_coordination"
    assert r2.suspected_intent == "coordinated_campaign"


def test_amplification_dimension_framed_as_inferred_not_measured_reach():
    spec = INTELLIGENCE_DIMENSIONS["amplification_probability"]
    assert spec.key == "amplification_probability"  # public API key unchanged
    d = spec.description.lower()
    assert "inferred" in d and "not a measurement" in d
