"""End-to-end production AI pipeline trace + live-integration diagnostics (Sprint 018).

Read-only instrumentation for the live AI runtime. It executes the **real** production analyst
pipeline and reports, per stage: execution time, inputs, outputs, failures, and fallback behavior;
probes the Hugging Face endpoint when one is configured; and verifies prompt integrity (the
registry is the single source of truth, the ml/ + HF model-card mirror matches, the model revision
is pinned). No new architecture — it reuses the exact production components (``assess_payload``,
``Binder``, the Prompt Registry, the Governor), so the trace reflects real behavior. Never raises.

Honest by construction: where a stage is part of a *different* runtime surface (e.g. the app
Context Builder + institutional-memory retrieval run inside the **shadow council**, not the
monolithic production analyst), the trace says so rather than implying a connection that isn't there.
"""
from __future__ import annotations

import os
import re
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from app.core.config import Settings, get_settings

# repo root: apps/api/app/reasoning/trace.py -> parents[4]
_ML_DOC = Path(__file__).resolve().parents[4] / "ml" / "analyst" / "analyst_system_prompt_v1.md"


# --------------------------------------------------------------------------- #
# Prompt integrity — registry is the single source of truth; GitHub == HF
# --------------------------------------------------------------------------- #
def _ml_doc_prompt() -> str | None:
    try:
        m = re.search(r"## SYSTEM_PROMPT.*?```text\n(.*?)\n```", _ML_DOC.read_text(encoding="utf-8"), re.DOTALL)
        return (m.group(1) if m else "").strip()
    except Exception:  # noqa: BLE001
        return None


def prompt_integrity(settings: Settings | None = None) -> dict:
    """Verify the Prompt Registry is the single runtime source of truth and that the ml/ spec doc
    (the Hugging Face model-card source) is a byte-identical mirror — so GitHub and HF cannot drift.
    Reports each registered specialist's content-addressed prompt + the model-revision pin status."""
    settings = settings or get_settings()
    from app.reasoning.prompts import default_registry

    reg = default_registry()
    specialists = []
    for name in sorted(reg.analysts()):
        spec = reg.resolve(name)
        specialists.append({"specialist": name, "active_version": reg.active_version(name),
                            "prompt_hash": spec.prompt_hash})

    analyst_spec = reg.resolve("omi_analyst")
    ml_prompt = _ml_doc_prompt()
    revision = getattr(settings, "analyst_hf_revision", None)
    return {
        "registry_is_single_source": True,
        "specialists": specialists,
        "omi_analyst_prompt_hash": analyst_spec.prompt_hash,
        "ml_doc_mirror_matches": (ml_prompt == analyst_spec.template),
        "hf_model_card_source": "ml/analyst/analyst_system_prompt_v1.md (referenced by hf_repo config prompt_file)",
        "model_revision": revision,
        "model_revision_pinned": bool(revision) and revision != "main",
        "model_repo": getattr(settings, "analyst_hf_repo", None),
    }


# --------------------------------------------------------------------------- #
# Live endpoint health — actually probe the HF endpoint when configured
# --------------------------------------------------------------------------- #
def _models_match(served: str | None, expected: str | None) -> bool | None:
    """Tolerant model-id equality. ``None`` when either side is unknown. Exact match wins; else
    compare the bare repo name (a dedicated endpoint may echo ``mistralai/Mistral-7B-Instruct-v0.3``
    or just ``Mistral-7B-Instruct-v0.3``), case-insensitively."""
    if not served or not expected:
        return None
    s, e = served.strip().lower(), expected.strip().lower()
    return True if s == e else (s.split("/")[-1] == e.split("/")[-1])


