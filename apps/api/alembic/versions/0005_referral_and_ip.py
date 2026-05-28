"""Referral system + signup-IP fraud prevention.

Adds five columns to the users table:
  * signup_ip_hash               — SHA-256 of the IP a user signed up from
  * referral_code                — unique URL-safe code per user
  * referred_by_user_id          — FK to the inviter (nullable)
  * referral_credits_earned      — running total of bonuses received
  * referral_subscription_bonus_paid — idempotency guard for the +5 bonus

Migration is idempotent — adds columns/indexes only when missing — so it
can run safely against fresh and existing deployments.

Revision ID: 0005_referral_and_ip
Revises: 0004_scan_jobs
Create Date: 2026-05-28
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0005_referral_and_ip"
down_revision: Union[str, None] = "0004_scan_jobs"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_COLUMNS = {
    "signup_ip_hash":                  sa.Column("signup_ip_hash", sa.String(64), nullable=True),
    "referral_code":                   sa.Column("referral_code", sa.String(16), nullable=True),
    "referred_by_user_id":             sa.Column("referred_by_user_id", sa.Integer, nullable=True),
    "referral_credits_earned":         sa.Column("referral_credits_earned", sa.Integer, nullable=False, server_default="0"),
    "referral_subscription_bonus_paid": sa.Column("referral_subscription_bonus_paid", sa.Integer, nullable=False, server_default="0"),
}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "users" not in inspector.get_table_names():
        return

    existing_cols = {c["name"] for c in inspector.get_columns("users")}
    for name, column in _COLUMNS.items():
        if name not in existing_cols:
            op.add_column("users", column)

    existing_indexes = {ix["name"] for ix in inspector.get_indexes("users")}
    if "ix_users_signup_ip_hash" not in existing_indexes:
        op.create_index("ix_users_signup_ip_hash", "users", ["signup_ip_hash"])
    if "ix_users_referral_code" not in existing_indexes:
        op.create_index("ix_users_referral_code", "users", ["referral_code"], unique=True)
    if "ix_users_referred_by_user_id" not in existing_indexes:
        op.create_index("ix_users_referred_by_user_id", "users", ["referred_by_user_id"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "users" not in inspector.get_table_names():
        return

    existing_indexes = {ix["name"] for ix in inspector.get_indexes("users")}
    for ix_name in ("ix_users_referred_by_user_id", "ix_users_referral_code", "ix_users_signup_ip_hash"):
        if ix_name in existing_indexes:
            op.drop_index(ix_name, table_name="users")

    existing_cols = {c["name"] for c in inspector.get_columns("users")}
    for col_name in reversed(list(_COLUMNS.keys())):
        if col_name in existing_cols:
            op.drop_column("users", col_name)
