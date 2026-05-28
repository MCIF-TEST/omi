"""Baseline — captures the schema as of v1.0.0.

This migration is intentionally a no-op. The existing boot flow
(``Base.metadata.create_all`` + the ``_INCREMENTAL_COLUMNS`` hook in
``app/storage/db.py``) creates every table this baseline would, and
existing production databases have those tables already.

The baseline exists so:

1. ``alembic stamp head`` on an existing deploy marks the DB as
   "current" without running any DDL — a safe one-line migration to
   Alembic.
2. Future migrations (``0002_*.py``, ``0003_*.py``, ...) form a clean
   chain from this baseline.
3. ``alembic upgrade head`` on a brand-new DB still works: it will run
   nothing here and then any subsequent migrations.

Revision ID: 0001_baseline
Revises:
Create Date: 2026-05-28
"""

from __future__ import annotations

from typing import Sequence, Union


revision: str = "0001_baseline"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Intentional no-op. See module docstring.
    pass


def downgrade() -> None:
    # Refuse to downgrade past the baseline — there's nothing below it.
    pass
