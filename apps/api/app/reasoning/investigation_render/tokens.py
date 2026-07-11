"""A deterministic, dependency-free token estimator for evidence budgeting.

This is an **estimate**, not the Mistral tokenizer: no tokenizer library is present in the runtime, so
budgeting uses a BPE-approximating proxy — word chunks and punctuation each cost one token, and long
identifiers split into ~4-char sub-words (mirroring how BPE fragments ``coordination_score``). It is
deterministic (same text → same count) so budget decisions are reproducible and content-addressable.
Every token figure the render layer reports is this estimate; a real tokenizer would only refine it.
"""
from __future__ import annotations

import json
import re
from typing import Any

_TOKEN_RE = re.compile(r"\w+|[^\w\s]")
_SUBWORD = 4  # long words fragment into ~4-char BPE sub-words


def estimate_tokens(text: str) -> int:
    """A BPE-approximating token estimate for a string. Deterministic; documented as an estimate."""
    if not text:
        return 0
    n = 0
    for chunk in _TOKEN_RE.findall(text):
        n += 1 + (len(chunk) - 1) // _SUBWORD
    return n


def estimate_json_tokens(obj: Any) -> int:
    """Estimate the token cost of an object as it will be rendered — canonical JSON (the render layer
    serializes evidence sections as sorted-key JSON)."""
    return estimate_tokens(json.dumps(obj, ensure_ascii=False, sort_keys=True, default=str))


__all__ = ["estimate_tokens", "estimate_json_tokens"]
