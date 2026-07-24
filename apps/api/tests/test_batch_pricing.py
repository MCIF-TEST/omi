"""Unit tests for batch-based scan credit pricing.

compute_scan_credits: ceil(max_commenters / batch_unit) × credits_per_batch[platform].
Minimum 1 credit regardless of inputs.
"""

from __future__ import annotations

import math

import pytest

from app.core.auth import compute_scan_credits
from app.core.config import Settings


def _settings(**overrides) -> Settings:
    """Build a Settings object with batch-pricing knobs set to the production defaults."""
    defaults = dict(
        scan_batch_unit=50,
        credits_per_batch_youtube=1,
        credits_per_batch_twitter=1,
    )
    defaults.update(overrides)
    return Settings(**defaults)


# ---------------------------------------------------------------------------
# YouTube (1 credit / 50 commenters)
# ---------------------------------------------------------------------------

def test_youtube_single_batch_exact():
    assert compute_scan_credits("youtube", 50, _settings()) == 1


def test_youtube_single_batch_partial():
    assert compute_scan_credits("youtube", 25, _settings()) == 1


def test_youtube_single_batch_one_over():
    assert compute_scan_credits("youtube", 51, _settings()) == 2


def test_youtube_two_batches():
    assert compute_scan_credits("youtube", 100, _settings()) == 2


def test_youtube_three_batches():
    assert compute_scan_credits("youtube", 101, _settings()) == 3


def test_youtube_max_commenters_default():
    s = _settings()
    # Default scan_max_commenters=100 → ceil(100/50)*1 = 2
    assert compute_scan_credits("youtube", s.scan_max_commenters, s) == 2


# ---------------------------------------------------------------------------
# Twitter — SAME flat rate as YouTube now: 1 credit / 50 accounts
# ---------------------------------------------------------------------------

def test_twitter_single_batch_exact():
    assert compute_scan_credits("twitter", 50, _settings()) == 1


def test_twitter_single_batch_partial():
    assert compute_scan_credits("twitter", 1, _settings()) == 1


def test_twitter_two_batches():
    assert compute_scan_credits("twitter", 51, _settings()) == 2


def test_twitter_100_commenters():
    assert compute_scan_credits("twitter", 100, _settings()) == 2


def test_both_platforms_charge_the_same():
    s = _settings()
    for n in [1, 25, 50, 75, 100, 150]:
        assert compute_scan_credits("youtube", n, s) == compute_scan_credits("twitter", n, s), f"n={n}"


def test_production_default_is_1_credit_per_50_both_platforms():
    """Pin the shipped default so a future edit can't silently change what users are charged."""
    assert Settings.model_fields["scan_batch_unit"].default == 50
    assert Settings.model_fields["credits_per_batch_youtube"].default == 1
    assert Settings.model_fields["credits_per_batch_twitter"].default == 1


def test_the_multiplier_still_scales_when_configured():
    """The formula must still honor a higher per-batch rate if a deploy sets one."""
    s = _settings(credits_per_batch_twitter=10)
    assert compute_scan_credits("twitter", 50, s) == 10
    assert compute_scan_credits("twitter", 100, s) == 20


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

def test_zero_commenters_returns_minimum():
    assert compute_scan_credits("youtube", 0, _settings()) >= 1


def test_unknown_platform_falls_back_to_youtube_rate():
    # Unrecognized platform → treated as YouTube
    assert compute_scan_credits("tiktok", 50, _settings()) == 1


def test_custom_batch_unit_and_rates():
    s = _settings(scan_batch_unit=10, credits_per_batch_youtube=2)
    # 25 commenters → ceil(25/10)=3 batches × 2 = 6
    assert compute_scan_credits("youtube", 25, s) == 6


def test_minimum_is_always_one():
    # Even with a 0-commenter edge case and a 0-rate (hypothetical), floor is 1
    s = _settings(credits_per_batch_youtube=0)
    assert compute_scan_credits("youtube", 1, s) == 1


def test_formula_matches_math_ceil():
    s = _settings()
    for n in [1, 10, 49, 50, 51, 99, 100, 150, 200]:
        expected = max(1, math.ceil(n / 50) * 1)
        assert compute_scan_credits("youtube", n, s) == expected, f"n={n}"
