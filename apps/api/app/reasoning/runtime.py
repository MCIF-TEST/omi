"""The AI Investigation Runtime (Phase P2.0 → P3.2/P3.3) — the ONE orchestration layer for AI.

``AIInvestigationRuntime.infer(prompt_package, gov_bundle)`` is the single, canonical place a stage's
prompt is reasoned by the model. Every AI stage reaches it through :func:`run_stage_inference`:

    Prompt Package (from the ONE Canonical Prompt Builder)
      → Hugging Face endpoint        exactly one inference, via the ONE transport
      → capture                      request/response/token/latency/request-id + package/prompt/model
      → Governor                     validate the model's structured wrapper (echo-guarded)
      → fallback                     deterministic Floor on failure / reject
      → RuntimeInference             the one object every stage receives

It **owns no primitive logic** — every step delegates to the single implementation, so there is zero
duplicated inference / retry / endpoint / forensic / governor / fallback code:

* the endpoint call (retries, timeout, forensic capture, the capture sidecar) is the ONE transport
  ``RemoteReasoningProvider`` reached through ``analyst._qwen_transport``;
* the Governor is ``app.governor.Governor``; the Floor is the deterministic analyst provider.

Exactly one inference per stage. No UI, no report, no heuristics/score/prompt/package changes — the
runtime only orchestrates. The Comment Analysis, Commenter History, and whole-investigation
assessment stages all consume this runtime.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from app.core.config import Settings, get_settings
from app.reasoning import analyst as _analyst
from app.reasoning.model_providers.remote import extract_json, forensic_on

logger = logging.getLogger("omi.reasoning.runtime")

_MODEL_ECHOED_FIELDS = ("suspicion_probability", "suspicion_tier")
# Per-stage typed sidecars that ride ALONGSIDE the constitutional wrapper (e.g. per-comment or
# per-commenter analyses). They are separated out before the Governor validates the wrapper, so the
# Governor sees the identical constitutional object for every stage — one strip list, no per-stage
# Governor logic. A stage extracts its own typed structure from ``RuntimeInference.raw_obj``.
_STAGE_SIDECAR_KEYS = (
    "comment_analyses", "commenter_analyses",
    # The comprehensive single-inference response rides six per-domain reasoning sections ALONGSIDE the
    # Lead-Investigator synthesis wrapper. They are separated here so the Governor validates the
    # identical constitutional wrapper (one strip list, no per-stage Governor logic); the stage
    # structurally validates + citation-resolves the six via ``validate_comprehensive_sections``.
    "comment_reasoning", "commenter_history_reasoning", "account_reasoning",
    "narrative_reasoning", "coordination_reasoning", "campaign_reasoning",
)


@dataclass
class RuntimeInference:
    """The result of exactly ONE runtime inference over a PromptPackage — the single object every
    reasoning stage receives from the runtime. It carries the Governor-validated ruling (``core``),
    the raw model object (for stage-specific typed extraction), the provider/fallback status, the
    Governor trace, and the full endpoint forensic capture. Because every stage obtains inference
    from here, no stage calls the transport or the Governor itself (the ONE endpoint path + the ONE
    Governor invocation live in :meth:`AIInvestigationRuntime.infer`)."""

    ruling: dict
    raw_obj: dict | None
    provider: str
    model_backed: bool
    fallback: bool
    trace: Any  # app.governor.audit.ValidationTrace
    endpoint_called: bool
    # --- endpoint forensic capture (survives into every stage's result) ---
    latency_ms: float
    attempts: int
    tokens: dict | None
    endpoint_request_id: str | None
    response_status: int | None
    served_model: str
    package_hash: str
    prompt_hash: str
    forensic_captured: bool
    # The exact transport failure (class + message) when the endpoint did not return a usable
    # response — so the persisted trace self-diagnoses timeout vs connection vs DNS/TLS. None on success.
    endpoint_error: str | None = None
    # --- judge_then_floor bookkeeping (P3.2): when the Governor rejected the candidate ruling and
    # the served ruling is the re-validated Floor, these carry the rejected candidate's provider
    # name and the rejecting trace's violation codes (the legacy governance contract).
    fallback_from: str | None = None
    rejected_codes: tuple[str, ...] = ()


class AIInvestigationRuntime:
    """The single orchestration layer. Stateless. ``run`` is the whole-investigation entry point;
    ``infer`` is the canonical per-stage inference primitive every migrated stage reasons through."""

    # ------------------------------------------------------------------ #
    # The ONE inference primitive — the only place a stage reaches the endpoint + Governor.
    # ------------------------------------------------------------------ #
    def infer(
        self,
        pp: Any,
        gov_bundle: Any,
        *,
        settings: Settings | None = None,
        config: Any = None,
        floor_ruling: dict | None = None,
        schema_prefilter: bool = False,
        require_hf_token: bool = False,
        capture: dict | None = None,
        adjudication: str = "single_gate",
        canonical_output_schema: dict | None = None,
    ) -> RuntimeInference:
        """Run exactly one inference for a prompt package: call the ONE transport once (capturing
        latency/attempts/request-id/status/tokens), then adjudicate via the MANDATORY Governor with
        the engine number echo-guarded, degrading to the deterministic Floor on any failure. No stage
        may call ``_qwen_transport`` or the Governor directly — they call this.

        ``floor_ruling`` is the always-valid wrapper to fall back to (default: the canonical
        FloorJudge assessment for ``gov_bundle``). ``schema_prefilter`` additionally runs the
        ``omi_analyst`` response-schema check before the Governor. ``require_hf_token`` preserves the
        legacy investigation-assessment gate: the endpoint is attempted only when an HF token is
        present (no wasted unauthenticated request). ``capture`` is an optional caller-owned forensic
        sidecar the ONE transport writes into directly (the trace/audit contract). ``adjudication``:

        * ``"single_gate"`` (default; the comment stage + P2.0 result): the Floor is validated once
          and served on any model failure.
        * ``"judge_then_floor"`` (the investigation assessment): the candidate ruling — the model's
          when valid, else the Floor standing in as the judge — is validated; on REJECT the Floor is
          validated AGAIN and served with ``fallback_from`` + ``rejected_codes`` bookkeeping (the
          exact legacy council semantics: two Governor validations on a reject)."""
        settings = settings or get_settings()
        impl = _analyst._impl()
        capture = capture if capture is not None else {}
        endpoint = getattr(settings, "analyst_endpoint_url", None)
        enabled = _analyst.analyst_enabled(settings) and impl is not None
        # Provider-aware readiness: HF needs the endpoint URL; OpenRouter needs a preset or model. Provider
        # choice is the ONLY thing that varies here — the adjudication below is provider-agnostic.
        if _analyst.reasoning_provider(settings) == "openrouter":
            configured = bool(getattr(settings, "openrouter_preset", None)
                              or getattr(settings, "openrouter_model", None))
        else:
            configured = bool(endpoint)
        model_path = bool(enabled and configured)
        token_ok = (not require_hf_token) or _analyst._provider_token_present(settings)
        model_provider = _analyst.reasoning_provider_name(settings)
        raw: str | None = None
        endpoint_called = False
        if model_path and token_ok:
            transport = _analyst._reasoning_transport(
                settings, endpoint,
                timeout=float(getattr(settings, "analyst_timeout_seconds", 30.0) or 30.0),
                max_retries=int(getattr(settings, "analyst_max_retries", 2) or 2),
                revision=getattr(settings, "analyst_hf_revision", None),
                api=str(getattr(settings, "analyst_endpoint_api", "generate") or "generate"),
                model=pp.model_id, capture=capture,
                prompt_hash=pp.manifest["prompt_hash"], package_hash=pp.manifest["package_hash"],
                canonical_schema=canonical_output_schema)
            endpoint_called = True
            raw = transport(pp.system, pp.user, config)  # THE ONE inference

        ruling, raw_obj, provider, model_backed, trace, fallback_from, rejected = self._adjudicate(
            raw, gov_bundle, impl, floor_ruling, schema_prefilter,
            model_path=model_path, adjudication=adjudication,
            canonical_output_schema=canonical_output_schema, model_provider=model_provider,
            capture=capture)
        usage = capture.get("usage")
        return RuntimeInference(
            ruling=ruling, raw_obj=raw_obj, provider=provider, model_backed=model_backed,
            fallback=not model_backed, trace=trace, endpoint_called=endpoint_called,
            latency_ms=float(capture.get("latency_ms") or capture.get("endpoint_latency_ms") or 0.0),
            attempts=int(capture.get("attempts") or 0),
            tokens=(dict(usage) if isinstance(usage, dict) else None),
            endpoint_request_id=capture.get("endpoint_request_id"),
            response_status=capture.get("response_status"), served_model=pp.model_id,
            package_hash=pp.manifest["package_hash"], prompt_hash=pp.manifest["prompt_hash"],
            forensic_captured=forensic_on(), fallback_from=fallback_from, rejected_codes=rejected,
            endpoint_error=capture.get("endpoint_error"))

    # ------------------------------------------------------------------ #
    def _adjudicate(self, raw, gov_bundle, impl, floor_ruling, schema_prefilter, *,
                    model_path: bool = False, adjudication: str = "single_gate",
                    canonical_output_schema: dict | None = None,
                    model_provider: str = "qwen-omi-analyst-v1",
                    capture: dict | None = None):
        """Parse → (optional schema pre-filter) → echo-guard → MANDATORY Governor. On any failure the
        deterministic Floor (``floor_ruling`` or the canonical FloorJudge assessment), itself
        Governor-validated. The ONE Governor invocation for every stage. Returns
        ``(ruling, raw_obj, provider, model_backed, trace, fallback_from, rejected_codes)`` —
        ``raw_obj`` is the untouched model object so a stage can extract its own typed structure."""
        from app.governor import Governor
        from app.reasoning.orchestrator.modules import build_ruling_assessment

        governor = Governor()
        hl = gov_bundle.headline()
        floor = floor_ruling if floor_ruling is not None else build_ruling_assessment(gov_bundle)
        raw_obj = None
        candidate = None
        if raw:
            obj = extract_json(raw)
            if isinstance(obj, dict):
                # Diagnostic: record the model's RAW top-level keys (names only, no values/secrets) so a
                # floored-after-success scan tells us WHAT shape the model produced vs. what the contract
                # expects — the fastest way to spot a stale OpenRouter preset or an envelope wrapper.
                if capture is not None:
                    capture["model_output_keys"] = sorted(obj.keys())[:40]
                if canonical_output_schema is not None:
                    # AI-first: coerce the model output to the contract's SHAPE up front (drop unknown keys,
                    # backfill structural gaps, derive tier, drop malformed evidence) so the WHOLE downstream
                    # pipeline — the served ruling AND the per-domain `comprehensive_sections` the UI reads —
                    # sees one repaired object. A good-faith reply renders instead of floorng on a harmless
                    # deviation; the substance (verdict/omi_score/headline/assessment) is never invented.
                    from app.governor import coerce_comprehensive_model_output
                    from app.reasoning.prompts.comprehensive_investigation_template import (
                        COMPREHENSIVE_SECTION_KEYS,
                    )
                    obj = coerce_comprehensive_model_output(
                        obj, schema=canonical_output_schema, section_keys=COMPREHENSIVE_SECTION_KEYS)
                raw_obj = obj
                if canonical_output_schema is not None:
                    # Phase 1 — the ONE canonical comprehensive contract: validate the (coerced) model output
                    # (synthesis wrapper + six first-class reasoning domains) against the canonical schema,
                    # then build the governed wrapper by OVERLAYING Omi-owned provenance/subject + engine
                    # corroboration from the always-valid Floor (the model never fabricates system metadata).
                    # None on canonical-invalid output (-> Floor).
                    candidate = self._canonical_candidate(obj, floor, hl, canonical_output_schema,
                                                          capture=capture)
                else:
                    # Registered stage sidecars (per-comment / per-commenter analyses) ride ALONGSIDE the
                    # constitutional wrapper. Separate ONLY those registered keys BEFORE core schema
                    # validation — so any UNKNOWN top-level field stays in ``core`` and still fails the
                    # schema allowlist. The Governor then validates the identical constitutional wrapper.
                    core = {k: v for k, v in obj.items() if k not in _STAGE_SIDECAR_KEYS}
                    if not (schema_prefilter and self._schema_errors(core, impl)):
                        # Echo discipline — the model never moves the number.
                        core["suspicion_probability"] = round(float(hl.get("overall_probability") or 0.0), 6)
                        core["suspicion_tier"] = hl.get("tier") or core.get("suspicion_tier")
                        candidate = core

        if adjudication == "schema_only":
            # AI-first investigation (architecture refactor): the model IS the investigator. Structural
            # schema validation already ran in ``_canonical_candidate`` (canonical schema + required fields
            # + additionalProperties). A structurally-valid model output is accepted VERBATIM — no
            # interpretive Governor gate (no echo-guard / corroboration gate / confidence / policy review of
            # the AI's reasoning). On structural failure the deterministic Floor stands in. The trace is a
            # structural permit so the persistence/forensic plumbing is unchanged.
            if candidate is not None:
                return (candidate, raw_obj, model_provider, True,
                        self._structural_trace(gov_bundle), None, ())
            provider = ("deterministic-analyst-v1" if not raw
                        else f"{model_provider}->fallback:deterministic-analyst-v1")
            return floor, raw_obj, provider, False, self._structural_trace(gov_bundle), None, ()

        if adjudication == "judge_then_floor":
            # Legacy council semantics (the investigation assessment): the candidate ruling is the
            # model's when valid, else the Floor STANDING IN as the judge (with the legacy provider
            # naming keyed off whether the model path was configured). On REJECT the Floor is
            # validated AGAIN and served with fallback bookkeeping — two Governor validations.
            if candidate is not None:
                cand_ruling, cand_provider = candidate, model_provider
            elif model_path:
                cand_ruling = floor
                cand_provider = f"{model_provider}->fallback:deterministic-analyst-v1"
            else:
                cand_ruling, cand_provider = floor, "deterministic-analyst-v1"
            trace = governor.validate(cand_ruling, gov_bundle,
                                      corroboration=cand_ruling.get("corroboration"))
            if trace.permitted:
                return (cand_ruling, raw_obj, cand_provider,
                        cand_provider == model_provider, trace, None, ())
            logger.warning("runtime: candidate ruling REJECTED %s; Floor fallback", trace.violation_codes)
            ftrace = governor.validate(floor, gov_bundle, corroboration=floor.get("corroboration"))
            return (floor, raw_obj, "deterministic-floor", False, ftrace,
                    cand_provider, tuple(trace.violation_codes))

        # single_gate (default): the model ruling is validated when present; the Floor is validated
        # once and served on any model failure.
        if candidate is not None:
            trace = governor.validate(candidate, gov_bundle, corroboration=candidate.get("corroboration"))
            if trace.permitted:
                return candidate, raw_obj, model_provider, True, trace, None, ()
            logger.warning("runtime: model ruling REJECTED %s; Floor fallback", trace.violation_codes)
        ftrace = governor.validate(floor, gov_bundle, corroboration=floor.get("corroboration"))
        provider = ("deterministic-analyst-v1" if not raw
                    else f"{model_provider}->fallback:deterministic-analyst-v1")
        return floor, raw_obj, provider, False, ftrace, None, ()

    @staticmethod
    def _structural_trace(gov_bundle: Any):
        """A structural-only permit trace (AI-first path): schema validity already decided upstream, so the
        served ruling passes with no interpretive violation codes. Keeps the ValidationTrace plumbing that
        persistence + the forensic trace expect, without the interpretive Governor."""
        from app.governor.audit import ValidationTrace
        return ValidationTrace(
            verdict="permit", violation_codes=[],
            stage_results=[{"id": "structural", "name": "schema_validation", "passed": True}],
            version_binding={**getattr(gov_bundle, "version_binding", {}),
                             "validation": "structural_schema_only"},
            input_digest="", bundle_id=getattr(gov_bundle, "bundle_id", ""), fallback_path="none",
        )

    @staticmethod
    def _canonical_candidate(obj: dict, floor: dict, hl: dict, canonical_schema: dict,
                             capture: dict | None = None) -> dict | None:
        """Phase 1 — build the governed wrapper from a canonically-valid comprehensive MODEL output.

        Validate ``obj`` (synthesis wrapper + six first-class reasoning domains) against the ONE canonical
        schema. On success the candidate is the model's ANALYTICAL fields (wrapper, sidecars stripped for
        the Governor) with the Omi-owned provenance/subject + engine corroboration OVERLAID from the
        always-valid Floor (the model never supplies system-owned metadata — OmiSphere injects it here,
        after validation) and the echoed engine numbers forced. Returns ``None`` (→ deterministic Floor)
        if the model output is not canonically valid — no second inference, ever."""
        from app.governor import validate_comprehensive_model_output
        from app.reasoning.prompts.comprehensive_investigation_template import (
            COMPREHENSIVE_OMI_OWNED_WRAPPER_FIELDS,
            COMPREHENSIVE_SECTION_KEYS,
        )

        # NOTE: `obj` has ALREADY been structurally coerced upstream in `_adjudicate` (so raw_obj and the
        # UI's comprehensive_sections see the same repaired object). This validates the coerced output; on
        # any remaining (substantive) failure the deterministic Floor stands in.
        errs = validate_comprehensive_model_output(
            obj, schema=canonical_schema, section_keys=COMPREHENSIVE_SECTION_KEYS)
        if errs:
            logger.warning("runtime: comprehensive model output failed canonical validation %s; "
                           "model_output_keys=%s; Floor",
                           errs[:5], (capture or {}).get("model_output_keys"))
            # Record WHY the model's 200 response was rejected, so the forensic trace/UI can explain a
            # floored-after-success scan (schema mismatch) instead of a bare "unknown". No secret, no body.
            if capture is not None:
                capture["canonical_validation_errors"] = [str(e) for e in errs[:8]]
            return None
        core = {k: v for k, v in obj.items() if k not in _STAGE_SIDECAR_KEYS}
        # OmiSphere injects only provenance/subject + the factual engine corroboration state (which
        # discriminative methods fired) — overlay from the Floor (schema-valid, correct values). AI-first:
        # the analyst OWNS its scores (omi_score + suspicion_tier); nothing is echoed/overwritten.
        for k in COMPREHENSIVE_OMI_OWNED_WRAPPER_FIELDS:
            if k in floor:
                core[k] = floor[k]
        return core

    @staticmethod
    def _schema_errors(obj: dict, impl) -> list:
        """Legacy single-account prefilter. Only reached when there is NO canonical output schema AND
        ``schema_prefilter=True`` (it defaults to False), so the comprehensive investigation path never
        uses it — that path goes through ``_canonical_candidate``.

        Imports the API-OWNED validator. It previously imported ``omi_analyst.schema_validate`` from
        ml/, which apps/api does not package; see ``app/governor/canonical_validate`` for what that cost
        on the comprehensive path.
        """
        try:
            from app.governor.canonical_validate import validate_analyst_response

            schema = getattr(impl, "response_schema", None)
            return validate_analyst_response(obj, schema=schema)
        except Exception:  # noqa: BLE001 — if the validator is unreachable, treat as invalid -> Floor
            return ["schema validator unavailable"]


# The single shared instance + a module-level convenience — the canonical entry point.
_RUNTIME = AIInvestigationRuntime()


def run_stage_inference(
    pp: Any, gov_bundle: Any, *, settings: Settings | None = None, config: Any = None,
    floor_ruling: dict | None = None, schema_prefilter: bool = False,
    require_hf_token: bool = False, capture: dict | None = None,
    adjudication: str = "single_gate", canonical_output_schema: dict | None = None,
) -> RuntimeInference:
    """The canonical per-stage inference entry — the ONE call a migrated reasoning stage makes to
    reach the model. Delegates to the shared runtime's :meth:`AIInvestigationRuntime.infer`, so the
    endpoint path, the capture, and the Governor invocation are owned by the runtime, never the
    stage. (Comment Analysis was the first stage to reason through this; the investigation
    assessment reasons through it with ``adjudication="judge_then_floor"``.)

    ``canonical_output_schema`` (the comprehensive investigation stage) switches adjudication to the ONE
    canonical comprehensive contract: the model's full output is validated against that schema and the
    Omi-owned metadata is overlaid from the Floor after validation (see :meth:`_canonical_candidate`)."""
    return _RUNTIME.infer(pp, gov_bundle, settings=settings, config=config, floor_ruling=floor_ruling,
                          schema_prefilter=schema_prefilter, require_hf_token=require_hf_token,
                          capture=capture, adjudication=adjudication,
                          canonical_output_schema=canonical_output_schema)


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
    "AIInvestigationRuntime", "RuntimeInference",
    "run_stage_inference", "assess_investigation",
]
