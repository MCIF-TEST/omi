"""Institutional memory engineering APIs (Sprint 013) — admin only.

Observability + maintenance for the tiered memory store: the tier distribution + distillation
metrics, and a trigger for the background consolidation pass. These operate on the DURABLE store
(Supabase when configured, else the main DB) — never the live investigation path, so they cannot
add latency to an investigation. Read-only stats + an explicit, deterministic consolidation pass.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.auth import CurrentUser, require_user
from app.core.config import get_settings
from app.memory.consolidation import consolidate
from app.memory.graph.postgres import PostgresMemoryStore
from app.memory.metrics import memory_stats

admin_router = APIRouter(prefix="/v1/admin/memory", tags=["admin-memory"])


def _require_admin(current: CurrentUser) -> None:
    if not current.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin only.")


def _durable_store() -> Any:
    """The persistent memory store (the dedicated Supabase DB when configured, else the main DB)."""
    settings = get_settings()
    if getattr(settings, "memory_database_url", None):
        from app.memory.db import memory_session
        return PostgresMemoryStore(lambda: memory_session(settings))
    from app.storage.db import get_session
    return PostgresMemoryStore(get_session)


@admin_router.get("/stats")
def memory_statistics(current: CurrentUser = Depends(require_user)) -> dict:
    """Tier distribution, growth, and distillation metrics over the durable memory store."""
    _require_admin(current)
    return memory_stats(_durable_store())


@admin_router.post("/consolidate")
def run_consolidation(current: CurrentUser = Depends(require_user)) -> dict:
    """Run one deterministic consolidation pass (tier classification + promotion/decay/archival).
    Idempotent; off the live investigation path. In production this is driven by a scheduled job."""
    _require_admin(current)
    store = _durable_store()
    report = consolidate(store)
    return {"report": report.to_dict(), "stats": memory_stats(store)}
