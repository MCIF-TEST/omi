"""Tests for the ML feature contract, export, and no-op serving scorer.

The feature contract is the train/serve interface — these tests pin its
shape so an accidental reorder/removal (which would silently break every
trained model) fails loudly in CI.
"""

from __future__ import annotations

from app.ml.features import (
    FEATURE_DIM,
    FEATURE_NAMES,
    FEATURE_SCHEMA_VERSION,
    build_feature_vector,
    feature_record,
)
from app.ml.scorer import MLScorer, _tier_for
from app.memory.fingerprint import extract_fingerprint
from app.schemas import Profile, ScanResult, SignalResult, Tier


def _scan(prob: float = 0.6, conf: float = 0.5) -> ScanResult:
    return ScanResult(
        overall_probability=prob,
        confidence=conf,
        tier=Tier.ELEVATED,
        signals=[
            SignalResult(name="temporal", probability=0.7, confidence=0.6,
                         sub_signals={"interval_cov": 0.2, "quiet_hours_count": 8.0,
                                      "burst_ratio": 5.0, "peak_hourly_rate": 6.0}),
            SignalResult(name="semantic", probability=0.8, confidence=0.7,
                         sub_signals={"mean_pairwise_cosine": 0.9, "top_cluster_mass": 0.6,
                                      "mean_ngram_jaccard": 0.5}),
            SignalResult(name="ai_writing", probability=0.55, confidence=0.4,
                         sub_signals={"burstiness": 0.3, "hedge_phrase_rate": 0.1,
                                      "em_dash_rate": 0.2, "sentence_start_repetition": 0.3}),
            SignalResult(name="profile", probability=0.5, confidence=0.5,
                         sub_signals={"handle_entropy": 3.0, "posts_per_day": 20.0,
                                      "follower_following_ratio": 0.5, "bio_quality": 10.0}),
            SignalResult(name="engagement", probability=0.6, confidence=0.5,
                         sub_signals={"emoji_density": 0.1, "url_inclusion_rate": 0.3,
                                      "emoji_burst_rate": 0.2, "engagement_bait_rate": 0.1}),
        ],
        summary="",
    )


def _profile() -> Profile:
    return Profile(platform="youtube", handle="test", follower_count=1000,
                   following_count=500, verified=False)


# ---------------------------------------------------------------------------
# Feature contract
# ---------------------------------------------------------------------------

def test_feature_dim_matches_names():
    assert FEATURE_DIM == len(FEATURE_NAMES)
    assert FEATURE_SCHEMA_VERSION >= 1


def test_build_feature_vector_length_and_range():
    vec = build_feature_vector(_scan(), profile=_profile(), post_count=30)
    assert len(vec) == FEATURE_DIM
    # Every feature is finite; fingerprint + detector blocks are 0..1.
    assert all(isinstance(x, float) for x in vec)
    assert all(0.0 <= x <= 1.0 for x in vec)


def test_fingerprint_block_matches_canonical_extractor():
    """The first 21 features must equal the persisted fingerprint exactly —
    otherwise serving features diverge from what's stored on accounts."""
    scan = _scan()
    canonical = extract_fingerprint(scan)
    vec = build_feature_vector(scan, profile=_profile(), post_count=10)
    assert vec[:len(canonical)] == canonical


def test_feature_record_is_named():
    rec = feature_record(_scan(), profile=_profile(), post_count=5)
    assert set(rec.keys()) == set(FEATURE_NAMES)
    assert "fp_overall_probability" in rec
    assert "det_temporal_probability" in rec
    assert "meta_log_followers" in rec


def test_missing_detectors_default_neutral():
    """A scan with no signals still yields a full-width vector (neutral
    fill), so partial scans don't crash the model."""
    bare = ScanResult(overall_probability=0.3, confidence=0.1, tier=Tier.MODERATE,
                      signals=[], summary="")
    vec = build_feature_vector(bare, profile=None, post_count=0)
    assert len(vec) == FEATURE_DIM


# ---------------------------------------------------------------------------
# Scorer no-op behavior (no model artifact present)
# ---------------------------------------------------------------------------

def test_scorer_noop_when_disabled():
    from app.core.config import Settings
    settings = Settings(use_ml_scorer=False)
    scan = _scan()
    out = MLScorer().rescore(scan, profile=_profile(), settings=settings)
    assert out is scan  # untouched


def test_scorer_noop_when_no_model_path():
    from app.core.config import Settings
    settings = Settings(use_ml_scorer=True, ml_model_path=None)
    scorer = MLScorer()
    assert scorer.is_active(settings) is False
    out = scorer.rescore(_scan(), profile=_profile(), settings=settings)
    assert out.overall_probability == _scan().overall_probability


def test_tier_cutoffs_match_engine():
    assert _tier_for(0.1) == Tier.LOW
    assert _tier_for(0.3) == Tier.MODERATE
    assert _tier_for(0.6) == Tier.ELEVATED
    assert _tier_for(0.9) == Tier.HIGH
