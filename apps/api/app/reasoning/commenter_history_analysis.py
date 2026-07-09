"""AI-Native Commenter History Analysis (Phase P3.2) — the second migrated reasoning stage.

Mistral reasons about every commenter's POSTING TRACK RECORD; the deterministic engine only produces
evidence. The flow is the identical canonical architecture the Comment Analysis stage established:

    CommenterHistoryBundle (P3.0)  →  Package Loader (P1.2)  →  Prompt Builder (package assets only)
      →  AI Investigation Runtime (the ONE endpoint + Governor + Floor + forensic path)
      →  Mistral  →  Governor  →  typed report.

Mirroring the approved comment-section-wrapper decision, the model returns per-commenter
:class:`CommenterHistoryAnalysis` objects inside ONE investigation-level assessment that echoes the
deterministic engine number, so the existing constitutional Governor validates the wrapper
**unchanged** (the runtime strips the ``commenter_analyses`` sidecar before validation). The
deterministic Floor stays available and produces a factual per-commenter analysis when the endpoint
is unreachable or the ruling is rejected. This module embeds ZERO prompt text — all scaffolding comes
from the commenter-history package asset, and it OWNS no orchestration/endpoint/Governor/fallback
logic (all delegated to :func:`app.reasoning.runtime.run_stage_inference`).

Only Commenter History is migrated. No other stage, prompt, package asset, heuristic, endpoint,
result, schema, or UI is changed. A compatibility mapping supplies the existing commenter shape.
"""
from __future__ import annotations

import logging
from dataclasses import asdict, dataclass
from typing import Any

from app.core.config import Settings, get_settings
from app.evidence import Binder
from app.evidence.bundle import digest
from app.reasoning import analyst as _analyst
from app.reasoning.context.investigation import InvestigationContext
from app.reasoning.evidence_bundles import CommenterHistoryBundle, build_commenter_history_bundle
from app.reasoning.package_loader import load_commenter_history_assets, load_package
from app.reasoning.prompt import PromptPackage, StagePromptSpec, build_prompt, register_stage_prompt
from app.reasoning.runtime import RuntimeInference, run_stage_inference

logger = logging.getLogger("omi.reasoning.commenter_history_analysis")


# --------------------------------------------------------------------------- #
# Typed output — structured reasoning only (no prose/markdown/UI)
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class CommenterHistoryAnalysis:
    """One commenter's structured track-record analysis. Immutable; the required P3.2 fields only."""

    commenter_ref: str
    track_record_assessment: str
    history_depth_reasoning: str
    recurrence_reasoning: str
    provenance_reasoning: str
    supporting_evidence: tuple[str, ...] = ()
    contradictory_evidence: tuple[str, ...] = ()
    uncertainty: tuple[str, ...] = ()
    confidence: float = 0.0
    reasoning_trace: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class CommenterHistoryReport:
    """The immutable output of the Commenter History stage: the per-commenter analyses + the
    Governor-validated investigation-level wrapper's provenance. Content-addressed by ``report_id``."""

    commenter_analyses: tuple[CommenterHistoryAnalysis, ...]
    provider: str
    model_backed: bool
    fallback: bool
    governor_verdict: str
    governor_trace_id: str
    violation_codes: tuple[str, ...]
    investigation_probability: float | None
    investigation_tier: str | None
    commenter_count: int
    commenter_bundle_id: str
    package_hash: str
    template_hash: str
    model_id: str
    endpoint_called: bool
    forensic_captured: bool
    # endpoint forensic metadata, surfaced from the runtime (never recomputed here). Excluded from the
    # ``report_id`` content address because it is non-deterministic (wall-clock/network).
    latency_ms: float = 0.0
    attempts: int = 0
    tokens: dict | None = None
    endpoint_request_id: str | None = None
    response_status: int | None = None
    prompt_hash: str = ""
    served_model: str = ""
    report_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["commenter_analyses"] = [c.to_dict() for c in self.commenter_analyses]
        return d


# --------------------------------------------------------------------------- #
# Prompt builder — assembles the prompt from package assets only (zero embedded text)
# --------------------------------------------------------------------------- #
def _commenter_ref(author_ref: str) -> str:
    return digest({"a": author_ref}, prefix="chi:")


def _render_commenters(bundle: CommenterHistoryBundle) -> list[dict]:
    return [{"commenter_ref": _commenter_ref(c.author_ref), "author_ref": c.author_ref,
             "activity_sample_count": c.activity_sample_count,
             "matched_prior_neighbors": c.matched_prior_neighbors, "from_cache": c.from_cache}
            for c in bundle.commenters]


def _commenter_history_sections(bundle: CommenterHistoryBundle, ctx: dict) -> dict:
    """Render the commenter-history stage's evidence sections (the ONLY stage-specific part of prompt
    assembly). The investigation echo number arrives via ``ctx`` (from the payload), not the bundle."""
    inv = ctx.get("investigation") or {}
    return {
        "investigation": {"overall_probability": inv.get("overall_probability"),
                          "tier": inv.get("tier"), "commenter_count": bundle.count},
        "commenters": _render_commenters(bundle),
    }


