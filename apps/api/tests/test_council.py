"""Analyst Council foundation tests (Sprint 004).

Covers the permanent execution framework: the Blackboard, Reasoning Contracts, the
deterministic council modules, the Orchestrator, mandatory Governor integration, the Floor
fallback, deterministic execution, and — the architectural goal — that a new module plugs
in through the contract without any orchestration change.
"""
from __future__ import annotations

import pytest

from app.evidence import Binder
from app.reasoning.contracts import Critique, Finding, ReasoningContract, validate_artifact
from app.reasoning.orchestrator import (
    AnalystModule,
    BehaviorAnalyst,
    Blackboard,
    BudgetController,
    CounterEvidenceAnalyst,
    Orchestrator,
)


def _payload() -> dict:
    return {
        "overall_probability": 0.72, "overall_tier": "elevated", "confidence": 0.6,
        "weak_signals": ["only 8 posts — temporal abstained"], "single_axis_capped": False,
        "contributions": [
            {"name": "temporal", "impact": 0.5, "logit_delta": 0.8, "direction": "raises"},
            {"name": "community", "impact": 0.2, "logit_delta": -0.3, "direction": "lowers"},
            {"name": "ai_writing", "impact": 0.1, "logit_delta": 0.0,
             "direction": "neutral", "supplemental": True},
        ],
        "video": {
            "clusters": [{"method": "co_engagement", "members": ["@a", "@b", "@c"]}],
            "commenters": [{"handle": "@a", "tier": "high"}],
        },
    }


def _bundle():
    return Binder().bind(_payload(), grain="comment_section", subject_ref="inv1", platform="youtube")


def _ev(bundle) -> str:
    return next(iter(bundle.evidence))


# --- Blackboard ------------------------------------------------------------- #
def test_blackboard_append_only_and_phase_gated_views():
    bundle = _bundle()
    bb = Blackboard(bundle)
    assert bb.citations == bundle.citation_index()       # shared citation registry
    assert bb.resolve(_ev(bundle)) is True               # immutable evidence references

    # Tier-1 view sees no upstream artifacts (blind specialists)
    assert bb.view_for(BehaviorAnalyst.contract).findings() == []
    bb.post(Finding(module="behavior_analyst", signal="temporal", claim="c",
                    direction="raises", evidence_refs=[_ev(bundle)]), tier=1)
    # a peer Tier-1 module still sees nothing (strictly lower tier)
    assert bb.view_for(BehaviorAnalyst.contract).findings() == []
    # a Tier-2 module sees the Tier-1 finding
    assert len(bb.view_for(CounterEvidenceAnalyst.contract).findings()) == 1
    assert len(bb.artifacts()) == 1                       # append-only


# --- Reasoning Contracts ---------------------------------------------------- #
def test_contract_is_versioned_and_frozen():
    c = BehaviorAnalyst.contract
    assert c.contract_version == "v1" and c.tier == 1 and c.output_kind == "finding"
    with pytest.raises(Exception):
        c.tier = 2                                        # frozen interface


def test_contract_validation_resolves_or_rejects():
    bundle = _bundle(); bb = Blackboard(bundle)
    good = Finding(module="behavior_analyst", signal="temporal", claim="c",
                   direction="raises", evidence_refs=[_ev(bundle)])
    ok, errs = validate_artifact(BehaviorAnalyst.contract, good, bb)
    assert ok, errs
    # wrong kind for the contract
    wrong = Critique(module="x", evidence_refs=[])
    assert not validate_artifact(BehaviorAnalyst.contract, wrong, bb)[0]
    # unresolved citation
    bad = Finding(module="x", signal="t", claim="c", direction="raises", evidence_refs=["ev:9999"])
    ok3, errs3 = validate_artifact(BehaviorAnalyst.contract, bad, bb)
    assert not ok3 and any("unresolved" in e for e in errs3)


def test_invalid_output_kind_raises():
    with pytest.raises(ValueError):
        ReasoningContract(module="x", tier=1, output_kind="nonsense")


