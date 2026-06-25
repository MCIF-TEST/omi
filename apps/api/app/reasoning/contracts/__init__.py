"""Reasoning Contracts (OMI_REASONING_ORCHESTRATION_V1 §E / Sprint 004).

The model-agnostic interfaces every analyst module communicates through. Typed artifacts
(Finding / Critique / Ruling) carry evidence references; a ``ReasoningContract`` declares a
module's tier, lens, output kind, and constraints. This is the seam that lets any future
reasoning model (Qwen, LoRA, ensemble) replace a deterministic analyst **without changing
orchestration** — modules never couple to each other, only to these contracts.
"""
from __future__ import annotations

from .artifacts import Artifact, Critique, Finding, Memory, Ruling
from .contract import ReasoningContract, validate_artifact

__all__ = [
    "Artifact", "Finding", "Critique", "Ruling", "Memory",
    "ReasoningContract", "validate_artifact",
]
