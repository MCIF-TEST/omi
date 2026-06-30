"""Memory persistence engine + session (Sprint 012).

The memory system can persist to a DEDICATED database (e.g. Supabase) separate from the main
app DB. When ``memory_database_url`` is set, a pooled engine targets it and only the memory
tables are created there; otherwise memory shares the main app session. The Council never sees
any of this — it calls the repository interface. The URL is a secret supplied via env
(``OMI_MEMORY_DATABASE_URL``); it is never hard-coded.
"""
from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import Settings, get_settings
from app.storage.models import (
    Base,
    KnowledgeObjectRow,
    KnowledgeObjectSignatureRow,
    MemoryRevisionRow,
    ObservationLedgerRow,
    PriorContextCacheRow,
)

logger = logging.getLogger("omi.memory.db")

_MEMORY_TABLES = [
    KnowledgeObjectRow.__table__, KnowledgeObjectSignatureRow.__table__,
    ObservationLedgerRow.__table__, MemoryRevisionRow.__table__, PriorContextCacheRow.__table__,
]

_engine: Engine | None = None
_SessionLocal: "sessionmaker[Session] | None" = None
_engine_url: str | None = None


def _build_engine(url: str, *, pool_size: int, max_overflow: int) -> Engine:
    if url.startswith("sqlite"):
        kwargs: dict = {"future": True, "connect_args": {"check_same_thread": False}}
        if ":memory:" in url:
            kwargs["poolclass"] = StaticPool
        return create_engine(url, **kwargs)
    return create_engine(url, future=True, pool_size=pool_size, max_overflow=max_overflow, pool_pre_ping=True)


def init_memory_db(settings: Settings | None = None) -> Engine:
    """Initialize the dedicated memory engine + create only the memory tables. Idempotent."""
    global _engine, _SessionLocal, _engine_url
    settings = settings or get_settings()
    url = settings.memory_database_url
    if not url:
        raise RuntimeError("memory_database_url is not configured")
    if _engine is None or _engine_url != url:
        _engine = _build_engine(url, pool_size=settings.memory_db_pool_size,
                                max_overflow=settings.memory_db_max_overflow)
        _engine_url = url
        Base.metadata.create_all(_engine, tables=_MEMORY_TABLES)
        _SessionLocal = sessionmaker(bind=_engine, future=True, expire_on_commit=False)
        logger.info("memory DB initialized (dedicated persistence engine)")
    return _engine


@contextmanager
def memory_session(settings: Settings | None = None) -> Iterator[Session]:
    """A session for the memory store. Uses the dedicated engine when ``memory_database_url`` is
    set, else the main app session — the repository is identical either way."""
    settings = settings or get_settings()
    if not settings.memory_database_url:
        from app.storage.db import get_session
        with get_session() as session:
            yield session
        return
    if _SessionLocal is None or _engine_url != settings.memory_database_url:
        init_memory_db(settings)
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


def reset_memory_db_for_tests() -> None:
    """Drop the dedicated memory engine (tests only)."""
    global _engine, _SessionLocal, _engine_url
    _engine = None
    _SessionLocal = None
    _engine_url = None
