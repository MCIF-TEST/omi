"""Train the learned tabular detector from an exported corpus.

Consumes the JSONL produced by ``python -m scripts.datasets export`` (or
``app.ml.export.export_jsonl``) and fits a binary inauthenticity classifier in
the *exact* feature space the serving scorer uses. Saves a joblib bundle that
:mod:`app.ml.scorer` loads as-is:

    {feature_schema_version, model, kind: "sklearn", trained_at, metrics}

LightGBM is preferred when installed; otherwise we fall back to scikit-learn's
HistGradientBoosting (and LogisticRegression for tiny corpora). The serving
path supports both kinds, so the artifact is drop-in either way.

    cd apps/api
    python -m scripts.train_model --corpus datasets/_generated/omi_corpus_accounts_YYYYMMDD.jsonl
    # then point the API at it:
    #   USE_ML_SCORER=true ML_MODEL_PATH=datasets/_generated/omi_model.joblib
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.ml.features import FEATURE_NAMES, FEATURE_SCHEMA_VERSION  # noqa: E402


def _load_corpus(path: Path):
    X, y, w = [], [], []
    header = None
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            if obj.get("_meta"):
                header = obj
                continue
            if obj.get("inauthentic") not in (0, 1):
                continue  # drop unclear / multi-class-only rows
            feats = obj.get("features")
            if not feats or len(feats) != len(FEATURE_NAMES):
                continue
            X.append(feats)
            y.append(int(obj["inauthentic"]))
            w.append(float(obj.get("sample_weight", 1.0)))
    return X, y, w, header


def main() -> int:
    ap = argparse.ArgumentParser(description="Train the learned tabular detector.")
    ap.add_argument("--corpus", type=Path, required=True, help="JSONL from `datasets export`.")
    ap.add_argument("--out", type=Path, default=Path("datasets/_generated/omi_model.joblib"))
    ap.add_argument("--test-size", type=float, default=0.25)
    ap.add_argument("--seed", type=int, default=13)
    args = ap.parse_args()

    if not args.corpus.exists():
        print(f"corpus not found: {args.corpus}", file=sys.stderr)
        return 2

    X, y, w, header = _load_corpus(args.corpus)
    if header and header.get("feature_schema_version") != FEATURE_SCHEMA_VERSION:
        print(f"FATAL: corpus schema v{header.get('feature_schema_version')} != "
              f"serving schema v{FEATURE_SCHEMA_VERSION}. Re-export the corpus.",
              file=sys.stderr)
        return 2
    n_pos, n_neg = sum(y), len(y) - sum(y)
    print(f"loaded {len(y)} rows (inauthentic={n_pos}, authentic={n_neg}) "
          f"x {len(FEATURE_NAMES)} features")
    if n_pos < 25 or n_neg < 25:
        print("Not enough labeled examples in both classes to train responsibly "
              "(need >=25 each). Ingest more datasets / label more accounts.",
              file=sys.stderr)
        return 1

    try:
        import joblib  # type: ignore
        from sklearn.metrics import brier_score_loss, roc_auc_score
        from sklearn.model_selection import train_test_split
    except Exception as e:  # noqa: BLE001
        print(f"scikit-learn / joblib unavailable: {e}", file=sys.stderr)
        return 2

    Xtr, Xte, ytr, yte, wtr, _wte = train_test_split(
        X, y, w, test_size=args.test_size, random_state=args.seed, stratify=y,
    )

    kind = "sklearn"
    model = None
    try:
        import lightgbm as lgb  # type: ignore
        model = lgb.LGBMClassifier(n_estimators=300, learning_rate=0.05,
                                   num_leaves=31, subsample=0.8, random_state=args.seed)
        model.fit(Xtr, ytr, sample_weight=wtr)
        kind = "sklearn"  # LGBMClassifier exposes predict_proba → sklearn path
    except Exception:  # noqa: BLE001
        from sklearn.ensemble import HistGradientBoostingClassifier
        try:
            model = HistGradientBoostingClassifier(
                max_iter=300, learning_rate=0.05, random_state=args.seed)
            model.fit(Xtr, ytr, sample_weight=wtr)
        except Exception:  # noqa: BLE001 — tiny corpus fallback
            from sklearn.linear_model import LogisticRegression
            model = LogisticRegression(max_iter=1000, class_weight="balanced")
            model.fit(Xtr, ytr, sample_weight=wtr)

    proba = [p[1] for p in model.predict_proba(Xte)]
    preds = [1 if p >= 0.5 else 0 for p in proba]
    accuracy = sum(int(a == b) for a, b in zip(preds, yte)) / len(yte)
    try:
        auc = float(roc_auc_score(yte, proba))
    except ValueError:
        auc = None
    brier = float(brier_score_loss(yte, proba))
    metrics = {
        "held_out_n": len(yte),
        "accuracy": round(accuracy, 4),
        "roc_auc": round(auc, 4) if auc is not None else None,
        "brier": round(brier, 4),
        "model_type": type(model).__name__,
    }
    print("held-out metrics:", json.dumps(metrics))

    args.out.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump({
        "feature_schema_version": FEATURE_SCHEMA_VERSION,
        "model": model,
        "kind": kind,
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "metrics": metrics,
        "n_train": len(ytr),
    }, args.out)
    print(f"saved model → {args.out}")
    print("Activate it:  USE_ML_SCORER=true ML_MODEL_PATH=" + str(args.out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
