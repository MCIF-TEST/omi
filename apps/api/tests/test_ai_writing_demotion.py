"""GAP-03 — AI-writing demoted to a supplemental (non-scoring) signal.

AI-assisted writing is not evidence of inauthenticity: the stylometric "tells"
(low burstiness, hedging boilerplate, em-dashes, templated openings) are produced
just as readily by ESL writers, formal/professional writers, and the large
population of legitimate users who run text through Grammarly or an LLM. These
tests pin the contract that the ai_writing detector still runs and is surfaced
for context, but can never raise an account's suspicion on its own or in
combination.
"""

from __future__ import annotations

import pytest

from app.detection.scoring import SUPPLEMENTAL_DETECTORS, aggregate
from app.intelligence.omiscore import compute_omiscore
from app.intelligence.signals import (
    CONTEXTUAL_DIMENSIONS,
    THREAT_DIMENSIONS,
    INTELLIGENCE_DIMENSIONS,
)
from app.schemas import ScanResult, SignalResult, Tier


def _sig(name, p, c, evidence=None, sub=None):
    return SignalResult(name=name, probability=p, confidence=c,
                        evidence=evidence or [], sub_signals=sub or {})


# --- the supplemental contract -------------------------------------------

def test_ai_writing_is_registered_supplemental():
    assert "ai_writing" in SUPPLEMENTAL_DETECTORS


def test_aggregate_stamps_supplemental_flag():
    res = aggregate([_sig("ai_writing", 0.95, 0.9), _sig("semantic", 0.2, 0.6)])
    ai = next(s for s in res.signals if s.name == "ai_writing")
    assert ai.supplemental is True
    # Non-supplemental signals keep the default.
    sem = next(s for s in res.signals if s.name == "semantic")
    assert sem.supplemental is False


def test_high_confidence_ai_writing_alone_stays_low():
    """A maxed-out ai_writing signal with nothing else must NOT raise the tier."""
    res = aggregate([_sig("ai_writing", 0.99, 1.0, ["heavy AI tells"])])
    assert res.tier == Tier.LOW
    assert res.overall_probability < 0.25


def test_ai_writing_does_not_change_the_composite_at_all():
    """The composite is identical with or without the ai_writing signal present —
    proof it contributes nothing to suspicion."""
    base = [_sig("semantic", 0.6, 0.7), _sig("profile", 0.55, 0.6)]
    without = aggregate(list(base))
    with_ai = aggregate(list(base) + [_sig("ai_writing", 0.97, 0.95)])
    assert with_ai.overall_probability == pytest.approx(without.overall_probability)
    assert with_ai.tier == without.tier
    assert with_ai.confidence == pytest.approx(without.confidence)


def test_ai_writing_cannot_complete_a_convergence_bonus():
    """Two real axes + a maxed ai_writing must NOT earn the 3-axis convergence
    bonus — ai_writing is not an independent corroborating axis."""
    sigs = [
        _sig("temporal", 0.7, 0.7),
        _sig("semantic", 0.7, 0.7),
        _sig("ai_writing", 0.95, 0.95),
    ]
    res = aggregate(sigs)
    assert not any("Convergence bonus" in a for a in res.score_adjustments)


def test_ai_writing_never_appears_in_reasons_or_intent():
    """Even at high probability, ai_writing must not produce a 'why flagged'
    reason or drive intent inference."""
    sigs = [
        _sig("engagement", 0.8, 0.7, ["promo url in every comment"]),
        _sig("ai_writing", 0.95, 0.95, ["burstiness matches AI"]),
    ]
    res = aggregate(sigs)
    assert all("AI-generation" not in r and "AI-writing" not in r for r in res.reasons)
    assert res.suspected_intent != "ai_content"


def test_ai_writing_not_a_weak_signal_penalty():
    """A missing/low-confidence ai_writing must not be reported as a weak signal
    lowering scan confidence — it isn't part of the suspicion model."""
    res = aggregate([_sig("semantic", 0.2, 0.6)])  # no ai_writing at all
    assert all("AI tells" not in w and "ai_writing" not in w for w in res.weak_signals)


# --- intelligence layer: ai_generation is contextual, not a threat -------

def test_ai_generation_excluded_from_threat_dimensions():
    assert "ai_generation_probability" not in THREAT_DIMENSIONS
    assert "ai_generation_probability" in CONTEXTUAL_DIMENSIONS


def test_authenticity_does_not_include_ai_writing():
    """Penalising AI-assisted phrasing as 'inauthentic' is the harm we removed."""
    auth = INTELLIGENCE_DIMENSIONS["authenticity_score"]
    detectors = {c.detector for c in auth.contributions}
    assert "ai_writing" not in detectors


def _scan_with(signals, prob, tier) -> ScanResult:
    return ScanResult(overall_probability=prob, confidence=0.7, tier=tier,
                      signals=signals, summary="", subject="t")


def test_omiscore_reports_ai_generation_but_excludes_it_from_composite():
    """High AI-generation must be reported (for context) yet not inflate the
    composite omi_score or become the primary threat."""
    # An organic account whose only elevated reading is AI-writing style.
    signals = [
        _sig("temporal", 0.15, 0.7), _sig("semantic", 0.12, 0.7),
        _sig("voice", 0.2, 0.6), _sig("profile", 0.18, 0.6),
        _sig("ai_writing", 0.95, 0.9, ["AI tells"]),
    ]
    scan = _scan_with(signals, prob=0.12, tier=Tier.LOW)
    omi = compute_omiscore(scan)
    # AI generation is reported and high…
    assert omi.ai_generation_probability > 50
    # …but the composite stays low-risk and AI isn't the primary threat.
    assert omi.risk_level == "low"
    assert omi.primary_threat != "ai_generation_probability"
    # The dimension is marked contextual in the explainability payload.
    ai_dim = next(d for d in omi.dimensions if d.key == "ai_generation_probability")
    assert ai_dim.is_contextual is True
    # And its evidence does not leak into the headline top-evidence roll-up.
    assert all("AI tells" not in e for e in omi.top_evidence)


def test_omiscore_ai_evidence_absent_from_top_evidence_even_when_spammy():
    """When a genuinely spammy account also writes like AI, the AI evidence
    must still be excluded from the threat roll-up."""
    signals = [
        _sig("engagement", 0.9, 0.8, ["every comment has a promo link"]),
        _sig("semantic", 0.85, 0.8, ["near-identical templates"]),
        _sig("ai_writing", 0.9, 0.9, ["AI burstiness signature"]),
    ]
    scan = _scan_with(signals, prob=0.7, tier=Tier.ELEVATED)
    omi = compute_omiscore(scan)
    assert all("AI burstiness" not in e for e in omi.top_evidence)
