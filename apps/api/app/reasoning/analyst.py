"""Omi Analyst — production wiring into app/reasoning (OMI_ANALYST_PRODUCTION_WIRING_V1).

Connects the completed Omi Analyst implementation (``ml/analyst/omi_analyst``) into the
backend as an OPTIONAL, feature-flagged, async, cached reasoning capability. Strictly
additive — exactly like the Phase-7 LLM layer, the Analyst:

  * is OFF by default (``settings.analyst_enabled = False``),
  * never makes a detection decision, never recomputes a score, never runs in the scan
    hot path, and is never required for the product to work,
  * does NOT touch detectors, scoring, OmiScore, or the existing commentary path.

The completed implementation lives in the decoupled ``ml/`` tree and is **lazily
imported only when the feature is enabled**, so the default (off) path imports nothing
from ``ml/`` and cannot affect production or the test suite. Any failure (feature off,
``ml/`` absent, model unreachable, invalid output) degrades to ``None`` — the caller
simply has no assessment, never an error in the request path.
"""
from __future__ import annotations

import hashlib
import logging
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.core.config import Settings, get_settings

logger = logging.getLogger("omi.reasoning.analyst")

# Where the cached structured assessment lives inside Investigation.payload_json.
CACHE_KEY = "analyst_assessment_v1"
# Repo root: apps/api/app/reasoning/analyst.py -> parents[4] == repo root.
_REPO_ROOT = Path(__file__).resolve().parents[4]
_ML_ANALYST_PATH = str(_REPO_ROOT / "ml" / "analyst")
_impl_cache: Any | None = None
_impl_failed = False


def analyst_enabled(settings: Settings | None = None) -> bool:
    settings = settings or get_settings()
    return bool(getattr(settings, "analyst_enabled", False))


def _impl():
    """Lazily import the completed ``omi_analyst`` package. Cached; never raises."""
    global _impl_cache, _impl_failed
    if _impl_cache is not None:
        return _impl_cache
    if _impl_failed:
        return None
    try:
        if _ML_ANALYST_PATH not in sys.path:
            sys.path.append(_ML_ANALYST_PATH)  # append: never shadow app modules
        import omi_analyst  # type: ignore

        _impl_cache = omi_analyst
        return _impl_cache
    except Exception:  # noqa: BLE001 — ml/ absent or import error → feature unavailable
        logger.warning("omi_analyst implementation not importable; analyst disabled", exc_info=True)
        _impl_failed = True
        return None


def available(settings: Settings | None = None) -> bool:
    """True only when the flag is on AND the implementation imported."""
    return analyst_enabled(settings) and _impl() is not None


# --------------------------------------------------------------------------- #
# Projection: Investigation payload -> Evidence Bundle (comment_section grain)
# --------------------------------------------------------------------------- #
def _ref(value: str) -> str:
    """Pseudonymous, stable reference — the analyst never sees a raw handle/PII."""
    return "sub_" + hashlib.sha256((value or "").encode("utf-8")).hexdigest()[:12]


def _coordination_from_payload(payload: dict) -> dict:
    clusters_in = ((payload.get("video") or {}).get("clusters")) or payload.get("clusters") or []
    methods: list[str] = []
    clusters: list[dict] = []
    for cl in clusters_in:
        m = cl.get("method")
        if m and m not in methods:
            methods.append(m)
        members = cl.get("members")
        clusters.append({"method": m, "members": len(members) if isinstance(members, list) else members})
    return {
        "methods": methods,
        "clusters": clusters,
        "coordination_score": payload.get("coordination_score"),
        "single_axis_capped": bool(payload.get("single_axis_capped", False)),
    }


def _components_from_payload(payload: dict, impl) -> list[dict]:
    """Fold the top flagged commenters into compact component descriptors (no
    per-commenter model call) so the investigation summary can synthesize across them."""
    commenters = ((payload.get("video") or {}).get("commenters")) or []
    flagged = [c for c in commenters if c.get("tier") in ("moderate", "elevated", "high")]
    flagged.sort(key=lambda c: -(c.get("overall_probability") or 0))
    out = []
    for c in flagged[:5]:
        tier = c.get("tier")
        verdict = "likely_inauthentic" if tier in ("elevated", "high") else "mixed"
        out.append({
            "grain": "commenter", "ref": _ref(c.get("handle") or "?"),
            "verdict": verdict, "suspicion_tier": tier,
            "suspicion_probability": c.get("overall_probability") or 0.0,
            "headline": (c.get("summary") or c.get("intent_label") or "")[:160],
        })
    return out