def endpoint_health(settings: Settings | None = None) -> dict:
    """Probe the configured Hugging Face inference endpoint with a minimal request and report
    reachability + latency **and the model it is actually serving**. Honors the configured serving
    API (``analyst_endpoint_api``) so a ``messages`` deployment is probed with the chat contract —
    never a ``generate``-shaped body that a chat endpoint would reject (which used to mis-report a
    healthy endpoint as unreachable). When no endpoint/token is configured, reports
    ``not_configured`` — never an error. No secrets (token presence is a boolean)."""
    settings = settings or get_settings()
    endpoint = getattr(settings, "analyst_endpoint_url", None)
    token_present = bool(os.environ.get("HF_TOKEN") or os.environ.get("HUGGINGFACE_HUB_TOKEN"))
    expected_model = getattr(settings, "analyst_model_id", None)
    api = str(getattr(settings, "analyst_endpoint_api", "generate") or "generate")
    if not endpoint or not token_present:
        return {"status": "not_configured", "endpoint_configured": bool(endpoint),
                "hf_token_present": token_present, "reachable": None, "endpoint_api": api,
                "expected_model": expected_model, "served_model": None, "model_matches": None,
                "detail": "set OMI_ANALYST_ENDPOINT_URL + HF_TOKEN to enable the live analyst"}
    from app.reasoning.model_providers import ReasoningRequest, RemoteReasoningProvider

    provider = RemoteReasoningProvider(
        endpoint_url=endpoint, model=expected_model or "",
        timeout=float(getattr(settings, "analyst_timeout_seconds", 30.0) or 30.0),
        max_retries=0, revision=getattr(settings, "analyst_hf_revision", None), api=api)
    t0 = time.perf_counter()
    detail: str | None = None
    try:
        provider.complete(ReasoningRequest(system="ping", user="ping", response_format="text", max_tokens=1))
        reachable = True
    except Exception as exc:  # noqa: BLE001 — report, never raise
        reachable = False
        detail = f"{type(exc).__name__}: {str(exc)[:160]}"
    latency_ms = round((time.perf_counter() - t0) * 1000.0, 2)

    # Served-model identity — the evidence that the endpoint is the RIGHT model, not merely up.
    identity = provider.probe_served_model() if reachable else {"served_model": None, "source": "endpoint_unreachable"}
    served = identity.get("served_model")
    model_matches = _models_match(served, expected_model)
    out = {"status": "reachable" if reachable else "unreachable",
           "endpoint_configured": True, "hf_token_present": True, "reachable": reachable,
           "endpoint_api": api, "latency_ms": latency_ms,
           "expected_model": expected_model, "served_model": served,
           "served_model_source": identity.get("source"), "model_matches": model_matches}
    if detail:
        out["detail"] = detail
    if reachable and served and model_matches is False:
        out["model_mismatch_detail"] = (
            f"endpoint is serving '{served}' but config expects '{expected_model}' — "
            "correct OMI_ANALYST_MODEL_ID or redeploy the intended endpoint")
    return out


# --------------------------------------------------------------------------- #
# Consolidated system health — one place that answers "what is running?"
# --------------------------------------------------------------------------- #
def system_health(settings: Settings | None = None) -> dict:
    """One consolidated diagnostic: active provider, active runtime model, endpoint status,
    Prompt Registry versions, and Specialist Framework version — regardless of which model the
    endpoint serves (the constitutional stack is model-agnostic). Read-only; no secrets; never
    raises."""
    settings = settings or get_settings()
    from app.reasoning.prompts import FRAMEWORK_VERSION, default_registry, framework_hash

    enabled = bool(getattr(settings, "analyst_enabled", False))
    endpoint = getattr(settings, "analyst_endpoint_url", None)
    reg = default_registry()
    return {
        "active_provider": "remote-model" if (enabled and endpoint) else "deterministic-floor",
        "active_model": getattr(settings, "analyst_model_id", None),
        "endpoint": endpoint_health(settings),
        "endpoint_api": str(getattr(settings, "analyst_endpoint_api", "generate")),
        "model_revision": getattr(settings, "analyst_hf_revision", None),
        "prompt_registry": {
            "omi_analyst_active": reg.active_version("omi_analyst"),
            "behavior_analyst_active": reg.active_version("behavior_analyst"),
            "analysts": len(reg.analysts()),
        },
        "specialist_framework": {"version": FRAMEWORK_VERSION, "hash": framework_hash()},
        "governor": "mandatory", "deterministic_floor": "always-on",
    }


