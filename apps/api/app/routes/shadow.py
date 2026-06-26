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
from app.evidence import Binder
from app.reasoning import analyst
from app.reasoning.context import build_context
from app.reasoning.model_providers import build_remote_provider, provider_status
from app.reasoning.prompts import PromptExperiment, compare_prompts, default_registry
from app.reasoning.shadow import (
    ab_evaluate,
    aggregate_stats,
    all_reports,
    cached_report,
    compare_context_modes,
    persist_report,
    run_shadow,
)
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


@admin_router.get("/prompts")
def list_prompts(analyst_name: str | None = None, current: CurrentUser = Depends(require_user)) -> dict:
    """The Prompt Registry listing — versioned, content-hashed prompts per analyst, with the
    active version flagged. Selection is config-driven (``OMI_ANALYST_PROMPT_VERSION``)."""
    _require_admin(current)
    registry = default_registry()
    return {"analysts": registry.analysts(), "prompts": registry.records(analyst_name)}


@admin_router.post("/context/{slug}")
def run_context(
    slug: str,
    budget: str = Query("standard"),
    current: CurrentUser = Depends(require_user),
) -> dict:
    """Build the structured Context Builder output + quality metrics for one investigation
    (model-independent, so it works offline). When a model endpoint is configured, also runs
    the raw-vs-structured reasoning comparison through Shadow Mode."""
    _require_admin(current)
    with get_session() as session:
        repo = AccountRepository(session)
        inv = repo.get_investigation(slug=slug, user_id=current.id if current.id != 0 else None)
        if inv is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Investigation not found.")
        payload = inv.payload_json or {}
        ref, platform = analyst._ref(inv.slug), analyst._platform_of(inv)
        bundle = Binder().bind(payload, grain="comment_section", subject_ref=ref, platform=platform)
        ctx = build_context(bundle, budget=budget)

        provider = build_remote_provider(get_settings())
        execution = None
        if provider is not None:
            execution = compare_context_modes(
                payload, ref=ref, provider_raw=provider, budget=budget, platform=platform,
            )
        return {"slug": slug, "budget": budget, "context": ctx.to_dict(), "execution": execution}


@admin_router.post("/ab/{slug}")
def run_ab(
    slug: str,
    variant_a: str = Query("v1"),
    variant_b: str = Query("v2"),
    analyst_name: str = Query("behavior_analyst"),
    current: CurrentUser = Depends(require_user),
) -> dict:
    """A/B two prompt versions on one investigation. The prompt diff is always returned; the
    live execution comparison requires a configured model endpoint (otherwise both variants
    fall back to deterministic — a null result by construction)."""
    _require_admin(current)
    registry = default_registry()
    try:
        spec_a, spec_b = registry.resolve(analyst_name, variant_a), registry.resolve(analyst_name, variant_b)
    except KeyError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown analyst or prompt version.")
    prompts = compare_prompts(spec_a, spec_b)

    with get_session() as session:
        repo = AccountRepository(session)
        inv = repo.get_investigation(slug=slug, user_id=current.id if current.id != 0 else None)
        if inv is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Investigation not found.")
        provider = build_remote_provider(get_settings())
        if provider is None:
            return {"slug": slug, "analyst": analyst_name, "prompts": prompts, "execution": None,
                    "note": "Live A/B requires a configured model endpoint; prompt diff shown."}
        result = ab_evaluate(
            inv.payload_json or {}, ref=analyst._ref(inv.slug),
            experiment=PromptExperiment(analyst_name, variant_a, variant_b),
            provider_a=provider, provider_b=provider, platform=analyst._platform_of(inv), registry=registry,
        )
        return {"slug": slug, "analyst": analyst_name, "prompts": prompts, "execution": result}


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
