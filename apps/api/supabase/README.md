# Supabase — OmiSphere Institutional Memory store

This directory is the source of truth for what lives in the **Supabase** project that backs the
Institutional Intelligence Memory System (Sprint 012). Per the Platform Synchronization
Directive, GitHub ↔ Supabase must not drift: the SQL here mirrors what is applied to Supabase.

## What is in Supabase

A dedicated memory database (separate from the main app DB on Render) holding the five memory
tables — `knowledge_objects`, `knowledge_object_signatures`, `observation_ledger`,
`memory_revisions`, `prior_context_cache` — created by `migrations/0008_memory_tables.sql`.

- The schema mirrors `app/storage/models.py` + `alembic/versions/0008_memory_tables.py` (the
  portable definition that also runs on the SQLite test DB and the main app DB).
- This file additionally applies **Row Level Security** (backend-only): RLS is enabled with no
  policies, so the public PostgREST API (`anon` / `authenticated`) is denied; the backend
  connects as the `postgres` owner role and is unaffected. Institutional memory is never exposed
  via the public API.
- **Confidence / contradiction / epistemic status are never stored** — they are recomputed from
  the append-only `observation_ledger` by the domain model (`app/memory/graph/objects.py`).

## How it is applied

Two equivalent paths produce the same tables:

1. **Backend (automatic):** with `OMI_MEMORY_DATABASE_URL` pointed at the Supabase connection
   string, `app/memory/db.py` creates the memory tables via `create_all` on first use.
2. **Migration (explicit):** apply `migrations/0008_memory_tables.sql` (idempotent) — this is
   what was applied to the live project, and it adds the RLS hardening that the portable Alembic
   migration cannot carry.

## Activation (operator)

```
OMI_MEMORY_PERSISTENCE_ENABLED=true
OMI_MEMORY_DATABASE_URL=<supabase postgres connection string>   # secret — never commit
OMI_MEMORY_DB_POOL_SIZE=5
OMI_MEMORY_DB_MAX_OVERFLOW=10
```

The connection string is a **secret** supplied only via the environment. Rotate the database
password if it has ever been shared outside the secret store.
