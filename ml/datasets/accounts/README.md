# `ml/datasets/accounts/`

**Per-account behavioral datasets** — the core supervised set for behavioral
models. One row per scanned account.

## What goes here
- Behavioral features + raw signals: profile shape, posting cadence, content
  repetition, personal-voice rate, engagement patterns, fingerprint-neighbor
  context, cross-account/coordination signal, and the 8 detector
  `SignalResult`s (probability + confidence + evidence) from a `Scan`.
- The engine's own outputs for baselining: `overall_probability`, `tier`,
  `confidence`.
- Labels (for supervised training) joined from `analyst_verdicts/`.

## Source
`apps/api` → `Account` (+ latest `Scan.signals_json`, `fingerprint_json`),
via offline export.

## Constraints
Single-account grain. The engine's calibrated probability is the **baseline to
beat**, not a label. Evidence-first; never store a verdict-as-truth here — the
gold label is the human verdict in `analyst_verdicts/`. Validate against
`ml/schemas/`. Governance applies.
