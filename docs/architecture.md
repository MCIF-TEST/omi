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
| `omi` (the engine) | Probabilistic detection, fingerprinting, coordination analysis. Runs without LLMs. | FastAPI + Python + Postgres + networkx |
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
│   │   │   ├── graph/                  coordination graph — networkx (Phase 4)
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
3. **The browser never calls Stripe or YouTube directly.** All third-party APIs are server-side (FastAPI or Next.js server components).
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

As shipped, the frontend deliberately avoids client-state libraries — no
TanStack Query, Zustand, or React Hook Form. Next.js server components do the
data fetching, and the few interactive surfaces use plain React state.

| State | Lives in | Why |
|-------|----------|-----|
| Current user, credits | Server components via `getCurrentUser()` (`/v1/auth/me`) | Server-owned; fetched per request |
| Active scan / investigation | Server components + `apiServer`/`apiClient` | Server-owned |
| Polling (alerts, bulk-job status) | `usePolling` hook (no dependency) | Lightweight client polling |
| UI selection (selected node, sheet open, filters) | Component-local `useState` | Client-owned, ephemeral |
| Form state (login, signup, investigate) | Component-local `useState` | Small forms, no library needed |
| Theme | CSS variables | No JS needed |

Saved investigations get a stable URL (`/investigations/{slug}`) so users can share or revisit.

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

* **Local dev:** SQLite by default (zero infra), or Postgres via
  `docker-compose up`.
* **Production:** managed Postgres (provider-agnostic — set
  `OMI_DATABASE_URL`). Auth stays bcrypt + signed cookies, independent of
  the provider. Production boot refuses to start on SQLite.
* **Schema provisioning:** `Base.metadata.create_all` at boot plus an
  idempotent incremental-column pass (`app/storage/db.py`). Alembic
  migrations under `apps/api/alembic/` are the reviewable record of schema
  changes and run cleanly as idempotent patches on top of a create_all'd DB.
* **Graph:** in-process `networkx` over the persistent `coordination_edges`
  table (no external graph DB). The `GraphStore` abstraction leaves room to
  swap in a dedicated graph database if the graph outgrows memory.

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

All nine build phases are complete (see `docs/roadmap.md`). Subsequent work
has continued past the original plan — content intelligence, dataset
training, referrals, password reset, account deletion, a user-curated graph
feature, a mobile shell, and a frontend test suite among them.

| Phase | Status |
|-------|--------|
| 1 — Foundation + core architecture | ✅ done |
| 2 — Core authenticity engine | ✅ done |
| 3 — Semantic + AI engagement intel | ✅ done |
| 4 — Graph + coordination intelligence | ✅ done (networkx, not Neo4j) |
| 5 — Investigative dashboard UI | ✅ done |
| 6 — Report generation | ✅ done |
| 7 — Optional LLM enhancement | ✅ done |
| 8 — Real-time monitoring | ✅ done |
| 9 — Scalability + optimization | ✅ done |

> Note: the endpoint catalog lives in [`api-spec.md`](api-spec.md).
