# Hugging Face Integration Plan

> **Status: architecture only.** No implementation, no code changes, no model
> trained. Production (Render + Postgres + the rule engine) is preserved
> untouched. Hugging Face is Omi's **ML layer** — dataset hosting, training
> compute, and a model registry — **never** its primary backend: HF never serves
> a user request and never holds the production stores.

## Key finding: the loop is already skeletoned

Omi is **not** greenfield here. The train → push → load → blend path already
exists and degrades to a safe no-op:

| Piece | Where | State |
|---|---|---|
| HF-push trainer | `apps/api/ml_training/train.py` (`--hf-repo/--hf-token`, `huggingface_hub.HfApi`) | exists |
| Serving loader/blender | `apps/api/app/ml/scorer.py` (`MLScorer`, joblib bundle `{feature_schema_version, model, kind: lightgbm\|sklearn, trained_at, metrics}`) | exists, no-op until artifact + flag |
| Config seams | `app/core/config.py:182-194` — `use_ml_scorer`, `ml_model_path`, `ml_text_model_path`, `hf_model_repo`, `ml_blend_weight` | exists |
| Feature contract | `app/ml/features.py` (`FEATURE_SCHEMA_VERSION`, `build_feature_vector`) | exists |
| HF embeddings | `sentence-transformers/all-MiniLM-L6-v2` (`config.py:21`, `narrative/embeddings.py`, `detection/semantic.py`, TF-IDF fallback) | exists |

**What's missing (this plan completes):** dataset→HF sync, automated boot-download
from the registry, registry/promotion conventions, Render env+disk wiring,
rollback, and cost. The integration is mostly *connecting* what's there.

---

## Investigation (current reality)

1. **Database architecture.** SQLAlchemy 2.0 (`app/storage/models.py`); SQLite dev,
   **Postgres prod** via `OMI_DATABASE_URL`; Alembic + an idempotent boot
   migration (`_INCREMENTAL_COLUMNS`/`_ensure_indexes` in `storage/db.py`). The
   six stores (Memory/fingerprints, Coordination edges, Campaigns, Narratives,
   Content, Investigations) + Accounts/Scans/Watchlists/Alerts/Users/Billing.
2. **Dataset locations.** `datasets/` (859 MB, governed by `datasets/manifest.toml`:
   train/validation/quarantine/archive/reference); `apps/api/app/evaluation/
   benchmarks/*.json` (`seed_v1`, coordination, memory); `app/content/
   featured_campaigns.json`; `ml/datasets/` scaffold; ingest adapters in
   `app/ml/datasets/`.
3. **Deployment architecture.** Render blueprint (`render.yaml`), region oregon,
   `autoDeploy` from `main`; all compute in-process (no ML/inference service).
4. **Render services.** `omisphere-api` (FastAPI, **starter**, py 3.11.9, build
   `pip install -e .[youtube,postgres]`, `/health`); `omisphere-web` (Next.js,
   **starter**, node 20); `omisphere-postgres` (**basic-256mb ≈ $6/mo**, paid for
   daily backups — free tier is explicitly forbidden: it's deleted ~90 days and
   holds irreplaceable data). **No persistent disk declared today.**
5. **PostgreSQL usage.** The system of record for everything irreplaceable
   (investigations, fingerprints, watchlists, ground-truth labels, users,
   billing); auto-wired via `fromDatabase`. **The ML layer must never depend on it
   for serving and never risk it.**
6. **ML folder structure.** `ml/` scaffold (datasets/features/models/training/
   evaluation/inference/schemas + `OMI_NEURAL_NETWORK_V1.md`); `app/ml/`
   (`scorer.py`, `features.py`, `datasets/`, `export.py`, `public_import.py`);
   `ml_training/train.py`. The V1 model (calibrated GBT/sklearn) from the NN plan
   matches the scorer's `sklearn|lightgbm` support.

---

## A. GitHub → Dataset Pipeline

