# `ml/datasets/`

Curated, **versioned** datasets derived from OmiSphere's own intelligence
stores, organized by grain. These are the inputs to `ml/features/` and the
held-out sets for `ml/evaluation/`.

## Governance (mirrors `datasets/manifest.toml`)

Every dataset declares a split: **train / validation / archive / quarantine**.
Quarantined or poisoned data is never used for training or evaluation. Datasets
are immutable once published; a new version is a new file, never an in-place
edit (so results stay reproducible).

## Evidence-first contract

A dataset row captures **observations + evidence + confidence + outcome**, not a
persisted verdict-as-truth. Where a label is needed for supervised learning, it
comes from `analyst_verdicts/` (human ground truth) or from a disclosed source
(e.g. a platform state-actor archive) — and the provenance is recorded.

## Subfolders (one per grain, matching the platform's stores)

| Folder | Source store | Grain |
|---|---|---|
| `investigations/` | `Investigation.payload_json` | end-to-end case (multi-input) |
| `narratives/` | `Narrative` / `NarrativeMembership` | message cluster |
| `campaigns/` | `Campaign` / `CampaignMember` / `CampaignObservation` | coordinated account cluster |
| `accounts/` | `Account` (+ `Scan` signals, fingerprint) | single account |
| `analyst_verdicts/` | `Investigation.verdict`, account labels | human ground-truth label |

## Format

Prefer columnar/line-delimited, schema-validated formats (CSV / JSONL /
Parquet). Every dataset must validate against a contract in `ml/schemas/`.
PII / handle minimization follows the platform's anonymization stance
(disclosure archives are already anonymized at source).
