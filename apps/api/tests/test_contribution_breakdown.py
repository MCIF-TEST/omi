"""GAP-06 explainability: faithful per-detector contribution breakdown.

The headline guarantee is *faithfulness* — the breakdown is computed from the
exact same log-odds deltas that build the score, so it reconstructs the headline
number rather than narrating a plausible story after the fact. These tests pin
that invariant, the directional attribution (raises / lowers / neutral), the
completeness (exculpatory contributions are shown; low-tier scans still get a
breakdown), and the supplemental handling.
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone

import pytest

from app.core.config import Settings
from app.detection.engine import analyze_account
from app.detection.scoring import aggregate
from app.schemas import Post, Profile, SignalResult, Tier


def _sig(name: str, p: float, c: float, evidence: str | None = None) -> SignalResult:
    return SignalResult(
        name=name, probability=p, confidence=c,
        evidence=[evidence] if evidence else [],
    )


def _sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


# ---------------------------------------------------------------------------
# Faithfulness invariant
# ---------------------------------------------------------------------------

def test_breakdown_reconstructs_the_score():
    """prior_logit + detector_logit_sum + convergence == posterior_logit, and
    sigmoid(posterior) == final probability (uncapped case)."""
    sigs = [
        _sig("semantic", 0.85, 0.7),
        _sig("temporal", 0.7, 0.5),
        _sig("voice", 0.65, 0.4),
    ]
    res = aggregate(sigs, Settings())
    b = res.score_breakdown
    assert b is not None
    reconstructed = b.prior_logit + b.detector_logit_sum + b.convergence_bonus_logit
    assert reconstructed == pytest.approx(b.posterior_logit, abs=1e-9)
    if not b.single_axis_capped:
        assert _sigmoid(b.posterior_logit) == pytest.approx(b.final_probability, abs=1e-9)
        assert b.final_probability == pytest.approx(res.overall_probability, abs=1e-9)


def test_contribution_deltas_sum_to_detector_logit_sum():
    """The per-detector deltas in the breakdown sum to detector_logit_sum exactly."""
    sigs = [
        _sig("semantic", 0.9, 0.8),
        _sig("engagement", 0.75, 0.6),
        _sig("profile", 0.2, 0.9),       # clean-ish, pulls down
    ]
    res = aggregate(sigs, Settings())
    total = sum(c.logit_delta for c in res.contributions)
    assert total == pytest.approx(res.score_breakdown.detector_logit_sum, abs=1e-9)


def test_single_axis_cap_recorded_in_breakdown():
    """A lone confident suspicious axis is capped below HIGH, and the breakdown
    records it: single_axis_capped True and final == the ELEVATED ceiling even
    though the raw posterior implies HIGH."""
    sigs = [_sig("temporal", 0.97, 0.95)]
    res = aggregate(sigs, Settings())
    b = res.score_breakdown
    assert b.single_axis_capped is True
    assert _sigmoid(b.posterior_logit) >= 0.75      # raw says HIGH
    assert res.overall_probability == pytest.approx(0.74)  # but capped to ELEVATED
    assert res.tier == Tier.ELEVATED


# ---------------------------------------------------------------------------
# Directional attribution (raises / lowers / neutral)
# ---------------------------------------------------------------------------

def test_suspicious_detector_raises():
    res = aggregate([_sig("semantic", 0.9, 0.8)], Settings())
    sem = next(c for c in res.contributions if c.name == "semantic")
    assert sem.direction == "raises"
    assert sem.logit_delta > 0


def test_clean_detector_lowers():
    """A detector reporting a below-prior probability pulls the score down."""
    res = aggregate([_sig("semantic", 0.9, 0.8), _sig("profile", 0.03, 0.9)], Settings())
    prof = next(c for c in res.contributions if c.name == "profile")
    assert prof.direction == "lowers"
    assert prof.logit_delta < 0


def test_supplemental_detector_is_neutral_and_zero():
    """ai_writing is supplemental: shown for context, but contributes exactly
    zero to the score and is flagged supplemental."""
    res = aggregate([_sig("semantic", 0.8, 0.7), _sig("ai_writing", 0.95, 0.9)], Settings())
    aiw = next(c for c in res.contributions if c.name == "ai_writing")
    assert aiw.supplemental is True
    assert aiw.logit_delta == 0.0
    assert aiw.direction == "neutral"


def test_zero_confidence_detector_is_neutral():
    res = aggregate([_sig("semantic", 0.8, 0.7), _sig("narrative", 0.5, 0.0)], Settings())
    narr = next(c for c in res.contributions if c.name == "narrative")
    assert narr.logit_delta == 0.0
    assert narr.direction == "neutral"


# ---------------------------------------------------------------------------
# Completeness & ranking
# ---------------------------------------------------------------------------

def test_contributions_present_even_for_low_tier():
    """Unlike ``reasons`` (empty for low tier), the contribution breakdown is
    always populated, so a clean verdict is explained too."""
    res = aggregate([_sig("semantic", 0.05, 0.6), _sig("profile", 0.1, 0.8)], Settings())
    assert res.tier == Tier.LOW
    assert res.reasons == []
    assert len(res.contributions) == 2


def test_contributions_ranked_by_absolute_impact():
    sigs = [
        _sig("voice", 0.62, 0.3),        # small mover
        _sig("semantic", 0.95, 0.95),    # big mover
        _sig("temporal", 0.7, 0.5),      # medium
    ]
    res = aggregate(sigs, Settings())
    scored = [c for c in res.contributions if not c.supplemental and c.logit_delta != 0]
    deltas = [abs(c.logit_delta) for c in scored]
    assert deltas == sorted(deltas, reverse=True)
    assert scored[0].name == "semantic"


def test_impact_shares_in_unit_range_and_sum_to_one():
    sigs = [_sig("semantic", 0.9, 0.8), _sig("engagement", 0.75, 0.6), _sig("profile", 0.2, 0.9)]
    res = aggregate(sigs, Settings())
    movers = [c for c in res.contributions if c.logit_delta != 0]
    for c in res.contributions:
        assert 0.0 <= c.impact <= 1.0
    assert sum(c.impact for c in movers) == pytest.approx(1.0, abs=1e-9)


# ---------------------------------------------------------------------------
# Integration: the exculpatory community anchor is visible
# ---------------------------------------------------------------------------

def test_community_anchor_shows_as_lowering_contribution():
    """An established account's community footprint must appear in the breakdown
    as a 'lowers' contribution — the exculpatory side the suspicious-only
    ``reasons`` list never surfaces."""
    base = datetime(2024, 1, 1, 9, tzinfo=timezone.utc)
    posts = [
        Post(id=f"p{i}", author_handle="acct",
             text="Quarterly results exceeded expectations across most segments today.",
             created_at=base + timedelta(hours=i * 6))
        for i in range(12)
    ]
    prof = Profile(
        handle="bigbrand", follower_count=80_000, following_count=300,
        created_at=datetime.now(timezone.utc) - timedelta(days=2000),
        verified=False, bio="Daily market updates.",
    )
    res = analyze_account(prof, posts)
    comm = next((c for c in res.contributions if c.name == "community"), None)
    assert comm is not None
    assert comm.direction == "lowers"
    assert comm.logit_delta < 0
    assert "community" in comm.headline.lower()


def test_engine_output_carries_breakdown():
    res = analyze_account(
        Profile(handle="x", follower_count=100, created_at=None),
        [Post(id="1", author_handle="x", text="hello world",
              created_at=datetime(2024, 1, 1, tzinfo=timezone.utc))],
    )
    assert res.score_breakdown is not None
    assert len(res.contributions) >= 1
