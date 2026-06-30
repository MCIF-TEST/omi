"""Retrieval feedback + reuse counter — operational learning loop (Sprint 014).

Adds the append-only ``retrieval_feedback`` table (records WHY a memory was retrieved and what
happened — influenced / governor-accepted / analyst-agreed) and a denormalized ``reuse_count``
on ``knowledge_objects``. Both are MEASUREMENTS that improve future retrieval RANKING only; they
never change an investigation's score, the Governor, or OmiScore. Guarded + idempotent.

Revision ID: 0010_retrieval_feedback
Revises: 0009_memory_tiers
Create Date: 2026-06-30
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0010_retrieval_feedback"
down_revision: Union[str, None] = "0009_memory_tiers"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())
    if "knowledge_objects" not in tables:
        return

    columns = {c["name"] for c in inspector.get_columns("knowledge_objects")}
    if "reuse_count" not in columns:
        op.add_column(
            "knowledge_objects",
            sa.Column("reuse_count", sa.Integer(), nullable=False, server_default="0"),
        )

    if "retrieval_feedback" not in tables:
        op.create_table(
            "retrieval_feedback",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("ko_id", sa.String(length=128), nullable=False),
            sa.Column("investigation", sa.String(length=128), nullable=False),
            sa.Column("selected_because", sa.Text(), nullable=False, server_default=""),
            sa.Column("influenced", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("governor_accepted", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("analyst_agreed", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("at", sa.String(length=40), nullable=False, server_default=""),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
            sa.ForeignKeyConstraint(["ko_id"], ["knowledge_objects.id"], ondelete="CASCADE"),
        )
        op.create_index("ix_retrieval_feedback_ko_id", "retrieval_feedback", ["ko_id"])
        op.create_index("ix_retrieval_feedback_investigation", "retrieval_feedback", ["investigation"])
        op.create_index("ix_rfb_ko", "retrieval_feedback", ["ko_id"])


def downgrade() -> None:
    op.drop_index("ix_rfb_ko", table_name="retrieval_feedback")
    op.drop_index("ix_retrieval_feedback_investigation", table_name="retrieval_feedback")
    op.drop_index("ix_retrieval_feedback_ko_id", table_name="retrieval_feedback")
    op.drop_table("retrieval_feedback")
    op.drop_column("knowledge_objects", "reuse_count")
