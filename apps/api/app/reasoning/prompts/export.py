"""Prompt synchronization manifest — GitHub registry -> Hugging Face (Sprint 023).

Generates the authoritative prompt manifest that the Hugging Face deployment package carries so the
deployed AI (and any auditor) can verify prompt integrity: every registered prompt's analyst,
version, active flag, content hash, and output contract, plus the constitution version + hash and
the specialist-library status. The manifest is generated FROM the ONE Prompt Registry (the single
source of truth), so it can never drift from what the runtime actually resolves — a committed copy
lives under ``ml/analyst/hf_repo/prompts/`` and a drift-guard test regenerates + compares it.

This does NOT publish full specialist prompt bodies to HF: the deployed V1 uses only the
``omi_analyst`` system prompt (already published); the 13-specialist library is inert (not
activated), so the manifest records its versions + hashes for readiness without duplicating unused
content. When the council is activated, a follow-up sync publishes the full specialist assets.
"""
from __future__ import annotations

import json
from pathlib import Path

from .constitution import CONSTITUTION_VERSION, constitution_hash
from .registry import default_registry
from .specialists import LIBRARY_VERSION, SPECIALISTS

MANIFEST_VERSION = "v1"
# repo root: apps/api/app/reasoning/prompts/export.py -> parents[5]
MANIFEST_PATH = (
    Path(__file__).resolve().parents[5] / "ml" / "analyst" / "hf_repo" / "prompts" / "prompt_manifest.json"
)


def prompt_manifest() -> dict:
    """Build the deterministic prompt manifest from the registry (single source of truth)."""
    reg = default_registry()
    spec_keys = {s.key for s in SPECIALISTS}
    prompts: list[dict] = []
    for analyst in sorted(reg.analysts()):
        active = reg.active_version(analyst)
        for version in reg.versions(analyst):
            spec = reg.get(analyst, version)
            prompts.append({
                "analyst": analyst,
                "version": version,
                "active": version == active,
                "prompt_hash": spec.prompt_hash,
                "expected_output_contract": spec.expected_output_contract,
                "model_compatibility": list(spec.model_compatibility),
                # the lib-v1 specialist prompts literally compose the constitution blocks; the live
                # omi_analyst / behavior prompts honor the same rules via their constraints.
                "composes_constitution": version == LIBRARY_VERSION and analyst in spec_keys,
            })
    return {
        "manifest_version": MANIFEST_VERSION,
        "generated_by": "app.reasoning.prompts.export.prompt_manifest",
        "source_of_truth": "GitHub app.reasoning.prompts.default_registry (do not hand-edit)",
        "constitution": {"version": CONSTITUTION_VERSION, "hash": constitution_hash()},
        "production_prompt": {
            "analyst": "omi_analyst",
            "active_version": reg.active_version("omi_analyst"),
            "prompt_hash": reg.resolve("omi_analyst").prompt_hash,
            "published_asset": "prompts/analyst_system_prompt_v1.md",
        },
        "specialist_library": {
            "version": LIBRARY_VERSION,
            "count": len(SPECIALISTS),
            "activated": False,
            "note": "inert readiness assets; full bodies live in the GitHub registry until activation",
        },
        "counts": {"analysts": len(reg.analysts()), "prompts": len(prompts)},
        "prompts": prompts,
    }


def render_manifest_json() -> str:
    """The manifest as canonical, stable JSON text (sorted keys, trailing newline)."""
    return json.dumps(prompt_manifest(), indent=2, sort_keys=True) + "\n"


def write_manifest(path: Path | None = None) -> Path:
    """Write the committed manifest artifact (used by the regen CLI). Returns the path written."""
    target = path or MANIFEST_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(render_manifest_json(), encoding="utf-8")
    return target


def manifest_matches_committed() -> bool:
    """True when the committed HF manifest equals a freshly generated one (drift guard)."""
    try:
        return MANIFEST_PATH.read_text(encoding="utf-8") == render_manifest_json()
    except OSError:
        return False


