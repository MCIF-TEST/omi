"""Institutional memory tiers — distillation cache (Sprint 013).

Adds the cached distillation ``tier`` (+ ``last_consolidated_at``) to ``knowledge_objects`` and
an index for tier-filtered retrieval at scale. The tier is a DERIVED cache refreshed by the
consolidation pipeline — never the source of truth (the tier is always recomputable from the
append-only ledger). Guarded + idempotent.

Revision ID: 0009_memory_tiers
Revises: 0008_memory_tables
Create Date: 2026-06-26
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0009_memory_tiers"
down_revision: Union[str, None] = "0008_memory_tables"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "knowledge_objects" not in set(inspector.get_table_names()):
        return
    columns = {c["name"] for c in inspector.get_columns("knowledge_objects")}
    if "tier" not in columns:
        op.add_column("knowledge_objects", sa.Column("tier", sa.String(length=16), nullable=True))
        op.create_index("ix_knowledge_objects_tier", "knowledge_objects", ["tier"])
    if "last_consolidated_at" not in columns:
        op.add_column("knowledge_objects",
                      sa.Column("last_consolidated_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_index("ix_knowledge_objects_tier", table_name="knowledge_objects")
    op.drop_column("knowledge_objects", "last_consolidated_at")
    op.drop_column("knowledge_objects", "tier")
