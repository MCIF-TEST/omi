"""Context Builder subsystem (Sprint 009).

Deterministic, versioned, fully-attributed context generation for AI specialists. Improves
reasoning quality by improving the *information* supplied to the model — never the model size
or council complexity — and any future AI specialist inherits it without architectural change.
"""
from __future__ import annotations

from .builder import (
    BUDGETS,
    CONTEXT_VERSION,
    AnalystContext,
    ContextSection,
    ContextStatement,
    build_context,
    raw_context_text,
)
from .investigation import (
    INVESTIGATION_CONTEXT_VERSION,
    SECTION_ORDER,
    InvestigationContext,
    build_investigation_context,
)
from .metrics import context_metrics, estimate_tokens

__all__ = [
    "build_context", "raw_context_text", "AnalystContext", "ContextSection", "ContextStatement",
    "BUDGETS", "CONTEXT_VERSION", "context_metrics", "estimate_tokens",
    # Phase P1.0 — the Investigation Context Builder (evidence assembly; no prompts/inference).
    "build_investigation_context", "InvestigationContext", "INVESTIGATION_CONTEXT_VERSION",
    "SECTION_ORDER",
]
