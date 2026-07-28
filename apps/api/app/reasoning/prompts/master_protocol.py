"""The Omi Master Analyst Protocol, the repository-owned, versioned, content-hashed instruction set.

Phase 2 establishes the deployment/versioning seam for delivering Omi's stable instruction hierarchy to
an OpenRouter Preset. The Master Analyst Protocol is NOT a newly authored prompt: it is the EXACT compiled
comprehensive-investigation SYSTEM message Omi already sends, the omi_analyst base prompt + constitution +
specialist framework + knowledge library + the comprehensive task + the ONE canonical output contract, 
assembled through the same shared assembler the runtime uses (:func:`assemble_stage_system`). Because it is
the same assembly over the same package assets, ``compile_master_analyst_protocol().text`` is byte-identical
to the ``pp.system`` the Hugging Face path delivers, and its hash equals the ``system_prompt_sha`` recorded
in every investigation trace.

The repository is the source of truth. An OpenRouter Preset is an execution/deployment mechanism that is
EXPECTED to contain this exact text; Omi records the version + content hash it expects the preset to hold so
drift is detectable, but it does not (and cannot) cryptographically verify the remote preset content. The
human deploys ``compile_master_analyst_protocol().text`` as the preset's system prompt.
"""
from __future__ import annotations

import hashlib

# A human label for the compiled protocol. It is derived from the versions of the assets that compose it,
# so it moves when any composing asset's version moves. The content HASH is the authoritative identity.
MASTER_ANALYST_PROTOCOL_NAME = "omi_master_analyst_protocol"


def _protocol_version() -> str:
    """A composed version label from the asset versions that make up the protocol (base prompt,
    constitution, framework, comprehensive template). The content hash remains authoritative."""
    from app.reasoning.prompts import CONSTITUTION_VERSION
    from app.reasoning.prompts.comprehensive_investigation_template import (
        COMPREHENSIVE_INVESTIGATION_TEMPLATE_VERSION,
    )
    from app.reasoning.prompts.framework import FRAMEWORK_VERSION
    from app.reasoning.prompts.registry import default_registry

    prompt_v = default_registry().resolve("omi_analyst").prompt_version
    return (f"map/prompt:{prompt_v}+constitution:{CONSTITUTION_VERSION}+framework:{FRAMEWORK_VERSION}"
            f"+template:{COMPREHENSIVE_INVESTIGATION_TEMPLATE_VERSION}")


def compile_master_analyst_protocol(model_id: str | None = None) -> dict:
    """Compile the Master Analyst Protocol from the canonical repository assets and content-address it.

    Returns ``{"name", "version", "hash", "text", "chars"}``. ``text`` is byte-identical to the comprehensive
    stage's ``pp.system`` (proven by tests), so deploying it as an OpenRouter Preset system prompt reproduces
    exactly what the Hugging Face path sends. ``hash`` (``map:``) equals the investigation trace's
    ``compiled_system_instruction_hash`` for the comprehensive stage."""
    from app.reasoning.package_loader import (
        load_comprehensive_investigation_assets,
        load_package,
    )
    from app.reasoning.prompt.stage_builder import assemble_stage_system

    lp = load_package(model_id)
    tmpl = load_comprehensive_investigation_assets().template()
    text = assemble_stage_system(lp, tmpl)
    digest = "map:" + hashlib.sha256(text.encode("utf-8")).hexdigest()[:24]
    return {
        "name": MASTER_ANALYST_PROTOCOL_NAME,
        "version": _protocol_version(),
        "hash": digest,
        "text": text,
        "chars": len(text),
    }


def master_analyst_protocol_identity(model_id: str | None = None) -> dict:
    """The lean identity (no prompt body) for forensic traces / diagnostics: name + version + hash + size.
    Never includes the protocol text, so it is safe to persist in an investigation trace."""
    p = compile_master_analyst_protocol(model_id)
    return {"name": p["name"], "version": p["version"], "hash": p["hash"], "chars": p["chars"]}


__all__ = [
    "MASTER_ANALYST_PROTOCOL_NAME",
    "compile_master_analyst_protocol",
    "master_analyst_protocol_identity",
]
