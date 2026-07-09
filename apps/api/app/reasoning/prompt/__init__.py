"""The ONE Canonical Prompt Builder (Phase P1.1 → P3.3 consolidation).

`build_prompt(stage, bundle)` is the single prompt-assembly implementation for every AI reasoning
stage. It is stage-agnostic: a stage registers a small :class:`StagePromptSpec` (its package assets,
evidence-section rendering, schema ref, and manifest fields) and the builder performs the identical
assembly for all of them, emitting one content-addressed :class:`PromptPackage`.

The builder contains ZERO prompt text: every human-readable string comes from a package asset,
obtained through the ONE Canonical Package Loader. It performs NO inference, invokes NO model, and
calls NO endpoint.
"""
from __future__ import annotations

from .builder import PromptPackage, build_prompt_package
from .stage_builder import (
    StagePromptSpec,
    build_prompt,
    register_stage_prompt,
    registered_stages,
)

__all__ = ["PromptPackage", "StagePromptSpec", "build_prompt", "build_prompt_package",
           "register_stage_prompt", "registered_stages"]
