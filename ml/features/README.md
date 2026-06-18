# `ml/features/`

**Feature engineering.** Transforms curated `ml/datasets/` records into
model-ready feature matrices for `ml/training/` and `ml/evaluation/`.

## What goes here
- Feature transforms / specifications (one module per feature family) and the
  versioned feature sets they emit.
- Feature definitions deliberately **mirror** the production detectors'
  semantics (cadence, repetition, profile, voice, engagement, fingerprint,
  coordination) so an offline feature stays consistent with the live signal it
  represents — but this code **does not import** `apps/api`. Consistency is by
  contract (`ml/schemas/`), not coupling.

## Contract
Inputs validate against the dataset schemas; outputs declare a feature-set
schema in `ml/schemas/`. A feature set is versioned and immutable so any model
trained on it is reproducible.

## Constraints
Offline only. No network, no production imports, no leakage of held-out/eval
rows into training features.
