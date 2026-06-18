# `ml/datasets/investigations/`

**End-to-end case datasets** — snapshots of `Investigation.payload_json`, the
comprehensive-scan result the product persists (focus account + a content's
commenters + pasted comments + the cross-links between them, with the overall
probability, tier, confidence, and coordination summary).

## What goes here
- One row/record per investigation case: the inputs provided, the per-component
  results, cross-link severities, the comprehensive verdict, and (when present)
  the analyst verdict joined from `analyst_verdicts/`.
- Used to train/evaluate **case-level** models and **explainability** models
  that must reason over multiple converging inputs, not a single account.

## Source
`apps/api` → `Investigation` store (snapshots), via offline export. Not a live
connection.

## Constraints
Evidence-first (store the evidence + cross-links, not a verdict-as-truth); the
human conclusion lives in `analyst_verdicts/`. Validate against
`ml/schemas/`. Respect train/validation/archive/quarantine governance.