GitHub stays the **authoritative source for `manifest.toml` + code + small
benchmarks/seed**. But the 859 MB of raw corpora in the app repo bloats Render
clones/builds and git history — so:

- **Move heavy raw corpora out of the app repo** into an HF Dataset repo (or
  git-lfs); GitHub keeps the manifest + small sets + pointers. (A repo-hygiene win
  independent of ML.)
- **Curation step** (offline script in `ml/training/` or `scripts/`, reusing
  `app/ml/datasets/` adapters): read `manifest.toml` → select non-quarantine
  `train`/`validation` → run feature extraction (`app/ml/features` + an offline
  detector pass for engine-signal parity, per the NN plan §7) → emit **versioned,
  schema-validated parquet** (against `ml/schemas/`) staged for HF sync.

## B. Dataset → Hugging Face Sync

- Push curated, validated splits to a **private HF Dataset repo** via
  `huggingface_hub` (one-way: curation → HF). Versioned by HF dataset revisions
  (git-backed) — immutable, reproducible.
- **Governance enforced at sync:** quarantine/archive never sync; only
  manifest-approved splits; PII stays hashed (IO archives already hashed); private
  repo + scoped tokens.
- HF Datasets offloads the 859 MB from GitHub/Render and gives free streaming +
  versioning. GitHub remains the governance source of truth; HF mirrors the
  approved subset.

## C. Hugging Face → Training Pipeline

- **Reuse `ml_training/train.py`** (it already trains lightgbm/sklearn tabular +
  optional text head and pushes to HF). Point it at the HF Dataset, train on
  **CPU** (sklearn HGBT/lightgbm, minutes at this scale), emit the joblib bundle
  `scorer.py` already expects, and push **artifact + HF model card** to a model
  repo.
- **Compute under budget:** HF **Spaces free CPU tier**, or a **Render one-off/
  cron Job**, or local. **Avoid** HF AutoTrain / GPU Spaces / Inference Endpoints
  (all cost). Text head (`transformers`) stays optional and precomputed, never in
  the request path.

## D. Model Registry

- **HF Model Hub = the registry.** One private model repo (e.g.
  `omisphere/omisphere-detector`, the id `hf_model_repo` already anticipates).
- Each **revision** carries: the joblib artifact, an **HF model card** (= the NN
  plan's required card: training-data revision, metrics, limits, failure modes,
  intended use), and the eval report.
- **Lifecycle tags:** `shadow` / `candidate` / `production`. HF commit history is
  the immutable audit trail. No bespoke registry, DB table, or service needed.

## E. Model Promotion Workflow

1. Train → push a `candidate` revision.
2. **Offline gate** (`ml/evaluation/`, per NN plan): beats rule-baseline Brier;
   calibration/ECE in-bound; **no control-FPR regression** on `known-mixed` +
   `real_users`; corroboration discipline preserved.
