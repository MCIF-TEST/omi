# OMISPHERE

YouTube comment-section intelligence. Detects bots, AI-generated engagement,
and coordinated influence campaigns on YouTube videos and channels. Powered
by the **omi** detection engine.

> Beta. All output is probabilistic — never a definitive judgement about
> any account or the person behind it.

---

## What this does today

Paste a YouTube video URL → OMISPHERE scans every commenter, fingerprints
their behavior across eight independent detectors, finds coordination
clusters between accounts, and saves the whole thing as an investigation
you can share, export, or rescan later.

Paste a YouTube channel → it does the same for that channel's account
profile and recent activity.

**What it does NOT do today** (be aware, then decide if it fits):

* No X / Twitter, Reddit, TikTok, or Instagram ingestion. The detection
  engine is platform-agnostic; only the YouTube ingestion adapter is
  shipped. Other platforms are on the roadmap and require their own API
  access.
* No real-time push. Watchlists are rescanned on a schedule, not by a
  firehose subscription.
* No team / multi-seat features. One account per workspace today.

Everything in the YouTube path — per-commenter scoring, the eight
detectors, coordination clusters, saved investigations, sharable reports,
watchlist alerts on a polling schedule, narrative tracking across all
scans — is live and tested.

---

## Repo layout

```
omisphere/
├── apps/
│   ├── api/        ← omi engine + FastAPI service (Python)
│   └── web/        ← OMISPHERE dashboard (Next.js + TypeScript)
├── packages/
│   └── shared/     ← shared TypeScript types
├── infrastructure/
│   ├── docker-compose.yml      (local Postgres)
│   └── render.yaml             (production blueprint)
├── docs/
│   ├── architecture.md         ← read first for design rationale
│   ├── design-system.md
│   ├── operations.md           ← deploy / scale / incident runbook
│   └── roadmap.md
└── scripts/        ← Windows launcher .bat files
```

See [`docs/architecture.md`](docs/architecture.md) for the system overview
and [`docs/operations.md`](docs/operations.md) for the deployment runbook.

---

## Quickstart (Mac / Linux)

```bash
# Postgres for local dev
docker compose -f infrastructure/docker-compose.yml up -d

# API
cd apps/api
pip install -e .[youtube,ml]
cp ../../.env.example .env   # then edit .env with your YouTube key
uvicorn app.main:app --reload --port 8000

# Web (in another terminal)
cd apps/web
npm install
npm run dev    # → http://localhost:3000
```

The `[ml]` extra installs `sentence-transformers` for real semantic
narrative clustering. Without it, OMI falls back to a hashing embedder
that produces coarser clusters; the API logs a warning if it boots in
that mode.

---

## Quickstart (Windows)

You need **Python 3.11+** and **Node.js 20 LTS** installed first.

* Python: [python.org/downloads](https://www.python.org/downloads/) — tick **"Add Python to PATH"**.
* Node:   [nodejs.org](https://nodejs.org/) — pick the LTS installer; tick **"Automatically install necessary tools"**.

Then:

1. Double-click `scripts\setup_omisphere.bat`. First run takes ~2 min — installs Python deps + npm modules + creates `.env`.
2. Open `apps\api\.env` in Notepad. Set `OMI_YOUTUBE_API_KEY=<your YouTube key>`. Save.
3. Double-click `scripts\start_omisphere.bat`. Two terminals open (API + Web). Browser opens to `http://localhost:3000`.

Sign up with any email + 8+ character password. You'll get 3 free trial credits.

---

## Required configuration

| Variable | Required in production | Purpose |
|---|---|---|
| `OMI_YOUTUBE_API_KEY` | **yes** | YouTube Data API v3 key. Without it, every scan returns 503. |
| `OMI_DATABASE_URL` | **yes** | Postgres connection string. SQLite is allowed in dev only — Render boot will refuse to start a production deploy with SQLite. |
| `OMI_SESSION_SECRET` | **yes (when require_auth)** | 32+ char random string. Forgeable cookies if missing. |
| `OMI_ENV` | yes | `production` or `development` |
| `OMI_ANTHROPIC_API_KEY` | optional | Enables Claude Haiku commentary on investigations. Falls back to a template generator when unset. |
| `OMI_STRIPE_*` | optional | Self-serve billing. Falls back to 503 on `/v1/billing/*` if unset; free tier still works. |
| `OMI_SMTP_*` | optional | Email alert delivery for watchlists. Webhooks work without it. |

In `production`, OMISPHERE refuses to start if `OMI_YOUTUBE_API_KEY` is
empty, `OMI_DATABASE_URL` points at SQLite, or `OMI_SESSION_SECRET` is the
dev default. Override with `OMI_ALLOW_DEGRADED_PRODUCTION=true` only for
emergency recovery.

---

## Running the tests

```bash
# Backend — 370+ tests
cd apps/api
pytest -q

# Frontend — Vitest unit tests for the shared client + formatters
cd apps/web
npm test
```

---

## Deploy to production

See [`docs/operations.md`](docs/operations.md) and
`infrastructure/render.yaml`. Render Blueprint provisions web + api +
Postgres; you supply the YouTube key.

---

## License

Proprietary — all rights reserved.
