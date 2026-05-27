"""Temporal cadence detector.

Hypothesis: humans sleep, get distracted, and post at irregular intervals.
Coordinated/scripted accounts tend toward mechanical regularity or impossible
activity windows. We compute four sub-signals and blend them.

All outputs are probabilities of *synthetic-or-coordinated cadence*, never
verdicts.
"""

from __future__ import annotations

import math
from collections import Counter
from datetime import datetime, timezone

from app.schemas import Post, SignalResult


MIN_POSTS_FOR_TEMPORAL = 8


def analyze_temporal(posts: list[Post]) -> SignalResult:
    if len(posts) < MIN_POSTS_FOR_TEMPORAL:
        return SignalResult(
            name="temporal",
            probability=0.5,
            confidence=0.0,
            evidence=[
                f"Insufficient temporal data ({len(posts)} posts < {MIN_POSTS_FOR_TEMPORAL} needed)."
            ],
        )

    sorted_posts = sorted(posts, key=lambda p: p.created_at)
    timestamps = [_to_utc(p.created_at) for p in sorted_posts]

    cov_prob, cov_value = _interval_cov_signal(timestamps)
    sleep_prob, quiet_hours, sleep_meaningful = _sleep_gap_signal(timestamps)
    burst_prob, burst_ratio, peak_rate = _burst_signal(timestamps)

    sub = {
        "interval_cov": cov_value,
        "quiet_hours_count": float(quiet_hours),
        "burst_ratio": burst_ratio,
        "peak_hourly_rate": peak_rate,
    }

    # Blend sub-signals. CoV is the dominant, most reliable tell. Sleep-gap is
    # strong but only meaningful with ≥ ~30h of data, otherwise we treat it as
    # neutral. Burst captures both "too flat" (scheduler) and "too spiky"
    # (coordinated burst) patterns. Weekday/weekend was dropped from Phase 0
    # as too noisy to add weight without calibration data.
    if sleep_meaningful:
        blended = 0.55 * cov_prob + 0.30 * sleep_prob + 0.15 * burst_prob
    else:
        # Re-weight when sleep evidence is unavailable, instead of letting a
        # neutral 0.5 drag a high CoV signal down.
        blended = 0.78 * cov_prob + 0.22 * burst_prob

    evidence: list[str] = []
    if cov_prob > 0.55:
        evidence.append(
            f"Post intervals show unusually low variation (CoV={cov_value:.2f}), "
            "patterns consistent with scheduled or scripted posting."
        )
    if sleep_meaningful and sleep_prob > 0.55:
        evidence.append(
            f"Only {quiet_hours} hours/day show near-zero activity — "
            "limited or absent sleep gap relative to typical human rhythms."
        )
    if burst_prob > 0.55:
        if burst_ratio < 3:
            evidence.append(
                f"Hourly posting rate is unusually flat (peak/median={burst_ratio:.1f}) "
                f"at {peak_rate:.1f} posts/hour — patterns consistent with a scheduler."
            )
        else:
            evidence.append(
                f"Activity bursts {burst_ratio:.1f}× the median hourly rate, "
                "suggesting potential coordination windows."
            )
    if not evidence:
        evidence.append("No strong temporal anomalies detected.")

    # Confidence scales with sample size (asymptote at ~200 posts).
    confidence = min(1.0, len(posts) / 200.0)

    return SignalResult(
        name="temporal",
        probability=_clip01(blended),
        confidence=confidence,
        evidence=evidence,
        sub_signals=sub,
    )


# ---------------------------------------------------------------------------
# Sub-signals
# ---------------------------------------------------------------------------


def _interval_cov_signal(timestamps: list[datetime]) -> tuple[float, float]:
    """Coefficient of variation of inter-post intervals.

    Lower CoV ⇒ more mechanical ⇒ higher synthetic probability.
    """
    intervals = [
        (timestamps[i + 1] - timestamps[i]).total_seconds()
        for i in range(len(timestamps) - 1)
    ]
    intervals = [i for i in intervals if i > 0]
    if not intervals:
        return 0.5, 1.0

    mean = sum(intervals) / len(intervals)
    if mean == 0:
        return 0.5, 0.0
    var = sum((x - mean) ** 2 for x in intervals) / len(intervals)
    cov = math.sqrt(var) / mean

    # Map CoV → probability with a sigmoid centered around CoV=0.7.
    #   cov ≈ 0.0  → ~0.97  (perfectly mechanical)
    #   cov ≈ 0.3  → ~0.88  (very regular)
    #   cov ≈ 0.7  → 0.50   (ambiguous)
    #   cov ≈ 1.0  → ~0.18  (human-like)
    #   cov ≥ 1.5  → ~0.02  (very bursty)
    prob = 1.0 / (1.0 + math.exp(5.0 * (cov - 0.7)))
    return prob, cov


def _sleep_gap_signal(timestamps: list[datetime]) -> tuple[float, int, bool]:
    """Count hours of the day with effectively no activity.

    Humans typically show ≥ 4 such hours. Bot networks running 24/7 show fewer.
    Only meaningful when the data window spans at least ~30 hours; otherwise
    we return (neutral, 0, False) so the caller can re-weight.

    Note: we currently align on UTC. A smarter version would detect the
    account's active timezone and shift accordingly — tracked in
    detection-methods.md as a Phase 1 refinement.
    """
    span_hours = (timestamps[-1] - timestamps[0]).total_seconds() / 3600.0
    if span_hours < 30:
        return 0.5, 0, False

    hour_counts = Counter(ts.hour for ts in timestamps)
    total = sum(hour_counts.values())
    threshold = max(1, total * 0.005)  # < 0.5% of activity counts as "quiet"
    quiet_hours = sum(1 for h in range(24) if hour_counts.get(h, 0) < threshold)

    # 0 quiet hours → very suspicious; ≥ 6 → normal.
    prob = max(0.0, min(1.0, (6 - quiet_hours) / 6.0))
    return prob, quiet_hours, True


def _burst_signal(timestamps: list[datetime]) -> tuple[float, float, float]:
    """Burst signal is U-shaped:

    * ``ratio = peak / median`` near 1 with non-trivial median is suspicious
      (high-volume scheduler — every hour looks identical).
    * ``ratio`` in the normal human range (3-20) is unremarkable.
    * ``ratio`` ≫ 30 indicates extreme bursts that may signal coordinated
      campaigns.
    """
    buckets: Counter[datetime] = Counter()
    for ts in timestamps:
        bucket = ts.replace(minute=0, second=0, microsecond=0)
        buckets[bucket] += 1

    counts = sorted(buckets.values())
    if not counts:
        return 0.5, 0.0, 0.0
    median = counts[len(counts) // 2]
    peak = counts[-1]
    ratio = peak / max(1, median)
    peak_rate = float(peak)

    if ratio < 2.5 and median >= 2:
        # Flat profile with non-trivial median = scheduler signature.
        # More posts per hour → more confident.
        prob = min(0.95, 0.55 + 0.10 * (median - 2))
    elif ratio > 30:
        prob = min(0.90, 0.55 + (ratio - 30) / 60.0)
    else:
        prob = 0.25
    return prob, ratio, peak_rate


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------


def _to_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _clip01(x: float) -> float:
    return max(0.0, min(1.0, x))
