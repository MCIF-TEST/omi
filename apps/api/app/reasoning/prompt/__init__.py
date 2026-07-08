"""Canonical Prompt Builder (Phase P1.1).

Assembles the final Mistral prompt for one investigation **exclusively from package assets**, taking
the :class:`InvestigationContext` (Phase P1.0) as its ONLY evidence input, and emits one
content-addressed :class:`PromptPackage` (system + user + provenance) ready for the inference stage.

The builder contains ZERO prompt text: every human-readable string in the assembled prompt comes
from a package asset — the ``omi_analyst`` system prompt (registry), the constitution, the specialist
framework, the knowledge library, and the Prompt Template + Response Contract assembly asset. The
builder only fills the template's named slots with those assets and with the InvestigationContext
data. It performs NO inference, invokes NO model, and calls NO endpoint. All assets arrive from the
ONE Canonical Package Loader — the builder never knows where they originate.
"""
from __future__ import annotations

from .builder import PromptPackage, build_prompt_package

__all__ = ["PromptPackage", "build_prompt_package"]