def build_bundle(payload: dict, *, ref: str, platform: str, impl) -> dict:
    scan = {
        "overall_probability": payload.get("overall_probability") or 0.0,
        "tier": payload.get("overall_tier") or payload.get("tier") or "low",
        "confidence": payload.get("confidence") or 0.0,
        "summary": payload.get("summary") or "",
        "weak_signals": payload.get("weak_signals") or [],
        "contributions": payload.get("contributions") or [],
        "coordination": _coordination_from_payload(payload),
    }
    return impl.evidence_bundle.project_investigation_bundle(
        ref=ref, platform=platform, scan=scan,
        components=_components_from_payload(payload, impl),
        cross_links=payload.get("cross_links") or [],
    )


# --------------------------------------------------------------------------- #
# Assessment (sync core) — off the hot path; safe to run in a worker thread
# --------------------------------------------------------------------------- #
def assess_payload(
    payload: dict, *, ref: str, platform: str = "youtube", settings: Settings | None = None,
) -> dict | None:
    """Produce a Governor-validated structured assessment for an investigation payload,
    or None if the feature is off / unavailable / errored. Never raises.

    The Constitutional Governor (Sprint 002) is **mandatory** on this path: the provider's
    assessment is validated against a freshly-bound canonical Evidence Bundle; on REJECT it
    falls back to the always-valid deterministic Floor (itself Governor-validated). A
    ``governance`` block (verdict, trace id, provider, model revision, latency) is attached
    for transparency. The Governor is never skipped and the Floor is never bypassed.
    """
    settings = settings or get_settings()
    if not analyst_enabled(settings):
        return None
    impl = _impl()
    if impl is None:
        return None
    try:
        config = impl.load_analyst_config(
            repo_id=settings.analyst_hf_repo, revision=settings.analyst_hf_revision,
        )
        # Sprint 016: the app Prompt Registry is the single runtime source of truth for the
        # analyst's system prompt (no longer the embedded ml/ doc). Resolve the active (or pinned)
        # version and inject it into the Qwen provider; the version + content hash are recorded in
        # the governance block so every AI assessment is attributable to a content-addressed prompt.
        from app.reasoning.prompts import default_registry
        spec = default_registry().resolve("omi_analyst", getattr(settings, "analyst_prompt_version", None))

        endpoint = getattr(settings, "analyst_endpoint_url", None)
        timeout = float(getattr(settings, "analyst_timeout_seconds", 30.0) or 30.0)
        if endpoint:
            provider = impl.QwenAnalystProvider(
                endpoint_url=endpoint, timeout=timeout, system_prompt=spec.template,
            )
        else:
            provider = impl.DeterministicAnalystProvider()
        analyst_obj = impl.OmiAnalyst(config=config, provider=provider, store=None, record=False)
        lossy_bundle = build_bundle(payload, ref=ref, platform=platform, impl=impl)

        t0 = time.perf_counter()
        outcome = analyst_obj.assess(lossy_bundle)
        latency_ms = (time.perf_counter() - t0) * 1000.0
        if not outcome.valid:
            logger.warning("omi_analyst produced invalid output: %s", outcome.errors[:3])
            return None

        return _govern(
            outcome.response, payload, ref=ref, platform=platform,
            provider=outcome.provider, latency_ms=latency_ms,
            model_revision=getattr(config, "model_revision", None),
            impl=impl, config=config, lossy_bundle=lossy_bundle,
            prompt_meta={"analyst": "omi_analyst", "version": spec.prompt_version,
                         "hash": spec.prompt_hash, "source": "registry"},
        )
    except Exception:  # noqa: BLE001 — never let the analyst break a caller
        logger.exception("omi_analyst assessment failed")
        return None


