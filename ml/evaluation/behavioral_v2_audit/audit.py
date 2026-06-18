"""OMI Behavioral Model V2 — Data Audit experiment (offline).

Why is V1 dominated by username morphology, and is there a behavior-first model
in the current data? Reuses the V1 pipeline (dataset/estimator/metrics) and runs
three models on the SAME stratified split + 5-fold CV (seed 42):

  1. v1_full        — all 25 features (the committed baseline)
  2. no_username    — username-morphology features removed (behavior-first candidate)
  3. username_only  — ONLY the 6 username features (the shortcut probe)

Then aggregates feature importance by category. Offline only: no apps/, no
deployment, no scorer, no HF. Writes results to this folder's results.json.

Run:  python ml/evaluation/behavioral_v2_audit/audit.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
from sklearn.calibration import CalibratedClassifierCV
from sklearn.model_selection import StratifiedKFold, cross_val_predict, train_test_split

_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_ROOT / "ml" / "training" / "behavioral_v1"))
sys.path.insert(0, str(_ROOT / "ml" / "evaluation" / "behavioral_v1"))
from dataset import build_dataset  # noqa: E402
from train import build_estimator  # noqa: E402
from evaluate import metric_block  # noqa: E402

SEED = 42
OUT = Path(__file__).resolve().parent / "results.json"

# Feature → category. "coordination" is intentionally empty: this is a
# single-account dataset, and coordination is a cross-account signal — its
# absence is itself a finding.
CATEGORIES: dict[str, list[str]] = {
    "username": ["username_randomness", "username_length", "digits_count",
                 "digit_ratio", "special_char_count", "repeat_char_count"],
    "temporal": ["account_age_days", "posts_per_day"],
    "engagement": ["follow_unfollow_rate", "spam_comments_rate", "generic_comment_rate"],
    "coordination": [],
    "content_semantic": ["caption_similarity_score", "content_similarity_score"],
    "profile_shape": ["has_profile_pic", "bio_length", "followers", "following",
                      "follower_following_ratio", "posts", "suspicious_links_in_bio", "verified"],
    "platform_context": ["platform_Instagram", "platform_Facebook", "platform_X", "platform_unknown"],
}
USERNAME = set(CATEGORIES["username"])


def _avg_gain(model, n_features: int) -> np.ndarray:
    imp = np.zeros(n_features)
    cc = getattr(model, "calibrated_classifiers_", [])
    for c in cc:
        est = getattr(c, "estimator", None)
        if est is not None and hasattr(est, "feature_importances_"):
            imp += np.asarray(est.feature_importances_)
    return imp / max(len(cc), 1)


def fit_eval(X, y, feats: list[str]) -> dict:
    Xs = X[feats]
    Xtr, Xte, ytr, yte = train_test_split(Xs, y, test_size=0.25, stratify=y, random_state=SEED)
    spw = int((ytr == 0).sum()) / max(int(ytr.sum()), 1)

    clf = CalibratedClassifierCV(estimator=build_estimator(spw), method="isotonic", cv=5)
    clf.fit(Xtr, ytr)
    p_test = clf.predict_proba(Xte)[:, 1]
    test = metric_block(np.asarray(yte), p_test)

    skf = StratifiedKFold(n_splits=5, shuffle=True, random_state=SEED)
    cv_clf = CalibratedClassifierCV(estimator=build_estimator(spw), method="isotonic", cv=5)
    p_cv = cross_val_predict(cv_clf, Xs, y, cv=skf, method="predict_proba", n_jobs=1)[:, 1]
    cv = metric_block(np.asarray(y), p_cv)

    gain = _avg_gain(clf, len(feats))
    return {"test": test, "cv": cv, "feature_gain": dict(zip(feats, gain.round(4).tolist()))}


def category_gain(feature_gain: dict) -> dict:
    total = sum(feature_gain.values()) or 1.0
    out = {}
    for cat, cols in CATEGORIES.items():
        out[cat] = round(sum(feature_gain.get(c, 0.0) for c in cols) / total, 4)
    return out


def headline(b: dict) -> dict:
    return {k: b[k] for k in ("accuracy", "precision_inauthentic", "recall_inauthentic",
                              "f1_inauthentic", "roc_auc", "pr_auc", "brier", "ece",
                              "false_positive_rate")}


def main() -> None:
    X, y, feat, meta = build_dataset()
    nouser = [f for f in feat if f not in USERNAME]
    useronly = [f for f in feat if f in USERNAME]

    v1 = fit_eval(X, y, feat)
    no_u = fit_eval(X, y, nouser)
    only_u = fit_eval(X, y, useronly)

    result = {
        "dataset": meta,
        "category_gain_v1_full": category_gain(v1["feature_gain"]),
        "models": {
            "v1_full": {"n_features": len(feat), "test": headline(v1["test"]), "cv": headline(v1["cv"])},
            "no_username": {"n_features": len(nouser), "test": headline(no_u["test"]), "cv": headline(no_u["cv"])},
            "username_only": {"n_features": len(useronly), "test": headline(only_u["test"]), "cv": headline(only_u["cv"])},
        },
        "v1_feature_gain": dict(sorted(v1["feature_gain"].items(), key=lambda t: t[1], reverse=True)),
    }
    OUT.write_text(json.dumps(result, indent=2))

    print("=== Category gain share (v1_full) ===")
    for cat, g in sorted(result["category_gain_v1_full"].items(), key=lambda t: t[1], reverse=True):
        print(f"  {cat:18s} {g:6.1%}")
    print("\n=== Held-out test comparison ===")
    print(f"  {'model':14s} {'acc':>6} {'prec':>6} {'rec':>6} {'F1':>6} {'AUC':>6} {'Brier':>6} {'ECE':>6} {'FPR':>6}")
    for name, m in result["models"].items():
        t = m["test"]
        print(f"  {name:14s} {t['accuracy']:6.3f} {t['precision_inauthentic']:6.3f} "
              f"{t['recall_inauthentic']:6.3f} {t['f1_inauthentic']:6.3f} {t['roc_auc']:6.3f} "
              f"{t['brier']:6.3f} {t['ece']:6.3f} {t['false_positive_rate']:6.3f}")
    print(f"\nresults -> {OUT}")


if __name__ == "__main__":
    main()
