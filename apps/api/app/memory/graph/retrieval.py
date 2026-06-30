"""Deterministic PriorContext retrieval — institutional memory as the council's 2nd input.

Given an Evidence Bundle, rank relevant knowledge objects into a bounded ``PriorContext``.
A prior matches by **containment** — how much of its characterizing signature (the firing
detectors/methods) is present in the current evidence — weighted by the object's
confidence × stability; controls get an **exculpatory boost** (memory is freer to exonerate
than to incriminate). Matched references are **bundle** evidence ids (resolvable for
citation); the ``ko_id`` is provenance. Retrieval is a deterministic function of
``(store, bundle, now)`` — no model involved.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from app.evidence.bundle import EvidenceBundle

from .store import MemoryStore

_SIGNATURE_KINDS = frozenset({"contribution", "coordination_method", "detector_signal"})


@dataclass
class RankedPrior:
    ko_id: str
    type: str
    label: str
    confidence: float
    stability_score: float
    epistemic_status: str
    contradiction_ratio: float
    is_control: bool
    influence_class: str            # context | exculpatory (never discriminative)
    match_basis: str
    score: float
    evidence_refs: list[str] = field(default_factory=list)   # bundle ev ids that matched
    tier: str | None = None                                  # distillation tier (Sprint 013), set by the engine
    usefulness: float = 0.0                                  # learned retrieval-usefulness (Sprint 014; ranking only)


def bundle_signature(bundle: EvidenceBundle) -> set[str]:
    """The firing detector/method names in the bundle (non-supplemental) — the query key."""
    return {
        it.originating_detector for it in bundle.evidence.values()
        if it.kind in _SIGNATURE_KINDS and not it.supplemental
    }


def _containment(ko_sig: set[str], bundle_sig: set[str]) -> float:
    """Share of the prior's signature present in the current evidence."""
    return (len(ko_sig & bundle_sig) / len(ko_sig)) if ko_sig else 0.0


def _matched_refs(bundle: EvidenceBundle, signature: set[str]) -> list[str]:
    return [it.id for it in bundle.evidence.values() if it.originating_detector in signature][:5]


def rank_priors(
    objects: "list", bundle: EvidenceBundle, *,
    top_k: int = 5, now: datetime | None = None,
    min_match: float = 0.5, control_boost: float = 1.5,
    usefulness: dict | None = None, usefulness_weight: float = 0.2,
) -> list[RankedPrior]:
    """Rank a given list of KnowledgeObjects against the bundle — the constitutional scoring,
    independent of where the objects came from (in-memory or Postgres). Deterministic.

    ``usefulness`` ({ko_id: rate in 0..1}) is the *learned* retrieval signal (Sprint 014): a memory
    the institution has repeatedly found useful gets a small, bounded ranking bonus
    (``score *= 1 + usefulness_weight * rate``, ≤ +20% by default). This influences RANKING ONLY —
    it never changes a prior's confidence/stability/contradiction (the constitutional measurements,
    still read straight from the ledger) nor any investigation score; it only reorders which priors
    surface first within the budget."""
    sig = bundle_signature(bundle)
    use = usefulness or {}
    out: list[RankedPrior] = []
    for ko in objects:
        ko_sig = set(ko.signature)
        m = _containment(ko_sig, sig)
        if m < min_match:
            continue
        conf = ko.confidence(now)
        stab = ko.stability_score()
        score = m * (0.4 + 0.6 * conf) * (0.5 + 0.5 * stab)
        if ko.is_control:
            score *= control_boost                       # exculpatory asymmetry
        u = max(0.0, min(1.0, float(use.get(ko.id, 0.0))))
        score *= 1.0 + usefulness_weight * u             # learned usefulness — ranking only, bounded
        out.append(RankedPrior(
            ko_id=ko.id, type=ko.type, label=ko.label, confidence=conf, stability_score=stab,
            epistemic_status=ko.epistemic_status(now), contradiction_ratio=ko.contradiction_ratio(),
            is_control=ko.is_control,
            influence_class=("exculpatory" if ko.is_control else ko.influence_class),
            match_basis=f"signature containment {round(m, 2)} over {sorted(ko_sig & sig)}",
            score=round(score, 4), evidence_refs=_matched_refs(bundle, ko_sig), usefulness=round(u, 4),
        ))
    out.sort(key=lambda r: (-r.score, r.ko_id))          # deterministic: score desc, ko_id tiebreak
    return out[:top_k]


def retrieve(
    store: Any, bundle: EvidenceBundle, *,
    top_k: int = 5, now: datetime | None = None,
    min_match: float = 0.5, control_boost: float = 1.5,
    usefulness: dict | None = None,
) -> list[RankedPrior]:
    """Return the top-K relevant priors from a store. Backend-agnostic: ``store`` may narrow the
    candidate set (``candidates_for``) for scale, else all objects are ranked. Deterministic.
    ``usefulness`` is the optional learned ranking signal (Sprint 014; ranking only)."""
    objects = store.candidates_for(bundle) if hasattr(store, "candidates_for") else store.all()
    return rank_priors(objects, bundle, top_k=top_k, now=now, min_match=min_match,
                       control_boost=control_boost, usefulness=usefulness)
