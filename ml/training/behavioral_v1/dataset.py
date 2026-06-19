"""OMI Behavioral Model V1 — offline dataset builder, label mapping, feature extraction.

Deliverables A + B + C. Fully offline: reads one governed CSV, returns a
model-ready (X, y) table. No imports from ``apps/`` — disconnected from
production by construction.

DATA: ``fake_social_media_global_2.0.csv`` — manifest status ``train``, the one
clean balanced behavioral set (is_fake 1059 / 1941, engine-INDEPENDENT labels,
so there is no leakage from Omi's own scoring).

FEATURE-SCHEMA NOTE (honest): OMI_FEATURE_SCHEMA_V1 is the 42-dim *engine* vector
(fingerprint + detector (prob,conf) + metadata), which requires running the
production detectors over RAW TIMELINES. This set ships PRE-ENGINEERED features
and no timelines, so V1 uses this DATASET-NATIVE feature set
(``dataset_native_v0``). These columns map conceptually to Omi's signal families
(profile shape, semantic repetition, engagement-spam, posting cadence). The
42-dim ``omi_v1`` parity path (offline engine extraction over timeline/IO data)
is the documented V2 bridge — see the model card. Because the production scorer
expects the 42-dim schema, an artifact trained here CANNOT be loaded into it —
"no production activation" is structural, not just policy.

LABEL: per OMI_LABEL_SCHEMA_V1 — y = 1 (inauthentic) when is_fake==1, else 0
(authentic). ``label_source = dataset_label`` (engine-independent).
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

FEATURE_SCHEMA = "dataset_native_v0"

# repo_root/datasets/... — this file lives at repo_root/ml/training/behavioral_v1/
DEFAULT_CSV = (
    Path(__file__).resolve().parents[3]
    / "datasets"
    / "Datasets"
    / "Fake Social Media Account Detection Dataset"
    / "fake_social_media_global_2.0.csv"
)

LABEL_COL = "is_fake"

# Engineered behavioral columns → conceptual Omi signal family (for the card).
NUMERIC_FEATURES = [
    "has_profile_pic", "bio_length", "username_randomness",          # profile
    "followers", "following", "follower_following_ratio",            # profile/shape
    "account_age_days", "posts", "posts_per_day",                    # cadence
    "caption_similarity_score", "content_similarity_score",          # semantic repetition
    "follow_unfollow_rate", "spam_comments_rate", "generic_comment_rate",  # engagement-spam
    "suspicious_links_in_bio", "verified",                           # profile
    "username_length", "digits_count", "digit_ratio",
    "special_char_count", "repeat_char_count",                       # handle entropy proxy
]
PLATFORM_VALUES = ["Instagram", "Facebook", "X"]


def map_label(v) -> int:
    """is_fake → authenticity label. 1 = inauthentic (fake), 0 = authentic."""
    return 1 if str(v).strip() in ("1", "1.0", "True", "true") else 0


def build_dataset(csv_path: Path | str = DEFAULT_CSV):
    """Return (X: DataFrame, y: Series, feature_names: list[str], meta: dict).

    NaNs are left intact — the gradient-booster handles missing values natively,
    which is more honest than imputing a value the source never recorded.
    """
    df = pd.read_csv(csv_path)
    y = df[LABEL_COL].map(map_label).astype(int)

    X = pd.DataFrame(index=df.index)
    for col in NUMERIC_FEATURES:
        X[col] = pd.to_numeric(df.get(col), errors="coerce")

    plat = df.get("platform")
    plat = (plat if plat is not None else pd.Series([""] * len(df))).fillna("").astype(str)
    for p in PLATFORM_VALUES:
        X[f"platform_{p}"] = (plat == p).astype(int)
    X["platform_unknown"] = (~plat.isin(PLATFORM_VALUES)).astype(int)

    feature_names = list(X.columns)
    meta = {
        "rows": int(len(df)),
        "positives_inauthentic": int(y.sum()),
        "negatives_authentic": int((y == 0).sum()),
        "feature_schema": FEATURE_SCHEMA,
        "n_features": len(feature_names),
        "source_csv": str(csv_path),
        "label_source": "dataset_label",
    }
    return X, y, feature_names, meta


if __name__ == "__main__":  # quick sanity
    X, y, feat, meta = build_dataset()
    print(meta)
    print("features:", feat)
