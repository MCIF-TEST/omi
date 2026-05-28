"""Create scan_jobs table for bulk URL scan queue.

Each row is one batch job submitted by a user. URLs are processed
sequentially in the background; results accumulate in results_json.

Revision ID: 0004_scan_jobs
Revises: 0003_investigation_verdict
Create Date: 2026-05-28
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0004_scan_jobs"
down_revision: Union[str, None] = "0003_investigation_verdict"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "scan_jobs" in inspector.get_table_names():
        return

    op.create_table(
        "scan_jobs",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("job_id", sa.String(32), nullable=False, unique=True),
        sa.Column(
            "user_id",
            sa.Integer,
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("urls_json", sa.JSON, nullable=False, server_default="[]"),
        sa.Column("results_json", sa.JSON, nullable=False, server_default="[]"),
        sa.Column("status", sa.String(16), nullable=False, server_default="queued"),
        sa.Column("total", sa.Integer, nullable=False, server_default="0"),
        sa.Column("completed", sa.Integer, nullable=False, server_default="0"),
        sa.Column("failed_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("credits_estimate", sa.Integer, nullable=False, server_default="0"),
        sa.Column("credits_used", sa.Integer, nullable=False, server_default="0"),
        sa.Column("max_commenters", sa.Integer, nullable=False, server_default="100"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_scanjob_job_id", "scan_jobs", ["job_id"])
    op.create_index("ix_scanjob_user_created", "scan_jobs", ["user_id", "created_at"])
    op.create_index("ix_scanjob_status", "scan_jobs", ["status"])


def downgrade() -> None:
    op.drop_index("ix_scanjob_status", table_name="scan_jobs")
    op.drop_index("ix_scanjob_user_created", table_name="scan_jobs")
    op.drop_index("ix_scanjob_job_id", table_name="scan_jobs")
    op.drop_table("scan_jobs")
