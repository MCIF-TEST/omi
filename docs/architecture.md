# OMISPHERE — Architecture (Phase 1)

> The single source of truth for how OMISPHERE is structured. Future
> phases extend this; they don't violate it.

---

## 1. Product split

**OMISPHERE** is the brand and the user-facing product.
**omi** is the detection engine that lives inside it.

Two systems sharing a backbone:

| System | Purpose | Stack |
|--------|---------|-------|
| `omi` (the engine) | Probabilistic detection, fingerprinting, coordination analysis. Runs without LLMs. | FastAPI + Python + Postgres + (later) Neo4j |
| `OMISPHERE` (the product) | Investigative workspace. Saved investigations, graph views, reports, billing. | Next.js 14 + TypeScript + Tailwind |

The split matters because:
* the engine can be embedded in other products without dragging the UI
* the UI can evolve independently of the engine
* the engine stays pure-Python (no JS pollution in detection code)

---

## 2. Repository layout

```
omisphere/                              ← monorepo root
├── apps/
│   ├── api/                            ← omi engine + HTTP API (FastAPI)
│   │   ├── app/
│   │   │   ├── core/                   auth, config, errors, deps
│   │   │   ├── detection/              probabilistic detectors (preserved)
│   │   │   ├── coordination/           cross-account clustering (Phase 4)
│   │   │   ├── narrative/              narrative intel (Phase 3)
│   │   │   ├── graph/                  Neo4j-backed queries (Phase 4)
│   │   │   ├── reports/                report generation (Phase 6)
│   │   │   ├── monitoring/             live anomaly feeds (Phase 8)
│   │   │   ├── reasoning/              LLM enhancement (Phase 7, optional)
│   │   │   ├── integrations/           YouTube, X (future), Reddit (future)
│   │   │   ├── memory/                 fingerprint store
│   │   │   ├── storage/                SQLAlchemy models + repositories
│   │   │   ├── billing/                Stripe checkout + webhooks
│   │   │   ├── routes/                 thin HTTP layer
│   │   │   └── main.py
│   │   ├── tests/
│   │   └── pyproject.toml
│   └── web/                            ← OMISPHERE dashboard (Next.js)
│       ├── app/
│       │   ├── (marketing)/            pricing, about, terms, privacy
│       │   ├── (auth)/                 login, signup
│       │   ├── (app)/                  authenticated routes
│       │   │   ├── dashboard/          home — recent scans, live anomalies
│       │   │   ├── investigate/        primary scan workspace
│       │   │   ├── investigations/[id]/   saved investigations
│       │   │   ├── graph/              coordination network view (Phase 4)
│       │   │   ├── narratives/         narrative observatory (Phase 3)
│       │   │   ├── monitoring/         live feeds (Phase 8)
│       │   │   ├── reports/            report generation (Phase 6)
│       │   │   └── settings/           account, billing, api keys
│       │   ├── layout.tsx
│       │   └── globals.css
│       ├── components/
│       │   ├── ui/                     design system primitives
│       │   ├── layout/                 AppShell, Sidebar, Header
│       │   └── shared/                 Logo, ProbabilityNumber, TierBadge
│       ├── lib/
│       │   ├── api.ts                  typed FastAPI client
│       │   ├── auth.ts                 server-side cookie helpers
│       │   ├── env.ts                  runtime env parsing
│       │   └── format.ts               number/date helpers
│       ├── middleware.ts               auth gate on protected routes
│       ├── next.config.mjs
│       ├── tailwind.config.ts
│       ├── tsconfig.json
│       └── package.json
├── packages/
│   └── shared/                         ← types shared web ⇄ api
│       └── types.ts                    (later: openapi-typescript generated)
├── infrastructure/
│   ├── docker-compose.yml              local: postgres + api + web
│   └── render.yaml                     production blueprint
├── docs/
│   ├── architecture.md                 ← this file
│   ├── design-system.md                tokens, primitives, patterns
│   ├── api-spec.md                     endpoint catalog
│   └── roadmap.md                      9-phase plan + status
├── scripts/
│   ├── setup_omisphere.bat             first-run installer (Windows)
│   └── start_omisphere.bat             launch both services (Windows)
├── package.json                        workspace root (npm workspaces)
├── README.md
└── .gitignore
```

---

## 3. Boundaries between systems

These are load-bearing rules. Crossing them creates tech debt.

