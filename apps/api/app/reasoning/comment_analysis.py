"""AI-Native Comment Analysis (Phase P3.1) — the first migrated reasoning stage.

Mistral reasons about every individual comment; the deterministic engine only produces evidence.
The flow is exactly the canonical architecture:

    CommentEvidenceBundle (P3.0)  →  Package Loader (P1.2)  →  Prompt Builder (package assets only)
      →  ONE Hugging Face request (via the ONE transport)  →  Mistral  →  Governor  →  typed report.

Per the approved P3.1 decision, the model returns per-comment :class:`CommentAnalysis` objects inside
ONE comment-section assessment that echoes the deterministic thread number, so the existing
constitutional Governor validates the wrapper **unchanged**. The deterministic Floor stays available
and produces a factual per-comment analysis when the endpoint is unreachable or the ruling is
rejected. This module embeds ZERO prompt text — all scaffolding comes from the comment package asset.

Only Comment Analysis is migrated. No other stage, prompt, package asset, heuristic, endpoint,
result, or report is changed. A compatibility mapping keeps the existing thread UI working.
"""
from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import asdict, dataclass
from typing import Any

from app.core.config import Settings, get_settings
from app.evidence import Binder
from app.evidence.bundle import digest
from app.reasoning import analyst as _analyst
from app.reasoning.context.investigation import InvestigationContext
from app.reasoning.evidence_bundles import CommentEvidenceBundle, build_comment_bundle
from app.reasoning.package_loader import load_comment_assets, load_package
from app.reasoning.prompt.builder import PromptPackage
from app.reasoning.runtime import RuntimeInference, run_stage_inference

logger = logging.getLogger("omi.reasoning.comment_analysis")


# --------------------------------------------------------------------------- #
# Typed output — structured reasoning only (no prose/markdown/UI)
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class CommentAnalysis:
    """One comment's structured analysis. Immutable; the required P3.1 fields only."""

    comment_ref: str
    authenticity_assessment: str
    manipulation_likelihood: float
    behavioral_reasoning: str
    linguistic_reasoning: str
    engagement_reasoning: str
    supporting_evidence: tuple[str, ...] = ()
    contradictory_evidence: tuple[str, ...] = ()
    uncertainty: tuple[str, ...] = ()
    confidence: float = 0.0
    reasoning_trace: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class CommentAnalysisReport:
    """The immutable output of the Comment Analysis stage: the per-comment analyses + the
    Governor-validated comment-section wrapper's provenance. Content-addressed by ``report_id``."""

    comment_analyses: tuple[CommentAnalysis, ...]
    provider: str
    model_backed: bool
    fallback: bool
    governor_verdict: str
    governor_trace_id: str
    violation_codes: tuple[str, ...]
    thread_probability: float | None
    thread_tier: str | None
    comment_count: int
    comment_bundle_id: str
    package_hash: str
    comment_template_hash: str
    model_id: str
    endpoint_called: bool
    forensic_captured: bool
    # C4 — endpoint forensic metadata, surfaced from the runtime (never recomputed here). Excluded
    # from the ``report_id`` content address because it is non-deterministic (wall-clock/network).
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
        d["comment_analyses"] = [c.to_dict() for c in self.comment_analyses]
        return d


# --------------------------------------------------------------------------- #
# Prompt builder — assembles the comment prompt from package assets only (zero embedded text)
# --------------------------------------------------------------------------- #
def _comment_ref(author_ref: str, text: str, created_at: str | None) -> str:
    return digest({"a": author_ref, "t": text, "c": created_at}, prefix="cm:")


def _render_comments(bundle: CommentEvidenceBundle) -> list[dict]:
    return [{"comment_ref": _comment_ref(c.author_ref, c.text, c.created_at), "author_ref": c.author_ref,
             "text": c.text, "created_at": c.created_at} for c in bundle.comments]