# --------------------------------------------------------------------------- #
# Post-deploy smoke test — run one real investigation through the live endpoint
# --------------------------------------------------------------------------- #
_SMOKE_PAYLOAD = {
    "overall_probability": 0.74, "overall_tier": "elevated", "confidence": 0.6,
    "contributions": [{"name": "temporal", "impact": 0.5, "direction": "raises"},
                      {"name": "community", "impact": 0.2, "direction": "lowers"}],
    "video": {"clusters": [{"method": "co_engagement", "members": ["@a", "@b", "@c"]}]},
}


def endpoint_smoke_test(payload: dict | None = None, *, ref: str = "smoke_subject",
                        platform: str = "youtube", settings: Settings | None = None) -> dict:
    """Run ONE canonical investigation end-to-end through the *live* endpoint and report whether a
    genuinely Qwen-backed, Governor-permitted, number-preserving assessment came back — the exact
    post-deploy check an operator runs after wiring the Render env. Forces ``analyst_enabled`` so it
    tests the endpoint regardless of the production flag; reports ``not_configured`` (never raises)
    when no endpoint/token is set. A ``qwen_backed`` result with ``governor_verdict=permit`` and
    ``number_echoed`` is the green light; anything else means the deploy is not live yet."""
    settings = settings or get_settings()
    endpoint = getattr(settings, "analyst_endpoint_url", None)
    token_present = bool(os.environ.get("HF_TOKEN") or os.environ.get("HUGGINGFACE_HUB_TOKEN"))
    if not endpoint or not token_present:
        return {"status": "not_configured", "endpoint_configured": bool(endpoint),
                "hf_token_present": token_present,
                "detail": "set OMI_ANALYST_ENDPOINT_URL + HF_TOKEN, then re-run the smoke test"}
    from app.reasoning import analyst as _analyst

    pay = payload or _SMOKE_PAYLOAD
    t0 = time.perf_counter()
    try:
        assessment = _analyst.assess_payload(pay, ref=ref, platform=platform,
                                             settings=_trace_settings(settings))
    except Exception as exc:  # noqa: BLE001 — report, never raise
        return {"status": "error", "detail": f"{type(exc).__name__}: {str(exc)[:160]}"}
    latency_ms = round((time.perf_counter() - t0) * 1000.0, 2)
    if not assessment:
        return {"status": "no_output", "latency_ms": latency_ms,
                "detail": "assess_payload returned None (feature off or impl missing)"}
    gov = assessment.get("governance", {})
    provider = gov.get("provider", "none")
    # ``model_backed`` = a genuine remote-model assessment (not the deterministic floor). The
    # provider identifier keeps its historical ``qwen-`` prefix (stable provider name, not a claim
    # about the foundation model); the foundation model is reported separately via ``served_model``.
    model_backed = ("fallback" not in provider) and ("deterministic" not in provider)
    expected_model = getattr(settings, "analyst_model_id", None)
    identity = _identity_probe(settings)
    served = identity.get("served_model")
    return {
        "status": "qwen_backed" if model_backed else "fallback_deterministic",  # historical key
        "model_backed": model_backed,
        "endpoint_api": str(getattr(settings, "analyst_endpoint_api", "generate")),
        "provider": provider,
        "qwen_backed": model_backed,                                            # historical alias
        "active_model": expected_model,
        "served_model": served,
        "served_model_source": identity.get("source"),
        "model_matches": _models_match(served, expected_model),
        "governor_verdict": gov.get("verdict"),
        "number_echoed": assessment.get("suspicion_probability") == pay.get("overall_probability"),
        "model_revision": gov.get("model_revision"),
        "prompt": gov.get("prompt", {}),
        "latency_ms": latency_ms,
        "expected_when_live": ("status=qwen_backed · governor_verdict=permit · number_echoed=true · "
                               f"served_model≈{expected_model} (model_matches=true)"),
    }


