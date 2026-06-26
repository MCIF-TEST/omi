"""Memory repository interface + factory (Sprint 012).

The seam that hides persistence from the Analyst Council. The Memory Analyst, the extractor, and
``retrieve`` depend only on this interface — never on Postgres, Supabase, or in-memory specifics.
``get_memory_store`` returns the configured backend: the in-memory store by default (existing
behavior, hermetic tests), or the Postgres-backed store when persistence is enabled (a dedicated
Supabase database when ``memory_database_url`` is set, else the main app database).
"""
from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from app.core.config import Settings, get_settings

from .graph.objects import KnowledgeObject
from .graph.store import MemoryStore


@runtime_checkable
class MemoryRepository(Protocol):
    """The persistence-agnostic memory interface the Council uses."""

    def get(self, ko_id: str) -> KnowledgeObject | None: ...
    def all(self, *, include_superseded: bool = False) -> list[KnowledgeObject]: ...
    def ingest(self, *, candidate: dict, investigation: str, stance: str, evidence_refs: list[str],
               independence_key: str, at: str, human_anchor: dict | None = ...,
               memory_influence: str = ..., match_threshold: float = ...) -> KnowledgeObject: ...
    def supersede(self, old_id: str, new_id: str) -> None: ...
    def __len__(self) -> int: ...


def get_memory_store(settings: Settings | None = None) -> Any:
    """Return the configured memory store. In-memory by default; Postgres-backed when
    ``memory_persistence_enabled`` — against a dedicated Supabase DB if ``memory_database_url`` is
    set, else the main app DB. The interface is identical, so callers never change."""
    settings = settings or get_settings()
    if not getattr(settings, "memory_persistence_enabled", False):
        return MemoryStore()

    from .graph.postgres import PostgresMemoryStore
    if getattr(settings, "memory_database_url", None):
        from .db import memory_session

        def _factory():
            return memory_session(settings)
        return PostgresMemoryStore(session_factory=_factory)

    from app.storage.db import get_session
    return PostgresMemoryStore(session_factory=get_session)
