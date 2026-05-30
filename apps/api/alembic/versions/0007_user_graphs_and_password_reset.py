"""User-curated named graphs + password-reset columns.

Brings the Alembic chain back in line with the models after two changes
that previously relied only on create_all / the incremental-column boot
pass:

* ``user_graphs`` + ``user_graph_members`` — operator-curated graphs of
  commenter profiles (the graph feature redesign).
* ``users.reset_token_hash`` + ``users.reset_token_expires`` — password
  reset.

Every step is guarded so the migration is idempotent and safe to run on a
database that already has some of these objects (e.g. one bootstrapped by
create_all).

Revision ID: 0007_user_graphs_and_password_reset
Revises: 0006_content_reply_pods
Create Date: 2026-05-30
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0007_user_graphs_and_password_reset"
down_revision: Union[str, None] = "0006_content_reply_pods"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    # --- user_graphs --------------------------------------------------------
    if "user_graphs" not in tables:
        op.create_table(
            "user_graphs",
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column(
                "user_id",
                sa.Integer,
                sa.ForeignKey("users.id", ondelete="CASCADE"),
                nullable=False,
                index=True,
            ),
            sa.Column("name", sa.String(200), nullable=False),
            sa.Column("platform", sa.String(32), nullable=False, server_default="youtube"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
            sa.UniqueConstraint("user_id", "name", name="uq_user_graph_name"),
        )

    # --- user_graph_members -------------------------------------------------
    if "user_graph_members" not in tables:
        op.create_table(
            "user_graph_members",
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column(
                "graph_id",
                sa.Integer,
                sa.ForeignKey("user_graphs.id", ondelete="CASCADE"),
                nullable=False,
                index=True,
            ),
            sa.Column("external_id", sa.String(128), nullable=False, index=True),
            sa.Column("platform", sa.String(32), nullable=False, server_default="youtube"),
            sa.Column("handle", sa.String(280), nullable=False, server_default=""),
            sa.Column("display_name", sa.String(280), nullable=True),
            sa.Column("tier", sa.String(16), nullable=True),
            sa.Column("avatar_url", sa.String(512), nullable=True),
            sa.Column("added_at", sa.DateTime(timezone=True), nullable=True),
            sa.UniqueConstraint("graph_id", "external_id", name="uq_graph_member"),
        )

    # --- users.reset_token_* -----------------------------------------------
    if "users" in tables:
        user_cols = {c["name"] for c in inspector.get_columns("users")}
        if "reset_token_hash" not in user_cols:
            op.add_column("users", sa.Column("reset_token_hash", sa.String(64), nullable=True))
            op.create_index("ix_users_reset_token_hash", "users", ["reset_token_hash"])
        if "reset_token_expires" not in user_cols:
            op.add_column(
                "users", sa.Column("reset_token_expires", sa.DateTime(timezone=True), nullable=True)
            )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "users" in tables:
        user_cols = {c["name"] for c in inspector.get_columns("users")}
        if "reset_token_expires" in user_cols:
            op.drop_column("users", "reset_token_expires")
        if "reset_token_hash" in user_cols:
            try:
                op.drop_index("ix_users_reset_token_hash", table_name="users")
            except Exception:
                pass
            op.drop_column("users", "reset_token_hash")

    if "user_graph_members" in tables:
        op.drop_table("user_graph_members")
    if "user_graphs" in tables:
        op.drop_table("user_graphs")