3. **Shadow mode:** deploy with `use_ml_scorer=true` but **`ml_blend_weight=0`**
   (compute + log the model's score, but it does not move the served verdict).
   Compare to live over N scans.
4. If shadow holds → tag the revision `production` and raise `ml_blend_weight`
   conservatively. Promotion is a deliberate tag + config change.

**Blocked until** `known-mixed` legitimate-coordination controls and exported
analyst verdicts exist (Dataset Audit gap) — so V1 lives in shadow indefinitely
until then.

## F. Render Model Loading Workflow

- `omisphere-api` at boot (or a guarded refresh hook) calls
  `huggingface_hub.hf_hub_download(repo=hf_model_repo, revision=<pinned>,
  token=HF_TOKEN)`, caches to a small **Render persistent disk**, sets
  `ml_model_path` to the cached file, and loads via the existing `MLScorer`
  (blend behind `use_ml_scorer`).
- **New env (all `sync:false` / pinned):** `OMI_HF_MODEL_REPO`,
  `OMI_HF_MODEL_REVISION` (**pin a revision, never `latest`**), `HF_TOKEN`
  (read-only), `OMI_USE_ML_SCORER`, `OMI_ML_BLEND_WEIGHT`.
- **Build deps:** add `huggingface_hub` (+ `lightgbm`/`joblib`) to the install
  extra used by `omisphere-api`; keep `transformers` optional (text head only).
- **Inference is in-process, CPU, sub-millisecond** — no new service, no GPU, no
  inference endpoint. A ~1 GB persistent disk holds the artifact + HF cache.

## G. Rollback Strategy

- **Instant kill switch:** `OMI_USE_ML_SCORER=false` (or `ml_blend_weight=0`) →
  rule engine resumes unchanged via the scorer's documented no-op path. No model
  redeploy needed — an env flip.
- **Version rollback:** repoint `OMI_HF_MODEL_REVISION` to the prior immutable HF
  revision + restart. HF retains every revision.
- **Pin, never `latest`:** deploy only pinned revisions (reproducible, blue/green
  at the artifact level).
- **Automatic schema guard:** the scorer refuses a `feature_schema_version`
  mismatch and returns the input unchanged — a bad artifact cannot corrupt
  scoring.
- **Shadow mode** stops bad models before they ever affect a verdict.
- **Postgres is never touched by the ML layer** → an ML failure cannot lose or
  corrupt the system of record.

## H. Cost Estimates

| Item | Plan | ~$/mo |
|---|---|---|
| omisphere-api | Render starter (existing) | ~7 |
| omisphere-web | Render starter (existing) | ~7 |
| omisphere-postgres | basic-256mb (existing) | ~6 |
| **Existing baseline** | | **~20** |
| HF private Dataset repo | free tier (859 MB fits) | 0 |
| HF private Model repo (registry) | free tier | 0 |
| Training compute | HF Spaces free CPU **or** Render cron | 0–~1 |
| Render persistent disk (artifact/cache, ~1 GB) | $0.25/GB/mo | ~1 |
| In-process CPU inference | existing api service | 0 |
| **New marginal spend** | | **~$0–2/mo** |

Optional, only if limits are hit: HF **PRO ($9/mo)** for more private storage/
Space hours; a larger Postgres as data grows. **Total stays well under $50.**
**Explicitly avoid** (break budget, unnecessary at CPU/in-process scale): HF
Inference Endpoints, HF AutoTrain, GPU Spaces, a dedicated model/inference
service.

---

## Constraints honored & risks

- **HF = ML layer only.** It hosts datasets, runs training, and stores model
  artifacts. It never serves user traffic and never holds the six production
  stores — those remain in Render Postgres (the preserved primary backend).
- **Production preserved.** The serving seam is a flagged no-op until a model +
  flag are present; this plan changes no scoring code.
- **No GPU, < $50/mo, commodity hardware** — sklearn/lightgbm CPU training, tiny
  artifact, in-process inference.
- **Design note (faithful to code):** `scorer.py` *blends* the final probability
  (`ml_blend_weight`) and re-tiers — it does not enter the log-odds aggregation as
  an independent axis. To preserve corroboration discipline, keep `ml_blend_weight`
  conservative and validate on legitimate controls before raising it, so the
  learned model cannot push a single-axis verdict to maximal. (Reconcile with the
  NN-plan "axis" framing during implementation.)
- **Privacy/governance:** private HF repos, read-only serving token, manifest
  quarantine never synced, IO identities stay hashed.

## Sequencing

1. Move heavy corpora to a private HF Dataset repo; GitHub keeps manifest + small
   sets (repo hygiene). 2. Stand up the curation→sync script. 3. Reuse
   `ml_training/train.py` against the HF Dataset → push a `candidate` to the model
   repo. 4. Wire the Render boot-download + disk + env (behind `use_ml_scorer`).
   5. Run shadow mode. 6. Populate `known-mixed` controls + analyst verdicts, then
   evaluate against the promotion gate before raising `ml_blend_weight`.
