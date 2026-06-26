"""Institutional Memory graph tests (Sprint 005) — objects, store, retrieval.

Verifies confidence evolution, decay, contradiction tracking, the independence /
memory-influence quarantine, the append-only evidence-gated write path, and deterministic
similarity retrieval with the exculpatory (control) boost.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.evidence import Binder
from app.memory.graph import (
    KnowledgeObject,
    MemoryStore,
    ObservationLedgerEntry,
    retrieve,
)

NOW = datetime(2026, 6, 25, tzinfo=timezone.utc)


def _at(days_ago: float = 0) -> str:
    return (NOW - timedelta(days=days_ago)).isoformat()


def _ko(supports=1, contradicts=0, primed=0, half_life=180.0, days_ago=0.0, is_control=False) -> KnowledgeObject:
    ledger = []
    for i in range(supports):
        ledger.append(ObservationLedgerEntry(
            investigation=f"hist:{i}", stance="supports", independence_key=f"k{i}",
            at=_at(days_ago), memory_influence="primed" if i < primed else "none",
            evidence_refs=[f"d{i}"],
        ))
    for j in range(contradicts):
        ledger.append(ObservationLedgerEntry(
            investigation=f"histc:{j}", stance="contradicts", independence_key=f"c{j}",
            at=_at(days_ago), evidence_refs=[f"e{j}"],
        ))
    return KnowledgeObject(id="ko:x:1", type="BehavioralArchetype", family="patterns",
                           label="burst-amplifier", signature=["temporal"], ledger=ledger,
                           half_life_days=half_life, is_control=is_control)


# --- confidence evolution --------------------------------------------------- #
def test_confidence_rises_with_independent_support():
    assert _ko(1).confidence(NOW) == 0.4
    assert _ko(2).confidence(NOW) > _ko(1).confidence(NOW)
    assert _ko(3).confidence(NOW) > _ko(2).confidence(NOW)


def test_contradiction_lowers_confidence():
    assert _ko(1, 1).confidence(NOW) < _ko(1, 0).confidence(NOW)


def test_decay_lowers_confidence_over_time():
    fresh = _ko(1, days_ago=0).confidence(NOW)
    one_halflife = _ko(1, days_ago=180).confidence(NOW)
    assert abs(one_halflife - fresh * 0.5) < 1e-3       # ~half after one half-life


def test_memory_influence_quarantine():
    # 2 supporting entries but one is memory-primed -> only 1 counts as independent.
    ko = _ko(supports=2, primed=1)
    assert ko.independent_support_count() == 1
    assert ko.confidence(NOW) == _ko(1).confidence(NOW)  # memory cannot confirm itself


def test_stability_and_contradiction_ratio():
    ko = _ko(3, 1)
    assert ko.stability_score() == 0.75
    assert ko.contradiction_ratio() == 0.25


def test_epistemic_status_ladder():
    assert _ko(1).epistemic_status(NOW) == "hypothesized"
    assert _ko(2).epistemic_status(NOW) == "observed"
    assert _ko(3).epistemic_status(NOW) == "corroborated"
    assert _ko(1, 2).epistemic_status(NOW) == "contested"     # contradictions dominate
    assert _ko(1, days_ago=3000).epistemic_status(NOW) == "retired"  # decayed below floor


# --- store: append-only, evidence-gated write path -------------------------- #
def test_ingest_matches_existing_or_creates():
    s = MemoryStore()
    ko = s.ingest(candidate={"type": "CoordinationFingerprint", "signature": ["co_engagement"],
                             "label": "co-engagement ring"},
                  investigation="h1", stance="supports", evidence_refs=["d1"],
                  independence_key="a", at=_at())
    assert len(s) == 1 and len(ko.ledger) == 1
    # same signature -> appends to the same object (recurrence), not a new one
    s.ingest(candidate={"type": "CoordinationFingerprint", "signature": ["co_engagement"]},
             investigation="h2", stance="supports", evidence_refs=["d2"], independence_key="b", at=_at())
    assert len(s) == 1 and len(ko.ledger) == 2
    # different signature -> a new object
    s.ingest(candidate={"type": "CoordinationFingerprint", "signature": ["style_match"]},
             investigation="h3", stance="supports", evidence_refs=["d3"], independence_key="c", at=_at())
    assert len(s) == 2


def test_observe_is_append_only_and_versioned():
    s = MemoryStore()
    ko = s.create(type="BehavioralArchetype", family="patterns", label="x", signature=["temporal"])
    s.observe(ko.id, ObservationLedgerEntry(investigation="h1", stance="supports", at=_at()))
    s.observe(ko.id, ObservationLedgerEntry(investigation="h2", stance="contradicts", at=_at()))
    assert len(ko.ledger) == 2
    assert len(ko.version_history) == 3                 # created + 2 observations


def test_supersede_excludes_from_active_set():
    s = MemoryStore()
    a = s.create(type="X", family="f", label="a", signature=["t"])
    b = s.create(type="X", family="f", label="b", signature=["t"])
    s.supersede(a.id, b.id)
    assert a.superseded_by == b.id
    assert b in s.all() and a not in s.all()


# --- retrieval -------------------------------------------------------------- #
def _bundle():
    payload = {
        "overall_probability": 0.66, "overall_tier": "elevated", "confidence": 0.6,
        "contributions": [
            {"name": "temporal", "impact": 0.4, "direction": "raises"},
            {"name": "community", "impact": 0.2, "direction": "lowers"},
        ],
        "video": {"clusters": [{"method": "co_engagement", "members": ["@a", "@b"]}]},
    }
    return Binder().bind(payload, grain="comment_section", subject_ref="i", platform="youtube")


def _seed(store, *, type, signature, label, is_control=False, days_ago=0.0):
    store.ingest(candidate={"type": type, "signature": signature, "label": label, "is_control": is_control},
                 investigation="h", stance="supports", evidence_refs=["d"], independence_key="a", at=_at(days_ago))


def test_retrieval_matches_by_signature_and_cites_bundle():
    s = MemoryStore()
    _seed(s, type="CoordinationFingerprint", signature=["co_engagement"], label="co-eng")
    priors = retrieve(s, _bundle(), now=NOW)
    assert priors and priors[0].type == "CoordinationFingerprint"
    assert priors[0].evidence_refs and all(r.startswith("ev:") for r in priors[0].evidence_refs)


def test_retrieval_no_match_below_threshold():
    s = MemoryStore()
    _seed(s, type="X", signature=["unrelated_detector"], label="x")
    assert retrieve(s, _bundle(), now=NOW) == []


def test_control_gets_exculpatory_boost():
    s = MemoryStore()
    _seed(s, type="CoordinationFingerprint", signature=["co_engagement"], label="ring")
    _seed(s, type="LegitimateCoordinationControl", signature=["co_engagement"], label="newsroom", is_control=True)
    priors = retrieve(s, _bundle(), now=NOW)
    assert priors[0].is_control is True and priors[0].influence_class == "exculpatory"


def test_decayed_prior_ranks_lower():
    s = MemoryStore()
    _seed(s, type="A", signature=["co_engagement"], label="fresh", days_ago=0)
    _seed(s, type="B", signature=["co_engagement"], label="stale", days_ago=360)
    labels = [p.label for p in retrieve(s, _bundle(), now=NOW)]
    assert labels.index("fresh") < labels.index("stale")