1. **No JS in `apps/api`.** It is a Python service. Period.
2. **No Python in `apps/web`.** It is a Next.js app. It talks to the API via HTTP.
3. **The browser never calls Stripe, YouTube, or Neo4j directly.** All third-party APIs are server-side (FastAPI or Next.js server components).
4. **Detection code is pure.** `app/detection/` has no I/O — no DB, no network. It computes signals from inputs. The orchestrator (`app/orchestrator.py`) handles I/O.
5. **The fingerprint feature list is append-only.** Removing or reordering invalidates every stored vector. New dims go at the end.
6. **LLM calls are never in the per-scan hot path.** They live in `app/reasoning/` and run only on user-triggered report generation.

---

## 4. Data flow (a single scan)

```
Browser
  │ POST /v1/scan/link {url}
  ▼
Next.js middleware checks session cookie
  │
  ▼
FastAPI /v1/scan/link
  │ require_user dependency (auth)
  │ consume_credits (decrement, 402 if dry)
  │ classify_url → video|channel|unknown
  ▼
orchestrator.scan_comprehensive(...)
  │ for each commenter:
  │   ├─ cache lookup (Postgres)
  │   ├─ fetch profile + history (YouTube API)
  │   ├─ run detectors (pure functions)
  │   ├─ extract fingerprint
  │   └─ persist scan + edges
  │ thread-level scan
  │ coordination clusters (5 detectors)
  │ cross-link computation
  │ synthesis (overall tier + intent + reasons)
  ▼
ComprehensiveScanResult (JSON)
  ▼
Next.js renders the investigation view
```

---

## 5. State management (frontend)

| State | Lives in | Why |
|-------|----------|-----|
| Current user, credits | TanStack Query (`/v1/auth/me`) | Server-owned; cache + refetch |
| Active scan / investigation | TanStack Query | Server-owned |
| UI selection (selected cluster, drawer open, panel sizes) | Zustand | Client-owned, ephemeral |
| Form state (login, signup, investigate) | React Hook Form | Component-local |
| Theme | CSS variables | No JS needed |

Saved investigations get a stable URL (`/investigations/{id}`) so users can share or revisit.

---

## 6. Authentication

* **Strategy:** signed httpOnly session cookie (`omi_session`), HMAC-signed
  with `OMI_SESSION_SECRET`. Stateless server-side. 30-day rolling expiry.
* **Auth UI:** real Next.js routes (`/login`, `/signup`) — not a modal.
* **Gate:** Next.js `middleware.ts` redirects unauthenticated requests on
  `/(app)/*` routes to `/login?next=…`.
* **Cookie sharing:** Next.js rewrites `/api/*` → FastAPI in dev so the
  browser sees a single origin. In production, both services live behind
  the same custom domain on Render.

---

## 7. Database

* **Local dev:** Postgres 16 via `docker-compose up` (replaces SQLite).
* **Production:** Supabase managed Postgres (free tier covers early use).
  We use Supabase as a Postgres provider only — not their Auth or
  Storage. Our auth stays bcrypt + signed cookies.
* **Migration tool:** alembic, added in Phase 2.
* **Graph DB:** Neo4j Aura free tier, added in Phase 4.

Schema is owned by `apps/api/app/storage/models.py`. Web app never
touches the DB directly.

---

## 8. Design system principles

(See `docs/design-system.md` for tokens + primitives.)

* **Sparing accent.** The cyan (`#22d3ee`) is for active state, CTAs,
  highlights. Not for borders, labels, or body text.
* **Monospace for data only.** IDs, scores, timestamps. Never for
  narrative.
* **Information density with whitespace.** Cards have generous padding.
  Tables are tight but readable.
* **Graph-first.** Coordination is the differentiator; the graph view
  is the primary surface (Phase 5).
* **Investigator workflows.** Scans become saved investigations.
  Returning to one restores the full view.

---

## 9. Deployment

* **Render Blueprint** (`infrastructure/render.yaml`) provisions:
  * `omisphere-web` (Next.js)
  * `omisphere-api` (FastAPI)
  * Both behind the same custom domain via Render's routing.
* **Supabase** for managed Postgres (`OMI_DATABASE_URL`).
* **Stripe** for billing (`OMI_STRIPE_*`).
* **Local dev** uses `docker-compose` so postgres + redis + neo4j are
  one command away.

---

## 10. Phase status

| Phase | Status |
|-------|--------|
| 1 — Foundation + core architecture | ⏳ in progress |
| 2 — Core authenticity engine | preserved from v0 |
| 3 — Semantic + AI engagement intel | partial (semantic exists, narrative new) |
| 4 — Graph + coordination intelligence | partial (5 detectors exist; Neo4j graph new) |
| 5 — Investigative dashboard UI | scaffolded in Phase 1, built in Phase 5 |
| 6 — Report generation | not started |
| 7 — Optional LLM enhancement | not started |
| 8 — Real-time monitoring | not started |
| 9 — Scalability + optimization | not started |
