"""The ONE Canonical (stage) Prompt Builder — assemble every reasoning stage's prompt identically.

``build_prompt(stage, bundle)`` is the single prompt-assembly implementation for every AI reasoning
stage (comment, commenter_history, and every future stage). It is **stage-agnostic**: it knows nothing
about any particular stage. A stage registers a small :class:`StagePromptSpec` — its package assets,
its evidence-section rendering, its schema ref, and its manifest fields — and the builder does the
identical assembly for all of them:

    system  = omi_analyst base + constitution + specialist framework + knowledge library
              + the stage's task block + the stage's output contract        (all package assets)
    user    = the stage's evidence sections, each rendered as JSON data      (from the Evidence Bundle)
    manifest= content hashes of every asset + the bundle id + the stage schema ref
    -> one content-addressed :class:`PromptPackage`

Two invariants this module upholds:

1. **No embedded stage prompt text** — every task/contract/section-header that is STAGE-specific comes
   from the stage's package template (loaded via the spec). Only stage-invariant structural glue
   (``"# OUTPUT CONTRACT\\n"`` and the section labels) lives here, identical for every stage.
2. **It obtains everything through the Package Loader** — the shared base prompt / constitution /
   framework / knowledge come from :func:`load_package`; the stage template/contract/schema come from
   the stage's loader accessor. The builder imports no prompt/template source module.

No model, no endpoint, no inference — the builder only assembles.
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
    """A stage's contribution to the canonical builder — everything that varies BETWEEN stages, and
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
    """The ONE system-message assembly shared by every stage — the stable instruction hierarchy the
    model receives: the omi_analyst base prompt + constitution + specialist framework + knowledge
    library + the stage task + the stage output contract. Factored out so a caller that needs the
    compiled system WITHOUT running an inference (e.g. the Master Analyst Protocol asset compiled for
    an OpenRouter Preset) produces byte-identical text to what :func:`build_prompt` sends."""
    return "\n\n".join([
        lp.system_prompt,
        "# REASONING & GOVERNANCE CONSTITUTION\n" + lp.constitution,
        "# SPECIALIST INVESTIGATION FRAMEWORK\n" + json.dumps(lp.framework(), ensure_ascii=False, sort_keys=True),
        "# KNOWLEDGE LIBRARY\n" + json.dumps(lp.knowledge()[:_KNOWLEDGE_LIMIT], ensure_ascii=False, sort_keys=True),
        tmpl["system_task"],
        "# OUTPUT CONTRACT\n" + tmpl["response_contract"],
    ]).strip()


def register_stage_prompt(spec: StagePromptSpec) -> None:
    """Register a stage's prompt spec. Called by each stage module at import time, so the builder
    core never imports a stage. Idempotent (re-registration overwrites with the same spec)."""
    _STAGE_REGISTRY[spec.stage] = spec


def registered_stages() -> tuple[str, ...]:
    return tuple(sorted(_STAGE_REGISTRY))


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

    # --- system message: identical assembly for every stage, from package assets only -------------
    system = assemble_stage_system(lp, tmpl)

    # --- user message: the stage's evidence sections, each rendered as JSON data ------------------
    sections = spec.render_sections(bundle, ctx)
    ev = [tmpl["evidence_preamble"]]
    for s in tmpl["evidence_sections"]:
        ev.append(s["header"] + "\n" + json.dumps(sections.get(s["section"], {}), ensure_ascii=False, sort_keys=True))
    ev.append(tmpl["evidence_instruction"])
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
