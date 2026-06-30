"""Institutional Intelligence Memory — production persistence tables (Sprint 012).

Adds the durable home of the memory system: knowledge objects, an append-only observation
ledger, version history, indexed signature tokens (fast lookup at scale), and a PriorContext
cache. Aggregates (confidence, contradiction history, epistemic status) are NEVER stored — they
are recomputed from the ledger by the domain model — so memory always evolves.

Every step is guarded so the migration is idempotent and safe on a database already bootstrapped
by create_all.

Revision ID: 0008_memory_tables
Revises: 0007_user_graphs_and_password_reset
Create Date: 2026-06-26
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0008_memory_tables"
down_revision: Union[str, None] = "0007_user_graphs_and_password_reset"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "knowledge_objects" not in tables:
        op.create_table(
            "knowledge_objects",
            sa.Column("id", sa.String(length=128), primary_key=True),
            sa.Column("type", sa.String(length=64), nullable=False, index=True),
            sa.Column("family", sa.String(length=64), nullable=False, server_default="patterns_signatures"),
            sa.Column("label", sa.Text(), nullable=False, server_default=""),
            sa.Column("signature", sa.JSON(), nullable=True),
            sa.Column("attributes", sa.JSON(), nullable=True),
            sa.Column("is_control", sa.Boolean(), nullable=False, server_default=sa.false(), index=True),
            sa.Column("influence_class", sa.String(length=16), nullable=False, server_default="context"),
            sa.Column("superseded_by", sa.String(length=128), nullable=True),
            sa.Column("half_life_days", sa.Float(), nullable=False, server_default="180.0"),
            sa.Column("retirement_floor", sa.Float(), nullable=False, server_default="0.12"),
            sa.Column("platform_scope", sa.JSON(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        )
        op.create_index("ix_ko_type_control", "knowledge_objects", ["type", "is_control"])
        op.create_index("ix_ko_active", "knowledge_objects", ["superseded_by"])

    if "knowledge_object_signatures" not in tables:
        op.create_table(
            "knowledge_object_signatures",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("ko_id", sa.String(length=128),
                      sa.ForeignKey("knowledge_objects.id", ondelete="CASCADE"), nullable=False, index=True),
            sa.Column("token", sa.String(length=128), nullable=False),
            sa.UniqueConstraint("ko_id", "token", name="uq_kosig_ko_token"),
        )
        op.create_index("ix_kosig_token", "knowledge_object_signatures", ["token"])

    if "observation_ledger" not in tables:
        op.create_table(
            "observation_ledger",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("ko_id", sa.String(length=128),
                      sa.ForeignKey("knowledge_objects.id", ondelete="CASCADE"), nullable=False, index=True),
            sa.Column("seq", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("investigation", sa.String(length=128), nullable=False, index=True),
            sa.Column("stance", sa.String(length=16), nullable=False),
            sa.Column("evidence_refs", sa.JSON(), nullable=True),
            sa.Column("independence_key", sa.String(length=128), nullable=False, server_default=""),
            sa.Column("at", sa.String(length=40), nullable=False, server_default=""),
            sa.Column("human_anchor", sa.JSON(), nullable=True),
            sa.Column("memory_influence", sa.String(length=16), nullable=False, server_default="none"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        )
        op.create_index("ix_obs_ko_seq", "observation_ledger", ["ko_id", "seq"])
        op.create_index("ix_obs_stance", "observation_ledger", ["stance"])

    if "memory_revisions" not in tables:
        op.create_table(
            "memory_revisions",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("ko_id", sa.String(length=128),
                      sa.ForeignKey("knowledge_objects.id", ondelete="CASCADE"), nullable=False, index=True),
            sa.Column("rev", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("change", sa.String(length=64), nullable=False, server_default=""),
            sa.Column("investigation", sa.String(length=128), nullable=True),
            sa.Column("at", sa.String(length=40), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        )
        op.create_index("ix_memrev_ko", "memory_revisions", ["ko_id", "rev"])

    if "prior_context_cache" not in tables:
        op.create_table(
            "prior_context_cache",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("signature_hash", sa.String(length=80), nullable=False, unique=True),
            sa.Column("result", sa.JSON(), nullable=True),
            sa.Column("memory_revision", sa.String(length=80), nullable=True),
            sa.Column("computed_at", sa.DateTime(timezone=True), nullable=True),
        )
        op.create_index("ix_pcc_sig", "prior_context_cache", ["signature_hash"])


def downgrade() -> None:
    for table in ("prior_context_cache", "memory_revisions", "observation_ledger",
                  "knowledge_object_signatures", "knowledge_objects"):
        op.drop_table(table)
