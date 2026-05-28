"""Add verdict, concluded_at, and notes columns to investigations.

Analysts can now mark an investigation with a verdict (confirmed_bot_ring,
likely_authentic, etc.) and attach private notes. Columns are nullable and
default NULL so all existing rows are unaffected.

Revision ID: 0003_investigation_verdict
Revises: 0002_account_labels
Create Date: 2026-05-28
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0003_investigation_verdict"
down_revision: Union[str, None] = "0002_account_labels"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    cols = {c["name"] for c in inspector.get_columns("investigations")}

    if "verdict" not in cols:
        op.add_column("investigations", sa.Column("verdict", sa.String(32), nullable=True))
        op.create_index("ix_investigations_verdict", "investigations", ["verdict"])

    if "concluded_at" not in cols:
        op.add_column("investigations", sa.Column("concluded_at", sa.DateTime(timezone=True), nullable=True))

    if "notes" not in cols:
        op.add_column("investigations", sa.Column("notes", sa.Text, nullable=True))


def downgrade() -> None:
    op.drop_index("ix_investigations_verdict", table_name="investigations")
    op.drop_column("investigations", "verdict")
    op.drop_column("investigations", "concluded_at")
    op.drop_column("investigations", "notes")
