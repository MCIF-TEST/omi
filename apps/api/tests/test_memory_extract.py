"""Memory write-loop tests (Sprint 006 — evidence-gated extractor).

Sprint 005 gave memory a read side (store + retrieval); this closes the loop: a settled
Evidence Bundle becomes structural KnowledgeObject candidates and append-only observations.
The constitutional guarantees are asserted here in code — patterns never verdicts, the
memory-influence quarantine (memory can't confirm itself), self-correction via
contradiction, determinism, and a full write -> read round-trip.
"""
from __future__ import annotations

from datetime import datetime, timezone

from app.evidence import Binder
from app.memory.graph import (
    MemoryStore,
    extract_candidates,
    record_settled_investigation,
    retrieve,
)

NOW = datetime(2026, 6, 25, tzinfo=timezone.utc)


def _payload() -> dict:
    return {
        "overall_probability": 0.72, "overall_tier": "elevated", "confidence": 0.6,
        "weak_signals": ["only 8 posts"], "single_axis_capped": False,
        "contributions": [
            {"name": "temporal", "impact": 0.5, "direction": "raises"},
            {"name": "community", "impact": 0.2, "direction": "lowers"},
            {"name": "ai_writing", "impact": 0.1, "direction": "neutral", "supplemental": True},
        ],
        "video": {"clusters": [{"method": "co_engagement", "members": ["@a", "@b", "@c"]}]},
    }


def _bundle():
    return Binder().bind(_payload(), grain="comment_section", subject_ref="inv1", platform="youtube")


def _by_type(store: MemoryStore, type_: str):
    return next((k for k in store.all() if k.type == type_), None)


# --- extraction: patterns, never verdicts ----------------------------------- #
def test_extract_yields_behavioral_and_coordination_signatures():
    cands = extract_candidates(_bundle())
    by = {c["type"]: c for c in cands}
    assert by["BehavioralArchetype"]["signature"] == ["temporal"]            # raising, non-supplemental
    assert by["CoordinationSignature"]["signature"] == ["co_engagement"]     # discriminative only


def test_extract_control_yields_only_the_control():
    cands = extract_candidates(_bundle(), is_control=True)
    assert len(cands) == 1
    assert cands[0]["type"] == "LegitimateCoordinationControl" and cands[0]["is_control"] is True
    assert cands[0]["signature"] == ["co_engagement"]


def test_extracted_candidate_carries_no_verdict():
    # a candidate is a structural pattern — no probability / tier / verdict leaks in.
    keys = set().union(*(c.keys() for c in extract_candidates(_bundle())))
    assert not (keys & {"overall_probability", "probability", "tier", "verdict", "suspicion"})


# --- recording: append-only knowledge objects ------------------------------- #
def test_record_creates_knowledge_objects_with_evidence():
    store = MemoryStore()
    affected = record_settled_investigation(
        store, _bundle(), investigation="h1", independence_key="a", at=NOW.isoformat(),
    )
    assert {k.type for k in affected} == {"BehavioralArchetype", "CoordinationSignature"}
    ko = _by_type(store, "CoordinationSignature")
    assert ko.confidence(NOW) > 0 and ko.ledger[0].evidence_refs    # evidence-gated, not empty


def test_repeated_records_append_independent_support():
    store = MemoryStore()
    for key in ("a", "b"):
        record_settled_investigation(
            store, _bundle(), investigation=f"inv-{key}", independence_key=key, at=NOW.isoformat(),
        )
    assert len(store) == 2                                          # matched, not duplicated
    ko = _by_type(store, "BehavioralArchetype")
    assert len(ko.ledger) == 2 and ko.independent_support_count() == 2
    assert ko.epistemic_status(NOW) == "observed"


# --- the loop-breaker: memory cannot confirm itself ------------------------- #
def test_primed_observation_is_quarantined():
    store = MemoryStore()
    record_settled_investigation(
        store, _bundle(), investigation="h1", independence_key="a", at=NOW.isoformat(),
        primed_signatures=["co_engagement"],            # memory surfaced this coordination prior
    )
    coord = _by_type(store, "CoordinationSignature")
    behav = _by_type(store, "BehavioralArchetype")
    assert coord.ledger[0].memory_influence == "primed"
    assert coord.independent_support_count() == 0       # primed -> cannot self-confirm
    assert coord.confidence(NOW) == 0.0
    assert behav.independent_support_count() == 1        # untouched pattern still counts


# --- self-correction: contradiction lowers confidence ----------------------- #
def test_contradiction_lowers_confidence_and_can_contest():
    store = MemoryStore()
    record_settled_investigation(
        store, _bundle(), investigation="h1", independence_key="a", at=NOW.isoformat())
    ko = _by_type(store, "CoordinationSignature")
    supported = ko.confidence(NOW)
    record_settled_investigation(                       # a later scan contradicts the pattern
        store, _bundle(), investigation="h2", independence_key="b", at=NOW.isoformat(),
        stance="contradicts")
    assert ko.confidence(NOW) < supported and ko.contradiction_ratio() > 0   # self-correction
    record_settled_investigation(                       # contradictions now outnumber support
        store, _bundle(), investigation="h3", independence_key="c", at=NOW.isoformat(),
        stance="contradicts")
    assert ko.epistemic_status(NOW) == "contested"      # n_con > n_sup


# --- write -> read round-trip + determinism --------------------------------- #
def test_recorded_control_round_trips_into_retrieval():
    store = MemoryStore()
    record_settled_investigation(
        store, _bundle(), investigation="h1", independence_key="a", at=NOW.isoformat(),
        is_control=True)
    priors = retrieve(store, _bundle(), now=NOW)
    assert priors and priors[0].is_control and priors[0].influence_class == "exculpatory"


def test_record_is_deterministic():
    def _run():
        s = MemoryStore()
        record_settled_investigation(
            s, _bundle(), investigation="h1", independence_key="a", at=NOW.isoformat())
        return [(k.id, tuple(k.signature), k.confidence(NOW)) for k in s.all()]
    assert _run() == _run()
