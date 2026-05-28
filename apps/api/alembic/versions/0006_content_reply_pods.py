"""Add latest_reply_pod_count to content_entities.

Tracks the number of reply pods detected on the most recent scan of each
content entity. Stored denormalized for fast list rendering without re-running
the detector on every page load.

Migration is idempotent — adds the column only when missing.

Revision ID: 0006_content_reply_pods
Revises: 0005_referral_and_ip
Create Date: 2026-05-28
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0006_content_reply_pods"
down_revision: Union[str, None] = "0005_referral_and_ip"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "content_entities" not in inspector.get_table_names():
        return
    existing_cols = {c["name"] for c in inspector.get_columns("content_entities")}
    if "latest_reply_pod_count" not in existing_cols:
        op.add_column(
            "content_entities",
            sa.Column("latest_reply_pod_count", sa.Integer, nullable=False, server_default="0"),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "content_entities" not in inspector.get_table_names():
        return
    existing_cols = {c["name"] for c in inspector.get_columns("content_entities")}
    if "latest_reply_pod_count" in existing_cols:
        op.drop_column("content_entities", "latest_reply_pod_count")