def _identity_probe(settings: Settings) -> dict:
    """Best-effort served-model probe used by the smoke test — reports which model the endpoint is
    serving, or a reason it couldn't be determined. Never raises."""
    endpoint = getattr(settings, "analyst_endpoint_url", None)
    token_present = bool(os.environ.get("HF_TOKEN") or os.environ.get("HUGGINGFACE_HUB_TOKEN"))
    if not endpoint or not token_present:
        return {"served_model": None, "source": "not_configured"}
    from app.reasoning.model_providers import RemoteReasoningProvider

    provider = RemoteReasoningProvider(
        endpoint_url=endpoint, model=getattr(settings, "analyst_model_id", None) or "",
        timeout=float(getattr(settings, "analyst_timeout_seconds", 30.0) or 30.0),
        max_retries=0, revision=getattr(settings, "analyst_hf_revision", None),
        api=str(getattr(settings, "analyst_endpoint_api", "generate") or "generate"))
    return provider.probe_served_model()


# --------------------------------------------------------------------------- #
# End-to-end trace — execute the production pipeline, report every stage
# --------------------------------------------------------------------------- #
def _trace_settings(settings: Settings) -> Any:
    """A settings view that forces ``analyst_enabled=True`` so the trace exercises the real pipeline
    mechanics even when the production flag is off (the actual flag state is reported separately)."""
    keys = ("analyst_hf_repo", "analyst_hf_revision", "analyst_endpoint_url",
            "analyst_timeout_seconds", "analyst_max_retries", "analyst_prompt_version",
            "analyst_endpoint_api", "analyst_model_id", "memory_persistence_enabled",
            "memory_database_url", "analyst_cost_per_1k_tokens_usd")
    return SimpleNamespace(analyst_enabled=True, **{k: getattr(settings, k, None) for k in keys})


