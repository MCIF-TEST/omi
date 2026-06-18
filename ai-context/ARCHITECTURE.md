# OmiSphere — ARCHITECTURE (current technical reality)

> Documented from the actual repository. Update when the architecture changes.
> Deeper design docs live in `docs/` (e.g. `docs/architecture.md`,
> `docs/api-spec.md`, `docs/engine-evaluation.md`).

## Monorepo layout

- `apps/api` — FastAPI backend (the detection/intelligence engine + REST API).
- `apps/web` — Next.js 14 frontend (analyst UI).
- `packages/shared` — shared assets between apps.
- `datasets/` — training/eval corpora, governed by `datasets/manifest.toml`
  (train / validation / archive / quarantine; poison stays quarantined).
- `docs/` — long-form design, audit, and roadmap docs.
- `infrastructure/` — `docker-compose.yml`, `render.yaml`.
- `scripts/`, `apps/api/ml_training/` — model training / ops scripts.

## Frontend (`apps/web`)

- Next.js **14.2** (app-router), React **18.3**, TypeScript **5.6**.
- Tailwind CSS **3.4**; icons via `lucide-react`.
- Tests: **vitest** (pure-function `lib/` tests; no React component-test infra).
- Auth gating via `middleware.ts`. App routes: dashboard, investigate,
  investigations, accounts, graph, narratives, content, channels, monitoring,
  search, bulk, reports, settings.
- Gates before commit: `npm run typecheck`, `npm run test`, `npm run build`.

## Backend (`apps/api`)

- **FastAPI** (≥0.115) + **uvicorn**, **Pydantic 2**, Python **3.11**.
- **SQLAlchemy 2.0** ORM (`app/storage/models.py`, sessions in
  `app/storage/db.py`).
- Auth: session cookies (`itsdangerous`) + `bcrypt`; `OMI_REQUIRE_AUTH`
  toggles local (id=0) vs authenticated mode.
- Networking: `httpx` (core — Twitter/X client + TestClient).
- Graphs: `networkx`. ML: `numpy` + `scikit-learn`; optional
  `sentence-transformers` (`ml` extra) for embeddings, with TF-IDF fallback.
- Background work: `app/core/background.py` — a bounded `ThreadPoolExecutor`
  for fire-and-forget tasks (content-intel recording, narrative ingestion,
  investigation persistence, alert delivery). Best-effort, never blocks a
  response. (Swap target: Dramatiq+Redis; interface `submit(fn, *args)`.)
- Gates before commit: full suite `cd apps/api && python -m pytest tests/ -q`
  (~746 tests). Best-effort DB writes are SAVEPOINT-isolated.

## Database

- Default **SQLite** (file, or in-memory for tests via `StaticPool`; WAL +
  busy-timeout for file SQLite). Production **Postgres** via `OMI_DATABASE_URL`.
- Migrations: **Alembic** (`apps/api/alembic`) **plus** an idempotent in-process
  boot upgrade pass in `db.py` (`_INCREMENTAL_COLUMNS` ALTER-TABLE +
  `_ensure_indexes`) so new columns/indexes land on existing DBs at startup.
- Test isolation note: the in-memory test DB is a single shared connection, so
  the (DB-heavy) content-intel task is run **inline** in tests via a conftest
  fixture; all other background tasks keep real async behavior.

## Hosting

- **Render.com** blueprint (`render.yaml`): `omisphere-web` (Next.js),
  `omisphere-api` (FastAPI), `omisphere-postgres` (Postgres). Region oregon.
  API: `pip install -e .[youtube,postgres]`, `uvicorn app.main:app`,
  health `/health`, autoDeploy from `main`. Python 3.11.9.
- Stripe webhook: `POST /v1/billing/webhook`.

## Platforms (data sources)

- **YouTube** (`app/integrations/youtube.py`) and **X/Twitter**
  (`app/integrations/twitter.py`, via twitterapi.io).
- Unified behind a **Source** protocol (`app/integrations/source.py` →
  `YouTubeSource`, `TwitterSource`): the only platform-specific seam. The
  detection/coordination/memory/OmiScore stack is platform-agnostic.

## Major systems (each: real module → REST prefix)

- **Scanning / Orchestrator** — `app/orchestrator.py` (`scan_comprehensive`,
  `scan_account_with_memory`, `scan_video_full`); routes `app/routes/scan.py`
  + `scan_async.py` (`/v1/scan/...`: `link/start` async job, `youtube/full`,
  `youtube/account`, `twitter/account`, `demo`, `bulk`, `comprehensive`,
  `estimate`). The product's primary flow is `/v1/scan/link` → comprehensive.
- **Detection engine** — `app/detection/scoring.py` (log-odds aggregate →
  `overall_probability` + 4-level `tier` LOW/MODERATE/ELEVATED/HIGH), detectors
  (temporal, semantic, ai_writing[supplemental], profile, voice, engagement,
  memory, coordination, narrative, community), correlation/decorrelation.
- **Coordination detection** — `app/detection/coordination/*`
  (`fingerprint_cluster`, `style_match`, `co_engagement`, `co_tag`,
  `age_cohort`, `temporal_semantic`, `reply_pods`; `aggregate.py` =
  corroboration-gated 0–1 score; `elevate.py`).
- **OmiScore intelligence** — `app/intelligence/` (omiscore.py, signals.py,
  schemas.py); `/v1/intelligence`. Composes a ScanResult into an explainable
  0–100 envelope (additive; reads the engine, does not replace it).
- **Memory** — `Account.fingerprint_json` + k-NN (`app/memory/`); the
  cross-scan learning loop.
- **Investigations** — `Investigation` model; `/v1/investigations`; persisted
  snapshot of a comprehensive scan, with analyst verdict + notes.
- **Campaigns** — `Campaign` / `CampaignMember` / `CampaignObservation`;
  `app/campaigns/service.py`; `/v1/campaigns` (+ public share router). Featured
  campaigns seeded from state-actor disclosure archives (`app/content/`).
- **Narratives** — `Narrative` / `NarrativeMembership`; `app/narrative/`
  (service.py, coordination.py); `/v1/narratives`. Message-cluster grain
  (distinct from account coordination).
- **Monitoring / Watchlists / Alerts** — `Watchlist` / `Alert`;
  `app/monitoring/` (service.py, scheduler.py, anomalies.py);
  `/v1/monitoring` + `/v1/watchlists`. Watchlists are platform-aware.
- **Graphs** — `CoordinationEdge` (cumulative cross-scan pairs) +
  `UserGraph` / `UserGraphMember` (analyst-curated); `/v1/graphs`.
- **Content Database** — `ContentEntity` / `CommentBatch` / `ContentComment`;
  `app/content/service.py`; `/v1/content`. Persistent per-content intelligence
  (recorded in the background from comprehensive YouTube scans).
- **Reports** — `/v1/reports` (share + public); `app/reports/`
  (campaign_pack, templates).
- **Auth / Billing / Credits** — `/v1/auth`, `/v1/billing` (Stripe, off by
  default → free tier).
- **ML / Learning** — `app/ml/` + `ml_training/` + `scripts/train_model.py`;
  `/v1/learning`; datasets governed by `datasets/manifest.toml`.

## Stores (the six, per the guardian model)

Memory (fingerprints + k-NN) · Coordination edges/clusters · Campaigns ·
Narratives · Content intelligence · Investigations (payload snapshots).

## Optional integrations (off by default in dev)

Anthropic LLM (analysis/reasoning; template fallback when off) · SMTP email
alerts (webhook delivery still works) · Stripe billing · background monitoring
scheduler · sentence-transformers embeddings.
