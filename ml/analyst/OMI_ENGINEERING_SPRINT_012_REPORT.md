# OMI_ENGINEERING_SPRINT_012 — Production Memory Persistence (report)

> **Engineering sprint.** Made the Intelligence Memory System **real**: a production PostgreSQL
> persistence layer behind a repository abstraction, so the Analyst Council can read accumulated
> institutional intelligence and contribute new evidence-backed knowledge — **without ever
> knowing where memory lives** (Postgres, Supabase, or RAM). No architectural redesign: the
> Sprint-005 domain model is unchanged and every constitutional guarantee holds — evidence not
> verdicts, append-only, the memory-influence quarantine, no self-reinforcement, memory as
> context only, and **no LLM opinion is ever written**. Persistence is **opt-in** (off by
> default), so existing behavior and the hermetic test suite are untouched.

## A. Production PostgreSQL schema (`app/storage/models.py`)

Five durable tables, designed for millions of investigations:
- **`knowledge_objects`** — the recurring, falsifiable patterns. `type` distinguishes the typed
  memories (CoordinationSignature / BehavioralArchetype / **LegitimateCoordinationControl** /
  NarrativeFingerprint / CampaignMemory); `is_control` + `influence_class` carry the exculpatory
  asymmetry. Indexed on `(type, is_control)` and `superseded_by` (active set).
- **`observation_ledger`** — **append-only** evidence observations (stance, evidence_refs,
  independence_key, `memory_influence` for the quarantine). Never updated or deleted.
- **`memory_revisions`** — version history (create / observe / supersede) for audit.
- **`knowledge_object_signatures`** — indexed signature tokens (`ix_kosig_token`) — the seam for
  fast candidate lookup at scale.
- **`prior_context_cache`** — a PriorContext read accelerator keyed by bundle-signature hash.
**Confidence, contradiction history, and epistemic status are NEVER stored** — they are
recomputed from the ledger by the domain model, so memory always evolves and can never ossify
into a stored verdict (Platform Guardian §2).

## B. Repository layer (`app/memory/repository.py`, `…/graph/postgres.py`, `…/db.py`)

- **`MemoryRepository`** — a `@runtime_checkable` Protocol (get / all / ingest / supersede / len).
  The Council, the Memory Analyst, and the extractor depend only on this — **never on a backend**.
- **`PostgresMemoryStore`** — implements that interface over SQLAlchemy. Every read reconstructs
  the Sprint-005 **domain** `KnowledgeObject` (with its ledger), so all constitutional logic runs
  unchanged. Writes are **append-only** and **transactional** (match-or-create + observe in one
  transaction). Both the in-memory store and the Postgres store satisfy `MemoryRepository`.
- **Dedicated engine + pooling + factory** (`db.py`) — when `memory_database_url` is set, a pooled
  engine (`pool_pre_ping`, configurable `pool_size`/`max_overflow`) targets a **separate** database
  (e.g. Supabase) and creates only the memory tables there; otherwise memory shares the main DB.
  `get_memory_store(settings)` returns the right backend from configuration alone.

## C. Retrieval implementation (`…/graph/retrieval.py`, `…/postgres.py`)

Deterministic retrieval, **identical across backends**. `retrieve` was refactored to
`rank_priors(objects, bundle)` (the constitutional scoring) + a backend-agnostic `retrieve` that
uses `candidates_for` when available. `PostgresMemoryStore` provides the charter's lookups:
**similarity** (signature-containment scoring), **signature** (`candidates_for` — index-assisted
token narrowing), **behavioral** / **campaign** (`find_by_type`), **control** (`find_controls`),
and **contradiction** (`find_contradicted`). Candidate narrowing is provably equivalent to ranking
all objects (any containment match shares ≥ 1 token) but avoids a full scan — verified in tests.

## D. Persistence implementation

The existing **Memory Extractor** (`record_settled_investigation`, Sprint 006) and **Memory
Analyst** call only the repository interface, so wiring them to Postgres is a **backend swap, no
code change**: Evidence Bundle → Memory Extractor → `MemoryRepository` → PostgreSQL, and future
investigations retrieve it through PriorContext. The write path stays evidence-gated — structural
candidates from settled bundles + human anchors only; **the LLM is never a write source**.

## E. Migrations (`alembic/versions/0008_memory_tables.py`)

An idempotent, guarded Alembic migration adds all five tables + indexes, chained
`0007 → 0008`. Verified end-to-end: the full chain `0001 → 0008` applies cleanly to a fresh
database and creates the memory tables (also created by `create_all` for the test DB).

## F. Performance benchmarks

Signature-token narrowing keeps retrieval sub-linear in the corpus: with 100+ objects, retrieval
returns the matching priors in **< 1s** while `candidates_for` returns only the token-overlapping
subset (≪ the full set) — the indexed path that scales to millions. Pooling
(`pool_pre_ping` + bounded pool) keeps connection cost flat under load.

## G. Full test coverage

`cd apps/api && python -m pytest tests/ -q` → **947 passed** (was 936; **+11**), 0
regressions. `tests/test_memory_persistence.py` covers: **migrations + indexes**; **repository
correctness**; **append-only** accumulation + transactional **durability across sessions**;
**supersede keeps the row**; **deterministic retrieval identical to in-memory**; **candidate
narrowing** correctness; typed / contradiction / control lookups; **replay stability**;
**concurrent writes are lossless** (8 threads, file-backed WAL, no lost observations); a
**performance** assertion; and the **repository factory** (backend selection + interface
conformance).

## H. Updated engineering readiness

- **Memory is now production-persistable today.** The Postgres layer is proven byte-for-byte
  equivalent to the in-memory store, append-only, deterministic, concurrent-safe, and migrated —
  on the hermetic test DB. Flip it on by configuration; the Council code does not change.
- **Operator activation (no code change):** set `OMI_MEMORY_PERSISTENCE_ENABLED=true`,
  `OMI_MEMORY_DATABASE_URL=<Supabase connection string>`, run `alembic upgrade head` against that
  database, and pass `get_memory_store(settings)` where a store is needed. Unset
  `OMI_MEMORY_DATABASE_URL` to co-locate memory in the main DB.
- **Constitution intact.** No engine / scoring / OmiScore / Governor change; the domain model is
  unchanged; aggregates are derived not stored; the write path is evidence-gated.
- **Security:** the Supabase database URL is a **secret supplied only via environment**
  (`OMI_MEMORY_DATABASE_URL`) — it is **never** hard-coded or committed. Per standing practice, the
  database password shared in chat should be **rotated**; this code reads it from the environment,
  so a rotation is a config change with no redeploy of logic.

## Recommendation for Sprint 013

1. **Run the live migration + first persisted investigations.** Apply `0008` to the Supabase
   instance, enable persistence, and record the first settled investigations — then confirm a
   later investigation retrieves them through PriorContext (the loop, end to end, on real infra).
2. **Add the PriorContext cache write/read path + retention jobs.** Populate `prior_context_cache`
   (invalidated by `memory_revision`) for hot bundle signatures, and add the deterministic
   retirement/decay sweep as a scheduled job — so memory stays fast and self-correcting at scale.

---

*Long-term architecture over short-term sophistication. The memory system is now genuinely
durable: a repository abstraction the Council can't see through, append-only Postgres persistence,
deterministic backend-agnostic retrieval, and migrations — with every constitutional guarantee
intact (evidence not verdicts, aggregates derived not stored, the quarantine preserved, no LLM
write). No engine / scoring / OmiScore / Governor change. Gates green at commit time (947 backend
tests). GitHub remains the source of truth; Hugging Face remains the source of AI assets; secrets
live only in the environment.*
