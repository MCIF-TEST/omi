"""The ONE Canonical (stage) Prompt Builder. Assemble every reasoning stage's prompt identically.

``build_prompt(stage, bundle)`` is the single prompt-assembly implementation for every AI reasoning
stage (comment, commenter_history, and every future stage). It is **stage-agnostic**: it knows nothing
about any particular stage. A stage registers a small :class:`StagePromptSpec`, its package assets,
its evidence-section rendering, its schema ref, and its manifest fields, and the builder does the
identical assembly for all of them:

    system  = omi_analyst base + constitution + knowledge library
              + the stage's task block + the stage's output contract        (all package assets)
    user    = the stage's evidence sections, each rendered as JSON data      (from the Evidence Bundle)
    manifest= content hashes of every asset + the bundle id + the stage schema ref
    -> one content-addressed :class:`PromptPackage`

Two invariants this module upholds:

1. **No embedded stage prompt text**, every task/contract/section-header that is STAGE-specific comes
   from the stage's package template (loaded via the spec). Only stage-invariant structural glue
   (``"# OUTPUT CONTRACT\\n"`` and the section labels) lives here, identical for every stage.
2. **It obtains everything through the Package Loader**, the shared base prompt / constitution /
   framework / knowledge come from :func:`load_package`; the stage template/contract/schema come from
   the stage's loader accessor. The builder imports no prompt/template source module.

No model, no endpoint, no inference, the builder only assembles.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Callable

from app.evidence.bundle import digest
from app.reasoning.package_loader import load_package

from .builder import PromptPackage

_KNOWLEDGE_LIMIT = 12
_RESPONSE_FORMAT = "json_object"


@dataclass(frozen=True)
class StagePromptSpec:
    """A stage's contribution to the canonical builder. Everything that varies BETWEEN stages, and
    nothing that is shared. The builder holds one of these per registered stage and performs the
    identical assembly for all of them. A stage registers its spec via :func:`register_stage_prompt`;
    the builder itself never imports or names any stage."""

    stage: str
    schema_ref: str
    assembled_from: str
    load_assets: Callable[[], Any]                    # -> the stage's verified package assets
    template_of: Callable[[Any], dict]                # assets -> the stage assembly template dict
    render_sections: Callable[[Any, dict], dict]      # (bundle, ctx) -> {evidence_section: data}
    manifest_extra: Callable[[Any, Any], dict]        # (assets, bundle) -> stage manifest fields


_STAGE_REGISTRY: dict[str, StagePromptSpec] = {}


def assemble_stage_system(lp, tmpl: dict) -> str:
    """The ONE system-message assembly shared by every stage, the stable instruction hierarchy the
    model receives: the omi_analyst base prompt + constitution + knowledge library + the stage task +
    the stage output contract. Factored out so a caller that needs the compiled system WITHOUT running
    an inference (e.g. the Master Analyst Protocol asset compiled for an OpenRouter Preset) produces
    byte-identical text to what :func:`build_prompt` sends.

    The specialist-council framework is deliberately NOT injected into the model instructions: the
    single-inference architecture has one Lead Investigator, not a 13-specialist council, so the
    council catalog would contradict that identity and spend tokens on unused metadata. The framework
    remains internal. Still loaded, still content-hashed, and still recorded in the manifest
    (``framework_hash``), so provenance and drift protection are unchanged."""
    return "\n\n".join([
        lp.system_prompt,
        "# REASONING & GOVERNANCE CONSTITUTION\n" + lp.constitution,
        "# KNOWLEDGE LIBRARY (reference doctrine. Concepts, terminology, investigative context; "
        "never evidence, never citable, never proof)\n"
        + json.dumps(lp.knowledge()[:_KNOWLEDGE_LIMIT], ensure_ascii=False, sort_keys=True),
        tmpl["system_task"],
        "# OUTPUT CONTRACT\n" + tmpl["response_contract"],
    ]).strip()


def register_stage_prompt(spec: StagePromptSpec) -> None:
    """Register a stage's prompt spec. Called by each stage module at import time, so the builder
    core never imports a stage. Idempotent (re-registration overwrites with the same spec)."""
    _STAGE_REGISTRY[spec.stage] = spec


def registered_stages() -> tuple[str, ...]:
    return tuple(sorted(_STAGE_REGISTRY))


def _closing_directive(sections: dict) -> str:
    """The short reminder that rides at the END of the evidence, after the alias legend.

    Only the constraints that actually fail in production, and only for stages that carry accounts.
    Every line here earns its per-request cost:

    * **Naming the aliases** is the one that buys the most. A model handed 25 accounts sometimes
      returns 21, and until it is told the expected set it has no way to notice; we could detect the
      shortfall but the model could not self-correct. Listing them turns "more verdicts" from a hope
      into a checkable instruction.
    * **The verification warning** is repeated here because it changes behaviour at generation time,
      and it is the last thing read before the model writes.
    * **Plain English** and **score from this account's own row** are the two quality failures that
      survive the protocol most often.
    """
    legend = sections.get("legend") or sections.get("alias_legend") or {}
    aliases = sorted((legend.get("accounts") or {}).keys(), key=lambda a: (len(a), a))
    if not aliases:
        return ""
    shown = ", ".join(aliases[:60]) + (", ..." if len(aliases) > 60 else "")
    return (
        "## Before you answer\n"
        f"The evidence above contains {len(aliases)} accounts: {shown}. Return EXACTLY "
        f"{len(aliases)} items in commenter_assessments, one per alias, none omitted and none "
        "invented, each with all eight signals.\n"
        "Take every figure and quote from that account's OWN row. Carrying a neighbour's number or "
        "wording across is the worst error here.\n"
        "Quotes and figures are machine-checked against the rows: one that does not match discards "
        "that account's whole assessment. Quote exactly or describe instead.\n"
        "A mostly-repost, one-subject feed is ordinary use and caps at 49. Nothing reaches 75 "
        "without a quotable tell: text this account repeated, a scheduler-regular rhythm, or its "
        "own pitch.\n"
        "No alias and no mention of another account in the assessment text. Short plain sentences."
    )


def build_prompt(
    stage: str,
    bundle: Any,
    *,
    loaded=None,
    model_id: str | None = None,
    assets: Any = None,
    **ctx: Any,
) -> PromptPackage:
    """Assemble the :class:`PromptPackage` for one ``stage`` over its Evidence ``bundle``, exclusively
    from package assets. Deterministic + content-addressed; performs no inference and calls no model.
    Extra keyword context (e.g. the investigation echo number for the commenter-history stage) is
    passed through to the stage's ``render_sections``."""
    spec = _STAGE_REGISTRY.get(stage)
    if spec is None:
        raise KeyError(f"no prompt spec registered for stage {stage!r}; "
                       f"registered: {registered_stages()}")
    lp = loaded or load_package(model_id)
    a = assets if assets is not None else spec.load_assets()
    tmpl = spec.template_of(a)

    # --- system message: assembled for HF + provenance; OpenRouter never ships it on the wire ----
    system = assemble_stage_system(lp, tmpl)

    # --- user message: the evidence package, then ONE short closing directive -------------------
    # OpenRouter never puts the local system on the wire; the dashboard Preset owns the instructions.
    # That leaves the operative task roughly 20k tokens behind the evidence by the time the model
    # reads it, and instructions at the very end of a long context are followed markedly more
    # reliably than the same instructions only at the front. So a SHORT tail restates the few
    # constraints that actually fail in practice, and names the exact accounts expected, which is the
    # only way to make a skipped account detectable by the model itself rather than only by us.
    #
    # Deliberately short. This rides on EVERY request, so it is a per-scan cost, unlike the preset.
    sections = spec.render_sections(bundle, ctx)
    ev = [tmpl["evidence_preamble"]]
    for s in tmpl["evidence_sections"]:
        ev.append(s["header"] + "\n" + json.dumps(sections.get(s["section"], {}), ensure_ascii=False, sort_keys=True))
    closing = _closing_directive(sections)
    if closing:
        ev.append(closing)
    user = "\n\n".join(ev).strip()

    manifest = {
        "assembled_from": spec.assembled_from,
        "package_hash": lp.package_hash, "prompt_hash": lp.prompt_hash,
        "constitution_hash": lp.constitution_hash, "framework_hash": lp.framework_hash,
        "knowledge_hash": lp.knowledge_hash,
        **spec.manifest_extra(a, bundle),
        "model_id": lp.model_id,
        "response_format": _RESPONSE_FORMAT, "schema_ref": spec.schema_ref,
        "system_prompt_sha": "sys:" + hashlib.sha256(system.encode("utf-8")).hexdigest()[:24],
    }
    ppid = digest({"system": system, "user": user, "manifest": manifest}, prefix="pp:")
    return PromptPackage(system=system, user=user, response_format=_RESPONSE_FORMAT,
                         schema_ref=spec.schema_ref, model_id=lp.model_id,
                         manifest=manifest, prompt_package_id=ppid)


__all__ = ["StagePromptSpec", "register_stage_prompt", "registered_stages", "build_prompt",
           "assemble_stage_system"]
