"""Comment-stage prompt builder — the comment Evidence Bundle → PromptPackage assembly.

The endpoint-capable per-stage Comment Analysis *runner* has been RETIRED (single-inference cutover):
comment intelligence is now a section of the ONE comprehensive investigation inference (its
``comment_reasoning`` sidecar), not a separate endpoint stage. There is exactly one production
investigation inference path (:func:`app.reasoning.analyst._assess_core`); this module no longer reaches
the endpoint, the Governor, or the Floor.

What remains is the comment stage's contribution to the ONE Canonical Stage Prompt Builder — the
evidence-section rendering + the :class:`StagePromptSpec` registration — so the builder-consolidation
proof (one stage-agnostic ``build_prompt``) and the published comment package asset keep their meaning.
This module embeds ZERO prompt text; it builds a PromptPackage and calls no model.
"""
from __future__ import annotations

import logging

from app.evidence.bundle import digest
from app.reasoning.evidence_bundles import CommentEvidenceBundle
from app.reasoning.package_loader import load_comment_assets
from app.reasoning.prompt import PromptPackage, StagePromptSpec, build_prompt, register_stage_prompt

logger = logging.getLogger("omi.reasoning.comment_analysis")


# --------------------------------------------------------------------------- #
# Prompt builder — assembles the comment prompt from package assets only (zero embedded text)
# --------------------------------------------------------------------------- #
def _comment_ref(author_ref: str, text: str, created_at: str | None) -> str:
    return digest({"a": author_ref, "t": text, "c": created_at}, prefix="cm:")


def _render_comments(bundle: CommentEvidenceBundle) -> list[dict]:
    return [{"comment_ref": _comment_ref(c.author_ref, c.text, c.created_at), "author_ref": c.author_ref,
             "text": c.text, "created_at": c.created_at} for c in bundle.comments]


def _comment_sections(bundle: CommentEvidenceBundle, ctx: dict) -> dict:
    """Render the comment stage's evidence sections from the bundle (the ONLY comment-specific part
    of prompt assembly; everything else is the shared canonical builder)."""
    return {
        "thread": {"thread_probability": bundle.thread_probability, "thread_tier": bundle.thread_tier,
                   "comment_count": bundle.comment_count},
        "comments": _render_comments(bundle),
    }


# Register the comment stage with the ONE Canonical Prompt Builder. The builder core stays
# stage-agnostic; this spec supplies only what varies for the comment stage (assets, sections,
# schema ref, manifest fields). Registered at import — reproduces the pre-P3.3 bytes exactly.
_COMMENT_PROMPT_SPEC = StagePromptSpec(
    stage="comment",
    schema_ref="comment_analysis_v1",
    assembled_from="hf-analyst-package (comment stage, via loader)",
    load_assets=load_comment_assets,
    template_of=lambda a: a.comment_template(),
    render_sections=_comment_sections,
    manifest_extra=lambda a, bundle: {
        "comment_template_hash": a.comment_template_hash,
        "comment_contract_hash": a.comment_contract_hash,
        "comment_schema_hash": a.comment_schema_hash,
        "comment_bundle_id": bundle.bundle_id(),
    },
)
register_stage_prompt(_COMMENT_PROMPT_SPEC)


def build_comment_prompt_package(
    bundle: CommentEvidenceBundle, *, loaded=None, comment_assets=None, model_id: str | None = None,
) -> PromptPackage:
    """Assemble the comment-analysis PromptPackage via the ONE Canonical Prompt Builder (P3.3). Thin
    stage entry — all assembly lives in ``app.reasoning.prompt.build_prompt``; this only names the
    stage. Byte-identical to the pre-consolidation output. Zero embedded prompt text; calls no model."""
    return build_prompt("comment", bundle, loaded=loaded, model_id=model_id, assets=comment_assets)


__all__ = ["build_comment_prompt_package"]