def build_comment_prompt_package(
    bundle: CommentEvidenceBundle, *, loaded=None, comment_assets=None, model_id: str | None = None,
) -> PromptPackage:
    """Assemble the comment-analysis PromptPackage from package assets + the CommentEvidenceBundle.
    Zero embedded prompt text — every header/instruction/contract comes from the comment package
    asset; the shared base prompt / constitution / framework / knowledge come from the loader."""
    lp = loaded or load_package(model_id)
    ca = comment_assets or load_comment_assets()
    tmpl = ca.comment_template()

    system = "\n\n".join([
        lp.system_prompt,
        "# REASONING & GOVERNANCE CONSTITUTION\n" + lp.constitution,
        "# SPECIALIST INVESTIGATION FRAMEWORK\n" + json.dumps(lp.framework(), ensure_ascii=False, sort_keys=True),
        "# KNOWLEDGE LIBRARY\n" + json.dumps(lp.knowledge()[:12], ensure_ascii=False, sort_keys=True),
        tmpl["system_task"],
        "# OUTPUT CONTRACT\n" + tmpl["response_contract"],
    ]).strip()

    thread = {"thread_probability": bundle.thread_probability, "thread_tier": bundle.thread_tier,
              "comment_count": bundle.comment_count}
    sections = {"thread": thread, "comments": _render_comments(bundle)}
    ev = [tmpl["evidence_preamble"]]
    for s in tmpl["evidence_sections"]:
        ev.append(s["header"] + "\n" + json.dumps(sections.get(s["section"], {}), ensure_ascii=False, sort_keys=True))
    ev.append(tmpl["evidence_instruction"])
    user = "\n\n".join(ev).strip()

    manifest = {
        "assembled_from": "hf-analyst-package (comment stage, via loader)",
        "package_hash": lp.package_hash, "prompt_hash": lp.prompt_hash,
        "constitution_hash": lp.constitution_hash, "framework_hash": lp.framework_hash,
        "knowledge_hash": lp.knowledge_hash, "comment_template_hash": ca.comment_template_hash,
        "comment_contract_hash": ca.comment_contract_hash, "comment_schema_hash": ca.comment_schema_hash,
        "comment_bundle_id": bundle.bundle_id(), "model_id": lp.model_id,
        "response_format": "json_object", "schema_ref": "comment_analysis_v1",
        "system_prompt_sha": "sys:" + hashlib.sha256(system.encode("utf-8")).hexdigest()[:24],
    }
    ppid = digest({"system": system, "user": user, "manifest": manifest}, prefix="pp:")
    return PromptPackage(system=system, user=user, response_format="json_object",
                         schema_ref="comment_analysis_v1", model_id=lp.model_id,
                         manifest=manifest, prompt_package_id=ppid)


# --------------------------------------------------------------------------- #
# Deterministic Floor — factual per-comment analysis (no model)
# --------------------------------------------------------------------------- #
def _floor_comment_analyses(bundle: CommentEvidenceBundle) -> tuple[CommentAnalysis, ...]:
    """Factual, deterministic per-comment analysis from the comment evidence — the always-available
    Floor. Structured statements only; the engine's thread number is the per-comment prior."""
    prob = float(bundle.thread_probability or 0.0)
    tier = str(bundle.thread_tier or "low")
    verdict = {"low": "inconclusive", "moderate": "mixed", "elevated": "mixed",
               "high": "inauthentic"}.get(tier, "inconclusive")
    out = []
    for c in bundle.comments:
        ref = _comment_ref(c.author_ref, c.text, c.created_at)
        length = len(c.text)
        out.append(CommentAnalysis(
            comment_ref=ref, authenticity_assessment=verdict, manipulation_likelihood=round(prob, 6),
            behavioral_reasoning=f"comment length {length} chars; author {c.author_ref}",
            linguistic_reasoning=f"{length} characters of text observed",
            engagement_reasoning=("posted on parent " + c.parent_ref) if c.parent_ref else "no parent context",
            supporting_evidence=((f"thread suspicion {round(prob, 3)} ({tier})",) if prob >= 0.5 else ()),
            contradictory_evidence=((f"thread suspicion {round(prob, 3)} is below the elevated gate",)
                                    if prob < 0.5 else ()),
            uncertainty=("deterministic floor — no per-comment model reasoning was available",),
            confidence=0.2, reasoning_trace=("echo thread number", "band by thread tier",
                                             "no model reasoning (floor)"),
        ))
    return tuple(out)


# --------------------------------------------------------------------------- #
# The Comment Analysis runtime
# --------------------------------------------------------------------------- #
def run_comment_analysis(
    context: InvestigationContext,
    bundle: CommentEvidenceBundle | None = None,
    *,
    payload: dict,
    platform: str | None = None,
    settings: Settings | None = None,
) -> CommentAnalysisReport:
    """Run AI-native Comment Analysis: one inference over the CommentEvidenceBundle, Governor-gated,
    Floor-backed. ``payload`` supplies the deterministic Governor/Floor evidence (same object the
    Context Builder consumed). Never raises — failure degrades to the deterministic Floor."""
    settings = settings or get_settings()
    payload = payload or {}
    bundle = bundle if bundle is not None else build_comment_bundle(context)
    ref = context.investigation.ref or _analyst._ref(context.context_id)
    platform = platform or context.investigation.platform or "unknown"

    loaded = load_package(getattr(settings, "analyst_model_id", None))
    comment_assets = load_comment_assets()
    pp = build_comment_prompt_package(bundle, loaded=loaded, comment_assets=comment_assets)

    # The Governor's evidence bundle — its ``headline()`` is the echo source; same bind params as the
    # council Orchestrator. The per-comment CommentAnalysis objects ride alongside the constitutional
    # wrapper; the runtime's Governor validates the wrapper unchanged (P3.1 grain decision).
    gov_bundle = Binder().bind(payload, grain="comment_section", subject_ref=ref, platform=platform)

    # THE ONE inference — owned by the AI Investigation Runtime (P3.1.6 cutover). This stage NEVER
    # touches the transport or the Governor: the runtime calls the endpoint once, captures the full
    # forensics, echo-guards, runs the MANDATORY Governor, and degrades to the deterministic Floor.
    inference: RuntimeInference = run_stage_inference(pp, gov_bundle, settings=settings)

    # Typed per-comment extraction — the model's individual-comment reasoning when its wrapper was
    # permitted and present, else the always-available deterministic per-comment Floor.
    if inference.model_backed and inference.raw_obj is not None:
        analyses = _model_comment_analyses(inference.raw_obj, bundle)
    else:
        analyses = _floor_comment_analyses(bundle)
    return _report(bundle, loaded, comment_assets, analyses, inference)


