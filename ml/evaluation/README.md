# `ml/evaluation/`

**Held-out evaluation harnesses, metrics, and reports.** The gate a model must
pass before it is even considered for promotion.

## What goes here
- Evaluation scripts + the reports they produce (versioned, tied to a model
  version and dataset/feature versions).
- Metrics that matter for this domain:
  - Calibration (Brier score, reliability curves) — probabilities must mean
    what they say.
  - Tier accuracy / macro-F1 vs. `analyst_verdicts/` ground truth.
  - **False-positive rate on legitimate controls** (newsrooms, on-message
    officials, benign automation) — the precision frontier; a model that lifts
    recall by raising control FPR does not pass.
  - Coordination: cluster recall + member precision/recall (network grain).

## Philosophy
Mirrors the in-product benchmark endpoints
(`/v1/intelligence/benchmark`, `/benchmark/coordination`, `/rescue`,
`/memory`) but runs **offline** here, so model R&D is measured the same way the
shipped engine is — without touching it.

## Constraints
Evaluate only on the `validation` split. A model with no current, passing report
is not promotion-eligible. Report regressions honestly.
