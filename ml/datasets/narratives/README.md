# `ml/datasets/narratives/`

**Message-cluster datasets** — from the `Narrative` / `NarrativeMembership`
store. A narrative is a semantic cluster of *messages* (comments), a different
grain than account coordination.

## What goes here
- Per-membership rows: comment text + author external id + timestamp +
  parent content + narrative id, plus the narrative-level signals
  (`coordination_score`, `manipulation_probability`, `synchronization_intensity`,
  `semantic_cohesion`, `cluster_confidence`).
- Used to train/evaluate **narrative-coordination** and **manipulation /
  astroturf** models, and explainability over message clusters.

## Source
`apps/api` → `Narrative` / `NarrativeMembership` (offline export).

## Constraints
Keep the message grain distinct from account/campaign grains. Evidence-first;
labels (if any) come from `analyst_verdicts/` or disclosed sources. Validate
against `ml/schemas/`. Governance applies.
