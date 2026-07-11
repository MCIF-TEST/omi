"""The Comprehensive Investigation stage — the ONE single-inference investigation prompt builder.

This is the canonical AI-native path: ONE Mistral inference reasons over the COMPLETE, budgeted
InvestigationPackage evidence and returns the seven sections (six per-domain reasoning sidecars + the
Lead-Investigator synthesis wrapper). Like every other stage it assembles its prompt through the ONE
Canonical Stage Prompt Builder (:func:`app.reasoning.prompt.build_prompt`) — it embeds ZERO prompt text;
all scaffolding comes from the comprehensive-investigation package asset (via the loader), and the user
message is the budgeted, normalized evidence rendered from the complete
:class:`~app.reasoning.investigation_composer.InvestigationPackage`.

Crucially, the Prompt Builder's canonical investigation input is now the **InvestigationPackage** (not a
summary bundle): Mistral receives the actual structured evidence content of the complete package, in one
request. This module owns no orchestration/endpoint/Governor/Floor logic — the stage runner is
:func:`app.reasoning.analyst._assess_core`, which hands the assembled prompt to
:func:`app.reasoning.runtime.run_stage_inference`.
"""
from __future__ import annotations

import logging
from typing import Any

from app.reasoning.investigation_render import RenderedEvidence, render_investigation_evidence
from app.reasoning.package_loader import load_comprehensive_investigation_assets
from app.reasoning.prompt import PromptPackage, StagePromptSpec, build_prompt, register_stage_prompt

logger = logging.getLogger("omi.reasoning.comprehensive_investigation_analysis")

COMPREHENSIVE_INVESTIGATION_STAGE = "comprehensive_investigation"

# Content-addressed 1-entry memo so the single render is shared between ``render_sections`` and
# ``manifest_extra`` within one ``build_prompt`` call. Keyed by ``package_id`` (a content hash), so it
# is always correct to reuse.
_RENDER_MEMO: dict[str, RenderedEvidence] = {}


def _rendered(package: Any) -> RenderedEvidence:
    pid = getattr(package, "package_id", "")
    memo = _RENDER_MEMO.get(pid)
    if memo is None:
        memo = render_investigation_evidence(package)
        _RENDER_MEMO.clear()          # keep only the most recent (investigations are one-shot)
        _RENDER_MEMO[pid] = memo
    return memo


def _comprehensive_sections(package: Any, ctx: dict) -> dict:
    """Render the complete InvestigationPackage into the model-facing evidence sections — the seven
    budgeted domain sections plus the coverage manifest + alias legend (disclosure). Pure projection of
    measured, budgeted evidence; no recomputation, no prose, no verdict."""
    rv = _rendered(package)
    return {
        **rv.sections,                 # the seven domain sections (normalized + budgeted)
        "coverage": rv.coverage,       # evidence-coverage manifest (observed/represented/omitted)
        "legend": rv.legend,           # reversible alias legend (aliases -> stable refs)
    }


def _manifest_extra(assets: Any, package: Any) -> dict:
    """Stage manifest fields — the asset hashes + the package identity + the sidecar section keys +
    the coverage summary. The full legend/coverage ride in the user message (disclosure to the model);
    the manifest keeps a lean provenance summary."""
    rv = _rendered(package)
    acct_cov = (rv.coverage.get("domains", {}) or {}).get("account_analysis", {})
    comm_cov = (rv.coverage.get("domains", {}) or {}).get("comment_analysis", {})
    return {
        "comprehensive_investigation_template_hash": assets.template_hash,
        "comprehensive_investigation_contract_hash": assets.contract_hash,
        "comprehensive_investigation_schema_hash": assets.schema_hash,
        "comprehensive_section_keys": list(assets.section_keys),
        "investigation_package_id": getattr(package, "package_id", ""),
        "evidence_snapshot_id": getattr(package, "snapshot_id", ""),
        "evidence_coverage_mode": rv.coverage.get("mode"),
        "evidence_tokens_est": rv.tokens,
        "evidence_sampling_truncated": bool(rv.coverage.get("sampling", {}).get("truncated_upstream")),
        "evidence_represented_accounts": acct_cov.get("represented"),
        "evidence_omitted_accounts": acct_cov.get("omitted"),
        "evidence_deduplicated_comments": comm_cov.get("deduplicated"),
    }


_COMPREHENSIVE_PROMPT_SPEC = StagePromptSpec(
    stage=COMPREHENSIVE_INVESTIGATION_STAGE,
    schema_ref="schema/analyst_response_schema.json",
    assembled_from="hf-analyst-package (comprehensive-investigation stage, via loader)",
    load_assets=load_comprehensive_investigation_assets,
    template_of=lambda a: a.template(),
    render_sections=_comprehensive_sections,
    manifest_extra=_manifest_extra,
)
register_stage_prompt(_COMPREHENSIVE_PROMPT_SPEC)


def build_comprehensive_investigation_prompt_package(
    package: Any, *, loaded=None, assets=None, model_id: str | None = None,
) -> PromptPackage:
    """Assemble the comprehensive-investigation PromptPackage via the ONE Canonical Prompt Builder — the
    single production investigation prompt. Its evidence input is the COMPLETE InvestigationPackage; the
    complete budgeted evidence becomes the model-facing user message in ONE request. Thin stage entry —
    all assembly lives in ``build_prompt``; this only names the stage."""
    return build_prompt(COMPREHENSIVE_INVESTIGATION_STAGE, package, loaded=loaded, model_id=model_id,
                        assets=assets)


__all__ = ["COMPREHENSIVE_INVESTIGATION_STAGE", "build_comprehensive_investigation_prompt_package"]
