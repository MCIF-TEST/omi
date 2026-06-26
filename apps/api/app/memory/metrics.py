"""Institutional-memory engineering metrics (Sprint 013).

Deterministic measurements over the tiered memory: growth, tier distribution, the distillation
ratio (how much memory has been distilled past raw candidates), and storage shape. Exposed via
the admin API so memory growth and retrieval economics are observable as the corpus scales to
millions of investigations. Pure functions of ``(store, now)``.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from .tiers import ARCHETYPE, ARCHIVED, INSTITUTIONAL, RETRIEVABLE_TIERS, tier_of


def memory_stats(store: Any, *, now: datetime | None = None) -> dict:
    """Tier distribution + growth + distillation metrics. ``distillation_ratio`` is the share of
    active memory that has been distilled to an archetype or institutional pattern — the measure
    of memory becoming progressively refined rather than merely accumulating."""
    objs = store.all(include_superseded=True)
    by_tier: dict[str, int] = {}
    observations = 0
    for ko in objs:
        by_tier[tier_of(ko, now)] = by_tier.get(tier_of(ko, now), 0) + 1
        observations += len(ko.ledger)

    active = len(objs) - by_tier.get(ARCHIVED, 0)
    distilled = by_tier.get(ARCHETYPE, 0) + by_tier.get(INSTITUTIONAL, 0)
    retrievable = sum(by_tier.get(t, 0) for t in RETRIEVABLE_TIERS)
    return {
        "knowledge_objects": len(objs),
        "active": active,
        "archived": by_tier.get(ARCHIVED, 0),
        "by_tier": by_tier,
        "retrievable": retrievable,
        "ledger_observations": observations,
        "distillation_ratio": round(distilled / active, 4) if active else 0.0,
        "retrievable_ratio": round(retrievable / active, 4) if active else 0.0,
        "observations_per_object": round(observations / len(objs), 4) if objs else 0.0,
    }
