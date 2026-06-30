-- Supabase memory store — deduplicate redundant indexes (Sprint 015).
--
-- Mirrors alembic/versions/0011_index_dedup.py. Six memory indexes provide no measurable value
-- because each is strictly shadowed by an existing composite/unique index sharing the same leading
-- column (or is an exact duplicate). On an append-only store each redundant index doubles write
-- amplification for that column and wastes storage at scale, for zero read benefit. Dropping them
-- is safe — the tables are empty and no query plan changes. Idempotent.
--
-- Dropped (covering index in parens):
--   ix_knowledge_objects_type            (ix_ko_type_control = (type, is_control))
--   ix_knowledge_object_signatures_ko_id (uq_kosig_ko_token = (ko_id, token))
--   ix_observation_ledger_ko_id          (ix_obs_ko_seq = (ko_id, seq))
--   ix_memory_revisions_ko_id            (ix_memrev_ko = (ko_id, rev))
--   ix_retrieval_feedback_ko_id          (ix_rfb_ko = (ko_id) — exact duplicate, Sprint 014)
--   ix_pcc_sig                           (prior_context_cache_signature_hash_key, unique)
--
-- Apply to the dedicated Supabase memory project (migration 0011_index_dedup).

DROP INDEX IF EXISTS public.ix_knowledge_objects_type;
DROP INDEX IF EXISTS public.ix_knowledge_object_signatures_ko_id;
DROP INDEX IF EXISTS public.ix_observation_ledger_ko_id;
DROP INDEX IF EXISTS public.ix_memory_revisions_ko_id;
DROP INDEX IF EXISTS public.ix_retrieval_feedback_ko_id;
DROP INDEX IF EXISTS public.ix_pcc_sig;
