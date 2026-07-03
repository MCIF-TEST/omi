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
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.core.config import Settings, get_settings
from app.reasoning.contracts import ReasoningContract, Ruling

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


def _qwen_transport(endpoint: str, *, timeout: float, max_retries: int, revision: str | None,
                    api: str = "generate", model: str | None = None, capture: dict | None = None):
    """The ONE Qwen HTTP transport (Sprint 017). The production analyst's model call goes through
    the constitutional ``RemoteReasoningProvider`` — the same HF client the council uses — instead
    of a second bespoke HTTP implementation. ``api`` selects the raw ``generate`` or OpenAI-
    compatible ``messages`` serving contract; ``model`` names the served model in the request body
    (so a dedicated endpoint's logs attribute the call correctly instead of the generic ``tgi``).
    Returns the raw generated text, or None on any failure so the analyst degrades to its
    deterministic provider. Each call is logged at INFO so Render logs show the outbound model
    request and its outcome."""
    from app.reasoning.model_providers import ReasoningRequest, RemoteReasoningProvider

    provider = RemoteReasoningProvider(
        endpoint_url=endpoint, model=model or "", timeout=timeout, max_retries=max_retries,
        revision=revision, api=api, capture=capture)

    def _call(system: str, user: str, config: Any) -> str | None:
        t0 = time.perf_counter()
        try:
            resp = provider.complete(ReasoningRequest(
                system=system, user=user, response_format="text",
                temperature=getattr(config, "temperature", 0.2),
                max_tokens=getattr(config, "max_new_tokens", 1024), revision=revision,
            ))
            dt = (time.perf_counter() - t0) * 1000.0
            logger.info("analyst.model_call: OK endpoint=%s api=%s model=%s chars=%d latency_ms=%.0f",
                        _redact_endpoint(endpoint), api, model or "tgi", len(resp.text or ""), dt)
            return resp.text
        except Exception as exc:  # noqa: BLE001 — provider failure -> deterministic fallback
            dt = (time.perf_counter() - t0) * 1000.0
            logger.warning("analyst.model_call: FAILED endpoint=%s api=%s model=%s latency_ms=%.0f "
                           "err=%s: %s -> deterministic fallback", _redact_endpoint(endpoint), api,
                           model or "tgi", dt, type(exc).__name__, str(exc)[:160])
            return None

    return _call


def _redact_endpoint(url: str | None) -> str:
    """Host-only view of the endpoint URL for logs (never the full path/query)."""
    if not url:
        return "-"
    try:
        from urllib.parse import urlsplit
        return urlsplit(url).netloc or url[:40]
    except Exception:  # noqa: BLE001
        return url[:40]


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


def build_bundle(payload: dict, *, ref: str, platform: str, impl, prior_context: list | None = None) -> dict:
    scan = {
        "overall_probability": payload.get("overall_probability") or 0.0,
        "tier": payload.get("overall_tier") or payload.get("tier") or "low",
        "confidence": payload.get("confidence") or 0.0,
        "summary": payload.get("summary") or "",
        "weak_signals": payload.get("weak_signals") or [],
        "contributions": payload.get("contributions") or [],
        "coordination": _coordination_from_payload(payload),
    }
    bundle = impl.evidence_bundle.project_investigation_bundle(
        ref=ref, platform=platform, scan=scan,
        components=_components_from_payload(payload, impl),
        cross_links=payload.get("cross_links") or [],
    )
    # Sprint 021 — institutional memory reaches the AI specialist as labeled CONTEXT (never proof).
    # Additive: the deterministic provider ignores this key (so its output is unchanged), while the
    # Qwen provider serializes the whole bundle, so the live model reasons with prior context.
    if prior_context:
        bundle["prior_context"] = prior_context
    return bundle


