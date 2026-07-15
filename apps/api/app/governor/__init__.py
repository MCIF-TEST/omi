"""Constitutional Governor (OMI_CONSTITUTIONAL_GOVERNOR_V1 / Sprint 002).

A deterministic, model-free validation layer: it reads a candidate assessment (Ruling)
and its Evidence Bundle and issues PERMIT or REJECT against a fixed constitution, with an
immutable ValidationTrace. It never reasons and never edits — a non-compliant assessment
is rejected (fallback to the Floor), never repaired. Standalone + additive; imports only
the Evidence layer, changes no existing behavior.
"""
from __future__ import annotations

from .audit import AuditLog, ValidationTrace
from .comprehensive import validate_comprehensive_model_output, validate_comprehensive_sections
from .governor import BANNED_PHRASES, CONSTITUTION_VERSION, Governor

__all__ = ["Governor", "ValidationTrace", "AuditLog", "BANNED_PHRASES", "CONSTITUTION_VERSION",
           "validate_comprehensive_sections", "validate_comprehensive_model_output"]
