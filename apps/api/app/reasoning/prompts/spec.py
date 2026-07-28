"""Versioned prompt specifications (Sprint 008).

A ``PromptSpec`` is the unit of the Intelligence Optimization Framework: the *content* of an
AI analyst's instruction (the template) plus the metadata that makes prompt evolution
measurable and reviewable. Version, content hash, authorship, model compatibility, reasoning
objectives, constraints, and the output contract it targets. AI-backed analysts execute from a
``PromptSpec`` resolved out of the registry, never from embedded prompt text, so every reasoning
run is attributable to a specific, content-addressed prompt version.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from app.evidence.bundle import digest


@dataclass(frozen=True)
class PromptSpec:
    """One immutable, versioned prompt. ``prompt_hash`` content-addresses the *behavioral*
    content (template + constraints + output contract), so a metadata-only edit (author) does
    not change it, while a real instruction change does."""

    analyst: str                                       # the contract module this prompt drives
    prompt_version: str                                # human label, e.g. "v1"
    template: str                                      # the system prompt text
    created_at: str = ""
    author: str = ""
    model_compatibility: tuple[str, ...] = ()          # model ids/families this prompt targets
    reasoning_objectives: tuple[str, ...] = ()         # what the prompt is trying to elicit
    constraints: tuple[str, ...] = ()                  # constitutional invariants it must honor
    expected_output_contract: str = ""                 # the artifact kind it must produce

    @property
    def prompt_hash(self) -> str:
        """Content address of the prompt's behavioral content. Stable across runs/processes."""
        return digest(
            {
                "analyst": self.analyst,
                "template": self.template,
                "constraints": list(self.constraints),
                "expected_output_contract": self.expected_output_contract,
            },
            prefix="ph:",
        )

    def to_record(self) -> dict:
        """Serializable registry record (the row the registry/observability APIs expose)."""
        return {
            "analyst": self.analyst,
            "prompt_version": self.prompt_version,
            "prompt_hash": self.prompt_hash,
            "created_at": self.created_at,
            "author": self.author,
            "model_compatibility": list(self.model_compatibility),
            "reasoning_objectives": list(self.reasoning_objectives),
            "constraints": list(self.constraints),
            "expected_output_contract": self.expected_output_contract,
            "template": self.template,
        }