def _retrieve_prior_context(store: Any, app_bundle: Any, *, now: Any = None, top_k: int = 5) -> list[dict]:
    """Retrieve institutional PriorContext for the analyst's input (Sprint 021). Each prior is
    background context — labeled, never proof, and carries NO resolvable evidence id (so the model
    cannot cite it as evidence; the memory boundary is preserved). Returns ``[]`` when memory is
    empty / unavailable. Never raises."""
    if store is None or app_bundle is None:
        return []
    try:
        from app.memory.graph import retrieve

        priors = retrieve(store, app_bundle, top_k=top_k, now=now)
        return [{
            "type": p.type, "label": p.label,
            "confidence": round(float(p.confidence), 3), "stability": round(float(p.stability_score), 3),
            "epistemic_status": p.epistemic_status, "influence_class": p.influence_class,
            "basis": p.match_basis, "note": "institutional memory — background context, never proof",
        } for p in priors]
    except Exception:  # noqa: BLE001 — memory must never break the analyst
        logger.warning("prior-context retrieval failed; proceeding without memory", exc_info=True)
        return []


# --------------------------------------------------------------------------- #
# Assessment (sync core) — off the hot path; safe to run in a worker thread
# --------------------------------------------------------------------------- #
# --------------------------------------------------------------------------- #
# The analyst as the constitutional council's judge (Sprint 017 — runtime convergence)
# --------------------------------------------------------------------------- #
# Production runs through the ONE Orchestrator — the same constitutional spine the shadow
# council uses. The rich OMI ANALYST is the council's *judge* (its schema-shaped assessment IS
# the Ruling); the deterministic analyst is the council's *floor*. The Orchestrator supplies the
# ONE Binder, the **mandatory** Governor, and the deterministic Floor fallback. There is no
# parallel governance path. OmiScore is never touched.
_JUDGE_CONSTRAINTS = (
    "echo the engine number; never recompute the score",
    "evidence, not verdict; cite only provided evidence",
    "respect the corroboration gate; supplemental signals are context only",
)


class _AnalystJudge:
    """The production OMI ANALYST wrapped as the council judge. ``OmiAnalyst.assess`` already
    degrades a failed/invalid model output to its deterministic provider, so ``run`` yields a
    schema-shaped Ruling; the Orchestrator's Governor + Floor are the outer constitutional gate."""

    contract = ReasoningContract(
        module="omi_analyst", tier=3, output_kind="ruling", contract_version="v1",
        inputs=("*",), constraints=_JUDGE_CONSTRAINTS,
    )

    def __init__(self, *, impl: Any, config: Any, provider: Any, payload: dict,
                 ref: str, platform: str, prompt_meta: dict, store: Any = None, now: Any = None) -> None:
        self._impl, self._config, self._provider = impl, config, provider
        self._payload, self._ref, self._platform = payload, ref, platform
        self._store, self._now = store, now
        self.last_meta: dict[str, Any] = {
            "provider": "none", "latency_ms": 0.0,
            "model_revision": getattr(config, "model_revision", None), "prompt": prompt_meta,
        }

    def run(self, view: Any) -> list:
        prior_context = _retrieve_prior_context(self._store, getattr(view, "bundle", None), now=self._now)
        lossy = build_bundle(self._payload, ref=self._ref, platform=self._platform,
                             impl=self._impl, prior_context=prior_context)
        self.last_meta["prior_context"] = len(prior_context)
        analyst_obj = self._impl.OmiAnalyst(
            config=self._config, provider=self._provider, store=None, record=False)
        t0 = time.perf_counter()
        outcome = analyst_obj.assess(lossy)
        self.last_meta = {**self.last_meta, "provider": outcome.provider,
                          "latency_ms": round((time.perf_counter() - t0) * 1000.0, 2)}
        if not outcome.valid:                          # essentially unreachable (assess self-degrades)
            logger.warning("omi_analyst produced invalid output: %s", outcome.errors[:3])
            return []                                  # no Ruling → caller degrades to None
        return [Ruling(module=self.contract.module, assessment=outcome.response)]


