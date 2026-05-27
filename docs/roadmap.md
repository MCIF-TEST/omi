# OMISPHERE — Roadmap

Tracks the 9-phase build. Each phase ships independently and integrates
into later phases. Status updates live here.

---

## Phase 1 — Foundation + core architecture · ✅ done

Monorepo, FastAPI reorganization, Next.js scaffold with auth + dashboard
shell, design system tokens + primitives, deployment blueprints.

**Deliverables:**
- `docs/architecture.md`, `docs/design-system.md`, `docs/roadmap.md`
- `apps/api/` — FastAPI reorganized (detection, coordination, integrations…)
- `apps/web/` — Next.js 14 app router + TypeScript + Tailwind
- Auth pages (`/login`, `/signup`) wired to existing `/v1/auth/*` endpoints
- Dashboard shell + sidebar nav
- Marketing pages (`/pricing`, `/about`, `/terms`, `/privacy`)
- `docker-compose.yml` for local Postgres + API + web
- `render.yaml` for production deployment

---

## Phase 2 — Core authenticity engine · ✅ done

The 8-detector engine carried over from v0 (temporal, semantic, ai_writing,
profile, voice, engagement, memory, coordination) + log-odds scorer with
convergence + single-signal cap.

**Phase 2 additions:**
- **Trend analysis** (`apps/api/app/detection/trend.py`) — linear regression
  + residual stdev over an account's scan history. Categorical output:
  stable / rising / falling / volatile / insufficient.
- **Weak signal flags** — `ScanResult.weak_signals` lists plain-language
  reasons a scan is low-confidence ("too few posts to establish cadence"
  etc.). UI surfaces them so data-quality caveats are explicit.
- **Account history endpoint** —
  `GET /v1/accounts/{platform}/{external_id}/history` returns the full
  scan history with trend metadata. New web page:
  `/(app)/accounts/[external_id]` renders a sparkline + scan table.
- **Calibration harness** (`apps/api/scripts/calibrate.py`) — runs the
  engine over a labeled JSON fixture, reports Brier score, per-detector
  influence, tier confusion matrix, and heuristic weight suggestions.
  Bundled fixture covers ai-content, engagement-farm, human (low/normal
  volume), scheduler-bot, and thin-data ambiguous cases.

