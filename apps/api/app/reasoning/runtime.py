"""The AI Investigation Runtime (Phase P2.0) — the ONE orchestration layer for AI execution.

This is the single, canonical place an investigation is reasoned by the model. It composes the
already-built layers in the approved order and returns one immutable result:

    InvestigationContext (P1.0)
      → Package Loader (P1.2)        load + verify the canonical package
      → Prompt Builder (P1.1)        assemble the PromptPackage from package assets only
      → Hugging Face endpoint        exactly one inference, via the ONE transport
      → capture                      request/response/token/latency/request-id + package/prompt/model
      → Governor                     validate the model's structured assessment
      → fallback                     deterministic Floor on failure / reject
      → AIInvestigationResult        one immutable object

It **owns no primitive logic** — every step delegates to the existing single implementation, so
there is zero duplicated inference / retry / endpoint / forensic / governor / fallback code:

* the endpoint call (retries, timeout, forensic capture, the capture sidecar) is the ONE transport
  ``RemoteReasoningProvider`` reached through ``analyst._qwen_transport``;
* the Governor is ``app.governor.Governor``; the Floor is the deterministic analyst provider; the
  evidence bundle + response schema are the existing ones.

Exactly one inference per investigation. No UI, no report, no heuristics/score/prompt/package
changes — the runtime only orchestrates. Everything else is meant to consume this runtime.
"""
from __future__ import annotations

import logging
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

from app.core.config import Settings, get_settings
from app.evidence import Binder
from app.evidence.bundle import digest
from app.reasoning import analyst as _analyst
from app.reasoning.context.investigation import InvestigationContext
from app.reasoning.model_providers.remote import extract_json, forensic_on
from app.reasoning.package_loader import load_package
from app.reasoning.prompt import build_prompt_package

logger = logging.getLogger("omi.reasoning.runtime")

_MODEL_ECHOED_FIELDS = ("suspicion_probability", "suspicion_tier")


