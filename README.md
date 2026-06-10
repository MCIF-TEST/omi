# OMISPHERE

**Evidence-based Campaign Intelligence** for investigators, researchers,
journalists, and trust-&-safety teams. OMISPHERE detects coordinated
account groups on YouTube and X (Twitter) — durable, evolving
**Campaign** records carrying their own evidence, confidence, and
corroboration. Powered by the **omi** detection engine.

> Beta. All output is probabilistic. We record observations, evidence,
> and confidence — never a verdict-as-truth about any account or the
> person behind it.

---

## What this does today

Paste a YouTube video or an X (Twitter) account URL → OMISPHERE scans
every commenter / poster, fingerprints their behavior, runs six
cross-account coordination detectors (`fingerprint_cluster`,
`co_engagement`, `co_tag`, `style_match`, `temporal_semantic`,
`age_cohort`), and surfaces the coordinated groups as a durable
**Campaign** with members, methods, hashtags/mentions, recurrence
across scans, and an observation timeline. Saved investigations are
shareable, exportable, and re-scannable.

**The trust contract** (validated on real state-IO disclosure
archives — Russia GRU/IRA, Iran, China Xinjiang/Changyu — alongside
legitimate-coordination controls: journalists, newsrooms, politicians,
brands):

* **Corroboration gate** — a campaign verdict requires either a
  discriminative detector (fingerprint / co-engagement / co-tag, the
  ones with measured IO-vs-human separation) or two distinct supporting
  detectors agreeing. A lone supporting signal is capped at MODERATE
  at both the campaign and per-member level. Campaign-level false-
  positive rate on legitimate-coordination controls: **0%**.
* **Evidence, not verdicts** — every campaign record stores observed
  scores + methods + evidence strings + observation history. Nothing is
  persisted as "this IS a manipulation campaign."
* **Visible uncertainty** — confidence band, evidence-for, evidence-
  weakening, and corroboration status are surfaced everywhere a verdict
  is shown.

**What it does NOT do today** (be aware, then decide if it fits):

* No Reddit, TikTok, or Instagram ingestion. The detection engine is
  platform-agnostic; YouTube and X ingestion adapters ship. Other
  platforms require their own API access.
* No real-time push. Watchlists are rescanned on a schedule, not by a
  firehose subscription.
* No team / multi-seat features. One account per workspace today.

Everything described above — per-account scoring, the six cross-account
coordination detectors, the Campaign Library, saved investigations,
narrative observatory, shareable evidence reports, watchlist alerts on a
polling schedule — is live and tested.

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
# Backend — 660+ tests, including coordination + IO-eval ratchets
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