# Register the commenter-history stage with the ONE Canonical Prompt Builder. Reproduces the pre-P3.3
# bytes exactly; the builder core stays stage-agnostic.
_COMMENTER_HISTORY_PROMPT_SPEC = StagePromptSpec(
    stage="commenter_history",
    schema_ref="commenter_history_v1",
    assembled_from="hf-analyst-package (commenter-history stage, via loader)",
    load_assets=load_commenter_history_assets,
    template_of=lambda a: a.template(),
    render_sections=_commenter_history_sections,
    manifest_extra=lambda a, bundle: {
        "template_hash": a.template_hash,
        "contract_hash": a.contract_hash,
        "schema_hash": a.schema_hash,
        "commenter_bundle_id": bundle.bundle_id(),
    },
)
register_stage_prompt(_COMMENTER_HISTORY_PROMPT_SPEC)


def build_commenter_history_prompt_package(
    bundle: CommenterHistoryBundle, *, investigation: dict | None = None, loaded=None, assets=None,
    model_id: str | None = None,
) -> PromptPackage:
    """Assemble the commenter-history PromptPackage via the ONE Canonical Prompt Builder (P3.3). Thin
    stage entry — all assembly lives in ``app.reasoning.prompt.build_prompt``; this only names the
    stage. ``investigation`` carries the engine number the wrapper echoes (never recomputed).
    Byte-identical to the pre-consolidation output. Zero embedded prompt text."""
    return build_prompt("commenter_history", bundle, loaded=loaded, model_id=model_id, assets=assets,
                        investigation=(investigation or {}))


# --------------------------------------------------------------------------- #
# Deterministic Floor — factual per-commenter track-record analysis (no model)
# --------------------------------------------------------------------------- #
def _floor_commenter_analyses(bundle: CommenterHistoryBundle) -> tuple[CommenterHistoryAnalysis, ...]:
    """Factual, deterministic per-commenter analysis from the track-record evidence — the always-
    available Floor. Structured statements only; thin history is 'not enough data', never 'clean'."""
    out = []
    for c in bundle.commenters:
        samples, neighbors, cached = c.activity_sample_count, c.matched_prior_neighbors, c.from_cache
        if neighbors > 0:
            assessment = "established"
        elif samples >= 3:
            assessment = "emerging"
        elif samples == 0:
            assessment = "fresh"
        else:
            assessment = "inconclusive"
        support: tuple[str, ...] = ()
        contra: tuple[str, ...] = ()
        if neighbors > 0:
            support += (f"{neighbors} prior institutional-memory neighbour(s) recurred",)
        if samples == 0:
            contra += ("no posting history on file — thin track record",)
        out.append(CommenterHistoryAnalysis(
            commenter_ref=_commenter_ref(c.author_ref),
            track_record_assessment=assessment,
            history_depth_reasoning=f"{samples} activity sample(s) on file",
            recurrence_reasoning=f"{neighbors} prior institutional-memory neighbour(s) matched",
            provenance_reasoning=("served from cache (a prior scan)" if cached
                                  else "freshly scanned in this investigation"),
            supporting_evidence=support,
            contradictory_evidence=contra,
            uncertainty=(("deterministic floor — no per-commenter model reasoning was available",)
                         + (("thin history — treat as 'not enough data', not 'clean'",) if samples == 0 else ())),
            confidence=0.2,
            reasoning_trace=("read track record", "band by history depth + memory recurrence",
                             "no model reasoning (floor)"),
        ))
    return tuple(out)


# --------------------------------------------------------------------------- #
# The Commenter History runtime
# --------------------------------------------------------------------------- #
def run_commenter_history_analysis(
    context: InvestigationContext,
    bundle: CommenterHistoryBundle | None = None,
    *,
    payload: dict,
    platform: str | None = None,
    settings: Settings | None = None,
) -> CommenterHistoryReport:
    """Run AI-native Commenter History analysis: one inference over the CommenterHistoryBundle,
    Governor-gated, Floor-backed. ``payload`` supplies the deterministic Governor/Floor evidence (the
    same object the Context Builder consumed). Never raises — failure degrades to the Floor."""
    settings = settings or get_settings()
    payload = payload or {}
    bundle = bundle if bundle is not None else build_commenter_history_bundle(context)
    ref = context.investigation.ref or _analyst._ref(context.context_id)
    platform = platform or context.investigation.platform or "unknown"
    investigation = {"overall_probability": payload.get("overall_probability"),
                     "tier": payload.get("overall_tier") or payload.get("tier")}

    loaded = load_package(getattr(settings, "analyst_model_id", None))
    assets = load_commenter_history_assets()
    pp = build_commenter_history_prompt_package(bundle, investigation=investigation, loaded=loaded,
                                                assets=assets)

    # The Governor's evidence bundle — its ``headline()`` is the echo source; same bind params as the
    # comment stage. The per-commenter analyses ride alongside the constitutional wrapper; the
    # runtime's Governor validates the wrapper unchanged (it strips the commenter_analyses sidecar).
    gov_bundle = Binder().bind(payload, grain="comment_section", subject_ref=ref, platform=platform)

    # THE ONE inference — owned by the AI Investigation Runtime. This stage NEVER touches the
    # transport or the Governor: the runtime calls the endpoint once, captures the forensics,
    # echo-guards, runs the MANDATORY Governor, and degrades to the deterministic Floor.
    inference: RuntimeInference = run_stage_inference(pp, gov_bundle, settings=settings)

    if inference.model_backed and inference.raw_obj is not None:
        analyses = _model_commenter_analyses(inference.raw_obj, bundle)
    else:
        analyses = _floor_commenter_analyses(bundle)
    return _report(bundle, loaded, assets, analyses, inference, investigation)