# --------------------------------------------------------------------------- #
# Prompt Catalog — complete per-prompt metadata (Sprint 024, Phase 2)
# --------------------------------------------------------------------------- #
CATALOG_VERSION = "v1"
CATALOG_PATH = (
    Path(__file__).resolve().parents[5] / "ml" / "analyst" / "hf_repo" / "prompts" / "prompt_catalog.json"
)
_CONTEXT_RULE = (
    "Structured evidence arrives as the projected Evidence Bundle (project_investigation_bundle); "
    "institutional memory arrives as prior_context (background, never proof, no citable id). Read "
    "both; cite only bundle evidence ids."
)
_EVIDENCE_RULE = (
    "Cite only bundle evidence; discriminative methods (fingerprint_cluster, co_engagement, co_tag) "
    "vs non-discriminative are gated; supplemental signals carry zero suspicion weight "
    "(see constitution evidence_rules block)."
)


def _framework_block(key: str) -> dict:
    """The Specialist Intelligence Framework dimensions for one specialist (Phase A1) — derived
    from the ONE framework module so the catalog carries the complete inherited record."""
    from .framework import framework_profiles

    profile = next(p for p in framework_profiles() if p.key == key)
    rec = profile.to_record()
    return {
        "execution": rec["execution"],
        "authority": rec["identity"]["authority"],
        "decision_workflow": rec["reasoning"]["decision_workflow"],
        "escalation": rec["reasoning"]["escalation"],
        "termination": rec["reasoning"]["termination"],
        "quality": rec["quality"],
        "validation": rec["validation"],
        "token_budget": rec["technical"]["token_budget"],
        "retrieval_strategy": rec["technical"]["retrieval_strategy"],
        "documentation": rec["documentation"],
    }


def _specialist_entry(spec, reg) -> dict:
    ps = reg.resolve(spec.key, LIBRARY_VERSION)
    return {
        "key": spec.key,
        "title": spec.title,
        "tier": spec.tier,
        "output_kind": spec.output_kind,
        "version": LIBRARY_VERSION,
        "prompt_hash": ps.prompt_hash,
        "expected_output_contract": ps.expected_output_contract,
        "json_schema": ("schema/analyst_response_schema.json" if spec.output_kind == "ruling"
                        else f"council {spec.output_kind} artifact contract"),
        "constitution_version": CONSTITUTION_VERSION,
        "composes_constitution": True,
        "mission": spec.mission,
        "inputs": list(spec.available_evidence),
        "outputs": spec.output_contract,
        "constraints": list(spec.constraints),
        "reasoning_rules": {"allowed": list(spec.allowed_reasoning),
                            "forbidden": list(spec.forbidden_reasoning)},
        "evidence_rules": _EVIDENCE_RULE,
        "citation_rules": spec.citation,
        "memory_rules": spec.memory_usage,
        "context_rules": _CONTEXT_RULE,
        "governor_compatibility": spec.governor_constraints,
        "failure_modes": list(spec.failure_modes),
        "dependencies": {
            "constitution": f"{CONSTITUTION_VERSION} ({constitution_hash()})",
            "primary_blocks": list(spec.primary_blocks),
            "interacts_with": list(spec.interactions),
        },
        "framework": _framework_block(spec.key),
    }


def prompt_catalog() -> dict:
    """The complete per-prompt metadata catalog (Phase 2): mission, inputs, outputs, constraints,
    evidence / citation / memory / context rules, Governor compatibility, JSON schema, version,
    prompt hash, constitution version, and dependencies — for the active production prompt and each
    of the 13 specialists. Generated from the registry + specialist library (single source of
    truth), so it mirrors runtime exactly and is drift-guarded. Complements ``prompt_manifest`` (the
    hash index) with full metadata."""
    reg = default_registry()
    omi = reg.resolve("omi_analyst")
    production = {
        "key": "omi_analyst",
        "role": "active production judge prompt — the ONLY prompt the deployed V1 uses",
        "version": reg.active_version("omi_analyst"),
        "prompt_hash": omi.prompt_hash,
        "expected_output_contract": omi.expected_output_contract,
        "json_schema": "schema/analyst_response_schema.json",
        "response_format": "json_object",
        "constraints": list(omi.constraints),
        "reasoning_objectives": list(omi.reasoning_objectives),
        "published_asset": "prompts/analyst_system_prompt_v1.md",
        "constitution_version": CONSTITUTION_VERSION,
    }
    from .framework import FRAMEWORK_VERSION, framework_hash, framework_profiles

    code_backed = sorted(p.key for p in framework_profiles() if p.technical.prompt_hash is None)
    return {
        "catalog_version": CATALOG_VERSION,
        "generated_by": "app.reasoning.prompts.export.prompt_catalog",
        "source_of_truth": "GitHub app.reasoning.prompts registry + specialist library (do not hand-edit)",
        "constitution": {"version": CONSTITUTION_VERSION, "hash": constitution_hash()},
        "framework": {"version": FRAMEWORK_VERSION, "hash": framework_hash(),
                      "profiles": len(framework_profiles()),
                      "code_backed_tier3": code_backed,
                      "note": "every specialist inherits the Specialist Intelligence Framework; "
                              "governor + floor are code-backed (never prompt- or model-driven)"},
        "schema": {"response_schema": "schema/analyst_response_schema.json", "response_format": "json_object"},
        "specialists_activated": False,
        "production_prompt": production,
        "specialists": [_specialist_entry(s, reg) for s in sorted(SPECIALISTS, key=lambda x: x.key)],
        "counts": {"production_prompts": 1, "specialists": len(SPECIALISTS)},
    }


