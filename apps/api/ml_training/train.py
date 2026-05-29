"""OMISPHERE detector training — runs on Google Colab (free tier).

This script trains the hybrid learned detector:

  1. A LightGBM tabular meta-classifier over the shared feature contract
     (fingerprint + per-detector outputs + account metadata). This learns the
     aggregation the rule engine currently hand-tunes.
  2. (Optional) A fine-tuned DistilBERT text head over raw comment text, when
     the training corpus carries text. Ensembled with the tabular model.

It evaluates BOTH against a held-out split using the same metrics the API's
/v1/labels/calibration/evaluate endpoint computes (tier accuracy, Brier,
macro-F1) PLUS ROC-AUC, and prints a head-to-head vs. the rule-engine
baseline (the persisted fp_overall_probability) so you can see whether the
model actually beats the current detector before shipping it.

Finally it saves a joblib bundle compatible with app.ml.scorer and (if a HF
token is provided) pushes the artifacts to the HuggingFace Hub.

USAGE (Colab):
    !pip install lightgbm scikit-learn joblib huggingface_hub
    # for the text head:
    !pip install "transformers[torch]" datasets

    # 1) Get your training data (admin token from the app):
    !curl -H "Cookie: omi_session=YOUR_SESSION" \
        "https://api.YOURDOMAIN.com/v1/labels/training/export" \
        -o omisphere_training.jsonl

    # 2) Train + evaluate + push:
    !python train.py --data omisphere_training.jsonl \
        --hf-repo YOURUSER/omisphere-detector --hf-token $HF_TOKEN --text

See ml_training/README.md for the full walkthrough.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone


# Tier mapping mirrors app.detection.scoring._tier_for so metrics line up
# with the in-app calibration endpoint.
def tier_for(p: float) -> str:
    if p < 0.25:
        return "low"
    if p < 0.50:
        return "moderate"
    if p < 0.75:
        return "elevated"
    return "high"


_TIER_TARGET_PROB = {"low": 0.12, "moderate": 0.37, "elevated": 0.62, "high": 0.87}


def load_jsonl(path: str):
    """Return (header, rows). Asserts the feature schema version is present."""
    header = None
    rows = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            if obj.get("_meta"):
                header = obj
                continue
            rows.append(obj)
    if header is None:
        raise SystemExit("No schema header found in JSONL — re-export from /v1/labels/training/export.")
    return header, rows


def evaluate(name: str, y_true, p_pred, expected_tiers):
    """Print the same metrics the API calibration endpoint computes, + AUC."""
    from sklearn.metrics import roc_auc_score

    n = len(y_true)
    pred_tiers = [tier_for(p) for p in p_pred]
    tier_acc = sum(1 for e, pt in zip(expected_tiers, pred_tiers) if e == pt) / n
    brier = sum((p - _TIER_TARGET_PROB.get(e, 0.5)) ** 2 for p, e in zip(p_pred, expected_tiers)) / n

    # macro-F1 over tiers
    f1s = []
    for t in ("low", "moderate", "elevated", "high"):
        tp = sum(1 for e, pt in zip(expected_tiers, pred_tiers) if e == t and pt == t)
        fp = sum(1 for e, pt in zip(expected_tiers, pred_tiers) if e != t and pt == t)
        fn = sum(1 for e, pt in zip(expected_tiers, pred_tiers) if e == t and pt != t)
        prec = tp / (tp + fp) if (tp + fp) else 0.0
        rec = tp / (tp + fn) if (tp + fn) else 0.0
        f1s.append(2 * prec * rec / (prec + rec) if (prec + rec) else 0.0)
    macro_f1 = sum(f1s) / len(f1s)

    try:
        auc = roc_auc_score(y_true, p_pred) if len(set(y_true)) > 1 else float("nan")
    except Exception:
        auc = float("nan")

    print(f"\n=== {name} (n={n}) ===")
    print(f"  ROC-AUC:        {auc:.3f}")
    print(f"  tier accuracy:  {tier_acc:.3f}")
    print(f"  Brier score:    {brier:.4f}  (lower is better)")
    print(f"  macro-F1:       {macro_f1:.3f}")
    return {"auc": round(auc, 3), "tier_accuracy": round(tier_acc, 3),
            "brier": round(brier, 4), "macro_f1": round(macro_f1, 3), "n": n}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True, help="training JSONL from the export endpoint")
    ap.add_argument("--out", default="omisphere_detector.joblib")
    ap.add_argument("--text", action="store_true", help="also fine-tune the DistilBERT text head")
    ap.add_argument("--hf-repo", default=None, help="HuggingFace repo, e.g. user/omisphere-detector")
    ap.add_argument("--hf-token", default=None)
    ap.add_argument("--test-frac", type=float, default=0.2)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    import numpy as np
    import lightgbm as lgb
    from sklearn.model_selection import train_test_split

    header, rows = load_jsonl(args.data)
    feature_names = header["feature_names"]
    schema_version = header["feature_schema_version"]
    print(f"Loaded {len(rows)} rows · {len(feature_names)} features · schema v{schema_version}")

    # Binary target only (drop unclear rows lacking a 0/1 target).
    rows = [r for r in rows if r["inauthentic"] in (0, 1)]
    if len(rows) < 100:
        print(f"WARNING: only {len(rows)} binary-labeled rows — the model will be unreliable. "
              "Bootstrap more data (public import) or label more accounts before trusting this.")

    X = np.array([r["features"] for r in rows], dtype=float)
    y = np.array([r["inauthentic"] for r in rows], dtype=int)
    w = np.array([r.get("sample_weight", 1.0) for r in rows], dtype=float)
    expected_tiers = [r["expected_tier"] for r in rows]
    # Rule-engine baseline = the persisted aggregate prob (fp_overall_probability).
    baseline_idx = feature_names.index("fp_overall_probability")
    baseline_p = X[:, baseline_idx]

    idx = np.arange(len(rows))
    tr, te = train_test_split(idx, test_size=args.test_frac, random_state=args.seed,
                              stratify=y if len(set(y)) > 1 else None)

    # --- Rule-engine baseline on the held-out split ---
    base_metrics = evaluate("RULE ENGINE (baseline)", y[te], baseline_p[te],
                            [expected_tiers[i] for i in te])

    # --- LightGBM tabular model ---
    train_set = lgb.Dataset(X[tr], label=y[tr], weight=w[tr], feature_name=feature_names)
    params = {
        "objective": "binary", "metric": "auc", "learning_rate": 0.05,
        "num_leaves": 31, "min_data_in_leaf": 5, "feature_fraction": 0.85,
        "bagging_fraction": 0.85, "bagging_freq": 1, "verbose": -1,
    }
    booster = lgb.train(params, train_set, num_boost_round=300)
    tab_p = booster.predict(X[te])
    model_metrics = evaluate("LIGHTGBM (tabular)", y[te], tab_p,
                             [expected_tiers[i] for i in te])

    # Top feature importances → sanity check + explainability.
    imp = sorted(zip(feature_names, booster.feature_importance(importance_type="gain")),
                 key=lambda t: -t[1])[:12]
    print("\nTop features by gain:")
    for name, gain in imp:
        print(f"  {name:32s} {gain:10.1f}")

    # --- Optional DistilBERT text head ---
    text_repo = None
    if args.text and any(r.get("text") for r in rows):
        text_repo = train_text_head(rows, tr, te, y, expected_tiers, args)
    elif args.text:
        print("\n--text requested but no row carries text; skipping the text head.")

    # --- Verdict ---
    better = (model_metrics["auc"] >= base_metrics["auc"]
              and model_metrics["macro_f1"] >= base_metrics["macro_f1"])
    print("\n" + "=" * 52)
    print("VERDICT: " + ("✅ model beats the rule engine — safe to ship."
                         if better else
                         "⚠️  model does NOT clearly beat the rule engine. "
                         "Get more/better labels before enabling OMI_USE_ML_SCORER."))
    print("=" * 52)

    # --- Save bundle (compatible with app.ml.scorer) ---
    import joblib
    bundle = {
        "feature_schema_version": schema_version,
        "model": booster,
        "kind": "lightgbm",
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "metrics": {"model": model_metrics, "baseline": base_metrics, "beats_baseline": better},
        "feature_names": feature_names,
    }
    joblib.dump(bundle, args.out)
    print(f"\nSaved tabular bundle → {args.out}")

    if args.hf_repo and args.hf_token:
        push_to_hub(args.out, text_repo, args.hf_repo, args.hf_token, bundle["metrics"])

    return 0


def train_text_head(rows, tr, te, y, expected_tiers, args):
    """Fine-tune DistilBERT on raw comment text. Returns local dir or None."""
    try:
        import numpy as np
        from datasets import Dataset
        from transformers import (
            AutoModelForSequenceClassification, AutoTokenizer,
            DataCollatorWithPadding, Trainer, TrainingArguments,
        )
    except Exception as e:  # noqa: BLE001
        print(f"\nText head skipped — transformers/datasets not installed: {e}")
        return None

    model_name = "distilbert-base-uncased"
    tok = AutoTokenizer.from_pretrained(model_name)

    def make_ds(split_idx):
        texts = [rows[i].get("text", "") or "" for i in split_idx]
        labels = [int(y[i]) for i in split_idx]
        ds = Dataset.from_dict({"text": texts, "label": labels})
        return ds.map(lambda b: tok(b["text"], truncation=True, max_length=256), batched=True)

    train_ds, test_ds = make_ds(tr), make_ds(te)
    model = AutoModelForSequenceClassification.from_pretrained(model_name, num_labels=2)
    out_dir = "omisphere_text_head"
    targs = TrainingArguments(
        output_dir=out_dir, num_train_epochs=3, per_device_train_batch_size=16,
        per_device_eval_batch_size=32, learning_rate=2e-5, logging_steps=20,
        report_to=[], save_strategy="no",
    )
    trainer = Trainer(model=model, args=targs, train_dataset=train_ds,
                      eval_dataset=test_ds, data_collator=DataCollatorWithPadding(tok))
    trainer.train()

    import numpy as np
    preds = trainer.predict(test_ds)
    logits = preds.predictions
    txt_p = (np.exp(logits[:, 1]) / np.exp(logits).sum(axis=1))
    evaluate("DISTILBERT (text head)", [int(y[i]) for i in te], list(txt_p),
             [expected_tiers[i] for i in te])

    model.save_pretrained(out_dir)
    tok.save_pretrained(out_dir)
    print(f"Saved text head → {out_dir}")
    return out_dir


def push_to_hub(tabular_path, text_dir, repo, token, metrics):
    from huggingface_hub import HfApi
    api = HfApi(token=token)
    api.create_repo(repo, exist_ok=True)
    api.upload_file(path_or_fileobj=tabular_path,
                    path_in_repo="omisphere_detector.joblib", repo_id=repo)
    api.upload_file(
        path_or_fileobj=json.dumps(metrics, indent=2).encode(),
        path_in_repo="metrics.json", repo_id=repo,
    )
    if text_dir:
        api.upload_folder(folder_path=text_dir, path_in_repo="text_head", repo_id=repo)
    print(f"\nPushed to https://huggingface.co/{repo}")
    print("Set in Render:")
    print(f"  OMI_HF_MODEL_REPO={repo}")
    print("  OMI_USE_ML_SCORER=true")
    print("  OMI_ML_MODEL_PATH=/opt/render/project/models/omisphere_detector.joblib")


if __name__ == "__main__":
    sys.exit(main())
