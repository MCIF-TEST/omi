"""Prompt Builder — assemble the final Mistral prompt EXCLUSIVELY from the canonical AI package.

Phase B: the Hugging Face analyst package defines HOW Mistral thinks. The builder assembles the
analyst's system prompt from package assets ONLY — the ``omi_analyst`` system prompt, the
**constitution** (the governance / reasoning / validation rules), and the **Knowledge Library**
(the reference domain knowledge the analyst reasons from) — never hard-coded prompt text. The result
is content-addressed: ``build_system`` returns the assembled prompt plus a manifest of every
component hash, so the exact prompt that produced an assessment is reproducible and auditable.

This promotes the Specialist Framework (expressed as the constitution the framework derives from)
and the Knowledge Library into the production reasoning prompt. It is flag-gated
(``analyst_prompt_assembly``): ``registry`` (default — the validated base prompt only) or
``package`` (base + framework + knowledge). Deterministic safety, the Governor, and the floor are
untouched.

RETIRED FROM PRODUCTION (Phase P3.4): the general Investigation Summary — the last production caller of
this builder — is now a canonical reasoning stage whose prompt is assembled by the ONE canonical stage
builder (``app.reasoning.prompt.build_prompt('investigation_summary', bundle)``), so ``PromptBuilder``
is no longer on any production path. It is retained (and directly unit-tested) as the ``package``-mode
system assembler, exactly as the legacy P1.1 ``build_prompt_package`` is retained, until its subsystem's
fate is decided. The ONE production Prompt Builder is the canonical stage builder.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass

from app.reasoning.package import AIPackage, load_ai_package


@dataclass(frozen=True)
class BuiltPrompt:
    system: str
    manifest: dict


class PromptBuilder:
    """Assembles the analyst system prompt from the canonical AI package. Deterministic + bounded."""

    def __init__(self, package: AIPackage | None = None, *, knowledge_limit: int = 12):
        self.package = package or load_ai_package()
        self.knowledge_limit = max(0, int(knowledge_limit))

    # ------------------------------------------------------------------ #
    def build_system(self, *, base_system: str, mode: str = "package") -> BuiltPrompt:
        """Assemble the analyst system prompt. ``registry`` returns the base prompt unchanged (with a
        manifest); ``package`` appends the constitution (governance/reasoning rules) and the Knowledge
        Library reference block — all package assets, content-addressed."""
        base = (base_system or "").strip()
        if mode != "package":
            return BuiltPrompt(system=base, manifest=self._manifest("registry", base, ()))

        from app.reasoning.prompts import constitution_text

        constitution = constitution_text().strip()
        knowledge, used = self._knowledge_block()
        system = "\n\n".join([
            base,
            "# REASONING & GOVERNANCE FRAMEWORK (authoritative — from the analyst package)\n"
            "Reason strictly within these constitutional rules. They bind every judgment; the "
            "Governor re-checks them after you answer.\n\n" + constitution,
            "# KNOWLEDGE LIBRARY (reference — reason FROM this; cite ONLY the evidence bundle, never this)\n"
            + knowledge,
            "# OUTPUT CONTRACT\nEmit exactly one JSON object valid against the response schema. Echo "
            "the engine's numbers; never recompute or move a score. Always include counter-evidence "
            "and named uncertainty. The human analyst sets the verdict.",
        ]).strip()
        return BuiltPrompt(system=system, manifest=self._manifest("package", system, used))

    # ------------------------------------------------------------------ #
    def _knowledge_block(self) -> tuple[str, tuple[str, ...]]:
        """A compact, bounded, deterministic rendering of the Knowledge Library for the prompt."""
        from app.reasoning import knowledge as _k

        entries = sorted(_k.default_library().all(), key=lambda e: e.id)[: self.knowledge_limit]
        lines, used = [], []
        for e in entries:
            used.append(e.id)
            indicators = "; ".join(e.indicators[:4]) if e.indicators else "—"
            lines.append(f"- **{e.title}** [{e.category} · {e.content_hash}]: {e.definition} "
                         f"Indicators: {indicators}")
        return ("\n".join(lines) if lines else "- (none)"), tuple(used)

    def _manifest(self, mode: str, system: str, knowledge_used: tuple[str, ...]) -> dict:
        return {
            "mode": mode,
            "assembled_from": "hf-analyst-package (omi_analyst prompt + constitution + knowledge)",
            "package_hash": self.package.package_hash,
            "prompt_hash": self.package.prompt_hash,
            "framework_hash": self.package.framework_hash,
            "constitution_hash": self.package.constitution_hash,
            "knowledge_hash": self.package.knowledge_hash,
            "knowledge_entries_used": list(knowledge_used),
            "system_prompt_sha": "sys:" + hashlib.sha256(system.encode("utf-8")).hexdigest()[:24],
            "system_prompt_chars": len(system),
        }


__all__ = ["PromptBuilder", "BuiltPrompt"]
