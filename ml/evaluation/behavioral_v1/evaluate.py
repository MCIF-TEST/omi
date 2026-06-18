"""OMI Behavioral Model V1 — evaluation script (Deliverable E).

Offline. Loads the frozen hold-out + artifact and reports every requested
metric: accuracy, precision, recall, F1, ROC-AUC, PR-AUC, calibration
(Brier + ECE + reliability bins), and false-positive rate — plus a 5-fold
stratified CV for robustness and feature importances (to surface any single
engineered feature dominating, an honesty check).

Positive class = "inauthentic" (is_fake=1); detection precision/recall are for
catching inauthentic accounts. FPR = authentic accounts wrongly flagged
inauthentic (the precision-frontier metric). authenticity_probability = 1 - p.

Run:  python ml/evaluation/behavioral_v1/evaluate.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import joblib
import numpy as np
from sklearn.calibration import CalibratedClassifierCV
from sklearn.metrics import (
    accuracy_score, average_precision_score, brier_score_loss, confusion_matrix,
    f1_score, precision_score, recall_score, roc_auc_score,
)
from sklearn.model_selection import StratifiedKFold, cross_val_predict

_TRAIN_DIR = Path(__file__).resolve().parents[2] / "training" / "behavioral_v1"
sys.path.insert(0, str(_TRAIN_DIR))
from dataset import build_dataset  # noqa: E402
from train import build_estimator  # noqa: E402

MODEL_DIR = Path(__file__).resolve().parents[2] / "models" / "omi-behavioral-v1"
SEED = 42


def expected_calibration_error(y, p, bins: int = 10):
    edges = np.linspace(0.0, 1.0, bins + 1)
    idx = np.clip(np.digitize(p, edges[1:-1]), 0, bins - 1)
    ece, table = 0.0, []
    n = len(y)
    for b in range(bins):
        m = idx == b
        cnt = int(m.sum())
        if cnt == 0:
            continue
        conf = float(p[m].mean())
        acc = float(y[m].mean())          # observed inauthentic rate in bin
        ece += (cnt / n) * abs(acc - conf)
        table.append({"bin": f"{edges[b]:.1f}-{edges[b+1]:.1f}", "n": cnt,
                      "mean_pred": round(conf, 4), "observed_rate": round(acc, 4)})
    return round(ece, 4), table


def metric_block(y, p, thr: float = 0.5) -> dict:
    y = np.asarray(y); p = np.asarray(p)
    yhat = (p >= thr).astype(int)
    tn, fp, fn, tp = confusion_matrix(y, yhat, labels=[0, 1]).ravel()
    ece, table = expected_calibration_error(y, p)
    return {
        "n": int(len(y)),
        "threshold": thr,
        "accuracy": round(accuracy_score(y, yhat), 4),
        "precision_inauthentic": round(precision_score(y, yhat, zero_division=0), 4),
        "recall_inauthentic": round(recall_score(y, yhat, zero_division=0), 4),
        "f1_inauthentic": round(f1_score(y, yhat, zero_division=0), 4),
        "roc_auc": round(roc_auc_score(y, p), 4),
        "pr_auc": round(average_precision_score(y, p), 4),
        "brier": round(brier_score_loss(y, p), 4),
        "ece": ece,
        "false_positive_rate": round(fp / max(fp + tn, 1), 4),
        "confusion_matrix": {"tn": int(tn), "fp": int(fp), "fn": int(fn), "tp": int(tp)},
        "reliability_bins": table,
    }


def main() -> None:
    bundle = joblib.load(MODEL_DIR / "model.joblib")
    hold = joblib.load(MODEL_DIR / "holdout.joblib")
    model = bundle["model"]

    # --- Held-out test (the headline numbers) ---
    p_test = model.predict_proba(hold["X_test"])[:, 1]   # P(inauthentic)
    test_metrics = metric_block(np.asarray(hold["y_test"]), p_test)

    # --- 5-fold stratified CV on the full dataset (robustness) ---
    X, y, feat, meta = build_dataset()
    pos = int(y.sum()); neg = int((y == 0).sum())
    cv_clf = CalibratedClassifierCV(
        estimator=build_estimator(neg / max(pos, 1)), method="isotonic", cv=5
    )
    skf = StratifiedKFold(n_splits=5, shuffle=True, random_state=SEED)
    p_cv = cross_val_predict(cv_clf, X, y, cv=skf, method="predict_proba", n_jobs=1)[:, 1]
    cv_metrics = metric_block(np.asarray(y), p_cv)

    # --- Feature importance (gain), averaged across calibrated sub-models ---
    importances = np.zeros(len(feat))
    cc = getattr(model, "calibrated_classifiers_", [])
    for c in cc:
        est = getattr(c, "estimator", None)
        if est is not None and hasattr(est, "feature_importances_"):
            importances += np.asarray(est.feature_importances_)
    if len(cc):
        importances /= len(cc)
    top = sorted(zip(feat, importances.tolist()), key=lambda t: t[1], reverse=True)[:10]
    top_features = [{"feature": f, "gain": round(g, 4)} for f, g in top]

    out = {
        "model": bundle["kind"],
        "feature_schema": bundle["feature_schema"],
        "dataset": meta,
        "holdout_test": test_metrics,
        "cv_5fold": cv_metrics,
        "top_features_by_gain": top_features,
        "output_field": "authenticity_probability = 1 - P(inauthentic)",
    }
    (MODEL_DIR / "metrics.json").write_text(json.dumps(out, indent=2))
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
