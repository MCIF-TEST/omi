"""Machine-learning track for OMISPHERE detection.

This package holds the *learned* scoring path that augments (and will
eventually lead) the hand-tuned rule engine in ``app.detection``:

* ``features``   — the single feature contract shared by training + serving.
* ``export``     — build labeled training rows from the live database.
* ``public_import`` — map public bot datasets onto the same feature space.
* ``scorer``     — load a trained model and re-score a ScanResult at serve
                    time. No-ops safely when no model artifact is present.

Design rule: training and serving MUST build features through the exact
same function (``features.build_feature_vector``) so there is zero
train/serve skew. The feature order + names are versioned; bumping the
schema invalidates old model artifacts on purpose.
"""

from __future__ import annotations

from app.ml.features import (
    FEATURE_NAMES,
    FEATURE_SCHEMA_VERSION,
    build_feature_vector,
)

__all__ = [
    "FEATURE_NAMES",
    "FEATURE_SCHEMA_VERSION",
    "build_feature_vector",
]