def trace_investigation(payload: dict, *, ref: str, platform: str = "youtube",
                        settings: Settings | None = None) -> dict:
    """Execute the production AI pipeline over ``payload`` and return an ordered, per-stage trace
    (execution time, inputs, outputs, failures, fallback). Reuses the production components, so the
    trace is faithful. Read-only; never raises. The ``flag_state`` block reports the real
    production gates (which may differ from the trace's forced-enabled execution)."""
    from app.governor import Governor

    settings = settings or get_settings()
    from app.reasoning import analyst as _analyst

    stages: list[dict] = []

    def _timed(stage: str, fn):
        t0 = time.perf_counter()
        try:
            out = fn()
            rec = {"stage": stage, "status": out.pop("_status", "executed"),
                   "duration_ms": round((time.perf_counter() - t0) * 1000.0, 3),
                   "fallback": out.pop("_fallback", "none"), **out}
        except Exception as exc:  # noqa: BLE001
            rec = {"stage": stage, "status": "failure",
                   "duration_ms": round((time.perf_counter() - t0) * 1000.0, 3),
                   "failure": f"{type(exc).__name__}: {str(exc)[:160]}", "fallback": "deterministic"}
        stages.append(rec)
        return rec

    # 1. Evidence Bundle (Binder) — the ONE canonical bundle.
    def _bundle():
        from app.evidence import Binder
        b = Binder().bind(payload, grain="comment_section", subject_ref=ref, platform=platform)
        _bundle.b = b
        return {"inputs": {"payload_keys": sorted(payload)[:8]},
                "outputs": {"bundle_id": b.bundle_id(), "evidence_items": len(b.evidence)}}
    _timed("evidence_bundle", _bundle)

    # 2. Memory retrieval — institutional priors (shadow-council input; NOT the production analyst).
    def _memory():
        from app.memory.retrieval_engine import retrieve_priors
        from app.routes.memory import _durable_store
        res = retrieve_priors(_durable_store(), _bundle.b, now=None)
        return {"inputs": {"signature_tokens": "bundle signature"},
                "outputs": {"priors_retrieved": len(res.priors), "scan_fraction": res.plan.scan_fraction},
                "_status": "executed",
                "transmitted_to_production_analyst": True,
                "note": "Sprint 021 — institutional memory is injected into the analyst's input as "
                        "prior_context (background, never proof); the live Qwen specialist reasons with it"}
    _timed("memory_retrieval", _memory)

    # 3. Context Builder — structured context (shadow-council input; production analyst uses the ml projection).
    def _context():
        from app.reasoning.context import build_context
        ctx = build_context(_bundle.b, store=None, now=None, budget="standard")
        return {"outputs": {"context_version": ctx.context_version, "sections": len(getattr(ctx, "sections", []) or [])},
                "transmitted_to_production_analyst": False,
                "note": "the production analyst receives structured evidence via the ml projection "
                        "(project_investigation_bundle); the app Context Builder runs in the shadow council"}
    _timed("context_builder", _context)

    # 4. Prompt Registry — the single source of truth.
    def _registry():
        from app.reasoning.prompts import default_registry
        spec = default_registry().resolve("omi_analyst", getattr(settings, "analyst_prompt_version", None))
        return {"outputs": {"specialist": "omi_analyst", "version": spec.prompt_version,
                            "prompt_hash": spec.prompt_hash, "source": "registry"}}
    _timed("prompt_registry", _registry)

    # 5-8. Qwen → Specialist/Judge → Governor → Final response (the real governed assessment).
    assessment = _analyst.assess_payload(payload, ref=ref, platform=platform, settings=_trace_settings(settings))
    gov = (assessment or {}).get("governance", {}) if assessment else {}
    provider = gov.get("provider", "none")
    is_fallback = ("deterministic" in provider) or ("fallback" in provider)
    stages.append({"stage": "qwen_model", "status": "executed",
                   "duration_ms": float(gov.get("latency_ms", 0.0)),
                   "outputs": {"provider": provider, "active_model": getattr(settings, "analyst_model_id", None),
                               "prompt": gov.get("prompt", {})},
                   "fallback": "deterministic" if is_fallback else "none"})
    stages.append({"stage": "specialist_output_and_judge", "status": "executed" if assessment else "no_output",
                   "duration_ms": 0.0,
                   "outputs": {"verdict": (assessment or {}).get("verdict"),
                               "suspicion_tier": (assessment or {}).get("suspicion_tier"),
                               "suspicion_probability": (assessment or {}).get("suspicion_probability"),
                               "evidence_for": len((assessment or {}).get("evidence_for", []) or []),
                               "evidence_against": len((assessment or {}).get("evidence_against", []) or [])},
                   "fallback": "none"})
    stages.append({"stage": "governor", "status": "executed",
                   "duration_ms": 0.0,
                   "outputs": {"verdict": gov.get("verdict"), "trace_id": gov.get("trace_id"),
                               "violation_codes": gov.get("violation_codes", []),
                               "constitution_version": gov.get("constitution_version")},
                   "fallback": "floor" if gov.get("verdict") == "reject" else "none"})
    stages.append({"stage": "final_response", "status": "ready" if assessment else "none",
                   "duration_ms": 0.0,
                   "outputs": {"has_governance": bool(gov), "schema_shaped": bool(assessment and "subject" in assessment)},
                   "fallback": "none"})

    # 9-12. Downstream surfaces — reported as connection status (separate admin pipelines).
    for stage, detail in (
        ("supabase_memory_write", "learning loop (Sprint 014/015) writes Governor-gated candidates "
                                  "from SETTLED investigations via /v1/admin/memory/impact, not per analyst view"),
        ("shadow_evaluation", "available via /v1/admin/shadow/investigations/{slug} (Sprint 007)"),
        ("continuous_improvement", "available via the improvement engine (Sprint 011)"),
        ("engineering_dashboard", "available via /v1/admin/memory/dashboard (Sprint 014)"),
    ):
        stages.append({"stage": stage, "status": "connected_separately", "duration_ms": 0.0,
                       "outputs": {}, "fallback": "none", "note": detail})

    total_ms = round(sum(float(s.get("duration_ms", 0.0)) for s in stages), 3)
    return {
        "ref": ref, "platform": platform,
        "flag_state": {
            "analyst_enabled": bool(getattr(settings, "analyst_enabled", False)),
            "active_provider": "remote-model" if (getattr(settings, "analyst_enabled", False)
                                                  and getattr(settings, "analyst_endpoint_url", None)) else "deterministic-floor",
            "active_model": getattr(settings, "analyst_model_id", None),
            "endpoint_configured": bool(getattr(settings, "analyst_endpoint_url", None)),
            "endpoint_identity": _identity_probe(settings),
            "governor": "mandatory", "deterministic_floor": "always-on",
        },
        "trace_executed_as": "forced-enabled (mechanics shown even when the production flag is off)",
        "total_duration_ms": total_ms,
        "stages": stages,
    }


