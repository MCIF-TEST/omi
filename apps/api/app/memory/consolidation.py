"""Background intelligence pipeline — deterministic consolidation + distillation (Sprint 013).

Learning happens **off the live path**: an investigation writes a raw observation and returns;
consolidation runs later (background worker / scheduled job). A single deterministic pass over
the store classifies each KnowledgeObject's tier, records promotions / demotions / archival as
version revisions (evidence-backed + reproducible), refreshes the cached tier for fast
tier-filtered queries, and reports the memory distribution.

No expensive learning runs during a live investigation; no score / Governor change; nothing is
fabricated; the pass is a pure function of ``(store state, now)`` so it is fully replayable.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

from .tiers import ARCHIVED, tier_of, tier_rank


@dataclass
class ConsolidationReport:
    """The deterministic outcome of a consolidation pass."""

    total: int
    by_tier: dict
    promotions: list = field(default_factory=list)
    demotions: list = field(default_factory=list)
    archivals: list = field(default_factory=list)
    ran_at: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def consolidate(store: Any, *, now: datetime | None = None) -> ConsolidationReport:
    """Run one consolidation pass: classify every object's tier, persist transitions (evidence-
    backed revisions), and report. Deterministic given ``(store, now)``. Idempotent — re-running
    on an unchanged store yields no new transitions."""
    objs = sorted(store.all(include_superseded=True), key=lambda k: k.id)
    cached = store.tiers() if hasattr(store, "tiers") else {}
    by_tier: dict[str, int] = {}
    promotions: list[dict] = []
    demotions: list[dict] = []
    archivals: list[dict] = []

    for ko in objs:
        new = tier_of(ko, now)
        by_tier[new] = by_tier.get(new, 0) + 1
        prev = cached.get(ko.id)
        if prev == new:
            continue
        if hasattr(store, "set_tier"):
            store.set_tier(ko.id, new)
        entry = {"ko_id": ko.id, "from": prev, "to": new}
        if new == ARCHIVED:
            archivals.append(entry)
        elif prev is None or tier_rank(new) > tier_rank(prev):
            promotions.append(entry)
        else:
            demotions.append(entry)

    return ConsolidationReport(
        total=len(objs), by_tier=by_tier, promotions=promotions, demotions=demotions,
        archivals=archivals, ran_at=(now or datetime.now(timezone.utc)).isoformat(),
    )