**Deferred to Phase 2.5:**
- Alembic migrations (current `Base.metadata.create_all` is sufficient
  for the schema's current shape; needed when we start changing columns)
- Suspicious-growth analysis (needs follower-history data we don't yet
  collect)

---

## Phase 3 — Comment + semantic intelligence (narrative) · ✅ done

The within-scan semantic detector already exists. Phase 3 adds the
**cross-corpus narrative observatory** — same topic + framing tracked
across all scanned accounts and videos and time.

**Phase 3 additions:**
- `apps/api/app/narrative/` module:
  - `embeddings.py` — `SentenceTransformerEmbedder` (all-MiniLM-L6-v2)
    with `HashingEmbedder` fallback when ML deps aren't installed.
    Tests inject a synthetic embedder via `set_embedder_for_tests`.
  - `clustering.py` — incremental online clustering. New comment →
    nearest centroid; cosine > 0.78 = assign, else spawn. Centroid
    updated as streaming mean.
  - `service.py` — `NarrativeService.ingest_batch()` + `list_trending()`.
- New DB tables: `narratives`, `narrative_memberships`.
- `GET /v1/narratives?window_days=7&limit=20` — returns trending
  narratives ranked by volume × spread (distinct authors / members).
- Ingestion hook: every video scan automatically feeds its comments
  into the narrative store (best-effort, never blocks the scan).
- Next.js page `/(app)/narratives` — narrative cards with sample
  text, distinct-authors count, recent-member count, spread bar.
- Sidebar item moved from "soon" to "new".
- 11 new tests; 79 total passing.

**Notes:**
- Without the `ml` extra installed, narratives still work via the
  hashing embedder — coarser clustering, no model download. Add
  `pip install -e .[ml]` for real semantic embeddings.
- Brute-force centroid scan is O(N) per comment. Phase 9 swaps for
  an ANN index when N narratives passes ~10k.

---

## Phase 4 — Graph + coordination intelligence · ✅ done

Per-scan clusters now persist into a cumulative, queryable coordination
graph. The 5 cross-account detectors become *graph builders* — every
cluster they emit adds edges that survive across scans.

**Phase 4 additions:**
- `apps/api/app/graph/` module
  - `store.py` — `GraphStore` over the new `coordination_edges` table.
    Symmetric (account_a < account_b), idempotent upserts, running-
    average cluster scores, deduplicated method lists.
  - `algorithms.py` — `edge_strength()` formula (observations + method
    diversity + recency + severity), Louvain community detection via
    networkx, `build_subgraph()` BFS to 2 hops.
  - `service.py` — high-level account_subgraph / communities / edge_detail.
- New table `coordination_edges`.
- New endpoints:
  - `GET /v1/graph/account/{platform}/{external_id}?depth=2`
  - `GET /v1/graph/communities?platform=youtube&min_size=3`
  - `GET /v1/graph/edges/{platform}/{a}/{b}`
- Orchestrator hook: every per-scan cluster auto-upserts edges. Best-
  effort; failure can't break a scan.
- Next.js `/(app)/graph` — radial SVG renderer, community-colored nodes,
  tier halos, edge thickness = strength. Click a node → inline detail
  with a link to its history page. Communities overview below the
  explorer.
- 13 new tests; 92 total passing.

**Stack decision:** networkx in-process (not Neo4j). The `GraphStore`
abstraction means a Neo4jStore swap is a focused change in Phase 9 when
the graph outgrows in-memory.

**Skipped for later:**
- Amplification pathway analysis (needs repost/reply graph — coming when
  the X integration lands in Phase 3.5).
- Force-directed layout (Cytoscape in Phase 5).

---

## Phase 5 — UI / UX intelligence dashboard · ✅ done

The workspace + persistent investigations + Cmd+K — what makes
OMISPHERE feel like an intelligence terminal instead of a dashboard.

**Phase 5 additions:**
- **Persistent investigations.** New `investigations` table, slug-based
  URLs (`inv_xxxxxxxx`), `/v1/investigations` (list) + `/v1/investigations/{slug}`
  (get). Scan flow auto-saves; continuation batches merge into the same
  row (commenters deduped by external_id).
- **Three-pane workspace** at `/(app)/investigate`: commenter list
  (filter + search, left) — selected detail (middle, swaps between
  synthesis and commenter detail) — insights rail (cross-links sorted by
  severity, right).
- **Saved investigation viewer** at `/(app)/investigations/[slug]` —
  same three-pane layout, driven by stored payload, read-only.
- **Dashboard recents** — newest investigations with tier badges,
  probability, batch count, quota used.
- **Cmd+K command palette** — global keybind, fuzzy filter across
  recent investigations + nav items.
- **Topbar ⌘K button** as a visible affordance.
- **Phased loading overlay** — six progress phases with elapsed counter.
- New primitives: `Dialog`, `Skeleton`, `TierBadge`, `ProbabilityBar`.
- 4 new tests; 96 total passing. Version 0.8.0.

**Skipped for later:**
- Coordination matrix UI (cross-links + graph carry the story now).
- Cytoscape force-directed graph (radial SVG from Phase 4 is enough).
- Live anomaly count on dashboard (Phase 8).

---

## Phase 6 — Report generation system · ✅ done

**Approach decision:** browser-print-to-PDF + Markdown/JSON exports
instead of server-side PDF rendering. Zero new infra dependencies
(no WeasyPrint C deps, no Playwright + Chromium). Print stylesheet
gives crisp output; server PDF can land in Phase 9 as a worker if
an enterprise tier demands it.

**Phase 6 additions:**
- New columns on `investigations`: `share_token` (nullable, opt-in),
  `is_public`, `published_at`.
- `app/reports/` module with two templates: `executive` (one-page
  brief — verdict, headline finding, top-5 flagged, methodology) and
  `evidence` (full document — all cross-links, full commenter list).
- `app/reports/templates.py` exposes `build_report_view()` (consumed by
  the Next.js public page) and `render_markdown()` (for downloads).
- Routes:
  - `POST /v1/investigations/{slug}/share` mints (or returns) a token,
    idempotent.
  - `DELETE /v1/investigations/{slug}/share` revokes it.
  - `GET /r/{token}` public report data (no auth).
  - `GET /r/{token}/markdown?template=...` downloadable Markdown.
  - `GET /r/{token}/json` raw payload export.
- Next.js public route group `(public)/r/[token]` — bare layout, no
  app shell, inline print stylesheet (@media print flips palette to
  light, hides chrome, sets @page margins). Toggle between executive
  and evidence templates via the URL.
- Share + export block on `/(app)/investigations/[slug]` — mint
  token, copy-link button (with success state), open report,
  download Markdown, download JSON, revoke.
- 7 new tests; 103 total passing. Version 0.9.0.

**Skipped for later:**
- Anonymization toggle (mask handles in shared reports).
- Watermarking.
- Server-side PDF rendering (Playwright worker, Phase 9).
- Third `intelligence` template (per-detector deep-dive).

---

## Phase 7 — Optional LLM enhancement layer · ✅ done

Strictly additive prose layer. LLMs never make detection decisions,
never run in the scan hot path, never are required for the product to
work.

**Phase 7 additions:**
- `apps/api/app/reasoning/`:
  - `providers.py` — `LLMProvider` Protocol + `TemplateProvider` (always
    available, zero cost) + `AnthropicProvider` (Claude Haiku via
    `claude-haiku-4-5-20251001`, prompt-cached system message).
  - `commentary.py` — `synthesize_commentary()` builds a tight structured
    digest (~250 tokens) from the investigation payload and asks the
    provider for a 120–180 word analyst paragraph. Locked-down system
    prompt enforcing probabilistic language and no accusations.
- New cached columns on `investigations`: `commentary_text`,
  `commentary_provider`, `commentary_generated_at`, `commentary_tokens_used`.
- `POST /v1/investigations/{slug}/commentary[?refresh=true]` — generate
  or return cached commentary. Idempotent by default.
- Surfaced in `/(app)/investigations/[slug]` via a generate/regenerate
  block with provider tag; surfaced on public reports `/r/{token}` when
  the owner has generated one (public route does NOT auto-generate to
  avoid recipients spending the owner's tokens).
- Markdown export includes commentary section when present.
- `anthropic>=0.40` declared as optional `reasoning` extra.
- 8 new tests including fake-provider injection; 111 total passing.
- Version 0.10.0.

**Design decisions documented:**
- Haiku, not Sonnet/Opus — synthesis from structured input is exactly
  Haiku's sweet spot, ~5x cheaper.
- Bounded tokens (input ~250, output ~320) + caching = ~$0.001/call
  steady-state with prompt cache hit.
- Commentary cached on the Investigation row — re-views are free.

---

## Phase 8 — Real-time intelligence + monitoring · ✅ done

**Approach decision:** in-process asyncio scheduler + frontend polling
(not Redis pub/sub + WebSockets). The product runs on Render starter
with no extra infra; the abstraction leaves room for a Dramatiq + Redis
swap in Phase 9 if multi-instance scaling demands it.

**Phase 8 additions:**
- New tables: `watchlists`, `alerts`.
- `app/monitoring/`:
  - `anomalies.py` — `detect_narrative_spikes` (>2× hour-over-hour
    growth, ≥5 new members) + `detect_high_tier_surge` (vs trailing
    24h baseline). Pure functions over existing tables.
  - `service.py` — `MonitoringService` with `run_anomaly_pass`,
    watchlist CRUD, `note_observation` (called from scan flow to
    fire tier-change alerts immediately).
  - `scheduler.py` — `lifespan_monitoring` asyncio task. Disabled by
    default via `OMI_ENABLE_MONITORING=false`. Per pass: run anomaly
    detection + rescan up to 5 due watchlists (cache-friendly).
- Routes:
  - `/v1/monitoring/feed` — global anomaly feed.
  - `/v1/monitoring/alerts[?unread=true]` — user's alerts.
  - `/v1/monitoring/alerts/{id}/read` — mark read.
  - `/v1/monitoring/run-pass` — admin-only on-demand trigger.
  - `/v1/watchlists` — CRUD.
- Orchestrator hook: `scan_account_with_memory` calls
  `note_observation` — manual rescans of a watched channel fire alerts
  on the spot, no waiting for the scheduler.
- Lifespan-managed FastAPI startup (replaces deprecated `on_event`).
- Next.js `/(app)/monitoring` rebuilt: live feed + alerts + watchlists
  with add form and per-row delete. Polls every 30s (feed) / 60s
  (alerts) / 2min (watchlists). Auto-pauses on hidden tabs.
- New `usePolling` hook (no TanStack dep).
- Bell icon in topbar with unread badge, polls every 60s, links to
  `/monitoring`.
- Sidebar: monitoring moved from "soon" to "live".
- 10 new tests; 121 total passing. Version 0.11.0.

**Skipped for later:**
- Redis pub/sub for true real-time push (Phase 9).
- Email notifications (Phase 9 once SES/Resend integration lands).
- Narrative watchlists (channel watchlists ship; narrative is 8.5).
- Cluster-burst + cross-link-severity anomaly detectors (8.5).

---

## Phase 9 — Scalability + optimization · ✅ done

The closing phase — make OMISPHERE production-ready without
over-engineering for hypothetical millions of users. First hundred
paying customers shouldn't make it fall over; the seams to scale
beyond that are in place.

**Phase 9 additions:**

Backend:
- `app/core/cache.py` — bounded TTL+LRU `TTLCache` with thread-safe
  `get/set/invalidate`. Wired into `/v1/status` (5s), `/v1/narratives`
  (60s), `/v1/graph/communities` (5min). Redis-swap path documented.
- `app/core/rate_limit.py` — sliding-window limiter. 10/min/IP on
  `/v1/auth/login` (brute-force protection), 5/hr/IP on `/v1/auth/signup`
  (account farming protection). Returns 429 with a clean error message.
- `app/core/metrics.py` — Counter + Histogram in-process registry,
  surfaced via admin-only `GET /v1/metrics` (per-route latency p50/p95,
  totals, lifetime YT quota + LLM tokens as cost proxies).
- `app/core/background.py` — bounded `ThreadPoolExecutor` for
  fire-and-forget work. Narrative ingestion offloaded here — scan HTTP
  responses no longer block on embedding 150+ comments. Drains on
  shutdown via lifespan.
- `app/core/middleware.py` — `RequestIdMiddleware` (round-trips
  X-Request-ID), `SecurityHeadersMiddleware` (X-Content-Type-Options,
  X-Frame-Options, Referrer-Policy, Permissions-Policy),
  `MetricsMiddleware` (per-route latency + status-class counters).
- `GZipMiddleware` added — typical scan response ~70% smaller over
  the wire.
- `TrustedHostMiddleware` in production.
- Composite database indexes: `Scan(account_id, scanned_at)`,
  `Investigation(user_id, created_at)`, `Alert(user_id, created_at)`.
- Structured JSON logging when `OMI_ENV=production`; readable text in dev.
- FastAPI lifespan now also drains the background queue on shutdown.

Docs:
- `docs/operations.md` — deploy checklist, common operations, scaling
  paths, incident response runbook.

Tests:
- 10 new tests covering cache behavior, rate limiter, metrics, security
  headers, request-id round-trip. 131 total passing.

Version bumped to **1.0.0** — OMISPHERE is ready to take its first
paying customers.

**Documented Phase 9.5+ paths** (when scale demands):
- Redis-backed `Cache` and `RateLimiter` (interfaces unchanged).
- Dramatiq + Redis background queue (replaces `background.submit`).
- Prometheus exporter scraping the existing `Registry`.
- Server-side PDF rendering via Playwright worker.
- Cytoscape force-directed graph view.
- Email + SMS notifications (SES / Twilio).