class _AnalystFloor:
    """The deterministic analyst as the council's always-valid Floor judge (rich, schema-shaped)."""

    contract = ReasoningContract(
        module="omi_analyst_floor", tier=3, output_kind="ruling", contract_version="v1",
        inputs=("*",), constraints=("always schema-valid by construction",),
    )

    def __init__(self, *, impl: Any, config: Any, payload: dict, ref: str, platform: str,
                 model_revision: str | None, store: Any = None, now: Any = None) -> None:
        self._impl, self._config = impl, config
        self._payload, self._ref, self._platform = payload, ref, platform
        self._store, self._now = store, now
        self.last_meta = {"provider": "deterministic-floor", "latency_ms": 0.0,
                          "model_revision": model_revision, "prompt": {}}

    def run(self, view: Any) -> list:
        prior_context = _retrieve_prior_context(self._store, getattr(view, "bundle", None), now=self._now)
        lossy = build_bundle(self._payload, ref=self._ref, platform=self._platform,
                             impl=self._impl, prior_context=prior_context)
        result = self._impl.DeterministicAnalystProvider().generate(lossy, self._config)
        return [Ruling(module=self.contract.module, assessment=result.response)]


# --------------------------------------------------------------------------- #
# Runtime measurement — per-investigation metrics + cache effectiveness
# --------------------------------------------------------------------------- #
_cache_stats = {"served_from_cache": 0, "generated": 0}


# Phase B — the origin of every report field: the MODEL reasons over the evidence and generates the
# analytical conclusions; the deterministic engine produces the authoritative measurable signals,
# which the model ECHOES and must never override (echo discipline). This map is the architectural
# contract surfaced in the forensic audit (items 8 & 9).
_MODEL_GENERATED_FIELDS = (
    "verdict", "confidence_band", "confidence_rationale", "headline", "assessment",
    "evidence_for", "evidence_against", "uncertainty", "what_would_change_this",
    "limits_statement", "coordination_label", "legitimate_hypothesis", "supplemental_context",
)
_DETERMINISTIC_ECHOED_FIELDS = ("suspicion_probability", "suspicion_tier")
_SYSTEM_FIELDS = ("governance", "ai_package", "prompt_build", "metrics", "subject",
                  "analyst_version", "prompt_version", "schema_version", "model_revision")


def field_provenance() -> dict:
    """Which report fields originate from the model vs the deterministic engine vs the system.
    Static architectural contract (Phase-B items 8/9): the AI is the analyst (it generates the
    reasoning), the deterministic engine is the evidence source (its measurable numbers are echoed,
    never overridden), and the Governor/package fields are system provenance."""
    return {
        "model_generated": list(_MODEL_GENERATED_FIELDS),
        "deterministic_echoed": list(_DETERMINISTIC_ECHOED_FIELDS),
        "system_provenance": list(_SYSTEM_FIELDS),
        "doctrine": ("the model generates the analytical conclusions FROM the evidence; the engine's "
                     "suspicion_probability/tier are authoritative measurable signals the model echoes "
                     "and never moves (echo discipline); the Governor re-validates every field"),
    }


def runtime_metrics() -> dict:
    """Process-lifetime AI runtime counters (cache effectiveness). Read-only; cheap; never raises."""
    c = dict(_cache_stats)
    total = c["served_from_cache"] + c["generated"]
    return {"assessment_cache": {**c, "total": total,
                                 "hit_rate": round(c["served_from_cache"] / total, 4) if total else 0.0}}