def render_catalog_json() -> str:
    """The catalog as canonical, stable JSON text (sorted keys, trailing newline)."""
    return json.dumps(prompt_catalog(), indent=2, sort_keys=True) + "\n"


def write_catalog(path: Path | None = None) -> Path:
    target = path or CATALOG_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(render_catalog_json(), encoding="utf-8")
    return target


def catalog_matches_committed() -> bool:
    """True when the committed prompt catalog equals a freshly generated one (drift guard)."""
    try:
        return CATALOG_PATH.read_text(encoding="utf-8") == render_catalog_json()
    except OSError:
        return False


# --------------------------------------------------------------------------- #
# Intelligence Library manifest — publish the knowledge alongside prompts (Sprint 025, Phase 5)
# --------------------------------------------------------------------------- #
KNOWLEDGE_PATH = (
    Path(__file__).resolve().parents[5] / "ml" / "analyst" / "hf_repo" / "knowledge" / "knowledge_manifest.json"
)


def knowledge_manifest() -> dict:
    """The Intelligence Library published alongside the prompts: per-entry metadata + content hash,
    the category taxonomy, the specialist dependency map, and the library hash — generated FROM the
    library (single source of truth). Full entry bodies stay canonical in GitHub (not duplicated);
    this index is the drift-guarded HF mirror."""
    from app.reasoning.knowledge import (
        default_library, specialist_dependencies, taxonomy_hash,
    )

    lib = default_library()
    entries = [{
        "id": e.id, "title": e.title, "category": e.category, "confidence": e.confidence,
        "version": e.version, "content_hash": e.content_hash,
        "relationships": list(e.relationships), "specialists": list(e.specialists),
        "platforms": list(e.platforms), "investigation_types": list(e.investigation_types),
        "tags": list(e.tags),
    } for e in lib.active()]
    return {
        "manifest_version": "v1",
        "generated_by": "app.reasoning.prompts.export.knowledge_manifest",
        "source_of_truth": "GitHub app.reasoning.knowledge.default_library (do not hand-edit)",
        "library_hash": lib.library_hash(),
        "taxonomy_hash": taxonomy_hash(),
        "categories": [{"id": c.id, "name": c.name} for c in lib.categories()],
        "counts": {"entries": len(entries), "categories": len(lib.categories())},
        "specialist_dependencies": specialist_dependencies(lib),
        "entries": entries,
    }


def render_knowledge_json() -> str:
    return json.dumps(knowledge_manifest(), indent=2, sort_keys=True) + "\n"


def write_knowledge(path: Path | None = None) -> Path:
    target = path or KNOWLEDGE_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(render_knowledge_json(), encoding="utf-8")
    return target


def knowledge_matches_committed() -> bool:
    """True when the committed knowledge manifest equals a freshly generated one (drift guard)."""
    try:
        return KNOWLEDGE_PATH.read_text(encoding="utf-8") == render_knowledge_json()
    except OSError:
        return False


# --------------------------------------------------------------------------- #
# Prompt Template + Response Contract — the assembly asset published to HF (Phase P1.1)
# --------------------------------------------------------------------------- #
PROMPT_TEMPLATE_PATH = (
    Path(__file__).resolve().parents[5] / "ml" / "analyst" / "hf_repo" / "prompts" / "prompt_template.json"
)


