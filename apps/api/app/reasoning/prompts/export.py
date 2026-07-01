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


__all__ = [
    "MANIFEST_VERSION", "MANIFEST_PATH", "prompt_manifest", "render_manifest_json",
    "write_manifest", "manifest_matches_committed",
]


if __name__ == "__main__":  # regenerate the committed manifest
    p = write_manifest()
    print(f"wrote {p}")
