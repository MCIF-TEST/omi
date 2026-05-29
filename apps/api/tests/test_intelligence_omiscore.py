"""Tests for the OmiScore intelligence engine.

These pin the Phase 4 output contract (the flat 0–100 envelope + risk_level)
and the explainability guarantees (every dimension traces to detectors and
evidence). They also guard the registry against typos that would silently
zero a dimension.
"""

from __future__ import annotations

from app.intelligence import OmiScore, compute_omiscore
from app.intelligence.signals import (
    INTELLIGENCE_DIMENSIONS,
    all_referenced_detectors,
)
from app.intelligence.omiscore import _risk_level_for
from app.schemas import ScanResult, SignalResult, Tier


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_VALID_DETECTORS = {
    "temporal", "semantic", "ai_writing", "voice",
    "engagement", "profile", "memory", "coordination",
}


def _sig(name: str, p: float, c: float, evidence=None, sub=None) -> SignalResult:
    return SignalResult(
        name=name, probability=p, confidence=c,
        evidence=evidence or [], sub_signals=sub or {},
    )


def _clean_scan() -> ScanResult:
    """An organic-looking account: all detectors low probability, decent confidence."""
    return ScanResult(
        overall_probability=0.12,
        confidence=0.7,
        tier=Tier.LOW,
        signals=[
            _sig("temporal", 0.15, 0.7),
            _sig("semantic", 0.10, 0.7),
            _sig("ai_writing", 0.12, 0.6),
            _sig("voice", 0.20, 0.6),
            _sig("engagement", 0.10, 0.6),
            _sig("profile", 0.18, 0.6),
        ],
        summary="",
        subject="organic_user",
    )


def _spam_bot_scan() -> ScanResult:
    """A spam/AI bot: high engagement+semantic+ai_writing, in a coordination cluster."""
    return ScanResult(
        overall_probability=0.86,
        confidence=0.75,
        tier=Tier.HIGH,
        signals=[
            _sig("temporal", 0.80, 0.7, ["Posts every 4.0 min like clockwork"]),
            _sig("semantic", 0.88, 0.8, ["92% of comments are near-identical templates"]),
            _sig("ai_writing", 0.84, 0.7, ["Writing burstiness matches AI generation"]),
            _sig("voice", 0.70, 0.5, ["First-person voice almost absent"]),
            _sig("engagement", 0.90, 0.8, ["Every comment includes a promo URL"]),
            _sig("profile", 0.60, 0.6, ["Account created 3 days ago"]),
            _sig("coordination", 0.85, 0.8, ["In a 6-account fingerprint cluster"],
                 {"detector_count": 3.0}),
        ],
        summary="",
        subject="spam_bot_42",
    )


# ---------------------------------------------------------------------------
# Registry integrity
# ---------------------------------------------------------------------------

def test_registry_references_only_real_detectors():
    """A typo'd detector name would silently zero a dimension — catch it here."""
    assert all_referenced_detectors() <= _VALID_DETECTORS


def test_every_dimension_has_contributions():
    for key, spec in INTELLIGENCE_DIMENSIONS.items():
        assert spec.contributions, f"dimension {key} has no contributions"
        total_w = sum(c.weight for c in spec.contributions)
        assert total_w > 0, f"dimension {key} has zero total weight"


# ---------------------------------------------------------------------------
# Output contract
# ---------------------------------------------------------------------------

def test_omiscore_contract_shape():
    score = compute_omiscore(_spam_bot_scan())
    assert isinstance(score, OmiScore)
    # All flat fields present and in range.
    for field in ("omi_score", "authenticity_score", "coordination_probability",
                  "amplification_probability", "spam_probability",
                  "ai_generation_probability"):
        val = getattr(score, field)
        assert 0.0 <= val <= 100.0, f"{field}={val} out of range"
    assert score.risk_level in ("low", "medium", "high")


def test_clean_account_scores_low_and_authentic():
    score = compute_omiscore(_clean_scan())
    assert score.risk_level == "low"
    assert score.omi_score < 35.0
    # Organic account → high authenticity.
    assert score.authenticity_score > 60.0
    assert score.primary_threat is None


def test_spam_bot_scores_high_with_threat_dimensions():
    score = compute_omiscore(_spam_bot_scan())
    assert score.risk_level == "high"
    assert score.omi_score >= 65.0
    # Spam + AI + coordination should all be elevated.
    assert score.spam_probability > 50.0
    assert score.ai_generation_probability > 50.0
    assert score.coordination_probability > 50.0
    # Authenticity is the inverse — should be low for a bot.
    assert score.authenticity_score < 40.0
    assert score.primary_threat in {
        "spam_probability", "ai_generation_probability",
        "amplification_probability", "coordination_probability",
    }


# ---------------------------------------------------------------------------
# Explainability
# ---------------------------------------------------------------------------

def test_every_dimension_is_traceable():
    score = compute_omiscore(_spam_bot_scan())
    by_key = {d.key: d for d in score.dimensions}
    # Spam dimension must trace back to engagement/semantic detectors.
    spam = by_key["spam_probability"]
    contributing = {c.detector for c in spam.contributions}
    assert contributing & {"engagement", "semantic"}
    # Contribution shares within a dimension sum to ~1.0 (confidence-weighted).
    share = sum(c.weight_share for c in spam.contributions)
    assert abs(share - 1.0) < 1e-6 or share == 0.0


def test_top_evidence_is_populated_for_threats():
    score = compute_omiscore(_spam_bot_scan())
    assert score.top_evidence, "expected evidence strings for a high-risk account"
    # Evidence is deduped.
    assert len(score.top_evidence) == len(set(score.top_evidence))


def test_missing_detectors_degrade_gracefully():
    """A bare scan (no signals) must not crash and must report low confidence."""
    bare = ScanResult(overall_probability=0.3, confidence=0.0, tier=Tier.MODERATE,
                      signals=[], summary="", subject="unknown")
    score = compute_omiscore(bare)
    assert isinstance(score, OmiScore)
    # No evidence → every threat dimension reports zero confidence.
    for d in score.dimensions:
        assert d.confidence == 0.0


def test_coordination_needs_the_coordination_detector():
    """Without a coordination signal, that dimension reports zero confidence
    (not a misleading neutral score)."""
    scan = _clean_scan()  # has no coordination signal
    score = compute_omiscore(scan)
    coord = next(d for d in score.dimensions if d.key == "coordination_probability")
    assert coord.confidence == 0.0


# ---------------------------------------------------------------------------
# Risk thresholds
# ---------------------------------------------------------------------------

def test_risk_level_cutoffs():
    assert _risk_level_for(10.0) == "low"
    assert _risk_level_for(34.9) == "low"
    assert _risk_level_for(35.0) == "medium"
    assert _risk_level_for(64.9) == "medium"
    assert _risk_level_for(65.0) == "high"
    assert _risk_level_for(100.0) == "high"