def prompt_template_manifest() -> dict:
    """The Prompt Template + Response Contract, published alongside the prompts so the deployed
    runtime (and any auditor) carries the exact assembly scaffolding the Prompt Builder fills.
    Generated FROM the template asset (single source of truth); drift-guarded."""
    from .template import (
        PROMPT_TEMPLATE_VERSION,
        assembly_template,
        contract_hash,
        template_hash,
    )

    tmpl = assembly_template()
    return {
        "manifest_version": "v1",
        "generated_by": "app.reasoning.prompts.export.prompt_template_manifest",
        "source_of_truth": "GitHub app.reasoning.prompts.template (do not hand-edit)",
        "template_version": PROMPT_TEMPLATE_VERSION,
        "template_hash": template_hash(),
        "response_contract_hash": contract_hash(),
        "response_format": "json_object",
        "response_schema": "schema/analyst_response_schema.json",
        "system_block_order": [b["slot"] for b in tmpl["system_blocks"]],
        "evidence_section_order": [s["section"] for s in tmpl["evidence_sections"]],
        "template": tmpl,
    }


def render_prompt_template_json() -> str:
    return json.dumps(prompt_template_manifest(), indent=2, sort_keys=True) + "\n"


def write_prompt_template(path: Path | None = None) -> Path:
    target = path or PROMPT_TEMPLATE_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(render_prompt_template_json(), encoding="utf-8")
    return target


def prompt_template_matches_committed() -> bool:
    """True when the committed prompt-template manifest equals a freshly generated one (drift guard)."""
    try:
        return PROMPT_TEMPLATE_PATH.read_text(encoding="utf-8") == render_prompt_template_json()
    except OSError:
        return False


# --------------------------------------------------------------------------- #
# Specialist Framework handbook — GitHub-side contributor doc (Phase A1)
# --------------------------------------------------------------------------- #
HANDBOOK_PATH = (
    Path(__file__).resolve().parents[5] / "ml" / "analyst" / "SPECIALIST_FRAMEWORK.md"
)


def write_handbook(path: Path | None = None) -> Path:
    """Write the generated Specialist Framework handbook (drift-guarded; GitHub-only doc —
    engineering documentation, not a deployment artifact)."""
    from .framework import render_handbook

    target = path or HANDBOOK_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(render_handbook(), encoding="utf-8")
    return target


def handbook_matches_committed() -> bool:
    from .framework import render_handbook

    try:
        return HANDBOOK_PATH.read_text(encoding="utf-8") == render_handbook()
    except OSError:
        return False


# --------------------------------------------------------------------------- #
# Behavioral Intelligence Library handbook — GitHub-side doc (Phase B1)
# --------------------------------------------------------------------------- #
BEHAVIORAL_HANDBOOK_PATH = (
    Path(__file__).resolve().parents[5] / "ml" / "analyst" / "BEHAVIORAL_ANALYST.md"
)


def write_behavioral_handbook(path: Path | None = None) -> Path:
    from .behavioral import render_behavioral_handbook

    target = path or BEHAVIORAL_HANDBOOK_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(render_behavioral_handbook(), encoding="utf-8")
    return target


def behavioral_handbook_matches_committed() -> bool:
    from .behavioral import render_behavioral_handbook

    try:
        return BEHAVIORAL_HANDBOOK_PATH.read_text(encoding="utf-8") == render_behavioral_handbook()
    except OSError:
        return False


__all__ = [
    "MANIFEST_VERSION", "MANIFEST_PATH", "prompt_manifest", "render_manifest_json",
    "write_manifest", "manifest_matches_committed",
    "CATALOG_VERSION", "CATALOG_PATH", "prompt_catalog", "render_catalog_json",
    "write_catalog", "catalog_matches_committed",
    "KNOWLEDGE_PATH", "knowledge_manifest", "render_knowledge_json",
    "write_knowledge", "knowledge_matches_committed",
    "PROMPT_TEMPLATE_PATH", "prompt_template_manifest", "render_prompt_template_json",
    "write_prompt_template", "prompt_template_matches_committed",
    "HANDBOOK_PATH", "write_handbook", "handbook_matches_committed",
    "BEHAVIORAL_HANDBOOK_PATH", "write_behavioral_handbook", "behavioral_handbook_matches_committed",
]


if __name__ == "__main__":  # regenerate manifest + catalog + knowledge index + handbooks
    print(f"wrote {write_manifest()}")
    print(f"wrote {write_catalog()}")
    print(f"wrote {write_knowledge()}")
    print(f"wrote {write_prompt_template()}")
    print(f"wrote {write_handbook()}")
    print(f"wrote {write_behavioral_handbook()}")