def _model_commenter_analyses(obj: dict, bundle: CommenterHistoryBundle) -> tuple[CommenterHistoryAnalysis, ...]:
    raw_list = obj.get("commenter_analyses") or []
    if not isinstance(raw_list, list) or not raw_list:
        return _floor_commenter_analyses(bundle)  # model omitted the per-commenter detail → factual floor

    def _f(v) -> float:
        try:
            return float(v)
        except (TypeError, ValueError):
            return 0.0

    out = []
    for d in raw_list:
        if not isinstance(d, dict):
            continue
        out.append(CommenterHistoryAnalysis(
            commenter_ref=str(d.get("commenter_ref") or ""),
            track_record_assessment=str(d.get("track_record_assessment") or "inconclusive"),
            history_depth_reasoning=str(d.get("history_depth_reasoning") or ""),
            recurrence_reasoning=str(d.get("recurrence_reasoning") or ""),
            provenance_reasoning=str(d.get("provenance_reasoning") or ""),
            supporting_evidence=tuple(str(x) for x in (d.get("supporting_evidence") or [])),
            contradictory_evidence=tuple(str(x) for x in (d.get("contradictory_evidence") or [])),
            uncertainty=tuple(str(x) for x in (d.get("uncertainty") or [])),
            confidence=_f(d.get("confidence")),
            reasoning_trace=tuple(str(x) for x in (d.get("reasoning_trace") or [])),
        ))
    return tuple(out) or _floor_commenter_analyses(bundle)


def _report(bundle, loaded, assets, analyses, inference: RuntimeInference,
            investigation: dict) -> CommenterHistoryReport:
    trace = inference.trace
    # Content address excludes the non-deterministic forensic capture (latency/tokens/etc.).
    addressed = {"analyses": [a.to_dict() for a in analyses], "provider": inference.provider,
                 "model_backed": inference.model_backed, "governor_verdict": trace.verdict,
                 "commenter_bundle_id": bundle.bundle_id(), "package_hash": loaded.package_hash}
    prob = investigation.get("overall_probability")
    return CommenterHistoryReport(
        commenter_analyses=analyses, provider=inference.provider, model_backed=inference.model_backed,
        fallback=inference.fallback, governor_verdict=trace.verdict,
        governor_trace_id=trace.trace_id(), violation_codes=tuple(trace.violation_codes),
        investigation_probability=(float(prob) if prob is not None else None),
        investigation_tier=investigation.get("tier"),
        commenter_count=bundle.count, commenter_bundle_id=bundle.bundle_id(),
        package_hash=loaded.package_hash, template_hash=assets.template_hash,
        model_id=loaded.model_id, endpoint_called=inference.endpoint_called,
        forensic_captured=inference.forensic_captured,
        latency_ms=inference.latency_ms, attempts=inference.attempts, tokens=inference.tokens,
        endpoint_request_id=inference.endpoint_request_id, response_status=inference.response_status,
        prompt_hash=inference.prompt_hash, served_model=inference.served_model,
        report_id=digest(addressed, prefix="chr:"),
    )


# --------------------------------------------------------------------------- #
# Compatibility layer — supply the existing commenter shape (UI unchanged)
# --------------------------------------------------------------------------- #
def to_commenter_compat(report: CommenterHistoryReport) -> dict:
    """Map the AI CommenterHistoryReport back to a commenter-shaped projection the existing UI can
    consume, so the current commenter display keeps functioning unmodified. The engine number is
    echoed (never recomputed); each commenter carries its AI track-record assessment + provenance."""
    return {
        "investigation_probability": report.investigation_probability or 0.0,
        "investigation_tier": report.investigation_tier or "low",
        "commenter_count": report.commenter_count,
        "provider": report.provider,
        "model_backed": report.model_backed,
        "commenters": [
            {"commenter_ref": a.commenter_ref, "track_record_assessment": a.track_record_assessment,
             "confidence": a.confidence}
            for a in report.commenter_analyses
        ],
    }


__all__ = [
    "CommenterHistoryAnalysis", "CommenterHistoryReport",
    "build_commenter_history_prompt_package", "run_commenter_history_analysis", "to_commenter_compat",
]