def _govern(
    assessment: dict, payload: dict, *, ref: str, platform: str, provider: str,
    latency_ms: float, model_revision: str | None, impl: Any, config: Any, lossy_bundle: dict,
    prompt_meta: dict | None = None,
) -> dict:
    """Mandatory Constitutional Governor gate (deterministic, model-free).

    Validates the assessment against a canonical Evidence Bundle (``app.evidence.Binder``)
    using ``app.governor.Governor``. PERMIT -> attach a ``governance`` block + return.
    REJECT -> ship the deterministic Floor (regenerated + Governor-validated), recording
    the rejected codes. Any error -> the deterministic Floor is the safest output. Never
    raises — governance must never break the caller."""
    from app.evidence import Binder
    from app.governor import Governor

    def _meta(trace: Any, prov: str, **extra: Any) -> dict:
        m = {
            "verdict": trace.verdict,
            "trace_id": trace.trace_id(),
            "violation_codes": trace.violation_codes,
            "provider": prov,
            "model_revision": model_revision,
            "prompt": prompt_meta or {},
            "latency_ms": round(float(latency_ms), 2),
            "constitution_version": Governor.constitution_version,
        }
        m.update(extra)
        return m

    governor = Governor()
    try:
        bundle = Binder().bind(payload, grain="comment_section", subject_ref=ref, platform=platform)
        trace = governor.validate(assessment, bundle, corroboration=assessment.get("corroboration"))
        if trace.permitted:
            assessment["governance"] = _meta(trace, provider)
            logger.info("analyst governed: PERMIT provider=%s latency=%.1fms", provider, latency_ms)
            return assessment

        logger.warning("analyst REJECTED by governor %s; falling back to Floor", trace.violation_codes)
        floor = impl.DeterministicAnalystProvider().generate(lossy_bundle, config).response
        ftrace = governor.validate(floor, bundle, corroboration=floor.get("corroboration"))
        floor["governance"] = _meta(
            ftrace, "deterministic-floor",
            fallback_from=provider, rejected_codes=trace.violation_codes,
        )
        return floor
    except Exception:  # noqa: BLE001 — governance must never break the caller
        logger.exception("governor gate errored; returning the deterministic Floor")
        try:
            floor = impl.DeterministicAnalystProvider().generate(lossy_bundle, config).response
            floor["governance"] = {
                "verdict": "error", "provider": "deterministic-floor",
                "model_revision": model_revision, "fallback_from": provider,
            }
            return floor
        except Exception:  # noqa: BLE001
            assessment["governance"] = {"verdict": "error", "provider": provider}
            return assessment


def runtime_status(settings: Settings | None = None) -> dict:
    """Diagnostic snapshot of the AI runtime path — which links are configured / ready.

    No secrets: ``HF_TOKEN`` presence is a boolean, never the value. Only imports the
    ``ml/`` impl when the feature is enabled (the off path stays import-free)."""
    settings = settings or get_settings()
    enabled = analyst_enabled(settings)
    endpoint = getattr(settings, "analyst_endpoint_url", None)
    token_present = bool(os.environ.get("HF_TOKEN") or os.environ.get("HUGGINGFACE_HUB_TOKEN"))
    impl_ok: bool | None = (_impl() is not None) if enabled else None
    provider = "qwen" if (enabled and endpoint) else "deterministic-floor"
    return {
        "enabled": enabled,
        "impl_importable": impl_ok,
        "endpoint_configured": bool(endpoint),
        "hf_token_present": token_present,
        "model_repo": getattr(settings, "analyst_hf_repo", None),
        "model_revision": getattr(settings, "analyst_hf_revision", None),
        "timeout_seconds": float(getattr(settings, "analyst_timeout_seconds", 30.0) or 30.0),
        "provider": provider,
        "governor": "mandatory",
        "deterministic_floor": "always-on",
        "ready_for_live_qwen": bool(enabled and endpoint and token_present and impl_ok is True),
    }


