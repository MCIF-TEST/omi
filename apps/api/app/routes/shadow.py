"""Internal Shadow Mode engineering APIs (Sprint 007) — admin only, never user-facing.

Exposes the evaluation pipeline for engineers: run a shadow evaluation on an investigation,
read its stored report, and read aggregate statistics (AI success / fallback / citation-failure
rates, agreement + number-preserved trends, Governor stats, latency). These are tools to
*measure* whether AI reasoning helps before any of it is exposed to production users — the
deterministic path remains the only thing users ever see.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.core.auth import CurrentUser, require_user
from app.core.config import get_settings
from app.reasoning import analyst
from app.reasoning.model_providers import provider_status
from app.reasoning.shadow import aggregate_stats, all_reports, cached_report, persist_report, run_shadow
from app.storage.db import get_session
from app.storage.repository import AccountRepository

admin_router = APIRouter(prefix="/v1/admin/shadow", tags=["admin-shadow"])


def _require_admin(current: CurrentUser) -> None:
    if not current.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin only.")


@admin_router.get("/status")
def shadow_status(current: CurrentUser = Depends(require_user)) -> dict:
    """Pipeline + AI-specialist readiness. The pipeline is always operational (it runs on the
    deterministic fallback when no model endpoint is configured)."""
    _require_admin(current)
    return {
        "pipeline": "operational",
        "production_path": "deterministic",
        "shadow_path": "ai-backed (eval only)",
        "governor": "mandatory",
        **provider_status(get_settings()),
    }


@admin_router.get("/stats")
def shadow_stats(current: CurrentUser = Depends(require_user)) -> dict:
    """Aggregate engineering metrics over every stored shadow evaluation."""
    _require_admin(current)
    with get_session() as session:
        return aggregate_stats(all_reports(session))


@admin_router.post("/investigations/{slug}")
def run_investigation_shadow(
    slug: str,
    refresh: bool = Query(False, description="Re-run even if a report is cached."),
    current: CurrentUser = Depends(require_user),
) -> dict:
    """Run (or return cached) Shadow Mode evaluation for one investigation. Engineering tool:
    the user's production result is unaffected — only an evaluation block is added to the row."""
    _require_admin(current)
    with get_session() as session:
        repo = AccountRepository(session)
        inv = repo.get_investigation(slug=slug, user_id=current.id if current.id != 0 else None)
        if inv is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Investigation not found.")

        cached = cached_report(inv)
        if cached and not refresh:
            return {"slug": slug, "cached": True, "report": cached}

        report = run_shadow(
            inv.payload_json or {}, ref=analyst._ref(inv.slug), platform=analyst._platform_of(inv),
        ).to_dict()
        stored = persist_report(session, inv, report)
        return {"slug": slug, "cached": False, "report": stored}


@admin_router.get("/investigations/{slug}")
def get_investigation_shadow(slug: str, current: CurrentUser = Depends(require_user)) -> dict:
    """Return the stored shadow report for one investigation (404 if none yet)."""
    _require_admin(current)
    with get_session() as session:
        repo = AccountRepository(session)
        inv = repo.get_investigation(slug=slug, user_id=current.id if current.id != 0 else None)
        if inv is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Investigation not found.")
        report = cached_report(inv)
        if report is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No shadow evaluation yet.")
        return {"slug": slug, "report": report}
