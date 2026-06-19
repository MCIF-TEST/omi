# HUGGING FACE UPLOAD PLAN (dataset organization V1)

> **Documentation only** — defines the Hugging Face target structure and upload
> plan. No files were moved; current repo paths are preserved. Complements
> `ml/HUGGING_FACE_INTEGRATION_PLAN.md` (the mechanics) with the dataset-group
> layout. See `DATASET_INVENTORY.md` (classification) and
> `DATASET_MIGRATION_MAP.md` (current→target).

## Target structure (proposed)
```
datasets/
├── authenticity/
│   ├── human_accounts/      real_users.csv · known-good/ (EVAL)
│   ├── bot_accounts/        fake_users.csv · cresci-rtbust-2019/
│   ├── mixed_quality/       fake_social_media_global_2.0 · TwitterData_Joined · ai-vs-human · reddit
│   └── quarantined/         bot_detection_data.csv            ← never uploaded
├── coordination/
│   ├── state_actor/         8 IO disclosure archives (Russia/Iran/China/GRU/IRA/Xinjiang/E+N Africa)
│   ├── campaign_data/       astroturf · featured_campaigns (pointer)
│   ├── narrative_data/      Narrative store export
│   └── coordination_controls/  known-mixed/ (to collect)
├── explainability/
│   ├── investigations/      Investigation payloads (export)
│   ├── analyst_verdicts/    Investigation.verdict + AccountLabel (gold)
│   ├── reports/             generated reports (export)
│   └── evidence_chains/     score_breakdown/contributions (export)
├── evaluation/
│   ├── benchmark_sets/      seed_v1 + coordination/memory (pointer to apps/api)
│   ├── holdout_sets/        omi-behavioral-v1 holdout (regenerable)
│   └── calibration_sets/    activity_botscore.csv
└── archive/
    ├── deprecated/          fake_social_media.csv · ai_vs_human_text.csv · article_discusses_claim · .xlsx
    ├── duplicates/          TwitterData_FE · Twitter_Data · Twitter_Users
    └── low_trust/           location_data.csv
```

## HF repo layout (private)
One **private HF Dataset repo per top-level group** (clean access control + size
isolation), versioned by HF dataset revisions:
| HF dataset repo | Holds | Upload? |
|---|---|---|
| `omisphere/authenticity` | human/bot/mixed_quality (TRAIN+EVAL) | ✅ |
| `omisphere/coordination` | state_actor + campaign + controls (EVAL) | ✅ (anonymized) |
| `omisphere/explainability` | investigations / analyst_verdicts (gold) | ✅ when exported |
| `omisphere/evaluation` | benchmark / holdout / calibration (EVAL) | ✅ |
| `archive/`, `authenticity/quarantined/` | deprecated / duplicates / low_trust / **poison** | ❌ **never uploaded** |

## What uploads vs what stays
- **Upload (TRAIN + EVAL):** the curated authenticity/coordination/evaluation
  groups. The 859 MB of raw corpora are the prime candidate to live in HF
  Datasets rather than the app repo (repo-hygiene win — see the integration plan).
- **Never upload:** `archive/*` and `authenticity/quarantined/*` (QUARANTINE) —
  governance excludes poison/low-trust from training *and* from the registry.
- **Pointers, not uploads (in-place prod assets):** `apps/api/app/evaluation/
  benchmarks/*.json` and `apps/api/app/content/featured_campaigns.json` stay in
  the app; the HF `evaluation/benchmark_sets/` references them.

## Governance & privacy
- Sync is **manifest-gated**: only `train`/`validation`/`reference` files sync;
  `archive`/`quarantine` never leave the repo.
- IO/state-actor identities are already **hashed** at source — keep them hashed;
  private repo + read-only tokens (per `ml/HUGGING_FACE_INTEGRATION_PLAN.md`).
- Datasets are **immutable per revision**; a new curation is a new HF revision.
- Each uploaded group ships a dataset card (provenance, labels, license, the
  leakage caveats from `DATASET_INVENTORY.md` — e.g. global_2.0's username
  shortcut).

## Sync mechanism (reuse existing)
One-way curation → HF via `huggingface_hub` (offline/CI), per
`ml/HUGGING_FACE_INTEGRATION_PLAN.md` §B. Order: (1) curate + schema-validate per
group, (2) push to the matching private HF dataset repo, (3) record the revision
in the dataset card. No production path, no GPU, ~$0 (free tier).

## Markers (every dataset)
TRAIN · EVAL · ARCHIVE · QUARANTINE assigned per dataset in
`DATASET_INVENTORY.md`. Upload eligibility = TRAIN or EVAL **and** not in
`archive/`/`quarantined/`.

*No files moved, no manifest/production/test changes — documentation only.*