def _assessment_metrics(governed: dict, gov: dict, settings: Settings, *, store_ms: float,
                        reasoning_ms: float, model_backed: bool, prompt_meta: dict) -> dict:
    """Additive per-investigation measurement (never affects the assessment). App-measured latencies
    are precise; token/cost are clearly-labeled completion-side ESTIMATES — authoritative token
    usage is available from the endpoint's ``usage`` field (a Phase-2 capture in the provider)."""
    import json as _json

    model_ms = float(gov.get("latency_ms", 0.0) or 0.0)
    payload_only = {k: v for k, v in governed.items() if k not in ("governance", "metrics")}
    est_completion_tokens = round(len(_json.dumps(payload_only, ensure_ascii=False)) / 4)
    rate = float(getattr(settings, "analyst_cost_per_1k_tokens_usd", 0.0) or 0.0)
    return {
        "total_reasoning_ms": round(reasoning_ms, 2),
        "model_ms": round(model_ms, 2),
        "governor_and_assembly_ms": round(max(0.0, reasoning_ms - model_ms), 2),
        "memory_store_ms": round(store_ms, 2),
        "memory_durable": bool(getattr(settings, "memory_persistence_enabled", False)),
        "model_backed": model_backed,
        "est_completion_tokens": est_completion_tokens,
        "est_completion_cost_usd": round(est_completion_tokens / 1000.0 * rate, 6) if rate else None,
        "token_source": "estimate:chars/4 (authoritative usage is endpoint-side)",
        "prompt_version": prompt_meta.get("version"),
        "prompt_hash": prompt_meta.get("hash"),
    }


