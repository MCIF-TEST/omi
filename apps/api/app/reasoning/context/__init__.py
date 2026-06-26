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
from .metrics import context_metrics, estimate_tokens

__all__ = [
    "build_context", "raw_context_text", "AnalystContext", "ContextSection", "ContextStatement",
    "BUDGETS", "CONTEXT_VERSION", "context_metrics", "estimate_tokens",
]
