# Shadow-Mode Integration Plan — `omi-behavioral-v1` (Deliverable G)

> **Nothing here is executed now.** This documents *how* a learned authenticity
> model would later run in shadow, with no effect on live users. `use_ml_scorer`
> stays **OFF**; production scoring is unchanged.

## Why this exact artifact cannot shadow-deploy as-is
The serving scorer (`apps/api/app/ml/scorer.py`) builds inputs via
`app/ml/features.build_feature_vector` and refuses any artifact whose
`FEATURE_SCHEMA_VERSION` doesn't match the **42-dim `omi_v1`** vector.
`omi-behavioral-v1` uses `dataset_native_v0` (25 dataset-native columns) →
**structurally rejected**. The block is mechanical, not just policy — which is
the point: an offline baseline can never leak into production.

## The bridge to a shadow-able model (the V2 step, future task)
1. **Re-extract features in the `omi_v1` schema.** Run the production detectors
   offline over **raw timelines** (IO disclosure accounts as positives;
   `known-good` / `known-mixed` + genuine accounts as negatives) to produce the
   42-dim `build_feature_vector` rows. This closes the feature-parity gap the
   audits flagged.
2. **Retrain** the same CPU XGBoost + isotonic calibration on those features.
3. **Emit the serving bundle** matching the scorer's expected shape
   (`feature_schema_version`, `model`, `kind`, `trained_at`, `metrics`).

## Shadow rollout (once a `omi_v1`-schema model exists)
1. Publish the artifact to the HF model registry (per `HUGGING_FACE_INTEGRATION_PLAN`),
   pin a revision, and have `omisphere-api` download it at boot.
2. Set `use_ml_scorer=true` **but `ml_blend_weight=0`** → the scorer **computes
   and logs** `authenticity_probability` alongside the rule verdict but **does
   not change the served score**. (True shadow: zero user impact.)
3. **Observe** for N scans: agreement with the rule engine, Brier vs the rule
   baseline, and especially **FPR on `known-mixed` legitimate-coordination
   controls** (newsrooms, officials, brands).

## Promotion gate (must all hold before raising `ml_blend_weight`)
- Beats the rule baseline's Brier on held-out data.
- **No regression in control-FPR** (`known-mixed` / `real_users`) — hard gate.
- Calibration (ECE) within bound; corroboration discipline preserved (the
  learned prior cannot push a single-axis verdict to maximal).
- Model card + current evaluation report attached.

## Rollback
`OMI_USE_ML_SCORER=false` (or `ml_blend_weight=0`) → rule engine resumes via the
scorer's documented no-op path; repoint `OMI_HF_MODEL_REVISION` to roll back a
version. Postgres / production stores are never touched by the ML layer.

## Status today
`omi-behavioral-v1` remains an **offline baseline** in `ml/models/`.
`use_ml_scorer = False`. No deployment, no blending, no shadow run — train +
evaluate only.