@dataclass(frozen=True)
class AIInvestigationResult:
    """The immutable output of one AI investigation run — the governed assessment plus the full
    execution provenance (what package/prompt/model produced it, how the endpoint behaved, and how
    the Governor ruled). Content-addressed by ``result_id`` (excludes wall-clock + latency)."""

    assessment: dict
    provider: str
    model_backed: bool
    fallback: bool
    # governance
    governor_verdict: str
    governor_trace_id: str
    violation_codes: tuple[str, ...]
    constitution_version: str
    # package / prompt / model identity
    package_hash: str
    prompt_hash: str
    template_hash: str
    model_id: str
    prompt_package_id: str
    context_id: str
    # endpoint execution metadata
    latency_ms: float
    attempts: int
    tokens: dict | None
    endpoint_request_id: str | None
    response_status: int | None
    endpoint_called: bool
    forensic_captured: bool
    # content address (deterministic) + wall-clock (excluded from the address)
    result_id: str = ""
    generated_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class AIInvestigationRuntime:
    """The single orchestration layer. Stateless; ``run`` is the only entry point."""

    def run(
        self,
        context: InvestigationContext,
        *,
        payload: dict,
        platform: str | None = None,
        settings: Settings | None = None,
    ) -> AIInvestigationResult:
        """Reason over one :class:`InvestigationContext` and return the immutable result.

        ``payload`` is the engine's serialized investigation (the same object the Context Builder
        consumed) — the runtime binds the Governor's Evidence Bundle + the deterministic Floor's
        bundle from it (both are evidence-based and predate the context). Never raises for the
        caller: any failure degrades to the always-valid deterministic Floor.
        """
        settings = settings or get_settings()
        payload = payload or {}
        ref = context.investigation.ref or _analyst._ref(context.context_id)
        platform = platform or context.investigation.platform or "unknown"

        # --- P1.2 + P1.1: load the canonical package, build the prompt from its assets ----------
        loaded = load_package(getattr(settings, "analyst_model_id", None))
        pp = build_prompt_package(context, loaded=loaded)

        # --- the deterministic evidence the Governor + Floor validate against (reused collectors) -
        impl = _analyst._impl()
        gov_bundle = Binder().bind(payload, grain="comment_section", subject_ref=ref,
                                   platform=platform, enrich=True)

        capture: dict[str, Any] = {}
        endpoint = getattr(settings, "analyst_endpoint_url", None)
        enabled = _analyst.analyst_enabled(settings) and impl is not None
        raw: str | None = None
        endpoint_called = False

        if enabled and endpoint:
            config = impl.load_analyst_config(
                repo_id=getattr(settings, "analyst_hf_repo", None),
                revision=getattr(settings, "analyst_hf_revision", None))
            lossy = _analyst.build_bundle(payload, ref=ref, platform=platform, impl=impl)
            # ONE inference — via the ONE transport (retries/timeout/forensic/capture all inside it).
            transport = _analyst._qwen_transport(
                endpoint, timeout=float(getattr(settings, "analyst_timeout_seconds", 30.0) or 30.0),
                max_retries=int(getattr(settings, "analyst_max_retries", 2) or 2),
                revision=getattr(settings, "analyst_hf_revision", None),
                api=str(getattr(settings, "analyst_endpoint_api", "generate") or "generate"),
                model=pp.model_id, capture=capture,
                prompt_hash=pp.manifest["prompt_hash"], package_hash=pp.manifest["package_hash"])
            endpoint_called = True
            raw = transport(pp.system, pp.user, config)
        else:
            config = impl.load_analyst_config(
                repo_id=getattr(settings, "analyst_hf_repo", None),
                revision=getattr(settings, "analyst_hf_revision", None)) if impl is not None else None
            lossy = _analyst.build_bundle(payload, ref=ref, platform=platform, impl=impl) if impl else {}

        # --- adjudicate: model output (Governor-permitted) else deterministic Floor -------------
        assessment, provider, model_backed, trace = self._adjudicate(
            raw, gov_bundle, lossy, impl, config)

        return self._result(
            context=context, pp=pp, loaded=loaded, capture=capture, endpoint_called=endpoint_called,
            assessment=assessment, provider=provider, model_backed=model_backed, trace=trace)

    # ------------------------------------------------------------------ #
    def _adjudicate(self, raw, gov_bundle, lossy, impl, config):
        """Parse → schema-validate → echo-guard → Governor. On any failure, the deterministic Floor
        (always schema-valid), itself Governor-validated. Reuses the single Governor + Floor."""
        from app.governor import Governor

        governor = Governor()
        if raw and impl is not None:
            obj = extract_json(raw)
            if obj is not None and not self._schema_errors(obj, impl):
                # echo discipline — the engine's numbers are authoritative; the model never moves them.
                hs = (lossy or {}).get("headline_scores") or {}
                obj["suspicion_probability"] = round(float(hs.get("overall_probability") or 0.0), 6)
                obj["suspicion_tier"] = hs.get("tier") or obj.get("suspicion_tier")
                trace = governor.validate(obj, gov_bundle, corroboration=obj.get("corroboration"))
                if trace.permitted:
                    return obj, "qwen-omi-analyst-v1", True, trace
                logger.warning("runtime: model ruling REJECTED %s; Floor fallback", trace.violation_codes)

        # deterministic Floor (always-valid), Governor-validated
        floor = impl.DeterministicAnalystProvider().generate(lossy, config)
        ftrace = governor.validate(floor.response, gov_bundle,
                                   corroboration=floor.response.get("corroboration"))
        provider = floor.provider if raw is None else f"qwen-omi-analyst-v1->fallback:{floor.provider}"
        return floor.response, provider, False, ftrace

    @staticmethod
    def _schema_errors(obj: dict, impl) -> list:
        try:
            from omi_analyst.schema_validate import validate_analyst_response
            return validate_analyst_response(obj)
        except Exception:  # noqa: BLE001 — if the validator is unreachable, treat as invalid -> Floor
            return ["schema validator unavailable"]

    # ------------------------------------------------------------------ #
    def _result(self, *, context, pp, loaded, capture, endpoint_called, assessment, provider,
                model_backed, trace) -> AIInvestigationResult:
        from app.governor import Governor

        usage = capture.get("usage")
        addressed = {
            "assessment": assessment, "provider": provider, "model_backed": model_backed,
            "governor_verdict": trace.verdict, "violation_codes": list(trace.violation_codes),
            "package_hash": loaded.package_hash, "prompt_hash": loaded.prompt_hash,
            "template_hash": loaded.template_hash, "model_id": loaded.model_id,
            "prompt_package_id": pp.prompt_package_id, "context_id": context.context_id,
        }
        return AIInvestigationResult(
            assessment=dict(assessment), provider=provider, model_backed=model_backed,
            fallback=not model_backed,
            governor_verdict=trace.verdict, governor_trace_id=trace.trace_id(),
            violation_codes=tuple(trace.violation_codes),
            constitution_version=Governor.constitution_version,
            package_hash=loaded.package_hash, prompt_hash=loaded.prompt_hash,
            template_hash=loaded.template_hash, model_id=loaded.model_id,
            prompt_package_id=pp.prompt_package_id, context_id=context.context_id,
            latency_ms=float(capture.get("latency_ms") or 0.0),
            attempts=int(capture.get("attempts") or 0),
            tokens=(dict(usage) if isinstance(usage, dict) else None),
            endpoint_request_id=capture.get("endpoint_request_id"),
            response_status=capture.get("response_status"),
            endpoint_called=endpoint_called, forensic_captured=forensic_on(),
            result_id=digest(addressed, prefix="air:"),
            generated_at=datetime.now(timezone.utc).isoformat(),
        )


# The single shared instance + a module-level convenience — the canonical entry point.
_RUNTIME = AIInvestigationRuntime()


def run_investigation(
    context: InvestigationContext, *, payload: dict, platform: str | None = None,
    settings: Settings | None = None,
) -> AIInvestigationResult:
    """Run the canonical AI Investigation Runtime for one context. The one call the rest of the
    system makes to reach the model."""
    return _RUNTIME.run(context, payload=payload, platform=platform, settings=settings)


def assess_investigation(
    payload: dict, *, ref: str, platform: str = "youtube", settings: Settings | None = None,
    capture: dict | None = None,
) -> dict | None:
    """The AI Investigation Runtime's production orchestration entry (P2.1 cutover). This is the ONE
    path every investigation executes through: the ``assess_payload`` compatibility wrapper and the
    forensic trace/audit both delegate here. It drives the Governor-gated, Floor-backed council
    orchestration — package loading, prompt assembly, the endpoint call (via the ONE transport), the
    mandatory Governor, and the deterministic fallback — and returns the governed assessment.

    Behavior, governance, metadata, and package/prompt hashes are byte-identical to the pre-cutover
    ``assess_payload``: the orchestration ENTRY is consolidated into the runtime; the reasoning,
    prompt, package, schema, and report are unchanged (P2.1 changed no behavior)."""
    return _analyst._assess_core(payload, ref=ref, platform=platform, settings=settings, capture=capture)


__all__ = [
    "AIInvestigationResult", "AIInvestigationRuntime", "run_investigation", "assess_investigation",
]