# --- Council modules -------------------------------------------------------- #
def test_behavior_analyst_emits_cited_findings_excluding_supplemental():
    bb = Blackboard(_bundle())
    findings = BehaviorAnalyst().run(bb.view_for(BehaviorAnalyst.contract))
    assert findings and all(f.kind == "finding" for f in findings)
    assert all(f.signal != "ai_writing" for f in findings)        # supplemental excluded
    assert {f.direction for f in findings} >= {"raises", "lowers"}
    assert all(f.evidence_refs and bb.resolve(f.evidence_refs[0]) for f in findings)


def test_counter_evidence_emits_critique():
    bb = Blackboard(_bundle())
    crit = CounterEvidenceAnalyst().run(bb.view_for(CounterEvidenceAnalyst.contract))[0]
    assert crit.kind == "critique"
    assert crit.exculpatory and crit.would_flip_if


# --- Orchestrator + mandatory Governor -------------------------------------- #
def test_council_runs_and_passes_governor():
    res = Orchestrator().run(_payload(), ref="inv1", platform="youtube")
    assert res.permitted and not res.fallback
    assert res.trace.verdict == "permit", res.trace.violation_codes
    a = res.assessment
    assert a["suspicion_probability"] == 0.72              # echo, not recomputed
    assert a["evidence_for"] and a["evidence_against"]     # both sides surfaced
    assert a["uncertainty"] and a["what_would_change_this"]
    kinds = {x.kind for x in res.blackboard.artifacts()}
    assert "finding" in kinds and "critique" in kinds      # the council actually ran


def test_council_execution_is_deterministic():
    r1 = Orchestrator().run(_payload(), ref="inv1", platform="youtube")
    r2 = Orchestrator().run(_payload(), ref="inv1", platform="youtube")
    assert r1.assessment == r2.assessment
    assert r1.trace.trace_id() == r2.trace.trace_id()
    assert r1.bundle_id == r2.bundle_id


def test_budget_floor_only_skips_council():
    class FloorOnly(BudgetController):
        def decide(self, bundle):
            return "floor_only"

    res = Orchestrator(budget=FloorOnly()).run(_payload(), ref="inv1", platform="youtube")
    assert res.permitted
    assert res.blackboard.artifacts() == []               # council not convened


def test_governor_reject_falls_back_to_floor(monkeypatch):
    from app.governor import Governor
    from app.governor.audit import ValidationTrace

    real = Governor.validate
    calls = {"n": 0}

    def fake(self, ruling, bundle, *, corroboration=None):
        calls["n"] += 1
        t = real(self, ruling, bundle, corroboration=corroboration)
        if calls["n"] == 1:                               # reject the council ruling
            return ValidationTrace(
                verdict="reject", violation_codes=["gate_breach"],
                stage_results=t.stage_results, version_binding=t.version_binding,
                input_digest=t.input_digest, bundle_id=t.bundle_id, fallback_path="floor",
            )
        return t                                          # permit the Floor

    monkeypatch.setattr(Governor, "validate", fake)
    res = Orchestrator().run(_payload(), ref="inv1", platform="youtube")
    assert res.fallback and res.permitted
    assert res.rejected_codes == ["gate_breach"]
    assert calls["n"] == 2


# --- AI readiness: a new module plugs in without orchestration change -------- #
def test_custom_module_plugs_in_via_contract():
    class CustomSpecialist:
        contract = ReasoningContract(module="custom", tier=1, output_kind="finding")

        def run(self, view):
            ref = next(iter(view.bundle.evidence))
            return [Finding(module="custom", signal="custom", claim="a custom read",
                            direction="neutral", evidence_refs=[ref])]

    assert isinstance(CustomSpecialist(), AnalystModule)   # satisfies the permanent interface
    res = Orchestrator(modules=[CustomSpecialist()]).run(_payload(), ref="inv1", platform="youtube")
    assert res.permitted
    assert any(a.module == "custom" for a in res.blackboard.artifacts())
