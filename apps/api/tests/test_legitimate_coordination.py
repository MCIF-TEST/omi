"""Legitimate-coordination reasoning — the Sprint 019 intelligence improvement.

Highest-ROI gap closed: the AI used to *list* exculpatory institutional memory (a known
legitimate-coordination control) yet still read the subject as hostile coordination — a precision
failure on the exact frontier the Gold Corpus measures (control false-positive rate). Now, when a
KNOWN legitimate-coordination control is present alongside a discriminative coordination read, the
analyst reasons *from* it: it generates the explicit legitimate hypothesis and downgrades its
interpretation from hostile to **mixed** ("the evidence does not distinguish hostile from benign
coordination"). Exculpatory-only (memory may lower, never raise), so the engine number, tier,
confidence band, corroboration gate, Governor, and OmiScore are all untouched.

The tests lock: the precision win (control FPR 1.0 → 0.0), recall preservation (a discriminative
method with no control prior stays suspicious), the Governor still permitting, the echoed number,
and the new hypothesis-generation capability — with a Shadow-Mode comparison.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.evidence import Binder
from app.governor import Governor
from app.memory.graph import MemoryStore
from app.reasoning.contracts import Memory
from app.reasoning.evaluation import GoldCase, GoldCorpus, evaluate_corpus
from app.reasoning.evaluation.corpus import _is_false_positive
from app.reasoning.orchestrator import (
    BehaviorAnalyst,
    CounterEvidenceAnalyst,
    MemoryAnalyst,
    Orchestrator,
)
from app.reasoning.orchestrator.modules import build_ruling_assessment

NOW = datetime(2026, 6, 28, tzinfo=timezone.utc)


def _payload(method: str, *, prob: float = 0.7, tier: str = "elevated") -> dict:
    return {
        "overall_probability": prob, "overall_tier": tier, "confidence": 0.6,
        "contributions": [{"name": "temporal", "impact": 0.4, "direction": "raises"}],
        "video": {"clusters": [{"method": method, "members": ["@a", "@b", "@c", "@d"]}]},
    }


def _bundle(method: str):
    return Binder().bind(_payload(method), grain="comment_section", subject_ref="x", platform="youtube")


def _control_memory(bundle=None) -> Memory:
    # a real run carries resolvable bundle refs (the coordination evidence the prior matched);
    # use one so the Governor's citation-resolution stage is satisfied, mirroring the live path.
    refs: list[str] = []
    if bundle is not None:
        refs = [it.id for it in bundle.evidence.values() if it.kind == "coordination_method"][:1]
    return Memory(
        module="memory_analyst",
        contradicting=[{"type": "LegitimateCoordinationControl",
                        "claim": "matches the @CityDesk newsroom legitimate-coordination control",
                        "evidence_refs": refs}],
        supporting=[], uncertainty=[])


def _seed_control(store: MemoryStore, signature=("co_engagement",)) -> None:
    for i in range(3):  # corroborated across independent investigations
        store.ingest(
            candidate={"type": "LegitimateCoordinationControl", "signature": list(signature),
                       "label": "newsroom control", "is_control": True},
            investigation=f"i{i}", stance="supports", evidence_refs=["d"],
            independence_key=f"k{i}", at=NOW.isoformat())


def _council(store):
    return Orchestrator(modules=[BehaviorAnalyst(), MemoryAnalyst(store, now=NOW), CounterEvidenceAnalyst()])


# --------------------------------------------------------------------------- #
# The capability — exculpatory memory now changes the read, not just the listing
# --------------------------------------------------------------------------- #
def test_known_legitimate_control_downgrades_hostile_read():
    bundle = _bundle("co_engagement")
    before = build_ruling_assessment(bundle, memories=None)                     # no exculpatory memory
    after = build_ruling_assessment(bundle, memories=[_control_memory(bundle)])  # known legitimate control
    # BEFORE: hostile read (the precision frontier failure).
    assert before["verdict"] == "likely_inauthentic" and before["coordination_label"] == "suspicious"
    assert _is_false_positive(before) is True
    # AFTER: the same evidence, contextualized by the known legitimate control → mixed, not hostile.
    assert after["verdict"] == "mixed" and after["coordination_label"] == "mixed"
    assert _is_false_positive(after) is False
    assert after["legitimate_hypothesis"] and "legitimate" in after["legitimate_hypothesis"].lower()


def test_recall_preserved_without_a_control_prior():
    """A discriminative coordination read with NO legitimate-control prior stays suspicious."""
    a = build_ruling_assessment(_bundle("fingerprint_cluster"), memories=None)
    assert a["verdict"] == "likely_inauthentic" and a["coordination_label"] == "suspicious"
    # a NON-control exculpatory prior must NOT trigger the downgrade (only known controls do).
    other = Memory(module="memory_analyst",
                   contradicting=[{"type": "BehavioralArchetype", "claim": "x", "evidence_refs": []}],
                   supporting=[], uncertainty=[])
    b = build_ruling_assessment(_bundle("fingerprint_cluster"), memories=[other])
    assert b["coordination_label"] == "suspicious"


def test_legitimate_hypothesis_generated_for_all_coordination_reads():
    """Hypothesis generation (spec §13) is now always present for coordination reads, None otherwise."""
    assert build_ruling_assessment(_bundle("co_engagement"))["legitimate_hypothesis"]            # provisional
    no_coord = Binder().bind({"overall_probability": 0.2, "overall_tier": "low", "confidence": 0.5,
                              "contributions": [{"name": "temporal", "impact": 0.1, "direction": "raises"}]},
                             grain="comment_section", subject_ref="x", platform="youtube")
    assert build_ruling_assessment(no_coord)["legitimate_hypothesis"] is None


# --------------------------------------------------------------------------- #
# Constitutional safety — number echoed, Governor still permits, OmiScore intact
# --------------------------------------------------------------------------- #
def test_downgrade_preserves_number_and_governor_permits():
    bundle = _bundle("co_engagement")
    a = build_ruling_assessment(bundle, memories=[_control_memory(bundle)])
    assert a["suspicion_probability"] == 0.7 and a["suspicion_tier"] == "elevated"   # OmiScore untouched
    trace = Governor().validate(a, bundle, corroboration=a["corroboration"])
    assert trace.permitted is True                                                   # still Governor-valid


# --------------------------------------------------------------------------- #
# End-to-end through the real council (memory refs resolve) + Gold-corpus benchmark
# --------------------------------------------------------------------------- #
def test_end_to_end_council_precision_and_recall():
    store = MemoryStore()
    _seed_control(store, signature=("co_engagement",))           # known legitimate control on co_engagement
    ctrl = _council(store).run(_payload("co_engagement"), ref="ctrl", platform="youtube")
    host = _council(store).run(_payload("fingerprint_cluster"), ref="host", platform="youtube")
    assert ctrl.permitted and host.permitted
    assert not _is_false_positive(ctrl.assessment)               # precision: control no longer flagged
    assert _is_false_positive(host.assessment)                  # recall: hostile still flagged
    assert ctrl.assessment["suspicion_probability"] == 0.7      # number echoed both ways


def test_gold_corpus_control_fpr_drops_with_recall_preserved():
    store = MemoryStore()
    _seed_control(store, signature=("co_engagement",))
    corpus = GoldCorpus()
    corpus.add(GoldCase(id="hostile", payload=_payload("fingerprint_cluster"),
                        label={"expected_coordination_label": "suspicious"}))
    corpus.add(GoldCase(id="legit_control", payload=_payload("co_engagement"),
                        label={"is_control": True}))
    out = evaluate_corpus(corpus, store=store, now=NOW)
    s = out["summary"]
    assert s["controls"] == 1
    assert s["production_control_fpr"] == 0.0      # the legitimate control is no longer a false positive
    assert s["number_preserved_rate"] == 1.0       # AI never moved the engine number (Shadow Mode)


def test_shadow_mode_agreement_number_preserved():
    """Shadow Mode (deterministic vs AI council, fallback): both echo the engine number and agree —
    the improvement applies on the shared Judge, so there is no production/shadow divergence."""
    store = MemoryStore()
    _seed_control(store, signature=("co_engagement",))
    corpus = GoldCorpus()
    corpus.add(GoldCase(id="legit_control", payload=_payload("co_engagement"), label={"is_control": True}))
    out = evaluate_corpus(corpus, store=store, now=NOW)
    assert out["summary"]["number_preserved_rate"] == 1.0
    assert out["summary"]["agreement_rate"] == 1.0
