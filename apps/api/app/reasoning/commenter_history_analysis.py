"""Commenter-history-stage prompt builder — the commenter Evidence Bundle → PromptPackage assembly.

The endpoint-capable per-stage Commenter History *runner* has been RETIRED (single-inference cutover):
commenter-track-record intelligence is now a section of the ONE comprehensive investigation inference
(its ``commenter_history_reasoning`` sidecar), not a separate endpoint stage. There is exactly one
production investigation inference path (:func:`app.reasoning.analyst._assess_core`); this module no
longer reaches the endpoint, the Governor, or the Floor.

What remains is the commenter-history stage's contribution to the ONE Canonical Stage Prompt Builder —
the evidence-section rendering + the :class:`StagePromptSpec` registration — so the builder-consolidation
proof (one stage-agnostic ``build_prompt``) and the published commenter-history package asset keep their
meaning. This module embeds ZERO prompt text; it builds a PromptPackage and calls no model.
"""
from __future__ import annotations

import logging

from app.evidence.bundle import digest
from app.reasoning.evidence_bundles import CommenterHistoryBundle
from app.reasoning.package_loader import load_commenter_history_assets
from app.reasoning.prompt import PromptPackage, StagePromptSpec, build_prompt, register_stage_prompt

logger = logging.getLogger("omi.reasoning.commenter_history_analysis")


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
    Byte-identical to the pre-consolidation output. Zero embedded prompt text; calls no model."""
    return build_prompt("commenter_history", bundle, loaded=loaded, model_id=model_id, assets=assets,
                        investigation=(investigation or {}))


__all__ = ["build_commenter_history_prompt_package"]
