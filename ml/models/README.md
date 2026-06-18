# `ml/models/`

**Serialized model artifacts + model cards.** The output of `ml/training/`,
the input to `ml/evaluation/` and `ml/inference/`.

## What goes here
- Versioned artifacts (e.g. `.joblib` / `.onnx` / weights) — never overwritten;
  a retrain is a new version.
- A **model card** per model (markdown): training data + versions, features used,
  metrics (incl. FPR on legitimate controls), intended use, **limitations and
  failure modes**, and promotion status.

## Model families (see top-level README)
1. **Behavioral** — account authenticity / coordination scoring.
2. **Explainability** — evidence ranking / rationale over an existing score
   (never a bare verdict).
3. **Calibration** — probability calibration / threshold mapping.

## Constraints
Artifacts here are **inert**. They run in production only after a deliberate,
flag-gated promotion into `apps/api/app/ml/scorer.py`. No artifact is
promotion-eligible without a model card and a passing `ml/evaluation/` report
that does not regress control false-positive rate vs. the rule baseline.
