"""AI-Native Investigation Summary (Phase P3.4) — the overall investigation assessment as a stage.

The Investigation Summary is the whole-investigation synthesis the website's analyst panel renders. It
is now **just another AI reasoning stage**, exactly like Comment Analysis and Commenter History:

    InvestigationSummaryBundle (P3.0, enriched P3.4)  →  Package Loader (P1.2)
      →  Canonical Stage Prompt Builder (package assets only)  →  AI Investigation Runtime
      (the ONE endpoint + Governor + Floor + forensic path)  →  Mistral  →  Governor  →  assessment.

Unlike the comment / commenter-history stages it introduces NO new output schema: its output contract is
the EXISTING analyst response schema (``schema/analyst_response_schema.json``) — the same structured
assessment the website already renders — so the compatibility layer, the Governor, and the deterministic
Floor are all unchanged. This module embeds ZERO prompt text (all scaffolding comes from the
investigation-summary package asset) and OWNS no orchestration/endpoint/Governor/Floor logic: the stage
runner is :func:`app.reasoning.analyst._assess_core`, which hands the assembled prompt to
:func:`app.reasoning.runtime.run_stage_inference` under the legacy judge-then-floor semantics.

This is the last production reasoning path to migrate onto the canonical stage architecture: after it,
the general Investigation Summary no longer assembles its prompt with the legacy ``PromptBuilder`` +
``build_user_message`` + inline ``PromptPackage``.
"""
from __future__ import annotations

import logging
from typing import Any

from app.reasoning.evidence_bundles import InvestigationSummaryBundle
from app.reasoning.package_loader import load_investigation_summary_assets
from app.reasoning.prompt import PromptPackage, StagePromptSpec, build_prompt, register_stage_prompt

logger = logging.getLogger("omi.reasoning.investigation_summary_analysis")


# --------------------------------------------------------------------------- #
# Prompt builder — assembles the prompt from package assets only (zero embedded text)
# --------------------------------------------------------------------------- #
def _investigation_summary_sections(bundle: InvestigationSummaryBundle, ctx: dict) -> dict:
    """Render the investigation-summary stage's evidence sections from the enriched bundle (the ONLY
    stage-specific part of prompt assembly; everything else is the shared canonical builder). Pure
    projection of the bundle's measured evidence — no recomputation, no prose."""
    coord = bundle.coordination
    acct = bundle.accounts_digest
    return {
        "investigation": {
            "overall_probability": bundle.overall_probability, "overall_tier": bundle.overall_tier,
            "confidence": bundle.confidence, "convergence_score": bundle.convergence_score,
            "inputs_provided": list(bundle.inputs_provided), "platform": bundle.platform,
            "post_content_id": bundle.post_content_id,
        },
        "coordination": ({
            "coordination_score": coord.coordination_score, "coordination_tier": coord.coordination_tier,
            "single_axis_capped": coord.single_axis_capped,
            "discriminative_methods": list(coord.discriminative_methods),
            "cluster_count": coord.cluster_count,
        } if coord is not None else {}),
        "drivers": [{"name": c.name, "impact": c.impact, "direction": c.direction,
                     "supplemental": c.supplemental} for c in bundle.contributions],
        "accounts": ({
            "count": acct.count, "flagged_count": acct.flagged_count, "high_count": acct.high_count,
            "max_probability": acct.max_probability, "mean_probability": acct.mean_probability,
        } if acct is not None else {}),
        "cross_links": [{"kind": l.kind, "severity": l.severity, "evidence": list(l.evidence),
                         "related_refs": list(l.related_refs)} for l in bundle.cross_links],
        "weak_signals": list(bundle.weak_signals),
        "memory": [{"type": p.type, "label": p.label, "confidence": p.confidence,
                    "influence_class": p.influence_class, "epistemic_status": p.epistemic_status}
                   for p in bundle.memory_priors],
        "components": bundle.component_map(),
    }


# Register the investigation-summary stage with the ONE Canonical Prompt Builder. The builder core
# stays stage-agnostic; this spec supplies only what varies for the summary stage (assets, sections,
# schema ref, manifest fields). Registered at import — so importing the stage entry registers it.
_INVESTIGATION_SUMMARY_PROMPT_SPEC = StagePromptSpec(
    stage="investigation_summary",
    schema_ref="schema/analyst_response_schema.json",
    assembled_from="hf-analyst-package (investigation-summary stage, via loader)",
    load_assets=load_investigation_summary_assets,
    template_of=lambda a: a.template(),
    render_sections=_investigation_summary_sections,
    manifest_extra=lambda a, bundle: {
        "investigation_summary_template_hash": a.template_hash,
        "investigation_summary_contract_hash": a.contract_hash,
        "investigation_summary_schema_hash": a.schema_hash,
        "investigation_summary_bundle_id": bundle.bundle_id(),
    },
)
register_stage_prompt(_INVESTIGATION_SUMMARY_PROMPT_SPEC)


def build_investigation_summary_prompt_package(
    bundle: InvestigationSummaryBundle, *, loaded=None, assets=None, model_id: str | None = None,
) -> PromptPackage:
    """Assemble the investigation-summary PromptPackage via the ONE Canonical Prompt Builder (P3.3/P3.4).
    Thin stage entry — all assembly lives in ``app.reasoning.prompt.build_prompt``; this only names the
    stage. Zero embedded prompt text; the output contract is the existing analyst response schema."""
    return build_prompt("investigation_summary", bundle, loaded=loaded, model_id=model_id, assets=assets)


__all__ = ["build_investigation_summary_prompt_package"]
