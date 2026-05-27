# OMISPHERE

Probabilistic social authenticity intelligence. Detects bots, AI-generated
engagement, coordinated influence campaigns, and synthetic virality on
public social media. Powered by the **omi** detection engine.

> Private beta. All output is probabilistic — never a definitive judgement.

---

## Repo layout

This is a monorepo:

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
│   ├── architecture.md         ← READ FIRST
│   ├── design-system.md
│   └── roadmap.md              ← 9-phase plan + status
└── scripts/        ← Windows launcher .bat files
```

See [`docs/architecture.md`](docs/architecture.md) for the system overview
and [`docs/roadmap.md`](docs/roadmap.md) for what's built vs. coming.

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

## Quickstart (Mac / Linux)

```bash
# Postgres for local dev (optional in Phase 1 — SQLite works too)
docker compose -f infrastructure/docker-compose.yml up -d

# API
cd apps/api
pip install -e .[youtube]
cp ../../.env.example .env   # then edit .env with your YT key
uvicorn app.main:app --reload --port 8000

# Web (in another terminal)
cd apps/web
npm install
npm run dev    # → http://localhost:3000
```

---

## Running the tests

```bash
cd apps/api
pytest -q       # 56 tests
```

Frontend tests land in Phase 5.

---

## Deploy to production

See [`docs/deploy.md`](docs/deploy.md) (coming) and `infrastructure/render.yaml`.
Render Blueprint provisions web + api + Postgres in one click.

---

## License

Proprietary — all rights reserved.
