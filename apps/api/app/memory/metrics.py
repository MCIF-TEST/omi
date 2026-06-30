"""Institutional-memory engineering metrics (Sprint 013).

Deterministic measurements over the tiered memory: growth, tier distribution, the distillation
ratio (how much memory has been distilled past raw candidates), and storage shape. Exposed via
the admin API so memory growth and retrieval economics are observable as the corpus scales to
millions of investigations. Pure functions of ``(store, now)``.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from .compression import compression_potential
from .feedback import aggregate_feedback
from .quality_signals import quality_of
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


def dashboard(store: Any, *, feedback: list | None = None, now: datetime | None = None,
              top: int = 5) -> dict:
    """The institutional-knowledge dashboard (Sprint 014) — a deterministic, read-only snapshot of
    memory health: tier distribution + distillation (``memory_stats``), how much denser compression
    could make it, reuse frequency, the strongest archetypes and institutional patterns, memories
    that are retrievable yet never reused, and **retrieval precision** (the share of retrievals that
    proved genuinely useful — influenced AND Governor-accepted AND analyst-agreed).

    A pure function of ``(store, feedback, now)`` that NEVER mutates the store or any score — every
    number is a measurement. ``feedback`` defaults to the store's own ``feedback()`` when present."""
    fb_rows = feedback if feedback is not None else (store.feedback() if hasattr(store, "feedback") else [])
    agg = aggregate_feedback(fb_rows)

    base = memory_stats(store, now=now)
    active = store.all()
    tier_map = {k.id: tier_of(k, now) for k in active}

    reuses = [int(getattr(k, "reuse_count", 0)) for k in active]
    total_reuse = sum(reuses)
    reused_objects = sum(1 for r in reuses if r > 0)

    q = [quality_of(k, agg, now=now) for k in active]
    by_quality = sorted(q, key=lambda r: (-r["quality"], r["ko_id"]))
    top_archetypes = [r for r in by_quality if tier_map.get(r["ko_id"]) == ARCHETYPE][:top]
    top_institutional = [r for r in by_quality if tier_map.get(r["ko_id"]) == INSTITUTIONAL][:top]
    unused = sorted(
        (r["ko_id"] for r in q
         if tier_map.get(r["ko_id"]) in RETRIEVABLE_TIERS and r["reuse_count"] == 0)
    )

    total_retrievals = sum(a["reuse_count"] for a in agg.values())
    useful_retrievals = sum(a["useful"] for a in agg.values())
    precision = round(useful_retrievals / total_retrievals, 4) if total_retrievals else 0.0

    return {
        **base,
        "compression": compression_potential(store, now=now),
        "reuse": {
            "total_reuse": total_reuse,
            "reused_objects": reused_objects,
            "mean_reuse": round(total_reuse / len(active), 4) if active else 0.0,
        },
        "retrieval_precision": precision,
        "retrieval_events": total_retrievals,
        "top_archetypes": top_archetypes,
        "top_institutional": top_institutional,
        "unused_retrievable": unused,
        "unused_count": len(unused),
    }
