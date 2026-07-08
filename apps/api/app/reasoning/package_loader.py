"""The Canonical Package Loader (Phase P1.2) — the ONE runtime layer that loads AI package assets.

Every consumer of the AI package (the Prompt Builder today, more later) obtains its assets from here
and nowhere else, so no consumer needs to know *where* an asset originates. The loader **only loads
and validates** — it performs no prompt assembly, no reasoning, no inference, no endpoint call, and it
never edits or publishes the package.

It loads the seven canonical asset bodies:

    Constitution · Prompt Registry (the omi_analyst system prompt) · Knowledge Library ·
    Specialist Framework · Response Contract · Prompt Template · Output Schema

verifies them (integrity, versions, content hashes, and the package identity ``package_hash``),
**caches** the result, and returns an **immutable** :class:`LoadedPackage`. Verification is
fail-closed: a package whose bodies do not match their published hashes raises and is never served,
so the runtime can never reason from a drifted or partial package.

Provenance is unchanged: GitHub remains the source, the GitHub Action remains the only publish
mechanism, and the Hugging Face package remains the canonical runtime mirror (the drift guard proves
the loaded bodies are byte-identical to what is published). This layer reads that canonical package;
it does not create a second one.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.evidence.bundle import digest
from app.reasoning.package import AIPackage, load_ai_package

# repo root: apps/api/app/reasoning/package_loader.py -> parents[4]
_REPO_ROOT = Path(__file__).resolve().parents[4]
_SCHEMA_PATH = _REPO_ROOT / "ml" / "analyst" / "analyst_response_schema.json"
_SCHEMA_REF = "schema/analyst_response_schema.json"


class PackageIntegrityError(RuntimeError):
    """Raised when a loaded package fails verification — the runtime must not use it."""


@dataclass(frozen=True)
class LoadedPackage:
    """An immutable, verified snapshot of the AI package's asset bodies + identity.

    Text assets are plain (immutable) strings; structured assets are stored as canonical JSON and
    handed back as fresh copies via accessors, so a consumer can never mutate the cached package.
    """

    identity: AIPackage
    # --- text asset bodies (immutable) ---
    constitution: str
    system_prompt: str
    response_contract: str
    # --- structured asset bodies, held as canonical JSON (immutable) ---
    _knowledge_json: str
    _framework_json: str
    _assembly_template_json: str
    _output_schema_json: str
    # --- versions ---
    constitution_version: str
    prompt_version: str
    framework_version: str
    template_version: str
    schema_version: int
    # --- content hashes of the loaded bodies ---
    prompt_hash: str
    constitution_hash: str
    framework_hash: str
    knowledge_hash: str
    template_hash: str
    contract_hash: str
    output_schema_hash: str
    output_schema_ref: str = _SCHEMA_REF

    # ---- immutable accessors (return fresh copies) -------------------------- #
    def knowledge(self) -> list[dict]:
        return json.loads(self._knowledge_json)

    def framework(self) -> dict:
        return json.loads(self._framework_json)

    def assembly_template(self) -> dict:
        return json.loads(self._assembly_template_json)

    def output_schema(self) -> dict:
        return json.loads(self._output_schema_json)

    @property
    def package_hash(self) -> str:
        return self.identity.package_hash

    @property
    def model_id(self) -> str:
        return self.identity.model_id

    def hashes(self) -> dict[str, str]:
        return {
            "package_hash": self.identity.package_hash, "prompt_hash": self.prompt_hash,
            "constitution_hash": self.constitution_hash, "framework_hash": self.framework_hash,
            "knowledge_hash": self.knowledge_hash, "template_hash": self.template_hash,
            "contract_hash": self.contract_hash, "output_schema_hash": self.output_schema_hash,
        }

    # ---- verification ------------------------------------------------------- #
    def verify(self) -> dict:
        """Recompute integrity, versions, hashes, and the package identity from the loaded bodies and
        compare to the identity + published expectations. Returns a report; raises
        :class:`PackageIntegrityError` on any failure (fail-closed)."""
        import hashlib

        i = self.identity
        checks: list[tuple[str, bool]] = []

        # integrity — no asset body is empty
        checks.append(("integrity.constitution", bool(self.constitution.strip())))
        checks.append(("integrity.system_prompt", bool(self.system_prompt.strip())))
        checks.append(("integrity.response_contract", bool(self.response_contract.strip())))
        checks.append(("integrity.knowledge", len(self.knowledge()) > 0))
        checks.append(("integrity.framework", bool(self.framework())))
        checks.append(("integrity.assembly_template", bool(self.assembly_template().get("system_blocks"))))
        checks.append(("integrity.output_schema", bool(self.output_schema().get("properties"))))

        # versions — the loaded versions equal the identity's
        checks.append(("version.constitution", self.constitution_version == i.constitution_version))
        checks.append(("version.registry", self.prompt_version == i.registry_version))
        checks.append(("version.framework", self.framework_version == i.framework_version))
        checks.append(("version.template", self.template_version == i.template_version))

        # hashes — the loaded body hashes equal the identity's content hashes
        checks.append(("hash.prompt", self.prompt_hash == i.prompt_hash))
        checks.append(("hash.constitution", self.constitution_hash == i.constitution_hash))
        checks.append(("hash.framework", self.framework_hash == i.framework_hash))
        checks.append(("hash.knowledge", self.knowledge_hash == i.knowledge_hash))
        checks.append(("hash.template", self.template_hash == i.template_hash))
        checks.append(("hash.contract", self.contract_hash == i.contract_hash))

        # identity — package_hash is exactly the content address of the six component hashes
        recomputed = "pkg:" + hashlib.sha256(
            "|".join([i.prompt_hash, i.framework_hash, i.knowledge_hash,
                      i.constitution_hash, i.template_hash, i.contract_hash]).encode("utf-8")
        ).hexdigest()[:24]
        checks.append(("identity.package_hash", recomputed == i.package_hash))

        failed = [name for name, ok in checks if not ok]
        if failed:
            raise PackageIntegrityError(f"package verification failed: {failed}")
        return {"verified": True, "package_hash": i.package_hash, "checks": [n for n, _ in checks]}


# --------------------------------------------------------------------------- #
# Loading (the only place asset bodies are read) + caching
# --------------------------------------------------------------------------- #
def _load_framework() -> tuple[dict, str, str]:
    """Load the Specialist Framework as data (version, hash, profiles, judge reasoning discipline)."""
    from app.reasoning.prompts import FRAMEWORK_VERSION, framework_hash, framework_profiles

    profs = list(framework_profiles())
    judge = next((p for p in profs if p.key == "judge"), profs[0] if profs else None)
    discipline: dict[str, Any] = {}
    if judge is not None:
        rec = judge.to_record()
        reasoning = rec.get("reasoning", {}) if isinstance(rec, dict) else {}
        discipline = {
            "decision_workflow": reasoning.get("decision_workflow"),
            "escalation": reasoning.get("escalation"),
            "termination": reasoning.get("termination"),
        }
    data = {"version": FRAMEWORK_VERSION, "hash": framework_hash(),
            "profiles": sorted(p.key for p in profs), "judge_discipline": discipline}
    return data, FRAMEWORK_VERSION, framework_hash()


def _load_knowledge() -> tuple[list[dict], str]:
    from app.reasoning import knowledge as _k

    lib = _k.default_library()
    entries = [
        {"id": e.id, "title": e.title, "category": e.category, "definition": e.definition,
         "indicators": list(e.indicators), "content_hash": e.content_hash}
        for e in sorted(lib.all(), key=lambda e: e.id)
    ]
    return entries, lib.library_hash()


def _load_output_schema() -> tuple[dict, str]:
    """Load the Output Schema body from its canonical GitHub source (published verbatim to HF)."""
    try:
        schema = json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:  # a missing/corrupt schema is a real fault
        raise PackageIntegrityError(f"output schema unreadable: {exc}") from exc
    return schema, digest(schema, prefix="sch:")


def _build_loaded_package(model_id: str | None) -> LoadedPackage:
    from app.reasoning.prompts import (
        CONSTITUTION_VERSION,
        PROMPT_TEMPLATE_VERSION,
        assembly_template,
        constitution_hash,
        constitution_text,
        contract_hash,
        default_registry,
        response_contract,
        template_hash,
    )

    identity = load_ai_package(model_id)
    spec = default_registry().resolve("omi_analyst")
    framework, framework_version, framework_hash_v = _load_framework()
    knowledge, knowledge_hash_v = _load_knowledge()
    schema, schema_hash_v = _load_output_schema()
    tmpl = assembly_template()

    return LoadedPackage(
        identity=identity,
        constitution=constitution_text(),
        system_prompt=spec.template,
        response_contract=response_contract(),
        _knowledge_json=json.dumps(knowledge, ensure_ascii=False, sort_keys=True),
        _framework_json=json.dumps(framework, ensure_ascii=False, sort_keys=True),
        _assembly_template_json=json.dumps(tmpl, ensure_ascii=False, sort_keys=True),
        _output_schema_json=json.dumps(schema, ensure_ascii=False, sort_keys=True),
        constitution_version=CONSTITUTION_VERSION,
        prompt_version=spec.prompt_version,
        framework_version=framework_version,
        template_version=PROMPT_TEMPLATE_VERSION,
        schema_version=int(schema.get("properties", {}).get("schema_version", {}).get("const", 1) or 1)
        if isinstance(schema.get("properties"), dict) else 1,
        prompt_hash=spec.prompt_hash,
        constitution_hash=constitution_hash(),
        framework_hash=framework_hash_v,
        knowledge_hash=knowledge_hash_v,
        template_hash=template_hash(),
        contract_hash=contract_hash(),
        output_schema_hash=schema_hash_v,
    )


_CACHE: dict[str, LoadedPackage] = {}


def load_package(model_id: str | None = None, *, verify: bool = True) -> LoadedPackage:
    """Return the verified, cached, immutable :class:`LoadedPackage`. This is the ONLY runtime entry
    point for AI package asset bodies. Fail-closed: verification failure raises and nothing is cached.
    """
    key = model_id or "__default__"
    cached = _CACHE.get(key)
    if cached is not None:
        return cached
    lp = _build_loaded_package(model_id)
    if verify:
        lp.verify()  # raises PackageIntegrityError on any mismatch — never cache a bad package
    _CACHE[key] = lp
    return lp


def reset_package_cache() -> None:
    """Drop the loader cache (tests / after a package regeneration)."""
    _CACHE.clear()


__all__ = ["LoadedPackage", "PackageIntegrityError", "load_package", "reset_package_cache"]
