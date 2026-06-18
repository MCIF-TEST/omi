# `ml/inference/`

**Offline / batch inference + the production promotion contract.**

## What goes here
- Batch scoring scripts that run a trained `ml/models/` artifact over a dataset
  (e.g. to backfill scores for analysis or to compare a candidate model against
  the rule baseline at scale).
- A **production-shaped interface contract**: the input/output signature a model
  must satisfy to slot into the live scorer, documented against the real seam
  `apps/api/app/ml/scorer.py` (`get_scorer()`, today dormant — flag off, no
  artifact). Promotion is then *wiring*, not a rewrite.

## The single promotion point
A behavioral model reaches production **only** by:
1. passing `ml/evaluation/` (incl. control-FPR guard), and
2. being loaded into `apps/api/app/ml/scorer.py` behind its existing flag,
3. as a deliberate, reviewed change — never auto-loaded from here.

## Constraints
Nothing in this folder runs in production or is imported by it. No network, no
writes to production stores. The contract documents the boundary; it does not
cross it.
