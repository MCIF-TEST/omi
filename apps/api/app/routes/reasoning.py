"""Reasoning endpoints — Phase 7.

Only one for now: generate (or fetch cached) commentary on an
investigation. Always authenticated; commentary lives on the user's
investigation row.

Public report routes (under /r/...) do NOT generate commentary; they
only display it if the owner has already generated one. This prevents
share recipients from running up the owner's token bill.
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

from app.core import background
from app.core.auth import CurrentUser, require_user
from app.core.config import get_settings
from app.reasoning import analyst, synthesize_commentary
from app.schemas import AnalystResponse, CommentaryResponse
from app.storage.db import get_session
from app.storage.repository import AccountRepository


router = APIRouter(prefix="/v1/investigations", tags=["reasoning"])


@router.post("/{slug}/commentary", response_model=CommentaryResponse)
def generate_commentary(
    slug: str,
    refresh: bool = Query(False, description="Force regeneration even if cached."),
    current: CurrentUser = Depends(require_user),
) -> CommentaryResponse:
    """Generate (or return cached) analyst-style commentary on an
    investigation. Idempotent unless ``refresh=true``."""
    with get_session() as session:
        repo = AccountRepository(session)
        inv = repo.get_investigation(
            slug=slug, user_id=current.id if current.id != 0 else None,
        )
        if inv is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Investigation not found.",
            )

        # Cache hit
        if inv.commentary_text and not refresh:
            return CommentaryResponse(
                slug=inv.slug,
                text=inv.commentary_text,
                provider=inv.commentary_provider or "unknown",
                tokens_used=inv.commentary_tokens_used or 0,
                generated_at=inv.commentary_generated_at or datetime.now(timezone.utc),
                cached=True,
            )

        # Generate
        result = synthesize_commentary(
            investigation={
                "label": inv.label,
                "input_url": inv.input_url,
                "kind": inv.kind,
                "slug": inv.slug,
                "created_at": inv.created_at,
            },
            payload=inv.payload_json or {},
        )
        now = datetime.now(timezone.utc)
        inv.commentary_text = result.text
        inv.commentary_provider = result.provider
        inv.commentary_tokens_used = result.tokens_used
        inv.commentary_generated_at = now

        return CommentaryResponse(
            slug=inv.slug,
            text=result.text,
            provider=result.provider,
            tokens_used=result.tokens_used,
            generated_at=now,
            cached=False,
        )


@router.post("/{slug}/analyst", response_model=AnalystResponse)
def generate_analyst_assessment(
    slug: str,
    response: Response,
    refresh: bool = Query(False, description="Force regeneration even if cached."),
    current: CurrentUser = Depends(require_user),
) -> AnalystResponse:
    """Return (or asynchronously generate) the Omi Analyst's structured, evidence-
    bounded assessment of an investigation. Feature-flagged OFF by default; never
    touches detection, scoring, or OmiScore — it interprets evidence the engine
    already produced.

    * Disabled  -> 503.
    * Cached    -> 200 with the assessment.
    * Uncached  -> 202; generation runs off the request hot path (background pool)
      and the client polls this endpoint again until it returns 200.
    """
    settings = get_settings()
    if not analyst.analyst_enabled(settings):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Omi Analyst is disabled (feature-flagged off).",
        )

    with get_session() as session:
        repo = AccountRepository(session)
        inv = repo.get_investigation(
            slug=slug, user_id=current.id if current.id != 0 else None,
        )
        if inv is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Investigation not found.",
            )

        entry = analyst.cached_assessment(inv)
        if entry and not refresh:
            if analyst.entry_is_model_backed(entry):
                return AnalystResponse(
                    slug=inv.slug, enabled=True, status="ready", cached=True,
                    assessment=entry["assessment"], provider=entry.get("provider"),
                    generated_at=entry.get("generated_at"),
                )
            # The cached assessment is the deterministic Floor (the model wasn't reached, or its output
            # failed validation). Auto-regenerate ONCE — a fresh model call — so a stale Floor self-heals
            # without the user doing anything. While that fresh attempt runs we keep the client polling
            # (202); if we've already retried this investigation, serve the honest Floor with its diagnostic.
            # Only when a live model call is actually POSSIBLE (provider + credential configured) — otherwise
            # floorng is expected and permanent, and re-triggering would just churn.
            if not analyst.runtime_status(settings).get("ready_for_live_model"):
                return AnalystResponse(
                    slug=inv.slug, enabled=True, status="ready", cached=True,
                    assessment=entry["assessment"], provider=entry.get("provider"),
                    generated_at=entry.get("generated_at"),
                )
            if analyst.is_generation_inflight(inv.slug):
                response.status_code = status.HTTP_202_ACCEPTED
                return AnalystResponse(slug=inv.slug, enabled=True, status="generating", cached=False)
            if analyst.claim_floor_autorefresh(inv.slug):
                refresh = True
            else:
                return AnalystResponse(
                    slug=inv.slug, enabled=True, status="ready", cached=True,
                    assessment=entry["assessment"], provider=entry.get("provider"),
                    generated_at=entry.get("generated_at"),
                )

        # A generation is already running for this investigation (e.g. auto-scheduled at scan time) —
        # keep the client polling WITHOUT re-submitting a background job on every poll. The in-flight
        # guard would skip a duplicate anyway; short-circuiting here avoids the per-poll churn seen in the
        # logs while a slow model call is in flight.
        if analyst.is_generation_inflight(inv.slug) and not refresh:
            response.status_code = status.HTTP_202_ACCEPTED
            return AnalystResponse(slug=inv.slug, enabled=True, status="generating", cached=False)

        # Async: generate off the request hot path; client polls for the result.
        background.submit(
            analyst.generate_and_persist, inv.slug,
            current.id if current.id != 0 else None, refresh,
        )
        response.status_code = status.HTTP_202_ACCEPTED
        return AnalystResponse(
            slug=inv.slug, enabled=True, status="generating", cached=False,
        )


@router.get("/analyst/status")
def analyst_runtime_status(current: CurrentUser = Depends(require_user)) -> dict:
    """Diagnostic snapshot of the AI runtime path — which links are configured / ready
    (HF token, endpoint, impl, the mandatory Governor, the always-on Floor) plus the full
    ordered runtime **dependency graph** (Sprint 016: every link marked verified /
    operator_action / blocked, so activation readiness is a single verifiable answer). No
    secrets: token presence is a boolean, never the value."""
    settings = get_settings()
    status = analyst.runtime_status(settings)
    status["runtime_path"] = analyst.runtime_path(settings)
    return status


@router.get("/analyst/integrity")
def analyst_integrity(current: CurrentUser = Depends(require_user)) -> dict:
    """Live AI integration diagnostics (Sprint 018): prompt integrity (the Prompt Registry is the
    single source of truth; the ml/ + HF model-card mirror matches; per-specialist content-addressed
    hashes; model-revision pin status) + a real Hugging Face endpoint health probe (when configured).
    No secrets — token presence is a boolean."""
    if not current.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin only.")
    from app.reasoning import analyst
    from app.reasoning.package import load_ai_package
    from app.reasoning.trace import endpoint_health, prompt_integrity, system_health

    settings = get_settings()
    return {"prompt_integrity": prompt_integrity(settings), "endpoint_health": endpoint_health(settings),
            "system_health": system_health(settings), "runtime_metrics": analyst.runtime_metrics(),
            "ai_package": load_ai_package(getattr(settings, "analyst_model_id", None)).provenance()}


@router.post("/analyst/probe")
def analyst_openrouter_probe(current: CurrentUser = Depends(require_user)) -> dict:
    """Make ONE real, minimal OpenRouter call with the CONFIGURED key + base URL + preset, and report
    exactly what happened — a definitive connectivity check that is independent of the investigation
    pipeline, the caches, and the schema validation. Admin only (it spends a trivial amount on the key).

    Use this to answer 'does the deployed service actually reach OpenRouter with my key?': a success here
    appears on your OpenRouter dashboard (cross-reference ``generation_id``); a failure returns the exact
    HTTP status / error class. No secret is ever returned — the key rides in the Authorization header only.
    """
    if not current.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin only.")
    import os

    from app.reasoning.model_providers import OpenRouterReasoningProvider, ReasoningRequest
    from app.reasoning.model_providers.openrouter import OPENROUTER_URL, classify_transport_failure

    settings = get_settings()
    provider_sel = analyst.reasoning_provider(settings)
    preset = getattr(settings, "openrouter_preset", None)
    model = getattr(settings, "openrouter_model", None)
    key_present = bool(os.environ.get("OPENROUTER_API_KEY"))
    base_url = str(getattr(settings, "openrouter_base_url", OPENROUTER_URL) or OPENROUTER_URL)

    result: dict = {
        "active_provider": provider_sel,
        "openrouter_preset": preset,
        "openrouter_model": model,
        "openrouter_api_key_present": key_present,       # boolean only — never the value
        "base_url": base_url,
        "reached_openrouter": False,
    }
    if provider_sel != "openrouter":
        result["error"] = (f"active provider is '{provider_sel}', not 'openrouter' — set "
                           "OMI_ANALYST_PROVIDER=openrouter (and configure a preset).")
        return result
    if not (preset or model):
        result["error"] = "no OpenRouter preset or model configured (OMI_OPENROUTER_PRESET)."
        return result
    if not key_present:
        result["error"] = "OPENROUTER_API_KEY is not set in the environment."
        return result

    capture: dict = {}
    provider = OpenRouterReasoningProvider(
        base_url=base_url, model=model, preset=preset,
        structured_output=False,                         # a plain ping — no schema, minimal tokens
        referer=getattr(settings, "openrouter_referer", None),
        title=getattr(settings, "openrouter_title", None),
        timeout=float(getattr(settings, "analyst_timeout_seconds", 30.0) or 30.0),
        max_retries=0, capture=capture)
    try:
        resp = provider.complete(ReasoningRequest(
            system="", user="Reply with the single word: pong.",
            response_format="text", temperature=0.0, max_tokens=8))
        result["reached_openrouter"] = True
        result["http_status"] = capture.get("response_status")
        result["served_model"] = capture.get("served_model") or resp.model
        # Verify the served model IS the expected one (GPT-5 Mini) so the probe answers "which model?"
        # definitively, not just "reachable?". None when no expectation is configured.
        _expected = getattr(settings, "openrouter_expected_model", None)
        result["expected_model"] = _expected or None
        result["served_model_verified"] = analyst._served_model_matches(result["served_model"], _expected)
        result["generation_id"] = capture.get("endpoint_request_id")   # cross-reference on the dashboard
        result["usage"] = capture.get("usage")
        result["latency_ms"] = capture.get("latency_ms")
        result["reply_excerpt"] = (resp.text or "")[:120]
    except Exception as exc:  # noqa: BLE001 — report the failure, never raise
        st = capture.get("response_status")
        result["reached_openrouter"] = bool(st)          # an HTTP status means the request reached the API
        result["http_status"] = st
        result["failure_class"] = classify_transport_failure(exc, st if isinstance(st, int) else None)
        result["error"] = f"{type(exc).__name__}: {str(exc)[:200]}"
        result["generation_id"] = capture.get("endpoint_request_id")
    return result


@router.post("/{slug}/analyst/trace")
def analyst_trace(slug: str, current: CurrentUser = Depends(require_user)) -> dict:
    """Execute the production AI pipeline over a REAL stored investigation and return the ordered,
    per-stage end-to-end trace (execution time, inputs, outputs, failures, fallback). Read-only
    diagnostic — reuses the production runtime, never mutates the investigation or OmiScore."""
    if not current.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin only.")
    from app.reasoning.trace import trace_investigation

    with get_session() as session:
        inv = AccountRepository(session).get_investigation(
            slug=slug, user_id=current.id if current.id != 0 else None)
        if inv is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Investigation not found.")
        payload = inv.payload_json or {}
        ref, platform = analyst._ref(inv.slug), analyst._platform_of(inv)
    return {"slug": slug, "trace": trace_investigation(payload, ref=ref, platform=platform)}


@router.post("/{slug}/analyst/audit")
def analyst_audit(slug: str, current: CurrentUser = Depends(require_user)) -> dict:
    """Forensic single-investigation audit (endpoint UNTRUSTED): run the REAL analyst path once with
    full capture and return per-stage evidence — the exact final prompt sent, the prompt
    version/hash from the AI package, the served model id, the raw model response before the
    Governor, the Governor verdict + rejection reason on fallback, and whether the report renders the
    model or the deterministic floor. Read-only; reuses the production runtime; also written to the
    Render log (``omi.reasoning.audit``)."""
    if not current.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin only.")
    from app.reasoning.trace import audit_investigation

    with get_session() as session:
        inv = AccountRepository(session).get_investigation(
            slug=slug, user_id=current.id if current.id != 0 else None)
        if inv is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Investigation not found.")
        payload = inv.payload_json or {}
        ref, platform = analyst._ref(inv.slug), analyst._platform_of(inv)
    return {"slug": slug, "audit": audit_investigation(payload, ref=ref, platform=platform)}
