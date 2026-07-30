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
    is_file_sqlite = url.startswith("sqlite") and ":memory:" not in url
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
            # Background tasks (narrative ingestion, content intelligence,
            # investigation persistence) contend for the write lock. Without a
            # timeout they fail immediately with "database is locked". 30 seconds
            # is generous — any longer and the background pool would back up.
            connect_args["timeout"] = 30
    if not url.startswith("sqlite"):
        # Managed Postgres gets restarted for maintenance and failover, which silently kills pooled
        # connections. Without pre-ping the next request to reuse one fails with
        # "server closed the connection unexpectedly" until the pool turns over — an outage that looks
        # random and recurring rather than like scheduled maintenance. pre_ping costs one cheap
        # round-trip per checkout and removes the entire failure mode.
        kwargs["pool_pre_ping"] = True
        # Recycle below common proxy/server idle timeouts so we retire connections before something
        # upstream does it for us.
        kwargs["pool_recycle"] = 1800
        # Sized explicitly rather than inherited (SQLAlchemy defaults to 5 + 10 overflow). Keep
        # instances × (pool_size + max_overflow) under the database plan's connection limit, or new
        # connections start being refused under load. Env-tunable so scaling out doesn't need a code
        # change: OMI_DB_POOL_SIZE / OMI_DB_MAX_OVERFLOW.
        #
        # NB: uses the MODULE-level `os` import deliberately. A local `import os` here would make `os`
        # a local for the whole function, so the SQLite branch above (os.makedirs) would raise
        # UnboundLocalError before this line ever ran — the function-level-import trap in CLAUDE.md.
        kwargs["pool_size"] = int(os.environ.get("OMI_DB_POOL_SIZE", "5"))
        kwargs["max_overflow"] = int(os.environ.get("OMI_DB_MAX_OVERFLOW", "10"))

    engine = create_engine(url, connect_args=connect_args, **kwargs)
    if is_file_sqlite:
        # WAL journal mode: readers never block writers; multiple readers can
        # proceed concurrently with a single writer. NORMAL synchronous is safe
        # under WAL (a crash mid-write at worst loses the last unflushed
        # transaction, not the whole DB) and is significantly faster than FULL.
        from sqlalchemy import event, text as _text

        @event.listens_for(engine, "connect")
        def _set_sqlite_pragmas(dbapi_conn, _record):
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA journal_mode=WAL")
            cur.execute("PRAGMA synchronous=NORMAL")
            cur.execute("PRAGMA wal_autocheckpoint=1000")
            cur.close()

    return engine


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
    _ensure_indexes(_engine)
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
    # Referral system + signup-IP fraud prevention
    ("users", "signup_ip_hash", "VARCHAR(64)"),
    ("users", "referral_code", "VARCHAR(16)"),
    ("users", "referred_by_user_id", "INTEGER"),
    ("users", "referral_credits_earned", "INTEGER DEFAULT 0"),
    ("users", "referral_subscription_bonus_paid", "INTEGER DEFAULT 0"),
    # Phase C — reply-pod count on content entities
    ("content_entities", "latest_reply_pod_count", "INTEGER DEFAULT 0"),
    # Password reset (single-use token hash + expiry)
    ("users", "reset_token_hash", "VARCHAR(64)"),
    ("users", "reset_token_expires", "TIMESTAMP WITH TIME ZONE"),
    # Investigation analyst verdict + notes (added after initial release)
    ("investigations", "verdict", "VARCHAR(32)"),
    ("investigations", "concluded_at", "TIMESTAMP WITH TIME ZONE"),
    ("investigations", "notes", "TEXT"),
    # Investigation overall confidence (derived from payload) — list readability
    ("investigations", "confidence", "DOUBLE PRECISION"),
    # Platform + thumbnail denormalised out of payload_json so the archive list never loads the blob
    # (see Investigation.platform). Existing rows stay NULL and fall back to URL heuristics.
    ("investigations", "platform", "VARCHAR(16)"),
    ("investigations", "thumbnail_url", "VARCHAR(500)"),
    # Funnel: which shared report a claimed copy came from (see Investigation.claimed_from_token).
    # Existing rows stay NULL, which correctly means "not claimed from anyone".
    ("investigations", "claimed_from_token", "VARCHAR(48)"),
    # How many commenters were compiled for the post, for the shared-report funnel's "checked N of M".
    ("investigations", "commenters_available", "INTEGER"),
    # Public campaign sharing (opt-in, revocable) — distribution phase
    ("campaigns", "share_token", "VARCHAR(64)"),
    ("campaigns", "is_public", "INTEGER DEFAULT 0"),
    ("campaigns", "published_at", "TIMESTAMP WITH TIME ZONE"),
    # Watchlist platform-awareness — route History links + re-scans correctly.
    # Existing rows backfill to "youtube" (the only platform they could be).
    ("watchlists", "platform", "VARCHAR(32) DEFAULT 'youtube'"),
    # Clerk auth linkage — maps a local account to its Clerk user (linked by email on first sign-in).
    ("users", "clerk_user_id", "VARCHAR(64)"),
    # Real post title (video title / tweet text) for human-readable investigation labels.
    ("candidate_lists", "content_title", "VARCHAR(500)"),
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


def _ensure_indexes(engine: Engine) -> None:
    """Create any model-declared index that doesn't exist on an existing table.

    ``create_all`` builds indexes only for tables it *newly* creates; an index
    added to the model AFTER a table already exists in production is never
    created (create_all leaves existing tables untouched, and the column-upgrade
    pass only adds columns). On a long-lived database that means large tables
    silently fall back to full scans for queries the composite indexes were
    meant to serve (e.g. ``Scan(account_id, scanned_at)``,
    ``Investigation(user_id, created_at)``, ``Alert(user_id, created_at)``).

    This pass closes that gap. Idempotent (``checkfirst``) and best-effort: a
    failure to add one index is logged, never raised, so boot always proceeds.
    """
    try:
        insp = inspect(engine)
        existing_tables = set(insp.get_table_names())
    except Exception as e:
        _logger.warning("could not inspect schema for index upgrades: %s", e)
        return

    for table in Base.metadata.sorted_tables:
        if table.name not in existing_tables:
            continue  # create_all already built this table and its indexes
        try:
            present = {ix.get("name") for ix in insp.get_indexes(table.name)}
        except Exception as e:
            _logger.warning("could not read indexes for %s: %s", table.name, e)
            continue
        for index in table.indexes:
            if index.name in present:
                continue
            try:
                index.create(bind=engine, checkfirst=True)
                _logger.info("Created missing index %s on %s", index.name, table.name)
            except Exception as e:
                _logger.warning(
                    "could not create index %s on %s: %s", index.name, table.name, e
                )


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
