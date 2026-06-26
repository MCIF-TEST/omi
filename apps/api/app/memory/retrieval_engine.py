"""Scalable, explainable, tier-aware retrieval (Sprint 013).

Omi never scans the whole memory database. Retrieval narrows candidates through the
**index-assisted signature path** (``candidates_for`` — the signature-token index), categorizes
them by the mechanism that would have found them (signature / behavioral / campaign / control)
for **explainability**, filters to **retrievable tiers** (validated and above — candidates are
not surfaced), optionally applies a **temporal** recency filter, then ranks within a **budget**.
Deterministic given ``(store, bundle, now)``; the ``RetrievalPlan`` makes every path auditable
(it records what was scanned vs the corpus size, proving no full scan).
"""
from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from .graph.objects import _parse
from .graph.retrieval import rank_priors
from .tiers import RETRIEVABLE_TIERS, tier_of


@dataclass
class RetrievalPlan:
    basis: str
    strategies: dict
    scanned: int
    corpus_total: int
    retained_after_tier: int
    tier_filter: list
    budget: int
    temporal_window_days: float | None = None

    @property
    def scan_fraction(self) -> float:
        return round(self.scanned / self.corpus_total, 4) if self.corpus_total else 0.0


@dataclass
class RetrievalResult:
    priors: list
    plan: RetrievalPlan
    latency_ms: float

    def to_dict(self) -> dict:
        return {
            "priors": [
                {"ko_id": p.ko_id, "type": p.type, "label": p.label, "score": p.score,
                 "tier": p.tier, "is_control": p.is_control, "influence_class": p.influence_class,
                 "match_basis": p.match_basis, "evidence_refs": list(p.evidence_refs)}
                for p in self.priors
            ],
            "plan": {**asdict(self.plan), "scan_fraction": self.plan.scan_fraction},
            "latency_ms": self.latency_ms,
        }


def _within_window(ko: Any, now: datetime | None, days: float | None) -> bool:
    if days is None:
        return True
    last = _parse(ko.last_observed())
    if last is None:
        return True
    now = now or datetime.now(timezone.utc)
    return (now - last) <= timedelta(days=days)


def retrieve_priors(
    store: Any, bundle: Any, *, budget: int = 5, tiers: tuple = RETRIEVABLE_TIERS,
    now: datetime | None = None, control_boost: float = 1.5, temporal_window_days: float | None = None,
) -> RetrievalResult:
    """Retrieve PriorContext: narrow → categorize → tier-filter → (temporal) → rank within budget.
    Never scans the corpus; every prior carries an explainable ``match_basis`` + ``tier``."""
    t0 = time.perf_counter()
    if hasattr(store, "candidates_for"):
        candidates = store.candidates_for(bundle)
        basis = "signature-token index (no full scan)"
    else:
        candidates = store.all()
        basis = "full set (in-memory store)"

    strategies = {
        "signature": len(candidates),
        "behavioral": sum(1 for k in candidates if k.type == "BehavioralArchetype"),
        "campaign": sum(1 for k in candidates if k.type == "CampaignMemory"),
        "control": sum(1 for k in candidates if k.is_control),
    }

    tier_map = {k.id: tier_of(k, now) for k in candidates}
    tiered = [
        k for k in candidates
        if tier_map[k.id] in tiers and _within_window(k, now, temporal_window_days)
    ]
    ranked = rank_priors(tiered, bundle, top_k=budget, now=now, control_boost=control_boost)
    for p in ranked:                                    # annotate each prior with its tier (explainable)
        p.tier = tier_map.get(p.ko_id)

    plan = RetrievalPlan(
        basis=basis, strategies=strategies, scanned=len(candidates),
        corpus_total=len(store) if hasattr(store, "__len__") else len(candidates),
        retained_after_tier=len(tiered), tier_filter=list(tiers), budget=budget,
        temporal_window_days=temporal_window_days,
    )
    return RetrievalResult(priors=ranked, plan=plan, latency_ms=round((time.perf_counter() - t0) * 1000, 4))
