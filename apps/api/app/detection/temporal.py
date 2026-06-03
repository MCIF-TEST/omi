"""Temporal cadence detector.

Hypothesis: humans sleep, get distracted, and post at irregular intervals.
Coordinated/scripted accounts tend toward mechanical regularity or impossible
activity windows. We compute four sub-signals and blend them.

All outputs are probabilities of *synthetic-or-coordinated cadence*, never
verdicts.

Improvements over Phase 0:
* Recency window — the last 30 days of posts are used as the primary
  analysis window when sufficient (≥ MIN_POSTS_FOR_TEMPORAL). Stale
  behaviour from a year ago shouldn't dominate a current risk score.
* Timezone inference — derive a likely UTC offset from the account's
  posting-hour distribution and shift timestamps before computing the
  sleep-gap signal. This avoids false "no sleep gap" verdicts on accounts
  whose peak activity falls in UTC night-time hours.
"""

from __future__ import annotations

import math
from collections import Counter
from datetime import datetime, timedelta, timezone

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
    all_timestamps = [_to_utc(p.created_at) for p in sorted_posts]

    # --- Recency window ---
    # Prefer analysing the last 30 days when there's enough data.
    # Recent behaviour is more relevant than posts from months/years ago.
    now = datetime.now(timezone.utc)
    recent_cutoff = now - timedelta(days=30)
    recent_ts = [t for t in all_timestamps if t >= recent_cutoff]
    primary_ts = recent_ts if len(recent_ts) >= MIN_POSTS_FOR_TEMPORAL else all_timestamps
    using_recent = primary_ts is recent_ts and len(recent_ts) < len(all_timestamps)

    cov_prob, cov_value = _interval_cov_signal(primary_ts)
    burst_prob, burst_ratio, peak_rate = _burst_signal(primary_ts)

    # --- Timezone-aware sleep gap ---
    # Infer the account's likely UTC offset and localise before checking
    # which hours of the day are quiet. Without this, UTC-8 accounts
    # (peak at 20:00–02:00 UTC) look like they never sleep.
    tz_offset = _infer_tz_offset(all_timestamps)
    local_ts = [_shift_hour(t, tz_offset) for t in primary_ts]
    sleep_prob, quiet_hours, sleep_meaningful = _sleep_gap_signal(local_ts)

    sub = {
        "interval_cov": cov_value,
        "quiet_hours_count": float(quiet_hours),
        "burst_ratio": burst_ratio,
        "peak_hourly_rate": peak_rate,
        "inferred_tz_offset_h": float(tz_offset),
    }

    if sleep_meaningful:
        blended = 0.55 * cov_prob + 0.30 * sleep_prob + 0.15 * burst_prob
    else:
        blended = 0.78 * cov_prob + 0.22 * burst_prob

    evidence: list[str] = []
    if using_recent:
        evidence.append(
            f"Analysis focused on the most recent 30 days ({len(recent_ts)} posts)."
        )
    if cov_prob > 0.55:
        evidence.append(
            f"Post intervals show unusually low variation (CoV={cov_value:.2f}), "
            "patterns consistent with scheduled or scripted posting."
        )
    if sleep_meaningful and sleep_prob > 0.55:
        evidence.append(
            f"Only {quiet_hours} hours/day show near-zero activity "
            f"(inferred local time, UTC{tz_offset:+.0f}) — limited sleep gap."
        )
    if burst_prob > 0.55:
        if burst_ratio < 3:
            evidence.append(
                f"Hourly posting rate is unusually flat (peak/median={burst_ratio:.1f}) "
                f"at {peak_rate:.1f} posts/hour — consistent with a scheduler."
            )
        else:
            evidence.append(
                f"Activity bursts {burst_ratio:.1f}× the median hourly rate, "
                "suggesting potential coordination windows."
            )
    if not evidence:
        evidence.append("No strong temporal anomalies detected.")

    confidence = min(1.0, len(primary_ts) / 200.0)
    # Strength-aware: CoV < 0.05 (< 5% variation) is essentially impossible in
    # human posting — it requires machine-precision interval control. Even 8
    # posts at perfect 4-hour intervals are self-evidently scheduled, not a
    # low-confidence reading. Only the sub-5% threshold is this certain; normal
    # automated content bots have natural variation (CoV ≥ 0.1) and are NOT
    # boosted by this path, keeping them at MODERATE as expected.
    if cov_value < 0.05 and cov_prob >= 0.90:
        strength_conf = _clip01(0.25 + 0.35 * (1.0 - cov_value / 0.05))
        confidence = max(confidence, strength_conf)

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
    """Coefficient of variation of inter-post intervals."""
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

    prob = 1.0 / (1.0 + math.exp(5.0 * (cov - 0.7)))
    return prob, cov


def _sleep_gap_signal(timestamps: list[datetime]) -> tuple[float, int, bool]:
    """Count hours of the day with effectively no activity.

    Uses localised timestamps (after timezone inference) so UTC-shifted
    accounts don't get false "no sleep gap" verdicts.
    """
    span_hours = (timestamps[-1] - timestamps[0]).total_seconds() / 3600.0
    if span_hours < 30:
        return 0.5, 0, False

    hour_counts = Counter(ts.hour for ts in timestamps)
    total = sum(hour_counts.values())
    threshold = max(1, total * 0.005)
    quiet_hours = sum(1 for h in range(24) if hour_counts.get(h, 0) < threshold)

    prob = max(0.0, min(1.0, (6 - quiet_hours) / 6.0))
    return prob, quiet_hours, True


def _burst_signal(timestamps: list[datetime]) -> tuple[float, float, float]:
    """U-shaped burst signal: flat profile (scheduler) or extreme spikes (campaign)."""
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
        prob = min(0.95, 0.55 + 0.10 * (median - 2))
    elif ratio > 30:
        prob = min(0.90, 0.55 + (ratio - 30) / 60.0)
    else:
        prob = 0.25
    return prob, ratio, peak_rate


# ---------------------------------------------------------------------------
# Timezone inference
# ---------------------------------------------------------------------------


def _infer_tz_offset(timestamps: list[datetime]) -> int:
    """Estimate UTC offset (hours, integer) from posting-hour distribution.

    Strategy: humans typically post between 08:00–23:00 local time. Find
    the offset that centres the account's peak activity window in that
    daytime band. We try all integer offsets -12..+14 and pick the one
    that minimises the fraction of activity falling in the presumed
    sleep window (00:00–07:00 local).

    Falls back to 0 (UTC) when there are too few timestamps or the
    distribution is too flat to infer anything meaningful.
    """
    if len(timestamps) < 10:
        return 0

    best_offset = 0
    best_score = float("inf")

    for offset in range(-12, 15):
        hours = [(ts.hour + offset) % 24 for ts in timestamps]
        sleep_count = sum(1 for h in hours if 0 <= h < 7)
        # Lower is better — we want the offset that minimises presumed-sleep activity
        score = sleep_count
        if score < best_score:
            best_score = score
            best_offset = offset

    return best_offset


def _shift_hour(ts: datetime, offset_hours: int) -> datetime:
    """Return a datetime with the hour shifted by offset_hours (mod 24).

    Only the hour field is modified — this is intentionally lossy.
    We only use these shifted timestamps for hour-of-day bucketing.
    """
    new_hour = (ts.hour + offset_hours) % 24
    return ts.replace(hour=new_hour)


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------


def _to_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _clip01(x: float) -> float:
    return max(0.0, min(1.0, x))