def runtime_path(settings: Settings | None = None) -> dict:
    """The full AI runtime **dependency graph** (Sprint 016): every link from the website to Qwen
    and back, each marked ``verified`` / ``operator_action`` / ``blocked``, so *what prevents live
    Qwen reasoning* is one verifiable answer instead of a guess. Read-only; no secrets (token
    presence is a boolean); never raises. Ordered to mirror the runtime path."""
    settings = settings or get_settings()
    enabled = analyst_enabled(settings)
    endpoint = getattr(settings, "analyst_endpoint_url", None)
    token_present = bool(os.environ.get("HF_TOKEN") or os.environ.get("HUGGINGFACE_HUB_TOKEN"))
    impl_ok: bool | None = (_impl() is not None) if enabled else None

    def node(step: str, ok: bool, detail: str, *, operator: bool = False) -> dict:
        return {"step": step, "status": "verified" if ok else ("operator_action" if operator else "blocked"),
                "detail": detail}

    # The Prompt Registry is the single source of truth — verified independently of the feature flag.
    try:
        from app.reasoning.prompts import default_registry
        spec = default_registry().resolve("omi_analyst", getattr(settings, "analyst_prompt_version", None))
        prompt_node = node("prompt_registry", True, f"omi_analyst {spec.prompt_version} ({spec.prompt_hash})")
    except Exception as exc:  # noqa: BLE001 — a registry failure is a real (code) blocker
        prompt_node = node("prompt_registry", False, f"resolve failed: {str(exc)[:100]}")

    try:
        from app.governor import Governor
        gov_detail = f"mandatory (constitution {Governor.constitution_version})"
    except Exception:  # noqa: BLE001
        gov_detail = "mandatory"

    nodes = [
        node("feature_flag", enabled, f"analyst_enabled={enabled}", operator=not enabled),
        node("analyst_impl", impl_ok is True,
             "ml/analyst importable" if impl_ok else ("import failed" if enabled else "not checked (flag off)"),
             operator=(impl_ok is None)),
        node("evidence_bundle", True, "app.evidence.Binder available"),
        prompt_node,
        node("hf_endpoint", bool(endpoint), "configured" if endpoint else "analyst_endpoint_url unset",
             operator=not endpoint),
        node("hf_token", token_present,
             "present" if token_present else "HF_TOKEN / HUGGINGFACE_HUB_TOKEN unset", operator=not token_present),
        node("model", True,
             f"{getattr(settings, 'analyst_hf_repo', None)}@{getattr(settings, 'analyst_hf_revision', None) or 'main'}"),
        node("governor", True, gov_detail),
        node("deterministic_floor", True, "always-on fallback"),
    ]
    ready = bool(enabled and endpoint and token_present and impl_ok is True and prompt_node["status"] == "verified")
    return {
        "ready_for_live_qwen": ready,
        "active_provider": "qwen" if (enabled and endpoint) else "deterministic-floor",
        "nodes": nodes,
        "blockers": [n["step"] for n in nodes if n["status"] != "verified"],
        "governor": "mandatory",
        "deterministic_floor": "always-on",
    }


# --------------------------------------------------------------------------- #
# Caching on the Investigation row (SAVEPOINT-isolated best-effort write)
# --------------------------------------------------------------------------- #
def cached_assessment(inv) -> dict | None:
    payload = inv.payload_json or {}
    entry = payload.get(CACHE_KEY)
    if isinstance(entry, dict) and entry.get("assessment"):
        return entry
    return None


def persist_assessment(session, inv, assessment: dict, provider: str) -> dict:
    """Cache the assessment inside payload_json. SAVEPOINT-isolated so a write hiccup
    can never corrupt the surrounding transaction (Platform Guardian §4)."""
    entry = {
        "assessment": assessment,
        "provider": provider,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    try:
        with session.begin_nested():
            # Reassign so SQLAlchemy detects the JSON mutation.
            inv.payload_json = {**(inv.payload_json or {}), CACHE_KEY: entry}
            session.add(inv)
    except Exception:  # noqa: BLE001 — caching is best-effort
        logger.exception("failed to persist analyst assessment for inv=%s", getattr(inv, "slug", "?"))
    return entry


def generate_and_persist(slug: str, user_id: int | None, refresh: bool = False) -> dict | None:
    """Background worker: open an own session, generate the assessment, cache it.
    Idempotent. Runs off the request hot path via app.core.background.submit."""
    settings = get_settings()
    if not analyst_enabled(settings):
        return None
    from app.storage.db import get_session
    from app.storage.repository import AccountRepository

    with get_session() as session:
        repo = AccountRepository(session)
        inv = repo.get_investigation(slug=slug, user_id=user_id)
        if inv is None:
            return None
        if not refresh and cached_assessment(inv):
            return cached_assessment(inv)
        assessment = assess_payload(
            inv.payload_json or {},
            ref=_ref(inv.slug), platform=_platform_of(inv), settings=settings,
        )
        if assessment is None:
            return None
        gov = assessment.get("governance") or {}
        provider = gov.get("provider") or assessment.get("model_revision", "omi-analyst")
        return persist_assessment(session, inv, assessment, provider)


def _platform_of(inv) -> str:
    url = (getattr(inv, "input_url", "") or "").lower()
    if "twitter" in url or "x.com" in url:
        return "twitter"
    if "youtube" in url or "youtu.be" in url:
        return "youtube"
    return "unknown"