def _model_comment_analyses(obj: dict, bundle: CommentEvidenceBundle) -> tuple[CommentAnalysis, ...]:
    raw_list = obj.get("comment_analyses") or []
    if not isinstance(raw_list, list) or not raw_list:
        return _floor_comment_analyses(bundle)  # model omitted the per-comment detail → factual floor

    def _f(v) -> float:
        try:
            return float(v)
        except (TypeError, ValueError):
            return 0.0

    out = []
    for d in raw_list:
        if not isinstance(d, dict):
            continue
        out.append(CommentAnalysis(
            comment_ref=str(d.get("comment_ref") or ""),
            authenticity_assessment=str(d.get("authenticity_assessment") or "inconclusive"),
            manipulation_likelihood=_f(d.get("manipulation_likelihood")),
            behavioral_reasoning=str(d.get("behavioral_reasoning") or ""),
            linguistic_reasoning=str(d.get("linguistic_reasoning") or ""),
            engagement_reasoning=str(d.get("engagement_reasoning") or ""),
            supporting_evidence=tuple(str(x) for x in (d.get("supporting_evidence") or [])),
            contradictory_evidence=tuple(str(x) for x in (d.get("contradictory_evidence") or [])),
            uncertainty=tuple(str(x) for x in (d.get("uncertainty") or [])),
            confidence=_f(d.get("confidence")),
            reasoning_trace=tuple(str(x) for x in (d.get("reasoning_trace") or [])),
        ))
    return tuple(out) or _floor_comment_analyses(bundle)


def _report(bundle, loaded, comment_assets, analyses,
            inference: RuntimeInference) -> CommentAnalysisReport:
    trace = inference.trace
    # Content address excludes the non-deterministic forensic capture (latency/tokens/etc.).
    addressed = {"analyses": [a.to_dict() for a in analyses], "provider": inference.provider,
                 "model_backed": inference.model_backed, "governor_verdict": trace.verdict,
                 "comment_bundle_id": bundle.bundle_id(), "package_hash": loaded.package_hash}
    return CommentAnalysisReport(
        comment_analyses=analyses, provider=inference.provider, model_backed=inference.model_backed,
        fallback=inference.fallback, governor_verdict=trace.verdict,
        governor_trace_id=trace.trace_id(), violation_codes=tuple(trace.violation_codes),
        thread_probability=bundle.thread_probability, thread_tier=bundle.thread_tier,
        comment_count=bundle.comment_count, comment_bundle_id=bundle.bundle_id(),
        package_hash=loaded.package_hash, comment_template_hash=comment_assets.comment_template_hash,
        model_id=loaded.model_id, endpoint_called=inference.endpoint_called,
        forensic_captured=inference.forensic_captured,
        # C4 — the runtime's endpoint forensics survive into the typed result.
        latency_ms=inference.latency_ms, attempts=inference.attempts, tokens=inference.tokens,
        endpoint_request_id=inference.endpoint_request_id, response_status=inference.response_status,
        prompt_hash=inference.prompt_hash, served_model=inference.served_model,
        report_id=digest(addressed, prefix="car:"),
    )


# --------------------------------------------------------------------------- #
# Compatibility layer — keep the existing thread UI working
# --------------------------------------------------------------------------- #
def to_thread_compat(report: CommentAnalysisReport) -> dict:
    """Map the AI CommentAnalysisReport back to the thread-shaped fields the existing UI consumes,
    so the current comment display keeps functioning until a future UI migration. The deterministic
    thread_scan remains the live UI source; this proves the report can supply the same shape."""
    return {
        "overall_probability": report.thread_probability or 0.0,
        "tier": report.thread_tier or "low",
        "comment_count": report.comment_count,
        "provider": report.provider,
        "model_backed": report.model_backed,
    }


__all__ = [
    "CommentAnalysis", "CommentAnalysisReport", "build_comment_prompt_package",
    "run_comment_analysis", "to_thread_compat",
]
