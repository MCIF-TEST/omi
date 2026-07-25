"""Prompt-builder shared types + the legacy P1.1 investigation-context builder.

This module hosts :class:`PromptPackage` (the assembled prompt object every builder emits) and the
**legacy** :func:`build_prompt_package` — the P1.1 whole-investigation builder that fills the
investigation template's ``system_blocks`` slots from an :class:`InvestigationContext`.

The ONE canonical **stage** prompt builder — ``build_prompt(stage, bundle)``, which every AI reasoning
stage uses — lives in :mod:`app.reasoning.prompt.stage_builder`. ``build_prompt_package`` is a
different input shape (context, not bundle) and is currently UNWIRED; it is retained only because it
is tied to the still-live investigation template asset (``prompt_template.json``) and its loader
proofs. Both emit a content-addressed :class:`PromptPackage`; neither performs inference.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from typing import Any

from app.evidence.bundle import digest
from app.reasoning.context.investigation import InvestigationContext
from app.reasoning.package_loader import LoadedPackage, load_package

_KNOWLEDGE_LIMIT = 12
_RESPONSE_FORMAT = "json_object"


@dataclass(frozen=True)
class PromptPackage:
    """The assembled, content-addressed prompt bundle — a Prompt Builder's output and the sole input
    to the inference stage. Carries the system + user messages and a provenance manifest that
    content-addresses every package asset + the evidence it was built from."""

    system: str
    user: str
    response_format: str
    schema_ref: str
    model_id: str
    manifest: dict = field(default_factory=dict)
    prompt_package_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# --------------------------------------------------------------------------- #
# Legacy P1.1 investigation-context builder — RETAINED (not part of the P3.3 stage consolidation).
# It assembles the whole-investigation prompt from the ONE Canonical Package Loader's *investigation*
# template (``assembly_template()``'s ``system_blocks``), taking an InvestigationContext (not an
# Evidence Bundle). It is currently UNWIRED (no production caller) but tied to the still-live
# investigation template asset (``prompt_template.json``) + its loader proofs, so it is kept until
# that subsystem's fate is decided. Distinct input shape from ``build_prompt(stage, bundle)``.
# --------------------------------------------------------------------------- #
def _block(header: str, preamble: str, body: str) -> str:
    return "\n".join(p for p in (header, preamble, body) if p)


def build_prompt_package(
    context: InvestigationContext,
    *,
    loaded: LoadedPackage | None = None,
    model_id: str | None = None,
    knowledge_limit: int = _KNOWLEDGE_LIMIT,
) -> PromptPackage:
    """Assemble the whole-investigation :class:`PromptPackage` from the investigation template slots,
    exclusively from the verified assets of the Canonical Package Loader. Deterministic +
    content-addressed; performs no inference and calls no model. (Legacy P1.1 — unwired; see the note
    above. The per-stage prompt is :func:`build_prompt`.)"""
    lp = loaded or load_package(model_id)
    tmpl = lp.assembly_template()

    entries = lp.knowledge()[: max(0, knowledge_limit)]
    knowledge_used = [e["id"] for e in entries]
    knowledge_body = json.dumps(
        [{"id": e["id"], "title": e["title"], "category": e["category"],
          "definition": e["definition"], "indicators": list(e.get("indicators", []))[:4],
          "content_hash": e["content_hash"]} for e in entries],
        ensure_ascii=False, sort_keys=True,
    )
    fills = {
        "system_prompt": lp.system_prompt,
        "constitution": lp.constitution,
        "specialist_framework": json.dumps(lp.framework(), ensure_ascii=False, sort_keys=True),
        "knowledge_library": knowledge_body,
        "response_contract": lp.response_contract,
    }
    system = "\n\n".join(
        s for s in (_block(b["header"], b["preamble"], fills.get(b["slot"], "")) for b in tmpl["system_blocks"]) if s
    ).strip()

    cdict = context.to_dict()
    ev_parts: list[str] = [tmpl["evidence_preamble"]]
    for s in tmpl["evidence_sections"]:
        section = cdict.get(s["section"], {})
        ev_parts.append(s["header"] + "\n" + json.dumps(section, ensure_ascii=False, sort_keys=True))
    user = "\n\n".join(ev_parts).strip()

    system_sha = "sys:" + hashlib.sha256(system.encode("utf-8")).hexdigest()[:24]
    manifest = {
        "assembled_from": "hf-analyst-package (via canonical package loader)",
        "package_hash": lp.package_hash,
        "prompt_hash": lp.prompt_hash,
        "framework_hash": lp.framework_hash,
        "knowledge_hash": lp.knowledge_hash,
        "constitution_hash": lp.constitution_hash,
        "template_version": lp.template_version,
        "template_hash": lp.template_hash,
        "contract_hash": lp.contract_hash,
        "output_schema_hash": lp.output_schema_hash,
        "knowledge_entries_used": knowledge_used,
        "context_version": context.context_version,
        "context_id": context.context_id,
        "model_id": lp.model_id,
        "response_format": _RESPONSE_FORMAT,
        "schema_ref": lp.output_schema_ref,
        "system_prompt_sha": system_sha,
        "system_prompt_chars": len(system),
        "user_message_chars": len(user),
    }
    prompt_package_id = digest({"system": system, "user": user, "manifest": manifest}, prefix="pp:")
    return PromptPackage(
        system=system, user=user, response_format=_RESPONSE_FORMAT, schema_ref=lp.output_schema_ref,
        model_id=lp.model_id, manifest=manifest, prompt_package_id=prompt_package_id,
    )


__all__ = ["PromptPackage", "build_prompt_package"]
