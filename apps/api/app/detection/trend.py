"""Trend analysis over an account's scan history.

Pure function — no I/O. Takes a list of (timestamp, probability) points
and returns a categorical trend + linear slope + volatility metric.

Used by /v1/accounts/{platform}/{external_id}/history to answer the
question "is this account getting worse / better / staying stable over
time?". Surfaces in the UI as a trend chip on the account page.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

TrendDirection = Literal["stable", "rising", "falling", "volatile", "insufficient"]


@dataclass
class TrendAnalysis:
    direction: TrendDirection
    # Linear-regression slope on probability vs. scan index (0..n).
    # Positive = trending toward more suspicion over time.
    slope: float
    # Standard deviation of probabilities — high = noisy account.
    volatility: float
    # Difference between most recent prob and oldest prob (signed).
    net_change: float
    # n scans considered.
    sample_size: int
    # Friendly one-liner for the UI.
    summary: str


def analyze_trend(points: list[tuple[datetime, float]]) -> TrendAnalysis:
    """Categorize an account's probability-over-time.

    ``points`` should be sorted oldest → newest. Probabilities are 0..1.
    """
    n = len(points)
    if n < 2:
        return TrendAnalysis(
            direction="insufficient",
            slope=0.0,
            volatility=0.0,
            net_change=0.0,
            sample_size=n,
            summary=(
                "Only one scan on file — re-scan in a few days to start "
                "tracking this account's trend." if n == 1
                else "No scan history yet."
            ),
        )

    probs = [p for _, p in points]
    mean = sum(probs) / n

    # Linear regression: y = slope*x + intercept where x = index
    xs = list(range(n))
    x_mean = sum(xs) / n
    num = sum((xs[i] - x_mean) * (probs[i] - mean) for i in range(n))
    den = sum((x - x_mean) ** 2 for x in xs) or 1.0
    slope = num / den
    intercept = mean - slope * x_mean

    # Residual standard deviation — noise around the regression line.
    # This is what distinguishes "smooth monotone rise" from "erratic
    # swings": a monotone series has near-zero residual after detrending.
    residuals = [probs[i] - (slope * xs[i] + intercept) for i in range(n)]
    residual_var = sum(r * r for r in residuals) / n
    volatility = residual_var ** 0.5

    net_change = probs[-1] - probs[0]

    # Thresholds — tuned conservatively. Volatile only when residual noise
    # is large AND there's no clear directional trend.
    if volatility >= 0.12 and abs(slope) < 0.08:
        direction: TrendDirection = "volatile"
    elif slope >= 0.05:
        direction = "rising"
    elif slope <= -0.05:
        direction = "falling"
    else:
        direction = "stable"

    summary = _trend_summary(direction, n, net_change, volatility)
    return TrendAnalysis(
        direction=direction,
        slope=slope,
        volatility=volatility,
        net_change=net_change,
        sample_size=n,
        summary=summary,
    )


def _trend_summary(d: TrendDirection, n: int, net: float, vol: float) -> str:
    pct_net = int(round(abs(net) * 100))
    if d == "rising":
        return (
            f"Score has risen {pct_net} points over {n} scans — this account "
            "is trending toward more suspicious patterns."
        )
    if d == "falling":
        return (
            f"Score has fallen {pct_net} points over {n} scans — this account "
            "is trending more authentic over time."
        )
    if d == "volatile":
        return (
            f"Score moves erratically across {n} scans (σ ≈ {int(round(vol*100))} points) — "
            "behavior is inconsistent, worth a closer look."
        )
    return (
        f"Score has stayed stable across {n} scans (σ ≈ {int(round(vol*100))} points)."
    )
