"""Behavioral fingerprint extraction.

A scan's fingerprint is a fixed-width vector built from each detector's
``sub_signals`` map plus the aggregate score. All entries are normalized to
roughly the ``[0, 1]`` range so Euclidean distance is meaningful across
dimensions.

The dimension list is **append-only**. Adding a new feature is fine; removing
or reordering would invalidate every stored fingerprint, so don't.
"""

from __future__ import annotations

import math

from app.schemas import ScanResult, SignalResult


# (name, getter) pairs. Each getter takes the full {signal_name: SignalResult}
# map and returns a 0..1 float. Missing data returns the neutral 0.5.
_FEATURES: list[tuple[str, str, str, float, float]] = [
    # (feature_id, signal_name, sub_signal_key, low, high)
    # Temporal
    ("interval_cov",        "temporal",   "interval_cov",         0.0, 2.0),
    ("quiet_hours",         "temporal",   "quiet_hours_count",    0.0, 12.0),
    ("burst_ratio",         "temporal",   "burst_ratio",          0.0, 30.0),
    ("peak_hourly_rate",    "temporal",   "peak_hourly_rate",     0.0, 30.0),
    # Semantic
    ("mean_cosine",         "semantic",   "mean_pairwise_cosine", 0.0, 1.0),
    ("top_cluster_mass",    "semantic",   "top_cluster_mass",     0.0, 1.0),
    ("mean_ngram_jaccard",  "semantic",   "mean_ngram_jaccard",   0.0, 1.0),
    # AI writing
    ("burstiness",          "ai_writing", "burstiness",           0.0, 1.2),
    ("hedge_rate",          "ai_writing", "hedge_phrase_rate",    0.0, 0.5),
    ("em_dash_rate",        "ai_writing", "em_dash_rate",         0.0, 1.0),
    ("sentence_start_rep",  "ai_writing", "sentence_start_repetition", 0.0, 1.0),
    # Profile
    ("handle_entropy",      "profile",    "handle_entropy",       0.0, 5.0),
    ("posts_per_day",       "profile",    "posts_per_day",        0.0, 100.0),
    ("follower_ratio_log",  "profile",    "follower_following_ratio", -3.0, 3.0),  # log-transformed
    ("bio_quality",         "profile",    "bio_quality",          0.0, 30.0),
    # Engagement / content-style (append-only; do NOT reorder)
    ("emoji_density",          "engagement", "emoji_density",          0.0, 0.30),
    ("url_inclusion_rate",     "engagement", "url_inclusion_rate",     0.0, 1.0),
    ("emoji_burst_rate",       "engagement", "emoji_burst_rate",       0.0, 1.0),
    ("engagement_bait_rate",   "engagement", "engagement_bait_rate",   0.0, 0.50),
]

FINGERPRINT_DIM = len(_FEATURES) + 2  # + overall_probability, + confidence


def extract_fingerprint(scan: ScanResult) -> list[float]:
    """Build a normalized fingerprint vector from a ScanResult."""
    by_name: dict[str, SignalResult] = {s.name: s for s in scan.signals}
    vec: list[float] = []
    for feature_id, signal_name, sub_key, lo, hi in _FEATURES:
        sig = by_name.get(signal_name)
        if sig is None or sig.confidence == 0 or sub_key not in sig.sub_signals:
            vec.append(0.5)
            continue
        raw = sig.sub_signals[sub_key]
        if feature_id == "follower_ratio_log":
            # Log-transform: stored value is the linear ratio.
            raw = math.log10(max(1e-3, raw))
        normalized = (raw - lo) / (hi - lo) if hi > lo else 0.5
        vec.append(_clip01(normalized))
    vec.append(_clip01(scan.overall_probability))
    vec.append(_clip01(scan.confidence))
    return vec


def euclidean(a: list[float], b: list[float]) -> float:
    """Pure-Python Euclidean over two equal-length normalized vectors."""
    if len(a) != len(b):
        raise ValueError(f"fingerprint dim mismatch: {len(a)} vs {len(b)}")
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))


def _clip01(x: float) -> float:
    return max(0.0, min(1.0, float(x)))
