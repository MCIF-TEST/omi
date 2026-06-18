# `ml/training/`

**Offline, reproducible training pipelines.** Consume `ml/features/` (+ labels
from `ml/datasets/analyst_verdicts/`) and emit artifacts to `ml/models/`.

## What goes here
- Config-driven training scripts (one per model family) and their run configs.
- Each run records: dataset versions, feature-set version, hyperparameters,
  random seed, and the resulting model version — so any model is reproducible
  from its config alone.

## Constraints
- Offline only: no network calls, no imports from `apps/api`/`apps/web`, no
  writes to any production store.
- Train only on the `train` split; never touch `validation` (held out for
  `ml/evaluation/`) or `quarantine`.
- Supersedes the legacy `apps/api/app/ml_training/` + `scripts/train_model.py`
  for new work; those remain untouched until/unless explicitly retired.
