"""Intelligence Optimization Framework — prompt registry (Sprint 008).

Versioned, content-addressed prompts with config-driven selection, rollback, experiments, and
comparison. AI-backed analysts execute from a registered :class:`PromptSpec` rather than
embedded text, so reasoning quality can be improved through measurable, version-controlled
prompt evolution — without touching the architecture or any constitutional guarantee.
"""
from __future__ import annotations

from .registry import (
    PromptExperiment,
    PromptRegistry,
    compare_prompts,
    default_registry,
)
from .spec import PromptSpec

__all__ = [
    "PromptSpec", "PromptRegistry", "PromptExperiment",
    "compare_prompts", "default_registry",
]
