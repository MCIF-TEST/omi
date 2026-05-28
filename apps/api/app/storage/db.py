"""Database engine + session management.

Sync SQLAlchemy 2.0. SQLite by default (no infra required), Postgres in
production via ``OMI_DATABASE_URL``. FastAPI runs sync endpoints in a
threadpool, so blocking I/O here is safe.
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Iterator

import logging

from sqlalchemy import Engine, create_engine, inspect
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import get_settings
from app.storage.models import Base


_engine: Engine | None = None
_SessionLocal: sessionmaker[Session] | None = None
_logger = logging.getLogger("omi.storage")


def _build_engine(url: str) -> Engine:
    connect_args: dict = {}
    kwargs: dict = {"future": True}
    if url.startswith("sqlite"):
        # Allow multiple threads (FastAPI uses a threadpool for sync endpoints).
        connect_args["check_same_thread"] = False
        if ":memory:" in url:
            # In-memory SQLite is per-connection by default; force a single
            # shared connection so the schema we created persists across
            # ``get_session()`` calls during tests.
            kwargs["poolclass"] = StaticPool
        else:
            # Make sure the parent directory exists for file-backed sqlite.
            path = url.split("sqlite:///", 1)[-1]
            os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    return create_engine(url, connect_args=connect_args, **kwargs)


def init_db(url: str | None = None) -> Engine:
    """Initialize the global engine + session factory. Idempotent.

    Uses ``Base.metadata.create_all`` which creates missing tables but never
    alters existing ones. Safe to call on every startup. Also runs a small
    in-process schema upgrade pass that ALTERs existing tables when new
    columns are declared on the model — covers the gap between
    ``create_all`` (new tables only) and a full Alembic setup. Logs every
    change so deploys are auditable.
    """
    global _engine, _SessionLocal
    if _engine is not None and url is None:
        return _engine
    target = url or get_settings().database_url
    _engine = _build_engine(target)
    _SessionLocal = sessionmaker(bind=_engine, expire_on_commit=False, future=True)

    try:
        before = set(inspect(_engine).get_table_names())
    except Exception as e:
        _logger.warning("could not enumerate existing tables: %s", e)
        before = set()

    Base.metadata.create_all(_engine)

    try:
        after = set(inspect(_engine).get_table_names())
        new_tables = sorted(after - before)
        if new_tables:
            _logger.info("Created %d new tables: %s", len(new_tables), ", ".join(new_tables))
    except Exception as e:
        _logger.warning("could not verify table creation: %s", e)

    _add_missing_columns(_engine)
    return _engine


# Columns we've added to existing tables AFTER the initial release. Listed
# here so init_db can ALTER TABLE them in on existing production databases
# (create_all only creates missing tables, never alters existing ones).
# Each entry: (table_name, column_name, DDL fragment without trailing comma).
_INCREMENTAL_COLUMNS: list[tuple[str, str, str]] = [
    # Phase 10 — content intelligence
    ("comment_batches", "next_page_token", "VARCHAR(500)"),
    # Phase 11 — alert notifications
    ("users", "notify_alerts_email", "INTEGER DEFAULT 1"),
    ("users", "notify_alerts_webhook", "INTEGER DEFAULT 0"),
    ("users", "webhook_url", "VARCHAR(500)"),
    ("alerts", "delivered_at", "TIMESTAMP WITH TIME ZONE"),
    ("alerts", "delivery_status", "VARCHAR(32)"),
    ("alerts", "delivery_error", "VARCHAR(500)"),
]


def _add_missing_columns(engine: Engine) -> None:
    """ALTER TABLE ... ADD COLUMN for any registered incremental column that
    doesn't exist yet. Idempotent: a missing table is skipped, an existing
    column is skipped, errors are logged but never raised (the boot path
    must keep working even if a migration step fails)."""
    from sqlalchemy import text
    try:
        insp = inspect(engine)
        tables = set(insp.get_table_names())
    except Exception as e:
        _logger.warning("could not inspect schema for column upgrades: %s", e)
        return

    # SQLite uses simpler types — strip "TIMESTAMP WITH TIME ZONE" → "TIMESTAMP"
    is_sqlite = engine.dialect.name == "sqlite"

    for table, column, ddl in _INCREMENTAL_COLUMNS:
        if table not in tables:
            continue
        try:
            existing_cols = {c["name"] for c in insp.get_columns(table)}
            if column in existing_cols:
                continue
            type_clause = ddl
            if is_sqlite and "WITH TIME ZONE" in type_clause.upper():
                type_clause = type_clause.replace("WITH TIME ZONE", "").replace("with time zone", "").strip()
            stmt = text(f'ALTER TABLE {table} ADD COLUMN {column} {type_clause}')
            with engine.begin() as conn:
                conn.execute(stmt)
            _logger.info("Added column %s.%s (%s)", table, column, ddl)
        except Exception as e:
            _logger.warning("Could not add column %s.%s: %s", table, column, e)


def reset_db_for_tests(url: str = "sqlite:///:memory:") -> Engine:
    """Drop the global engine and rebuild against ``url``. Tests only."""
    global _engine, _SessionLocal
    _engine = None
    _SessionLocal = None
    return init_db(url)


@contextmanager
def get_session() -> Iterator[Session]:
    if _SessionLocal is None:
        init_db()
    assert _SessionLocal is not None
    session = _SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
