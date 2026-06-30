-- Supabase memory store — distillation tier cache (Sprint 013).
--
-- Mirrors alembic/versions/0009_memory_tiers.py. Adds the cached distillation `tier`
-- (+ `last_consolidated_at`) to knowledge_objects and an index for tier-filtered retrieval at
-- scale. The tier is a DERIVED cache refreshed by the consolidation pipeline — the source of
-- truth is always the recomputed tier_of() over the append-only ledger. Idempotent.
-- Applied to the dedicated Supabase memory project on 2026-06-26 (migration 0009_memory_tiers).

ALTER TABLE public.knowledge_objects ADD COLUMN IF NOT EXISTS tier text;
ALTER TABLE public.knowledge_objects ADD COLUMN IF NOT EXISTS last_consolidated_at timestamptz;
CREATE INDEX IF NOT EXISTS ix_knowledge_objects_tier ON public.knowledge_objects (tier);
