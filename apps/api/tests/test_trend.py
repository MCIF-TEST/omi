"""Tests for the trend analysis module."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.detection.trend import analyze_trend


def _series(probs: list[float]) -> list[tuple[datetime, float]]:
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return [(base + timedelta(days=i), p) for i, p in enumerate(probs)]


def test_insufficient_when_empty():
    t = analyze_trend([])
    assert t.direction == "insufficient"
    assert t.sample_size == 0


def test_insufficient_when_single_point():
    t = analyze_trend(_series([0.5]))
    assert t.direction == "insufficient"
    assert t.sample_size == 1


def test_stable_when_flat():
    t = analyze_trend(_series([0.20, 0.21, 0.19, 0.20, 0.22]))
    assert t.direction == "stable"
    assert abs(t.net_change) < 0.05
    assert t.volatility < 0.05


def test_rising_when_monotone_up():
    t = analyze_trend(_series([0.20, 0.30, 0.40, 0.55, 0.70]))
    assert t.direction == "rising"
    assert t.slope > 0.05
    assert t.net_change > 0.4


def test_falling_when_monotone_down():
    t = analyze_trend(_series([0.80, 0.65, 0.50, 0.35, 0.20]))
    assert t.direction == "falling"
    assert t.slope < -0.05
    assert t.net_change < -0.4


def test_volatile_when_noisy():
    # Big swings — high variance, low net slope
    t = analyze_trend(_series([0.20, 0.85, 0.25, 0.80, 0.15, 0.78, 0.30]))
    assert t.direction == "volatile"
    assert t.volatility >= 0.15


def test_summary_is_present():
    t = analyze_trend(_series([0.20, 0.30, 0.40]))
    assert t.summary
    assert isinstance(t.summary, str)
