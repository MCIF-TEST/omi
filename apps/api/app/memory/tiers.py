"""Memory tiers — the deterministic distillation lifecycle (Sprint 013).

Institutional memory is tiered, not flat: not every observation becomes permanent memory. A
``KnowledgeObject``'s tier is a **pure, reproducible function** of its epistemic state (support /
stability / confidence / age) — all derived from the append-only ledger, never stored as a
verdict. The lifecycle:

    raw observation → candidate → validated → archetype → institutional   (+ archived)

- **raw** — an observation in the ledger (not a stored KnowledgeObject).
- **candidate** — hypothesized or contested (not yet corroborated). NOT surfaced to reasoning.
- **validated** — observed across ≥ 2 independent investigations.
- **archetype** — corroborated (≥ 3 independent supports, stable).
- **institutional** — corroborated, highly stable, long-lived, many independent supports.
- **archived** — retired (decayed below floor) or superseded — kept for audit, never retrieved.

Only ``validated`` and above inform PriorContext, so memory becomes progressively distilled.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .graph.objects import _parse

RAW = "raw"
CANDIDATE = "candidate"
VALIDATED = "validated"
ARCHETYPE = "archetype"
INSTITUTIONAL = "institutional"
ARCHIVED = "archived"

# The active distillation ladder (raw lives in the ledger, archived is excluded).
TIER_LADDER = (CANDIDATE, VALIDATED, ARCHETYPE, INSTITUTIONAL)
# Tiers that may inform reasoning — candidates are deliberately NOT surfaced.
RETRIEVABLE_TIERS = (VALIDATED, ARCHETYPE, INSTITUTIONAL)

_INSTITUTIONAL_MIN_SUPPORT = 5
_INSTITUTIONAL_MIN_STABILITY = 0.8
_INSTITUTIONAL_MIN_CONFIDENCE = 0.5
_INSTITUTIONAL_MIN_AGE_DAYS = 30.0

_RANK = {ARCHIVED: 0, RAW: 0, CANDIDATE: 1, VALIDATED: 2, ARCHETYPE: 3, INSTITUTIONAL: 4}


def _age_days(ko: Any, now: datetime | None) -> float:
    first = _parse(ko.first_observed())
    if first is None:
        return 0.0
    now = now or datetime.now(timezone.utc)
    return max(0.0, (now - first).total_seconds() / 86400.0)


def tier_of(ko: Any, now: datetime | None = None) -> str:
    """The distillation tier of a KnowledgeObject — deterministic, derived from the ledger."""
    status = ko.epistemic_status(now)
    if status in ("superseded", "retired"):
        return ARCHIVED
    if status == "corroborated":
        if (ko.independent_support_count() >= _INSTITUTIONAL_MIN_SUPPORT
                and ko.stability_score() >= _INSTITUTIONAL_MIN_STABILITY
                and ko.confidence(now) >= _INSTITUTIONAL_MIN_CONFIDENCE
                and _age_days(ko, now) >= _INSTITUTIONAL_MIN_AGE_DAYS):
            return INSTITUTIONAL
        return ARCHETYPE
    if status == "observed":
        return VALIDATED
    return CANDIDATE                                    # hypothesized | contested


def tier_rank(tier: str) -> int:
    return _RANK.get(tier, 0)


def is_retrievable(tier: str) -> bool:
    return tier in RETRIEVABLE_TIERS
