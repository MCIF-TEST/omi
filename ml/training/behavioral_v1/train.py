"""OMI Behavioral Model V1 — training script (Deliverable D).

CPU-only XGBoost (the requested primary model), calibrated, seeded, fully
OFFLINE. Writes the artifact + a frozen hold-out split to ``ml/models/``.

Run:  python ml/training/behavioral_v1/train.py

It does NOT touch apps/, production scoring, or use_ml_scorer. The artifact is
explicitly flagged NOT_FOR_PRODUCTION_SCORER (its feature schema is
dataset_native_v0, not the 42-dim omi_v1 the serving scorer requires).
"""

from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
from sklearn.calibration import CalibratedClassifierCV
from sklearn.model_selection import train_test_split
from xgboost import XGBClassifier

sys.path.insert(0, str(Path(__file__).resolve().parent))
from dataset import FEATURE_SCHEMA, build_dataset  # noqa: E402

SEED = 42
OUT_DIR = Path(__file__).resolve().parents[3] / "ml" / "models" / "omi-behavioral-v1"


def build_estimator(scale_pos_weight: float) -> XGBClassifier:
    return XGBClassifier(
        n_estimators=400,
        max_depth=4,
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.8,
        reg_lambda=1.0,
        min_child_weight=2.0,
        tree_method="hist",      # CPU histogram method
        n_jobs=2,
        eval_metric="logloss",
        scale_pos_weight=scale_pos_weight,
        random_state=SEED,
    )


def main() -> None:
    X, y, feature_names, meta = build_dataset()

    X_tr, X_te, y_tr, y_te = train_test_split(
        X, y, test_size=0.25, stratify=y, random_state=SEED
    )
    pos = int(y_tr.sum())
    neg = int((y_tr == 0).sum())
    spw = neg / max(pos, 1)

    # Calibrated probabilities (isotonic, 5-fold) over the XGBoost base — so the
    # authenticity probability means what it says, per the evaluation contract.
    base = build_estimator(spw)
    clf = CalibratedClassifierCV(estimator=base, method="isotonic", cv=5)

    t0 = time.time()
    clf.fit(X_tr, y_tr)
    train_seconds = round(time.time() - t0, 2)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    bundle = {
        "model": clf,
        "kind": "xgboost-calibrated-isotonic",
        "feature_schema": FEATURE_SCHEMA,
        "feature_names": feature_names,
        "positive_class": "inauthentic (is_fake=1)",
        "output": "authenticity_probability = 1 - P(inauthentic)",
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "seed": SEED,
        "xgboost_params": base.get_params(),
        "scale_pos_weight": spw,
        "train_meta": meta,
        # Hard guard: this schema is NOT the 42-dim omi_v1 the serving scorer
        # (app/ml/scorer.py) expects, so it can never be loaded into production.
        "NOT_FOR_PRODUCTION_SCORER": True,
        "production_schema_required": "omi_v1 (42-dim build_feature_vector)",
    }
    joblib.dump(bundle, OUT_DIR / "model.joblib")
    joblib.dump(
        {"X_test": X_te, "y_test": y_te, "X_train": X_tr, "y_train": y_tr},
        OUT_DIR / "holdout.joblib",
    )

    summary = {
        "trained_at": bundle["trained_at"],
        "train_seconds": train_seconds,
        "train_rows": int(len(X_tr)),
        "test_rows": int(len(X_te)),
        "scale_pos_weight": round(spw, 4),
        **meta,
    }
    (OUT_DIR / "train_summary.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))
    print(f"artifact -> {OUT_DIR/'model.joblib'}")


if __name__ == "__main__":
    main()
