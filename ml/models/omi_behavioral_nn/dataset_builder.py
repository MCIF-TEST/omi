"""Dataset builder for the Omi Behavioral NN — OMI_FEATURE_SCHEMA_V1 contract.

Torch-free core (importable + testable without PyTorch): it maps a feature dict
to the canonical, ordered 42-dim vector defined by
``ml/features/OMI_FEATURE_SCHEMA_V1.md`` (== ``apps/api/app/ml/features.py``
``build_feature_vector``, ``FEATURE_SCHEMA_VERSION = 1``). The thin PyTorch
wrappers (``BehavioralDataset``, ``to_tensor``) import torch lazily.

Contract (append-only; reorder/remove breaks artifacts):
  21 fingerprint (fp_*) + 16 detector (det_<d>_{probability,confidence}) + 5
  metadata (meta_*) = 42 dims, all normalized to [0, 1].
  An absent detector defaults to (probability=0.5, confidence=0.0).
"""
from __future__ import annotations

import numpy as np

FEATURE_SCHEMA_VERSION = 1

# --- A1 fingerprint (21) — name -> raw (lo, hi) normalization range ----------- #
FINGERPRINT_RANGES: dict[str, tuple[float, float]] = {
    "fp_interval_cov": (0.0, 2.0),
    "fp_quiet_hours": (0.0, 12.0),
    "fp_burst_ratio": (0.0, 30.0),
    "fp_peak_hourly_rate": (0.0, 30.0),
    "fp_mean_cosine": (0.0, 1.0),
    "fp_top_cluster_mass": (0.0, 1.0),
    "fp_mean_ngram_jaccard": (0.0, 1.0),
    "fp_burstiness": (0.0, 1.2),
    "fp_hedge_rate": (0.0, 0.5),
    "fp_em_dash_rate": (0.0, 1.0),
    "fp_sentence_start_rep": (0.0, 1.0),
    "fp_handle_entropy": (0.0, 5.0),
    "fp_posts_per_day": (0.0, 100.0),
    "fp_follower_ratio_log": (-3.0, 3.0),
    "fp_bio_quality": (0.0, 30.0),
    "fp_emoji_density": (0.0, 0.30),
    "fp_url_inclusion_rate": (0.0, 1.0),
    "fp_emoji_burst_rate": (0.0, 1.0),
    "fp_engagement_bait_rate": (0.0, 0.50),
    "fp_overall_probability": (0.0, 1.0),
    "fp_confidence": (0.0, 1.0),
}
FINGERPRINT_FEATURES: list[str] = list(FINGERPRINT_RANGES)

# --- A2 detector block (16) — 8 detectors x (probability, confidence) -------- #
DETECTOR_NAMES: list[str] = [
    "temporal", "semantic", "ai_writing", "voice",
    "engagement", "profile", "memory", "coordination",
]
DETECTOR_FEATURES: list[str] = [
    f"det_{d}_{attr}" for d in DETECTOR_NAMES for attr in ("probability", "confidence")
]

# --- A3 metadata (5) — log1p-normalized to [0,1]; meta_verified in {0,1} ------ #
METADATA_FEATURES: list[str] = [
    "meta_log_followers", "meta_log_following", "meta_log_account_age_days",
    "meta_verified", "meta_log_post_count",
]

FEATURE_NAMES: list[str] = FINGERPRINT_FEATURES + DETECTOR_FEATURES + METADATA_FEATURES
INPUT_DIM: int = len(FEATURE_NAMES)  # 42
BLOCKS: dict[str, int] = {"fingerprint": 21, "detectors": 16, "metadata": 5}

# Schema defaults for absent values: detector probability -> 0.5, else 0.0.
DEFAULTS: dict[str, float] = {
    name: (0.5 if name in DETECTOR_FEATURES and name.endswith("_probability") else 0.0)
    for name in FEATURE_NAMES
}

assert INPUT_DIM == 42, f"feature schema must be 42-dim, got {INPUT_DIM}"
assert sum(BLOCKS.values()) == INPUT_DIM


def normalize_fingerprint(raw: dict[str, float]) -> dict[str, float]:
    """Min-max normalize raw fingerprint values into [0, 1] per FINGERPRINT_RANGES."""
    out: dict[str, float] = {}
    for name, (lo, hi) in FINGERPRINT_RANGES.items():
        if name in raw and raw[name] is not None:
            span = hi - lo or 1.0
            out[name] = float(min(1.0, max(0.0, (float(raw[name]) - lo) / span)))
    return out


def build_vector(features: dict[str, float]) -> list[float]:
    """Assemble the ordered 42-dim vector; absent values use the schema DEFAULTS."""
    vec = [float(features.get(name, DEFAULTS[name])) for name in FEATURE_NAMES]
    if len(vec) != INPUT_DIM:  # pragma: no cover - guarded by construction
        raise ValueError(f"expected {INPUT_DIM} features, built {len(vec)}")
    return vec


def vectorize_many(rows: list[dict[str, float]]) -> np.ndarray:
    """Stack many feature dicts into an (N, 42) float32 matrix."""
    if not rows:
        return np.empty((0, INPUT_DIM), dtype=np.float32)
    return np.asarray([build_vector(r) for r in rows], dtype=np.float32)


def synthetic_batch(n: int = 64, seed: int = 0) -> tuple[np.ndarray, np.ndarray]:
    """Schema-shaped RANDOM data for wiring/smoke checks only — NOT training data.

    Returns (X[n,42] in [0,1], y[n] in {0,1}). Architecture-only; carries no real
    signal and must never be used to train a real model.
    """
    rng = np.random.default_rng(seed)
    X = rng.random((n, INPUT_DIM), dtype=np.float32)
    y = (rng.random(n) < 0.5).astype(np.float32)
    return X, y


# --------------------------------------------------------------------------- #
# Thin PyTorch wrappers (torch imported lazily so the core stays torch-free).
# --------------------------------------------------------------------------- #
def to_tensor(matrix: np.ndarray):
    """Convert an (N, 42) array to a CPU float32 torch tensor."""
    import torch
    return torch.as_tensor(np.asarray(matrix, dtype=np.float32))


def make_dataset(X: np.ndarray, y: np.ndarray):
    """Build a torch TensorDataset from feature/label arrays (CPU)."""
    import torch
    from torch.utils.data import TensorDataset
    return TensorDataset(
        torch.as_tensor(np.asarray(X, dtype=np.float32)),
        torch.as_tensor(np.asarray(y, dtype=np.float32)).reshape(-1, 1),
    )
