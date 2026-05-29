"""The single feature contract for the learned detector.

Both the training pipeline (Colab) and the serving path (`app.ml.scorer`)
build their input vectors through :func:`build_feature_vector`. That is the
whole point of this module: if training features and serving features are
produced by different code, the model silently degrades in production
(train/serve skew). One function, one source of truth.

The vector has three blocks, concatenated in a fixed order:

1. **Fingerprint block (21 dims)** — the normalized behavioral fingerprint
   already computed for every scan (``app.memory.fingerprint``). These are
   platform-agnostic behavioral features (posting cadence, text repetition,
   AI-writing tells, profile shape, engagement-spam) so a model trained on
   one platform's principles transfers to another.

2. **Detector block (16 dims)** — the (probability, confidence) pair from
   each of the 8 detectors. This lets the model *learn* the aggregation that
   ``app.detection.scoring.aggregate`` currently hand-tunes with fixed
   weights.

3. **Metadata block (5 dims)** — a few raw account-shape features that are
   robust across platforms: log follower count, log following count, account
   age in days (log), verified flag, and post-volume (log).

The order is **append-only**. Adding a feature at the end + bumping
``FEATURE_SCHEMA_VERSION`` is safe. Reordering or removing breaks every
trained artifact — don't.
"""

from __future__ import annotations

import math
from datetime import datetime, timezone

from app.memory.fingerprint import _FEATURES as _FP_FEATURES  # (id, signal, sub, lo, hi)
from app.schemas import Profile, ScanResult, SignalResult


# Bump when the vector layout changes. Model artifacts record the version
# they were trained against; the scorer refuses to load a mismatched model.
FEATURE_SCHEMA_VERSION = 1


# The 8 detectors whose (probability, confidence) we expose to the model, in
# a fixed order. "memory" and "coordination" are injected signals; they may
# be absent on a given scan, in which case both values default to neutral.
_DETECTOR_ORDER: list[str] = [
    "temporal",
    "semantic",
    "ai_writing",
    "voice",
    "engagement",
    "profile",
    "memory",
    "coordination",
]


def _fingerprint_feature_names() -> list[str]:
    names = [f"fp_{fid}" for (fid, _sig, _sub, _lo, _hi) in _FP_FEATURES]
    names += ["fp_overall_probability", "fp_confidence"]
    return names


def _detector_feature_names() -> list[str]:
    out: list[str] = []
    for d in _DETECTOR_ORDER:
        out.append(f"det_{d}_probability")
        out.append(f"det_{d}_confidence")
    return out


_METADATA_FEATURE_NAMES = [
    "meta_log_followers",
    "meta_log_following",
    "meta_log_account_age_days",
    "meta_verified",
    "meta_log_post_count",
]


FEATURE_NAMES: list[str] = (
    _fingerprint_feature_names()
    + _detector_feature_names()
    + _METADATA_FEATURE_NAMES
)

FEATURE_DIM = len(FEATURE_NAMES)


def _clip01(x: float) -> float:
    return max(0.0, min(1.0, float(x)))


def _log1p_norm(value: float | None, scale: float) -> float:
    """log1p of a non-negative count, divided by ``scale`` and clipped to
    [0, 1]. Keeps heavy-tailed counts (followers, posts) in a bounded range
    without a hand-tuned cap. ``None``/negative collapse to 0.0."""
    if value is None or value <= 0:
        return 0.0
    return _clip01(math.log1p(value) / scale)


def _fingerprint_block(scan: ScanResult) -> list[float]:
    """Reproduce the stored fingerprint from a ScanResult's signals.

    Mirrors ``app.memory.fingerprint.extract_fingerprint`` exactly so a
    re-derived block matches the persisted ``fingerprint_json`` byte-for-byte.
    """
    by_name: dict[str, SignalResult] = {s.name: s for s in scan.signals}
    vec: list[float] = []
    for _fid, signal_name, sub_key, lo, hi in _FP_FEATURES:
        sig = by_name.get(signal_name)
        if sig is None or sig.confidence == 0 or sub_key not in sig.sub_signals:
            vec.append(0.5)
            continue
        raw = sig.sub_signals[sub_key]
        if _fid == "follower_ratio_log":
            raw = math.log10(max(1e-3, raw))
        normalized = (raw - lo) / (hi - lo) if hi > lo else 0.5
        vec.append(_clip01(normalized))
    vec.append(_clip01(scan.overall_probability))
    vec.append(_clip01(scan.confidence))
    return vec


def _detector_block(scan: ScanResult) -> list[float]:
    by_name: dict[str, SignalResult] = {s.name: s for s in scan.signals}
    vec: list[float] = []
    for d in _DETECTOR_ORDER:
        sig = by_name.get(d)
        if sig is None:
            # Neutral probability, zero confidence — "this detector said
            # nothing", which the model can learn to treat as a no-op.
            vec.append(0.5)
            vec.append(0.0)
        else:
            vec.append(_clip01(sig.probability))
            vec.append(_clip01(sig.confidence))
    return vec


def _metadata_block(profile: Profile | None, post_count: int) -> list[float]:
    if profile is None:
        return [0.0, 0.0, 0.0, 0.0, _log1p_norm(post_count, scale=6.0)]

    age_days = 0.0
    if profile.created_at is not None:
        created = profile.created_at
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        age_days = max(0.0, (datetime.now(timezone.utc) - created).total_seconds() / 86400.0)

    return [
        _log1p_norm(profile.follower_count, scale=16.0),   # ~e^16 ≈ 9M caps at 1.0
        _log1p_norm(profile.following_count, scale=16.0),
        _log1p_norm(age_days, scale=9.0),                  # ~e^9 ≈ 22yrs caps at 1.0
        1.0 if profile.verified else 0.0,
        _log1p_norm(post_count, scale=6.0),                # ~e^6 ≈ 400 posts caps at 1.0
    ]


def build_feature_vector(
    scan: ScanResult,
    *,
    profile: Profile | None = None,
    post_count: int = 0,
) -> list[float]:
    """Build the model input vector for one account.

    ``scan`` is the rule-engine ScanResult (its signals + fingerprint are the
    bulk of the features). ``profile`` and ``post_count`` add raw account
    shape. The returned list has exactly ``FEATURE_DIM`` entries, ordered to
    match ``FEATURE_NAMES``.
    """
    vec = (
        _fingerprint_block(scan)
        + _detector_block(scan)
        + _metadata_block(profile, post_count)
    )
    assert len(vec) == FEATURE_DIM, (
        f"feature vector dim mismatch: built {len(vec)}, expected {FEATURE_DIM}. "
        "Did you reorder _FEATURES or _DETECTOR_ORDER without bumping the schema?"
    )
    return vec


def feature_record(
    scan: ScanResult,
    *,
    profile: Profile | None = None,
    post_count: int = 0,
) -> dict[str, float]:
    """Same vector as a name→value dict — handy for dataframes / debugging."""
    return dict(zip(FEATURE_NAMES, build_feature_vector(scan, profile=profile, post_count=post_count)))
