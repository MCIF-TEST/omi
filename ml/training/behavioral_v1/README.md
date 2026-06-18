# OMI Behavioral Model V1 — offline baseline

The first trainable Omi behavioral model. **Completely offline**, inside `ml/`,
disconnected from `apps/`/production. No neural networks; XGBoost (CPU). Train +
evaluate only — no deployment, no blending, `use_ml_scorer` stays OFF.

## Deliverables map
| | Deliverable | File |
|---|---|---|
| A | Training dataset builder | `ml/training/behavioral_v1/dataset.py` |
| B | Label mapping pipeline | `dataset.py:map_label` (is_fake → authenticity, engine-independent) |
| C | Feature extraction pipeline | `dataset.py:build_dataset` (`dataset_native_v0`, 25 features) |
| D | Training script | `ml/training/behavioral_v1/train.py` (XGBoost + isotonic calibration) |
| E | Evaluation script | `ml/evaluation/behavioral_v1/evaluate.py` (acc/P/R/F1/AUC/PR-AUC/Brier/ECE/FPR + CV) |
| F | Model card | `ml/models/omi-behavioral-v1/model_card.md` |
| G | Shadow-mode integration plan | `ml/models/omi-behavioral-v1/SHADOW_MODE_PLAN.md` |

## Run (CPU, ~seconds; requires `xgboost`)
```bash
python ml/training/behavioral_v1/train.py        # → ml/models/omi-behavioral-v1/{model,holdout}.joblib
python ml/evaluation/behavioral_v1/evaluate.py   # → ml/models/omi-behavioral-v1/metrics.json
```
`.joblib` artifacts are regenerable (seed 42) and git-ignored; the committed
deliverables are the code, `metrics.json`, `train_summary.json`, and the docs.

## Headline results (see `model_card.md` / `metrics.json`)
Held-out test (n=750): **acc 0.916 · F1 0.876 · ROC-AUC 0.982 · Brier 0.051 · ECE 0.019 · FPR 0.043**.
5-fold CV (n=3,000): acc 0.904 · F1 0.866 · AUC 0.974 · Brier 0.060 · FPR 0.083.

## Read this before trusting the numbers
**~89% of model gain is username-string morphology** — a synthetic-dataset
artifact, not a deep behavioral signal. And the feature schema is
`dataset_native_v0`, **not** the 42-dim `omi_v1` engine vector the serving
scorer requires — so this artifact is structurally un-loadable into production.
It is a **baseline** (a metric floor + a working train/eval loop), **not** a
promotable detector. The V2 bridge (engine-extracted `omi_v1` features +
`known-mixed` controls) is in `SHADOW_MODE_PLAN.md`.

## Decision note
OMI_FEATURE_SCHEMA_V1 (42-dim engine vector) needs raw timelines run through the
production detectors, which the clean balanced labeled set lacks and which would
couple `ml/`→`apps/`. So V1 uses the dataset's own behavioral features
(`dataset_native_v0`), conceptually aligned to Omi's signal families. This is the
honest, achievable first model; parity is the documented next step.
