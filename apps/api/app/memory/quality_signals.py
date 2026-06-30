"""Adaptive memory quality — measurement only (Sprint 014).

A memory's *quality* is a deterministic measurement combining its **derived epistemics** (read
from the append-only ledger: confidence × stability, contradiction, epistemic status) with its
**retrieval track-record** (how often it was reused and how often that reuse was genuinely useful —
influenced reasoning AND the Governor accepted the ruling AND the analyst agreed).

Hard rule: this is **measurement, never control**. ``quality_of`` returns numbers; it NEVER edits
a memory, its confidence, its tier, an investigation's score, the Governor, or OmiScore. Quality
informs the dashboard and (via ``usefulness_map``) retrieval **ranking** only — it can change the
*order* priors are surfaced in, never *whether* a pattern is true or *what* an investigation scores.
A pure function of ``(ko, feedback_agg, now)``.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any


def quality_of(ko: Any, feedback_agg: dict | None = None, *, now: datetime | None = None) -> dict:
    """A measurement of one memory's quality. ``feedback_agg`` is the per-ko aggregate from
    ``aggregate_feedback`` ({ko_id: {reuse_count, useful, usefulness, last_validated}}); absent
    feedback simply means an untested memory (usefulness 0.0). The ``quality`` composite is a
    bounded 0..1 ranking aid — NOT a verdict and NEVER fed back into any score."""
    fb = (feedback_agg or {}).get(ko.id, {})
    conf = ko.confidence(now)
    stab = ko.stability_score()
    contra = ko.contradiction_ratio()
    usefulness = float(fb.get("usefulness", 0.0))
    reuse = int(fb.get("reuse_count", getattr(ko, "reuse_count", 0)))   # feedback agg authoritative
    # Bounded composite for dashboards/ranking: evidential strength, dragged down by contradiction,
    # lifted by a proven-useful track record. Measurement only.
    composite = round(0.5 * conf * stab + 0.2 * (1.0 - contra) + 0.3 * usefulness, 4)
    return {
        "ko_id": ko.id,
        "type": ko.type,
        "label": ko.label,
        "confidence": conf,
        "stability": stab,
        "contradiction_ratio": contra,
        "epistemic_status": ko.epistemic_status(now),
        "reuse_count": reuse,
        "usefulness": usefulness,
        "last_validated": fb.get("last_validated"),
        "is_control": bool(ko.is_control),
        "quality": composite,
    }


def quality_rankings(
    store: Any, feedback_agg: dict | None = None, *, now: datetime | None = None,
) -> list[dict]:
    """Quality measurement for every active memory, ordered by quality desc (id tiebreak) —
    deterministic. The dashboard's quality view; never mutates the store."""
    rows = [quality_of(ko, feedback_agg, now=now) for ko in store.all()]
    rows.sort(key=lambda r: (-r["quality"], r["ko_id"]))
    return rows
