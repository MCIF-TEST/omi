"""Add the account_labels table for ground-truth calibration.

This is the first migration that actually does work. New columns added
to ``app/storage/models.py`` should land as a sibling file here so the
schema history is real, not implicit.

For deploys already on a recent build, ``Base.metadata.create_all`` has
already created the table — this migration's ``CREATE TABLE IF NOT EXISTS``
behavior via Alembic's ``op.create_table`` plus a guard at the top makes
it safely idempotent.

Revision ID: 0002_account_labels
Revises: 0001_baseline
Create Date: 2026-05-28
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0002_account_labels"
down_revision: Union[str, None] = "0001_baseline"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Idempotent guard so this is safe to run on a DB where create_all
    # already laid down the table.
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "account_labels" in inspector.get_table_names():
        return

    op.create_table(
        "account_labels",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            "account_id",
            sa.Integer,
            sa.ForeignKey("accounts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            sa.Integer,
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("label", sa.String(32), nullable=False),
        sa.Column("expected_tier", sa.String(16), nullable=False),
        sa.Column("confidence", sa.String(8), nullable=False, server_default="medium"),
        sa.Column("source", sa.String(32), nullable=False, server_default="manual"),
        sa.Column("rationale", sa.Text, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.UniqueConstraint("account_id", "user_id", name="uq_account_label_per_user"),
    )
    op.create_index(
        "ix_account_labels_account_id", "account_labels", ["account_id"]
    )
    op.create_index(
        "ix_account_labels_user_id", "account_labels", ["user_id"]
    )
    op.create_index(
        "ix_account_labels_label", "account_labels", ["label"]
    )
    op.create_index(
        "ix_account_labels_created_at", "account_labels", ["created_at"]
    )
    op.create_index(
        "ix_account_label_source", "account_labels", ["source", "created_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_account_label_source", table_name="account_labels")
    op.drop_index("ix_account_labels_created_at", table_name="account_labels")
    op.drop_index("ix_account_labels_label", table_name="account_labels")
    op.drop_index("ix_account_labels_user_id", table_name="account_labels")
    op.drop_index("ix_account_labels_account_id", table_name="account_labels")
    op.drop_table("account_labels")
