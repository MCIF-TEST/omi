"""Database engine + session management.

Sync SQLAlchemy 2.0. SQLite by default (no infra required), Postgres in
production via ``OMI_DATABASE_URL``. FastAPI runs sync endpoints in a
threadpool, so blocking I/O here is safe.
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import get_settings
from app.storage.models import Base


_engine: Engine | None = None
_SessionLocal: sessionmaker[Session] | None = None


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
    """Initialize the global engine + session factory. Idempotent."""
    global _engine, _SessionLocal
    if _engine is not None and url is None:
        return _engine
    target = url or get_settings().database_url
    _engine = _build_engine(target)
    _SessionLocal = sessionmaker(bind=_engine, expire_on_commit=False, future=True)
    Base.metadata.create_all(_engine)
    return _engine


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