def assess_payload(
    payload: dict, *, ref: str, platform: str = "youtube", settings: Settings | None = None,
    capture: dict | None = None,
) -> dict | None:
    """Produce a Governor-validated structured assessment for an investigation payload, or None if
    the feature is off / unavailable / errored. Never raises.

    Sprint 017 — runtime convergence: this executes through the **constitutional council
    Orchestrator** (the same one the shadow council uses), not a parallel reasoning path. The rich
    OMI ANALYST is the council's *judge* and the deterministic analyst is its *floor*; the
    Orchestrator supplies the ONE Binder, the **mandatory** Governor, and the deterministic Floor
    fallback. The prompt comes from the ONE Prompt Registry (Sprint 016). A ``governance`` block
    (verdict, trace id, provider, model revision, prompt, latency) is attached for transparency.
    The Governor is never skipped; the Floor is never bypassed; OmiScore is never touched.
    """
    settings = settings or get_settings()
    if not analyst_enabled(settings):
        return None
    impl = _impl()
    if impl is None:
        return None
    try:
        from app.reasoning.orchestrator import Orchestrator
        from app.reasoning.prompts import default_registry

        config = impl.load_analyst_config(
            repo_id=settings.analyst_hf_repo, revision=settings.analyst_hf_revision,
        )
        spec = default_registry().resolve("omi_analyst", getattr(settings, "analyst_prompt_version", None))
        prompt_meta = {"analyst": "omi_analyst", "version": spec.prompt_version,
                       "hash": spec.prompt_hash, "source": "registry"}
        # The canonical AI deployment package (published to HF; loaded from bundled data) that this
        # investigation reasons with — content-addressed, recorded on every assessment for reproducibility.
        from app.reasoning.package import load_ai_package
        ai_package = load_ai_package(getattr(settings, "analyst_model_id", None))
        # Phase B — the Prompt Builder assembles the analyst SYSTEM prompt from the HF package
        # (base prompt + constitution + knowledge) when analyst_prompt_assembly="package"; the
        # default "registry" returns the validated base prompt unchanged (byte-identical behavior).
        from app.reasoning.prompt_builder import PromptBuilder
        prompt_mode = str(getattr(settings, "analyst_prompt_assembly", "registry") or "registry")
        built = PromptBuilder(ai_package).build_system(base_system=spec.template, mode=prompt_mode)
        system_prompt = built.system
        if capture is not None:
            # Item 2 — the prompt version/hash loaded from the (HF-published) package.
            capture["prompt_version"] = spec.prompt_version
            capture["prompt_hash"] = spec.prompt_hash
            capture["ai_package"] = ai_package.provenance()
            capture["prompt_build"] = built.manifest

        endpoint = getattr(settings, "analyst_endpoint_url", None)
        timeout = float(getattr(settings, "analyst_timeout_seconds", 30.0) or 30.0)
        if endpoint:
            api = str(getattr(settings, "analyst_endpoint_api", "generate") or "generate")
            model_id = getattr(settings, "analyst_model_id", None)
            transport = _qwen_transport(
                endpoint, timeout=timeout,
                max_retries=int(getattr(settings, "analyst_max_retries", 2) or 2),
                revision=getattr(settings, "analyst_hf_revision", None),
                api=api, model=model_id, capture=capture)
            provider = impl.QwenAnalystProvider(
                endpoint_url=endpoint, timeout=timeout, system_prompt=system_prompt, transport=transport)
            logger.info("analyst.assess: REMOTE provider selected ref=%s endpoint=%s api=%s model=%s "
                        "prompt=%s(%s) assembly=%s -> model call will be made",
                        ref, _redact_endpoint(endpoint), api, model_id, spec.prompt_version,
                        spec.prompt_hash, prompt_mode)
        else:
            provider = impl.DeterministicAnalystProvider()
            logger.info("analyst.assess: no analyst_endpoint_url configured ref=%s -> deterministic "
                        "floor (NO model call). Set OMI_ANALYST_ENDPOINT_URL to reach the endpoint.", ref)

        model_revision = getattr(config, "model_revision", None)
        # Sprint 021 — wire institutional memory into the AI specialist's input. ``get_memory_store``
        # returns the durable store when memory persistence is enabled, else an empty in-memory store
        # (so retrieval naturally no-ops). Memory is CONTEXT only; it never moves the engine number.
        t_store0 = time.perf_counter()
        from app.memory.repository import get_memory_store
        store = get_memory_store(settings)
        store_ms = (time.perf_counter() - t_store0) * 1000.0
        judge = _AnalystJudge(impl=impl, config=config, provider=provider, payload=payload,
                              ref=ref, platform=platform, prompt_meta=prompt_meta, store=store)
        floor = _AnalystFloor(impl=impl, config=config, payload=payload, ref=ref,
                              platform=platform, model_revision=model_revision, store=store)
        t_run0 = time.perf_counter()
        result = Orchestrator(modules=[], judge=judge, floor=floor).run(
            payload, ref=ref, platform=platform, grain="comment_section")
        reasoning_ms = (time.perf_counter() - t_run0) * 1000.0
        governed = _attach_governance(result, judge=judge, floor=floor)
        gov = governed.get("governance", {})
        prov = str(gov.get("provider", "?"))
        model_backed = ("fallback" not in prov) and ("deterministic" not in prov)
        governed["ai_package"] = ai_package.provenance()
        governed["prompt_build"] = built.manifest
        governed["metrics"] = _assessment_metrics(
            governed, gov, settings, store_ms=store_ms, reasoning_ms=reasoning_ms,
            model_backed=model_backed, prompt_meta=prompt_meta)
        governed["metrics"]["package_hash"] = ai_package.package_hash
        m = governed["metrics"]
        logger.info("analyst.assess: DONE ref=%s provider=%s model_backed=%s governor=%s revision=%s "
                    "| metrics total=%.0fms model=%.0fms governor+assembly=%.0fms est_completion_tokens=%d",
                    ref, prov, model_backed, gov.get("verdict"), gov.get("model_revision"),
                    m["total_reasoning_ms"], m["model_ms"], m["governor_and_assembly_ms"],
                    m["est_completion_tokens"])
        return governed
    except Exception:  # noqa: BLE001 — never let the analyst break a caller
        logger.exception("omi_analyst assessment failed")
        return None


def _attach_governance(result: Any, *, judge: "_AnalystJudge", floor: "_AnalystFloor") -> dict:
    """Attach the transparency ``governance`` block from the Orchestrator's CouncilResult — the
    same fields the pre-convergence gate emitted, so the API + cache contract is byte-preserved."""
    from app.governor import Governor

    assessment = dict(result.assessment)
    meta = floor.last_meta if result.fallback else judge.last_meta
    gov = {
        "verdict": result.trace.verdict,
        "trace_id": result.trace.trace_id(),
        "violation_codes": list(result.trace.violation_codes),
        "provider": meta["provider"],
        "model_revision": meta["model_revision"],
        "prompt": judge.last_meta.get("prompt") or {},
        "latency_ms": meta["latency_ms"],
        "constitution_version": Governor.constitution_version,
    }
    if result.fallback:
        gov["fallback_from"] = judge.last_meta["provider"]
        gov["rejected_codes"] = list(result.rejected_codes)
    assessment["governance"] = gov
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