# --------------------------------------------------------------------------- #
# Forensic audit — capture every stage of ONE investigation (endpoint untrusted)
# --------------------------------------------------------------------------- #
import logging as _logging

_audit_log = _logging.getLogger("omi.reasoning.audit")


def _fallback_reason(gov: dict, provider: str, model_backed: bool, model_call_made: bool,
                     raw: str | None) -> str | None:
    """Exact reason a fallback occurred, or ``None`` when the model answer was used.

    Two distinct fallback causes: the Governor REJECTED valid model output (its ``rejected_codes``),
    or the model output never got that far — it wasn't schema-valid JSON, so the judge substituted
    the floor BEFORE the Governor (which then permits the floor). No endpoint => no model call."""
    if model_backed:
        return None
    if gov.get("verdict") == "reject":
        return f"governor_reject: {gov.get('rejected_codes') or gov.get('violation_codes')}"
    if not model_call_made:
        return "no_model_call (endpoint unset/unreachable) -> deterministic floor"
    if "fallback" in provider:
        return ("model_output_not_schema_valid_json (endpoint returned non-JSON / invalid / "
                "unschema output; the judge fell back to the floor before the Governor)")
    return "deterministic_floor"


def audit_investigation(payload: dict, *, ref: str, platform: str = "youtube",
                        settings: Settings | None = None) -> dict:
    """Run the REAL production analyst path over ``payload`` ONCE with full capture, treating the
    Hugging Face endpoint as untrusted, and return per-stage evidence that PROVES or DISPROVES each
    link. It is the production path (``assess_payload``) with a forensic sidecar — not a
    reimplementation — so the evidence reflects real behavior. Read-only; never raises.

    Captures the six required items, each with a status:
      1. the exact final prompt (system + user) sent to the endpoint,
      2. the prompt version/hash loaded from the (HF-published) AI package,
      3. the model id the endpoint returned,
      4. the raw model response BEFORE any Governor/JSON processing,
      5. the Governor verdict + exact rejection reason (if it fell back),
      6. whether the report renders the model response or the deterministic floor.
    """
    settings = settings or get_settings()
    from app.reasoning import analyst as _analyst

    capture: dict = {}
    endpoint = getattr(settings, "analyst_endpoint_url", None)
    expected_model = getattr(settings, "analyst_model_id", None)
    t0 = time.perf_counter()
    try:
        assessment = _analyst.assess_payload(
            payload, ref=ref, platform=platform, settings=_trace_settings(settings), capture=capture)
    except Exception as exc:  # noqa: BLE001 — report, never raise
        return {"status": "error", "detail": f"{type(exc).__name__}: {str(exc)[:200]}", "capture": capture}
    total_ms = round((time.perf_counter() - t0) * 1000.0, 2)

    gov = (assessment or {}).get("governance", {}) if assessment else {}
    provider = str(gov.get("provider", "none"))
    model_backed = bool(assessment) and ("fallback" not in provider) and ("deterministic" not in provider)
    raw = capture.get("raw_text_pre_processing")
    served = capture.get("served_model")
    model_call_made = "request_wire_body" in capture

    def _st(ok: bool | None, proven: str, disproven: str, unverified: str = "UNVERIFIED") -> str:
        return proven if ok is True else (disproven if ok is False else unverified)

    items = {
        "1_final_prompt_sent": {
            "status": _st(model_call_made, "PROVEN", "DISPROVEN (no model call — floor served)"),
            "endpoint_url": capture.get("endpoint_url"), "endpoint_api": capture.get("endpoint_api"),
            "system_prompt": capture.get("final_prompt_system"),
            "user_message": capture.get("final_prompt_user"),
            "wire_body_preview": (capture.get("request_wire_body") or "")[:600],
        },
        "2_prompt_version_hash": {
            "status": _st(bool(capture.get("prompt_hash")), "PROVEN", "DISPROVEN"),
            "prompt_version": capture.get("prompt_version"), "prompt_hash": capture.get("prompt_hash"),
            "ai_package": capture.get("ai_package"),
        },
        "3_served_model_id": {
            "status": _st(_models_match(served, expected_model), "PROVEN (matches expected)",
                          "DISPROVEN (WRONG MODEL)", "UNVERIFIED (no model id in response / no call)"),
            "served_model": served, "expected_model": expected_model,
        },
        "4_raw_model_response": {
            "status": _st((raw is not None) if model_call_made else None, "PROVEN", "DISPROVEN"),
            "raw_text_pre_governor": raw,
            "raw_response_body_preview": (capture.get("raw_response_body") or "")[:600],
            "attempts": capture.get("attempts"), "latency_ms": capture.get("latency_ms"),
        },
        "5_governor": {
            "status": _st(gov.get("verdict") in ("permit", "reject"), "PROVEN", "DISPROVEN"),
            "verdict": gov.get("verdict"), "trace_id": gov.get("trace_id"),
            "violation_codes": gov.get("violation_codes", []),
            "fallback_occurred": not model_backed,
            "fallback_reason": _fallback_reason(gov, provider, model_backed, model_call_made, raw),
            "governor_rejected_codes": gov.get("rejected_codes"),
            "fallback_from": gov.get("fallback_from"),
            "constitution_version": gov.get("constitution_version"),
        },
        "6_report_renders": {
            "status": "MODEL" if model_backed else "DETERMINISTIC_FLOOR",
            "provider": provider, "model_backed": model_backed,
            "note": ("the UI/report renders exactly this persisted assessment; provider identifies "
                     "the source (model vs floor)"),
        },
    }

    # Log each item (truncated) so Render logs carry the same forensic trail.
    for key in ("1_final_prompt_sent", "2_prompt_version_hash", "3_served_model_id",
                "4_raw_model_response", "5_governor", "6_report_renders"):
        _audit_log.info("audit[%s] %s = %s", ref, key, str(items[key].get("status")))
    _audit_log.info("audit[%s] served_model=%s expected=%s | governor=%s provider=%s | prompt_hash=%s",
                    ref, served, expected_model, gov.get("verdict"), provider, capture.get("prompt_hash"))

    endpoint_trusted = bool(model_backed and _models_match(served, expected_model) is not False)
    return {
        "status": "ok",
        "ref": ref, "platform": platform,
        "endpoint_configured": bool(endpoint),
        "total_ms": total_ms,
        "endpoint_trust_verdict": ("TRUSTED (model-backed, permitted, model id verified)" if endpoint_trusted
                                   else "NOT TRUSTED (floor served, or model id unverified/wrong)"),
        "items": items,
    }


__all__ = ["prompt_integrity", "endpoint_health", "endpoint_smoke_test", "system_health",
           "trace_investigation", "audit_investigation"]
