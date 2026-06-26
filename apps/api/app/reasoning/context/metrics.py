"""Context quality metrics (Sprint 009).

Deterministic measurements over a built context — how faithfully it carries the bundle's
evidence and how it trades size for completeness. Exposed through Shadow Mode so structured
context can be compared to raw evidence on quality, not just on whether the model's read
changed.

- **evidence_coverage** — share of the bundle's informative (non-supplemental) evidence items
  that the context cites at least once.
- **citation_retention** — share of context statements that carry a reference (target 1.0: no
  synthesized statement loses traceability).
- **compression_ratio** — context tokens / raw-context tokens (below 1 compresses, above 1 expands).
- **token_utilization** — context tokens / the budget's token cap.
- **context_completeness** — share of the budget's sections that are populated.
"""
from __future__ import annotations

from typing import Any

_INFORMATIVE_KINDS = frozenset({"contribution", "coordination_method", "detector_signal"})


def estimate_tokens(text: str) -> int:
    """A deterministic, dependency-free token estimate (~4 chars/token)."""
    return max(1, len((text or "").strip()) // 4)


def context_metrics(
    bundle: Any, sections: list, *, budget: str, raw_text: str, context_text: str, token_cap: int,
) -> dict:
    """Compute the quality metrics for a built context. Pure + deterministic."""
    informative = {
        it.id for it in bundle.evidence.values()
        if not it.supplemental and it.kind in _INFORMATIVE_KINDS
    }
    cited_ev: set[str] = set()
    total = 0
    cited = 0
    for section in sections:
        for st in section.statements:
            total += 1
            if st.evidence_refs:
                cited += 1
            for ref in st.evidence_refs:
                if ref in bundle.evidence:        # only resolvable bundle ids count for coverage
                    cited_ev.add(ref)

    ctx_tokens = estimate_tokens(context_text)
    raw_tokens = estimate_tokens(raw_text)
    covered = len(cited_ev & informative)
    populated = sum(1 for s in sections if s.statements)
    return {
        "evidence_coverage": round(covered / len(informative), 4) if informative else 1.0,
        "citation_retention": round(cited / total, 4) if total else 1.0,
        "compression_ratio": round(ctx_tokens / raw_tokens, 4) if raw_tokens else 1.0,
        "token_utilization": round(ctx_tokens / token_cap, 4) if token_cap else 0.0,
        "context_completeness": round(populated / len(sections), 4) if sections else 0.0,
        "context_tokens": ctx_tokens,
        "raw_tokens": raw_tokens,
        "statements": total,
        "informative_evidence": len(informative),
        "cited_evidence": covered,
    }
