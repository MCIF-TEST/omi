# Omi Intelligence Foundation (`/ml`)

Forward-looking **infrastructure scaffold** for OmiSphere's next-generation
machine-learning work: behavioral models, explainability models, and
analyst-training datasets.

> **Status: infrastructure only.** Nothing in this directory is imported by, or
> wired into, `apps/api` or `apps/web`. It does **not** modify or replace the
> live detection engine, scoring, coordination logic, or any API. It is an
> offline staging ground for data curation, feature engineering, model R&D, and
> evaluation. Anything built here reaches production **only** through a
> deliberate, flag-gated promotion into the existing dormant model seam
> (`apps/api/app/ml/scorer.py`) — never by side-effect.

---

## Why this exists

OmiSphere's production engine today is a **calibrated rule engine**
(`apps/api/app/detection/scoring.py`) plus a corroboration-gated coordination
aggregator (`apps/api/app/detection/coordination/`) and an additive
explainability layer (`apps/api/app/intelligence/` — OmiScore). A learned
scorer slot already exists but ships **dormant** (`apps/api/app/ml/scorer.py`,
flag off, no artifact).

This `/ml` foundation is where the data and models that could one day fill that
slot are built — **without touching the engine until they are proven**. It
mirrors the platform's intelligence so offline work stays faithful to
production, but it stays decoupled so experimentation can never destabilize a
live scan.

## Relationship to existing repository assets (no overlap, no modification)

| Existing | Role | This `/ml` |
|---|---|---|
| `datasets/` + `datasets/manifest.toml` | Raw corpora + train/validation/archive/quarantine governance | We **reuse the same governance discipline**; `/ml/datasets/` holds curated, grain-specific datasets derived from Omi's own stores |
| `apps/api/app/ml/` (scorer, dormant) | The single production promotion point | `/ml/inference/` documents that contract; nothing here imports it |
| `apps/api/app/ml_training/`, `scripts/train_model.py` | Current training scripts | Superseded going forward by `/ml/training/`; the old scripts remain untouched |
| `apps/api/app/detection`, `app/intelligence` | Source-of-truth engine | Mirrored (not imported) by `/ml/features` and `/ml/schemas` |

## Directory structure

```
ml/
├── README.md            ← this file
├── datasets/            curated, versioned datasets, one subfolder per grain
│   ├── investigations/  end-to-end comprehensive-scan cases
│   ├── narratives/      message-cluster (narrative) datasets
│   ├── campaigns/       materialized coordinated-cluster datasets
│   ├── accounts/        per-account behavioral datasets
│   └── analyst_verdicts/ human ground-truth labels (the gold set)
├── features/            feature-engineering: datasets → model-ready matrices
├── models/             serialized model artifacts + model cards
├── training/           offline, config-driven training pipelines
├── evaluation/         held-out evaluation harnesses, metrics, reports
├── inference/          offline/batch inference + the promotion contract
└── schemas/            versioned data contracts between every layer
```

## The pipeline (how every future model flows through these folders)

```
Omi stores (the six)                  ← Memory, Coordination, Campaigns,
  exported snapshots                    Narratives, Content, Investigations
        ↓
ml/datasets/<grain>/                  ← curated + versioned + governed
        ↓  (validated against ml/schemas/)
ml/features/                          ← model-ready feature matrices
        ↓
ml/training/                          ← configs → fit
        ↓
ml/models/                           ← artifact + model card
        ↓
ml/evaluation/                       ← Brier, calibration, tier accuracy,
        ↓                              FPR on LEGITIMATE controls, cluster P/R
ml/inference/                        ← batch scoring + production-shaped contract
        ↓  (deliberate, flag-gated)
apps/api/app/ml/scorer.py            ← the ONE promotion point (today dormant)
```

## The three model families this structure is built for

1. **Behavioral models.** The eventual successor to the dormant learned-scorer
   slot: predict an account's authenticity / coordination likelihood from
   behavioral features (cadence, repetition, profile shape, fingerprint
   neighborhood, engagement, cross-account signals). A behavioral model is
   **only** promotion-eligible when it beats the calibrated rule baseline on
   Brier score **and** does not regress the false-positive rate on legitimate
   controls (newsrooms, on-message officials, benign automation).

2. **Explainability models.** Rank and articulate the **evidence and rationale**
   behind a score — feeding the OmiScore dimension trails and the
   evidence-for / evidence-against contract the UI already shows. These never
   emit a bare verdict; they make an existing score legible. Aligns with the
   product principle *transparency over certainty*.

3. **Analyst-training datasets.** Curated, labeled case libraries (with
   `analyst_verdicts/` as the gold labels) used two ways: to **train models**,
   and to **train and calibrate human analysts** (worked examples, edge cases,
   known false-positive traps). This operationalizes *analyst-controlled* — the
   human verdict is both the ground truth and the thing we help sharpen.

## Non-negotiable principles inherited from the platform

- **Evidence-first, never verdict-as-truth.** Datasets store observations,
  evidence, probabilities, confidence, and *outcomes* — not a persisted
  "this IS a bot/campaign" boolean.
- **Probabilistic + explainable.** Every model output must carry confidence and
  trace back to features/evidence.
- **Precision discipline.** Measure FPR on legitimate controls before claiming a
  win; a single non-discriminative signal must never drive a maximal verdict
  (the production corroboration gate is the reference behavior to preserve).
- **Governance.** Mirror `datasets/manifest.toml`: keep train / validation /
  archive / quarantine separated; quarantined/poison data never trains.
- **Decoupled.** No imports from here into production; promotion is explicit.

## Current contents

This is the initial scaffold: each folder carries a `README.md` describing its
purpose and the data/artifacts it will hold. No datasets, features, models, or
code are committed yet — that work lands in subsequent, scoped tasks.
