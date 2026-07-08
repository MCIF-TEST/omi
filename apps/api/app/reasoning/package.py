"""The canonical AI deployment package (final production AI architecture).

ONE content-addressed unit describing the AI layer the runtime uses to reason about an
investigation: the Prompt Registry (system + specialist prompts), the Specialist Framework, the
Knowledge Library, and the constitutional hierarchy. This is the SAME package published to the
Hugging Face repository ``Andrewexiga/omi-analyst-v1`` by the GitHub Action — **GitHub is where it
is developed, Hugging Face is where it is deployed, and the backend LOADS it from bundled package
data at runtime**. There is no per-request GitHub or Hugging Face fetch for prompts (an availability
coupling the always-on deterministic Floor is designed to avoid); the drift guard proves the loaded
package is byte-identical to the published HF manifests, so "the HF package is canonical" holds
without making HF a runtime dependency.

The ``package_hash`` changes iff any component changes, so a single value certifies the exact AI
layer that produced an assessment — reproducibility in one field.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass


@dataclass(frozen=True)
class AIPackage:
    """The canonical, content-addressed AI deployment package the runtime assembles prompts from."""

    model_id: str
    registry_version: str
    prompt_hash: str
    framework_version: str
    framework_hash: str
    knowledge_hash: str
    constitution_version: str
    constitution_hash: str
    template_version: str
    template_hash: str
    contract_hash: str
    analysts: int
    knowledge_entries: int
    knowledge_categories: int
    package_hash: str

    def provenance(self) -> dict:
        """Compact, JSON-safe provenance for the governance/report layer — the AI package that
        produced an assessment, every component content-addressed."""
        return {
            "package_hash": self.package_hash,
            "model_id": self.model_id,
            "source": "deployed-ai-package (published to HF Andrewexiga/omi-analyst-v1; GitHub = dev-only)",
            "prompt_registry": {"version": self.registry_version, "omi_analyst_hash": self.prompt_hash,
                                "analysts": self.analysts},
            "specialist_framework": {"version": self.framework_version, "hash": self.framework_hash},
            "knowledge_library": {"hash": self.knowledge_hash, "entries": self.knowledge_entries,
                                  "categories": self.knowledge_categories},
            "constitution": {"version": self.constitution_version, "hash": self.constitution_hash},
            "prompt_template": {"version": self.template_version, "hash": self.template_hash,
                                "response_contract_hash": self.contract_hash},
        }


def load_ai_package(model_id: str | None = None) -> AIPackage:
    """Assemble the canonical AI package from the bundled registry / framework / knowledge /
    constitution. Cheap, deterministic, never raises for the caller's benefit (import errors would
    surface as a real code fault, not a silent skip)."""
    from app.reasoning import knowledge as _k
    from app.reasoning.prompts import (
        CONSTITUTION_VERSION,
        FRAMEWORK_VERSION,
        PROMPT_TEMPLATE_VERSION,
        constitution_hash,
        contract_hash,
        default_registry,
        framework_hash,
        template_hash,
    )

    reg = default_registry()
    lib = _k.default_library()
    omi = reg.resolve("omi_analyst")
    ph, fh, kh, ch = omi.prompt_hash, framework_hash(), lib.library_hash(), constitution_hash()
    th, rc = template_hash(), contract_hash()
    # The package_hash certifies the EXACT AI layer — now including the Prompt Template + Response
    # Contract assembly asset (P1.1), so a scaffolding change is a new, attributable package version.
    package_hash = "pkg:" + hashlib.sha256("|".join([ph, fh, kh, ch, th, rc]).encode("utf-8")).hexdigest()[:24]
    return AIPackage(
        model_id=model_id or "mistralai/Mistral-7B-Instruct-v0.3",
        registry_version=reg.active_version("omi_analyst"),
        prompt_hash=ph,
        framework_version=FRAMEWORK_VERSION,
        framework_hash=fh,
        knowledge_hash=kh,
        constitution_version=CONSTITUTION_VERSION,
        constitution_hash=ch,
        template_version=PROMPT_TEMPLATE_VERSION,
        template_hash=th,
        contract_hash=rc,
        analysts=len(reg.analysts()),
        knowledge_entries=len(lib.all()),
        knowledge_categories=len(lib.categories()),
        package_hash=package_hash,
    )


__all__ = ["AIPackage", "load_ai_package"]
