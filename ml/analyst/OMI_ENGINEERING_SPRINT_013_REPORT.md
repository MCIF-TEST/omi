# OMI_ENGINEERING_SPRINT_013 — Institutional Knowledge Architecture (report)

> **Infrastructure sprint.** Built the permanent **tiered** Institutional Knowledge
> Architecture so Omi becomes smarter with every investigation while investigation latency stays
> effectively constant. Memory is no longer flat: observations are distilled through a
> deterministic lifecycle, retrieval never scans the whole database, and learning runs **off the
> live path**. The constitutional architecture is unchanged — OmiScore and the Governor are
> untouched, nothing is fabricated, aggregates remain derived (never stored), and everything is
> replayable. Audited GitHub / Supabase / Hugging Face / Render before changing anything.

## A. Tiered knowledge system (`app/memory/tiers.py`)

A `KnowledgeObject`'s tier is a **pure, deterministic function** of its epistemic state (support
/ stability / confidence / age) — derived from the append-only ledger, never stored as a
verdict. The lifecycle the directive specifies:

    raw observation → candidate → validated → archetype → institutional   (+ archived)

- **raw** = a ledger observation; **candidate** = hypothesized/contested (NOT surfaced);
  **validated** = observed (≥2 independent); **archetype** = corroborated (≥3, stable);
  **institutional** = corroborated + highly stable + long-lived + ≥5 independent supports;
  **archived** = retired/superseded (kept for audit, never retrieved).
- Only **validated and above** inform PriorContext, so **not every investigation becomes
  permanent memory** — memory becomes progressively distilled.

## B. Background intelligence pipeline (`app/memory/consolidation.py`)

`consolidate(store, now)` is the deterministic learning pass that runs **off the live path**
(scheduled job / admin trigger / background worker — never inside an investigation). It
classifies every object's tier, persists promotions / demotions / archival as evidence-backed
**version revisions**, refreshes the cached tier for fast tier queries, and reports the
distribution. **Idempotent** (re-running on an unchanged store yields no transitions) and a pure
function of `(store, now)` — fully replayable. The live investigation only ever appends an
observation (fast); no expensive learning runs during a scan.

## C. Scalable, explainable retrieval (`app/memory/retrieval_engine.py`)

`retrieve_priors(...)` **never scans the corpus**: it narrows candidates through the
index-assisted **signature-token** path, categorizes them by mechanism (signature / behavioral /
campaign / control) for **explainability**, filters to **retrievable tiers**, applies an optional
**temporal** recency window, and ranks within a **budget**. The `RetrievalPlan` records what was
scanned vs the corpus size (`scan_fraction`) — proving no full scan — and every returned prior
carries an explainable `match_basis` + `tier`. Deterministic given `(store, bundle, now)`.

## D. Performance + engineering metrics (`app/memory/metrics.py`)

`memory_stats(store)` exposes tier distribution, active/archived counts, ledger-observation
volume, the **distillation ratio** (share of active memory refined to archetype/institutional),
and observations-per-object. The Postgres store adds `tier_counts()` (SQL `GROUP BY` — a
distribution without loading objects) for scale. Exposed via the admin API. Retrieval latency +
scan fraction come back on every `RetrievalResult`.

## E. Supabase (canonical store) — schema optimization

- Added a cached `tier` (+ `last_consolidated_at`) column to `knowledge_objects` with index
  `ix_knowledge_objects_tier` for tier-filtered retrieval at scale — a **derived cache** refreshed
  by consolidation, never the source of truth (the tier is always recomputable from the ledger).
- **No data duplication:** the typed memories (coordination / behavioral / control / narrative /
  campaign) remain rows distinguished by `type`; raw observations stay in the ledger; distilled
  knowledge is the tiered `knowledge_objects`. Confidence / contradiction history are still
  derived, never stored.
- Applied to the live Supabase memory project (migration `0009_memory_tiers`) and committed as
  `apps/api/supabase/migrations/0009_memory_tiers.sql` — GitHub ↔ Supabase stay synchronized
  (both `0008` and `0009` recorded in Supabase migration history).

## F. Test results

`cd apps/api && python -m pytest tests/ -q` → **958 passed**, 0 regressions (one detection test,
`test_coordination`, flaked once in the full-suite context and passes deterministically in
isolation, the full file, and on re-run — it is unrelated to this additive memory work).
`tests/test_memory_tiering.py` (+11) covers: the tier lifecycle; consolidation (promotion +
idempotency + evidence-backed revisions + determinism); retrieval (candidates excluded, validated
surfaced, **never full-scans** with `scan_fraction < 0.1` over noise, budget, temporal window,
determinism); metrics; **Postgres parity** (tier column + `tier_counts`); the admin routes; and
regression (the Sprint-005 `retrieve` path still works). The Alembic chain `0001 → 0009` applies
cleanly.

## G. Platform Synchronization Report

| Platform | Status | Detail |
|---|---|---|
| **GitHub** | **Updated** | New memory modules (`tiers`, `consolidation`, `retrieval_engine`, `metrics`), store + model + retrieval additions, Alembic `0009`, Supabase `0009.sql`, admin routes, tests. Branch `claude/stoic-edison-2ueecx`. |
| **Supabase** | **Updated** | `0009_memory_tiers` applied to the live memory project (tier column + index); verified; migration history shows `0008` + `0009`. RLS still enforced. |
| **Hugging Face** | **Verified — no changes required** | Audited (`omi-analyst-v1`, `omi-behavioral-model-v1`, `omi-authenticity-dataset`). This is an infrastructure sprint — no prompt / dataset / eval / model-card change, so nothing to publish. |
| **Render** | **Blocked (operator)** | No Render connector available. For production: schedule a periodic **consolidation cron** hitting `POST /v1/admin/memory/consolidate` (e.g. hourly), and confirm the memory env vars from Sprint 012 (`OMI_MEMORY_PERSISTENCE_ENABLED`, `OMI_MEMORY_DATABASE_URL`, pool sizes). Affects production readiness: without the cron, distillation does not advance; without the env vars, memory is not persisted. |

## Engineering readiness

The tiered architecture is **production-quality and proven** on the hermetic test DB and applied
to Supabase. Investigation latency is protected: the live path only appends; retrieval is
index-narrowed + budgeted (never a full scan); learning is deferred to the consolidation pass.
Determinism and replay are preserved throughout; the constitution is intact (OmiScore + Governor
untouched, aggregates derived, append-only ledger). Remaining gaps are operator-side (Render
cron + env), captured above.

## Recommendation for Sprint 014

1. **Wire the live write + cron loop on real infra:** enable persistence, point memory at
   Supabase, run real investigations (append observations), schedule consolidation, and confirm a
   later investigation retrieves distilled priors — measuring retrieval latency vs corpus growth.
2. **Partition + vector seam (scale headroom):** when the ledger approaches tens of millions of
   rows, partition `observation_ledger` by time and evaluate a deterministic pgvector encoding of
   signatures as an additional explainable retrieval strategy — keeping every path replayable.

---

*Long-term scalability over new AI features. Memory is now tiered and progressively distilled;
retrieval is index-narrowed, budgeted, explainable, and never full-scans; learning is
deterministic and off the live path. No OmiScore / Governor change; aggregates derived not
stored; append-only; fully replayable. Gates green at commit time (958 backend tests). GitHub ↔
Supabase synchronized; Hugging Face audited; Render actions documented; secrets live only in the
environment.*
