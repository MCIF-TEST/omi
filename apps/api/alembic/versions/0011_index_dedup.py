"""Deduplicate redundant memory indexes — storage/write simplification (Sprint 015).

Audit of the memory schema found six indexes that provide no measurable value because each is
**strictly shadowed** by an existing composite or unique index sharing the same leading column (or
is an exact duplicate). On an append-only store every redundant index doubles write amplification
for that column and wastes storage at scale, for zero read benefit (Postgres serves the queries
from the covering index). Dropping them is safe — the tables are empty and no query plan changes.

Dropped (kept covering index in parens):
- ix_knowledge_objects_type              (ix_ko_type_control = (type, is_control))
- ix_knowledge_object_signatures_ko_id   (uq_kosig_ko_token = (ko_id, token))
- ix_observation_ledger_ko_id            (ix_obs_ko_seq = (ko_id, seq))
- ix_memory_revisions_ko_id              (ix_memrev_ko = (ko_id, rev))
- ix_retrieval_feedback_ko_id            (ix_rfb_ko = (ko_id) — exact duplicate, Sprint 014)
- ix_pcc_sig                             (prior_context_cache_signature_hash_key, unique)

Guarded + idempotent + reversible.

Revision ID: 0011_index_dedup
Revises: 0010_retrieval_feedback
Create Date: 2026-06-30
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0011_index_dedup"
down_revision: Union[str, None] = "0010_retrieval_feedback"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# (index_name, table_name, [columns]) — columns are used only to recreate on downgrade.
_REDUNDANT = [
    ("ix_knowledge_objects_type", "knowledge_objects", ["type"]),
    ("ix_knowledge_object_signatures_ko_id", "knowledge_object_signatures", ["ko_id"]),
    ("ix_observation_ledger_ko_id", "observation_ledger", ["ko_id"]),
    ("ix_memory_revisions_ko_id", "memory_revisions", ["ko_id"]),
    ("ix_retrieval_feedback_ko_id", "retrieval_feedback", ["ko_id"]),
    ("ix_pcc_sig", "prior_context_cache", ["signature_hash"]),
]


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())
    for index_name, table_name, _cols in _REDUNDANT:
        if table_name not in tables:
            continue
        existing = {ix["name"] for ix in inspector.get_indexes(table_name)}
        if index_name in existing:
            op.drop_index(index_name, table_name=table_name)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())
    for index_name, table_name, cols in _REDUNDANT:
        if table_name not in tables:
            continue
        existing = {ix["name"] for ix in inspector.get_indexes(table_name)}
        if index_name not in existing:
            op.create_index(index_name, table_name, cols)
