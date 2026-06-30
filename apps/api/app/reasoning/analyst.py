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


def _qwen_transport(endpoint: str, *, timeout: float, max_retries: int, revision: str | None):
    """The ONE Qwen HTTP transport (Sprint 017). The production analyst's model call goes through
    the constitutional ``RemoteReasoningProvider`` — the same HF client the council uses — instead
    of a second bespoke HTTP implementation. Returns the raw generated text, or None on any failure
    so the analyst degrades to its deterministic provider."""
    from app.reasoning.model_providers import ReasoningRequest, RemoteReasoningProvider

    provider = RemoteReasoningProvider(
        endpoint_url=endpoint, timeout=timeout, max_retries=max_retries, revision=revision)

    def _call(system: str, user: str, config: Any) -> str | None:
        try:
            resp = provider.complete(ReasoningRequest(
                system=system, user=user, response_format="text",
                temperature=getattr(config, "temperature", 0.2),
                max_tokens=getattr(config, "max_new_tokens", 1024), revision=revision,
            ))
            return resp.text
        except Exception:  # noqa: BLE001 — provider failure -> deterministic fallback
            return None

    return _call


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
                 ref: str, platform: str, prompt_meta: dict) -> None:
        self._impl, self._config, self._provider = impl, config, provider
        self._payload, self._ref, self._platform = payload, ref, platform
        self.last_meta: dict[str, Any] = {
            "provider": "none", "latency_ms": 0.0,
            "model_revision": getattr(config, "model_revision", None), "prompt": prompt_meta,
        }

    def run(self, view: Any) -> list:
        lossy = build_bundle(self._payload, ref=self._ref, platform=self._platform, impl=self._impl)
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
                 model_revision: str | None) -> None:
        self._impl, self._config = impl, config
        self._payload, self._ref, self._platform = payload, ref, platform
        self.last_meta = {"provider": "deterministic-floor", "latency_ms": 0.0,
                          "model_revision": model_revision, "prompt": {}}

    def run(self, view: Any) -> list:
        lossy = build_bundle(self._payload, ref=self._ref, platform=self._platform, impl=self._impl)
        result = self._impl.DeterministicAnalystProvider().generate(lossy, self._config)
        return [Ruling(module=self.contract.module, assessment=result.response)]


def assess_payload(
    payload: dict, *, ref: str, platform: str = "youtube", settings: Settings | None = None,
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

        endpoint = getattr(settings, "analyst_endpoint_url", None)
        timeout = float(getattr(settings, "analyst_timeout_seconds", 30.0) or 30.0)
        if endpoint:
            transport = _qwen_transport(
                endpoint, timeout=timeout,
                max_retries=int(getattr(settings, "analyst_max_retries", 2) or 2),
                revision=getattr(settings, "analyst_hf_revision", None))
            provider = impl.QwenAnalystProvider(
                endpoint_url=endpoint, timeout=timeout, system_prompt=spec.template, transport=transport)
        else:
            provider = impl.DeterministicAnalystProvider()

        model_revision = getattr(config, "model_revision", None)
        judge = _AnalystJudge(impl=impl, config=config, provider=provider, payload=payload,
                              ref=ref, platform=platform, prompt_meta=prompt_meta)
        floor = _AnalystFloor(impl=impl, config=config, payload=payload, ref=ref,
                              platform=platform, model_revision=model_revision)
        result = Orchestrator(modules=[], judge=judge, floor=floor).run(
            payload, ref=ref, platform=platform, grain="comment_section")
        return _attach_governance(result, judge=judge, floor=floor)
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