_autogen_inflight: set[str] = set()
_autogen_lock = threading.Lock()


def generate_and_persist(slug: str, user_id: int | None, refresh: bool = False) -> dict | None:
    """Background worker: open an own session, generate the assessment, cache it.
    Idempotent. Runs off the request hot path via app.core.background.submit.

    Exactly-once per investigation: the durable on-row cache is the cross-process guard, and an
    in-process in-flight set collapses the scan-time auto-trigger racing a UI-triggered request —
    so a single investigation makes at most ONE model (HF endpoint) call."""
    settings = get_settings()
    if not analyst_enabled(settings):
        return None
    with _autogen_lock:
        if slug in _autogen_inflight and not refresh:
            logger.info("analyst.generate: already in flight for slug=%s; skipping duplicate model call", slug)
            return None
        _autogen_inflight.add(slug)
    try:
        from app.storage.db import get_session
        from app.storage.repository import AccountRepository

        with get_session() as session:
            repo = AccountRepository(session)
            inv = repo.get_investigation(slug=slug, user_id=user_id)
            if inv is None:
                logger.info("analyst.generate: investigation slug=%s not found (user_id=%s); skipping",
                            slug, user_id)
                return None
            if not refresh and cached_assessment(inv):
                _cache_stats["served_from_cache"] += 1
                logger.info("analyst.generate: slug=%s already has a cached assessment; no model call "
                            "(cache hit_rate=%.2f)", slug, runtime_metrics()["assessment_cache"]["hit_rate"])
                return cached_assessment(inv)
            assessment = assess_payload(
                inv.payload_json or {},
                ref=_ref(inv.slug), platform=_platform_of(inv), settings=settings,
            )
            if assessment is None:
                return None
            _cache_stats["generated"] += 1
            gov = assessment.get("governance") or {}
            provider = gov.get("provider") or assessment.get("model_revision", "omi-analyst")
            return persist_assessment(session, inv, assessment, provider)
    finally:
        with _autogen_lock:
            _autogen_inflight.discard(slug)


def maybe_autogenerate(slug: str, user_id: int | None) -> bool:
    """Schedule a background analyst assessment for a freshly persisted investigation, so that
    EVERY real investigation reaches the model exactly once — the wire that was missing.

    Before this, ``assess_payload`` (→ the RemoteReasoningProvider → the HF endpoint) was reachable
    only through an explicit ``POST /v1/investigations/{slug}/analyst`` (the UI "Generate
    assessment" button); a normal scan never triggered it, so a live endpoint received zero
    requests. This runs off the scan's hot path via the background pool, is idempotent (cache +
    in-flight guard), and is a NO-OP unless the analyst is enabled — so it is fully backward
    compatible (endpoint unset → deterministic floor, exactly as before). Never raises."""
    try:
        settings = get_settings()
        if not analyst_enabled(settings):
            return False
        from app.core import background
        fut = background.submit(generate_and_persist, slug, user_id, False)
        scheduled = fut is not None
        target = "remote-model" if getattr(settings, "analyst_endpoint_url", None) else "deterministic-floor"
        logger.info("analyst.autogenerate: %s assessment for investigation slug=%s (target=%s)",
                    "scheduled" if scheduled else "could not schedule", slug, target)
        return scheduled
    except Exception:  # noqa: BLE001 — auto-generation must never disturb a scan
        logger.exception("analyst.autogenerate: failed to schedule for slug=%s", slug)
        return False


def _platform_of(inv) -> str:
    url = (getattr(inv, "input_url", "") or "").lower()
    if "twitter" in url or "x.com" in url:
        return "twitter"
    if "youtube" in url or "youtu.be" in url:
        return "youtube"
    return "unknown"
