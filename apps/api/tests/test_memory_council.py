"""Memory-in-the-Council tests (Sprint 005).

Verifies the Memory Analyst as a contract-compliant council specialist: memory artifacts,
blackboard integration, contract validation, and — the constitutional core — that memory
is **context, never proof**: it passes the Governor, surfaces exculpatory priors as
evidence_against, never enters evidence_for, and never changes the echoed number.
"""
from __future__ import annotations

from datetime import datetime, timezone

from app.evidence import Binder
from app.memory.graph import MemoryStore
from app.reasoning.contracts import Memory, validate_artifact
from app.reasoning.orchestrator import (
    AnalystModule,
    BehaviorAnalyst,
    Blackboard,
    CounterEvidenceAnalyst,
    Judge,
    MemoryAnalyst,
    Orchestrator,
)

NOW = datetime(2026, 6, 25, tzinfo=timezone.utc)


def _payload() -> dict:
    return {
        "overall_probability": 0.72, "overall_tier": "elevated", "confidence": 0.6,
        "weak_signals": ["only 8 posts — temporal abstained"], "single_axis_capped": False,
        "contributions": [
            {"name": "temporal", "impact": 0.5, "direction": "raises"},
            {"name": "community", "impact": 0.2, "direction": "lowers"},
            {"name": "ai_writing", "impact": 0.1, "direction": "neutral", "supplemental": True},
        ],
        "video": {
            "clusters": [{"method": "co_engagement", "members": ["@a", "@b", "@c"]}],
            "commenters": [{"handle": "@a", "tier": "high"}],
        },
    }


def _bundle():
    return Binder().bind(_payload(), grain="comment_section", subject_ref="inv1", platform="youtube")


def _store_with_control() -> MemoryStore:
    s = MemoryStore()
    s.ingest(
        candidate={"type": "LegitimateCoordinationControl", "signature": ["co_engagement"],
                   "label": "regional newsroom on-message", "is_control": True},
        investigation="h1", stance="supports", evidence_refs=["digest_x"],
        independence_key="a", at=NOW.isoformat(),
    )
    return s


def _store_with_archetype() -> MemoryStore:
    s = MemoryStore()
    s.ingest(
        candidate={"type": "BehavioralArchetype", "signature": ["temporal"], "label": "burst-amplifier"},
        investigation="h1", stance="supports", evidence_refs=["digest_y"],
        independence_key="a", at=NOW.isoformat(),
    )
    return s


# --- memory artifact + contract validation ---------------------------------- #
def test_memory_analyst_produces_structured_artifact():
    ma = MemoryAnalyst(_store_with_control(), now=NOW)
    m = ma.run(Blackboard(_bundle()).view_for(ma.contract))[0]
    assert m.kind == "memory"
    assert m.contradicting and m.contradicting[0]["influence_class"] == "exculpatory"
    assert m.evidence_refs and all(r.startswith("ev:") for r in m.evidence_refs)


def test_memory_artifact_validates_against_contract():
    bb = Blackboard(_bundle())
    ma = MemoryAnalyst(_store_with_control(), now=NOW)
    m = ma.run(bb.view_for(ma.contract))[0]
    ok, errs = validate_artifact(ma.contract, m, bb)
    assert ok, errs
    m.evidence_refs = ["ev:9999"]                       # fabricated citation
    assert not validate_artifact(ma.contract, m, bb)[0]


# --- blackboard integration ------------------------------------------------- #
def test_judge_view_sees_tier1_memory_artifact():
    bb = Blackboard(_bundle())
    ma = MemoryAnalyst(_store_with_control(), now=NOW)
    bb.post(ma.run(bb.view_for(ma.contract))[0], tier=1)
    assert bb.view_for(Judge.contract).memories()       # Tier-3 Judge sees Tier-1 memory
    assert bb.view_for(MemoryAnalyst(_store_with_control(), now=NOW).contract).memories() == []  # Tier-1 blind


# --- Governor compatibility: memory is context, never proof ----------------- #
def test_council_with_memory_passes_governor_and_preserves_echo():
    council = [BehaviorAnalyst(), MemoryAnalyst(_store_with_control(), now=NOW), CounterEvidenceAnalyst()]
    res = Orchestrator(modules=council).run(_payload(), ref="inv1", platform="youtube")
    assert res.permitted and not res.fallback, res.trace.violation_codes
    a = res.assessment
    assert a["suspicion_probability"] == 0.72            # memory NEVER changes the number
    # the control surfaced as EXCULPATORY evidence_against...
    assert any(e["signal"].startswith("memory:") for e in a["evidence_against"])
    # ...and NEVER as evidence_for (memory never raises suspicion)
    assert all(not e["signal"].startswith("memory:") for e in a["evidence_for"])


def test_supporting_prior_is_context_only():
    council = [BehaviorAnalyst(), MemoryAnalyst(_store_with_archetype(), now=NOW), CounterEvidenceAnalyst()]
    res = Orchestrator(modules=council).run(_payload(), ref="inv1", platform="youtube")
    assert res.permitted
    a = res.assessment
    assert any("Institutional memory" in u for u in a["uncertainty"])   # reported as context
    assert all(not e["signal"].startswith("memory:") for e in a["evidence_for"])


def test_council_with_memory_is_deterministic():
    def _run():
        council = [BehaviorAnalyst(), MemoryAnalyst(_store_with_control(), now=NOW), CounterEvidenceAnalyst()]
        return Orchestrator(modules=council).run(_payload(), ref="inv1", platform="youtube")
    r1, r2 = _run(), _run()
    assert r1.assessment == r2.assessment and r1.trace.trace_id() == r2.trace.trace_id()


# --- AI readiness ----------------------------------------------------------- #
def test_memory_analyst_satisfies_module_interface():
    assert isinstance(MemoryAnalyst(_store_with_control(), now=NOW), AnalystModule)
