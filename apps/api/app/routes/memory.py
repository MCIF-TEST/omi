"""Institutional memory engineering APIs (Sprint 013) — admin only.

Observability + maintenance for the tiered memory store: the tier distribution + distillation
metrics, and a trigger for the background consolidation pass. These operate on the DURABLE store
(Supabase when configured, else the main DB) — never the live investigation path, so they cannot
add latency to an investigation. Read-only stats + an explicit, deterministic consolidation pass.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.core.auth import CurrentUser, require_user
from app.core.config import get_settings
from app.memory.compression import compress
from app.memory.consolidation import consolidate
from app.memory.feedback import RetrievalFeedback
from app.memory.graph.postgres import PostgresMemoryStore
from app.memory.metrics import dashboard, memory_stats
from app.memory.pipeline import measure_memory_impact

admin_router = APIRouter(prefix="/v1/admin/memory", tags=["admin-memory"])


class FeedbackIn(BaseModel):
    """One retrieval-feedback event — a measurement that improves future retrieval RANKING only.
    It never changes an investigation's score, the Governor, or OmiScore."""

    ko_id: str
    investigation: str
    selected_because: str = ""
    influenced: bool = False
    governor_accepted: bool = False
    analyst_agreed: bool = False
    at: str = Field(default="")


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


@admin_router.get("/dashboard")
def memory_dashboard(current: CurrentUser = Depends(require_user)) -> dict:
    """The institutional-knowledge dashboard: tier distribution + distillation, compression
    potential, reuse frequency, top archetypes / institutional patterns, unused memories, and
    retrieval precision. A read-only measurement snapshot — never mutates memory or any score."""
    _require_admin(current)
    return dashboard(_durable_store())


@admin_router.post("/compress")
def run_compression(current: CurrentUser = Depends(require_user)) -> dict:
    """Run one deterministic compression pass (merge equivalent duplicates into a canonical object,
    provenance preserved — denser, not larger). Off the live investigation path; idempotent. Never
    deletes evidence or changes a score."""
    _require_admin(current)
    store = _durable_store()
    report = compress(store)
    return {"report": report.to_dict(), "stats": memory_stats(store)}


@admin_router.get("/feedback")
def list_feedback(ko_id: str | None = None, current: CurrentUser = Depends(require_user)) -> dict:
    """The append-only retrieval-feedback ledger (optionally for one knowledge object). A
    measurement that improves future retrieval RANKING only."""
    _require_admin(current)
    store = _durable_store()
    rows = store.feedback(ko_id=ko_id) if hasattr(store, "feedback") else []
    return {"feedback": [fb.to_dict() for fb in rows], "count": len(rows)}


@admin_router.post("/feedback")
def record_feedback(body: FeedbackIn, current: CurrentUser = Depends(require_user)) -> dict:
    """Record one retrieval-feedback event (append-only). ``useful`` ⇔ it influenced reasoning AND
    the Governor accepted the ruling AND the analyst agreed — the only thing that lifts a memory's
    future ranking. Never changes a score, a memory's confidence, the Governor, or OmiScore."""
    _require_admin(current)
    store = _durable_store()
    fb = RetrievalFeedback(
        ko_id=body.ko_id, investigation=body.investigation, selected_because=body.selected_because,
        influenced=body.influenced, governor_accepted=body.governor_accepted,
        analyst_agreed=body.analyst_agreed, at=body.at,
    )
    store.record_feedback(fb)
    return {"recorded": fb.to_dict()}


@admin_router.post("/impact/{slug}")
def investigation_memory_impact(
    slug: str, learn: bool = True, current: CurrentUser = Depends(require_user),
) -> dict:
    """Run the COMPLETE live loop over one real stored investigation and measure memory's effect:
    Investigation → Bundle → Governor → Retrieval → Council → Shadow → Memory Candidate. Runs the
    real Shadow pipeline with and without memory to isolate memory's effect, records Governor-gated
    feedback, and (``learn=true``, the default) writes the Governor-gated memory candidate to the
    durable store — connecting real investigations to persistent institutional memory.

    Engineering/validation tool: the user's production result is untouched and the engine number is
    constitutionally preserved (verified in the returned ``number_preserved``)."""
    _require_admin(current)
    from app.reasoning import analyst
    from app.storage.db import get_session
    from app.storage.repository import AccountRepository

    with get_session() as session:
        repo = AccountRepository(session)
        inv = repo.get_investigation(slug=slug, user_id=current.id if current.id != 0 else None)
        if inv is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Investigation not found.")
        payload = inv.payload_json or {}
        ref, platform = analyst._ref(inv.slug), analyst._platform_of(inv)

    impact = measure_memory_impact(
        payload, ref=ref, platform=platform, store=_durable_store(),
        settings=get_settings(), learn=learn,
    )
    return {"slug": slug, "impact": impact.to_dict()}
