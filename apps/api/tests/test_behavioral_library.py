"""The Behavioral Intelligence Library (Omi Intelligence Program — Phase B1).

Verifies the reference specialist library: the behavioral knowledge growth (reading list 5 -> 13,
every entry complete and integrity-clean), the deep methodology / failure / evaluation dimensions
applied as FRAMEWORK OVERRIDES (the Phase-A1 hook — no parallel systems), the evidence-justified
lib-v2 prompt (versioned through the ONE registry, INERT — live v1 untouched, replay preserved),
the measured behavioral Gold-Corpus benchmarks (control FPR stays 0.0), the generated drift-guarded
handbook, and the catalog/HF synchronization surface.
"""
from __future__ import annotations

from app.reasoning.evaluation import default_gold_corpus, evaluate_corpus
from app.reasoning.knowledge import KnowledgeIndex, default_library
from app.reasoning.prompts import (
    behavior_v2_prompt_spec,
    default_registry,
    framework_profiles,
    render_behavioral_handbook,
    validate_framework,
)
from app.reasoning.prompts.behavioral import (
    BEHAVIOR_V2,
    DECISION_WORKFLOW,
    EVALUATION_LIBRARY,
    FAILURE_LIBRARY,
    MISSION,
)
from app.reasoning.prompts.export import (
    BEHAVIORAL_HANDBOOK_PATH,
    behavioral_handbook_matches_committed,
    prompt_catalog,
    prompt_manifest,
)

_NEW_ENTRIES = {
    "engagement_farming", "reply_farms", "posting_cadence_analysis", "account_aging_behavior",
    "behavior_evolution", "hybrid_operation", "spam_campaigns", "adversarial_evasion",
}


# --------------------------------------------------------------------------- #
# 3. Behavioral Knowledge Base
# --------------------------------------------------------------------------- #
def test_behavioral_knowledge_base_grew_and_stays_clean():
    lib = default_library()
    assert _NEW_ENTRIES <= set(lib.entry_ids())
    assert lib.validate() == []                                   # no dangling refs/specialists
    reading = {e.id for e in KnowledgeIndex(lib).for_specialist("behavior_analyst")}
    assert _NEW_ENTRIES <= reading and len(reading) >= 13         # 5 -> 13
    # every new entry pairs hostile patterns with their benign twins (precision frontier).
    for eid in _NEW_ENTRIES:
        e = lib.get(eid)
        assert e.counter_indicators and e.false_positive_risks, eid
        assert e.sections_present() == 10, eid                    # complete metadata


def test_adversarial_entry_forbids_the_paranoid_inversion():
    e = default_library().get("adversarial_evasion")
    assert any("absence of evidence" in c for c in e.constitutional_constraints)


# --------------------------------------------------------------------------- #
# 2+5. Methodology + Failure Library applied as framework overrides
# --------------------------------------------------------------------------- #
def test_behavioral_overrides_are_live_in_the_framework():
    assert validate_framework() == []                             # overrides keep profiles complete
    p = next(x for x in framework_profiles() if x.key == "behavior_analyst")
    assert p.reasoning.decision_workflow == DECISION_WORKFLOW     # the deep playbook, verbatim
    assert p.reasoning.decision_workflow[0].startswith("INVENTORY")
    assert p.quality.failure_modes == FAILURE_LIBRARY["failure_modes"]
    assert any("paranoid inversion" in b for b in p.quality.anti_patterns)
    assert len(p.quality.false_negative_risks) == 3               # behavioral FN scenarios
    assert "benign_scheduler_news" in p.validation.benchmark_cases
    # other specialists keep their derived defaults (override is scoped).
    q = next(x for x in framework_profiles() if x.key == "coordination_analyst")
    assert q.reasoning.decision_workflow != DECISION_WORKFLOW


def test_mission_scope_excludes_adjudication():
    assert "never" in MISSION["scope"] and "verdict" in MISSION["scope"]


# --------------------------------------------------------------------------- #
# 8. Prompt improvement — lib-v2, inert, evidence-justified
# --------------------------------------------------------------------------- #
def test_lib_v2_is_registered_inert_and_distinct():
    reg = default_registry()
    assert reg.versions("behavior_analyst") == ["lib-v1", "lib-v2", "v1", "v2"]
    assert reg.active_version("behavior_analyst") == "v1"         # live prompt untouched -> replay safe
    v2 = reg.resolve("behavior_analyst", "lib-v2")
    assert v2.prompt_hash == behavior_v2_prompt_spec().prompt_hash
    assert v2.prompt_hash != reg.resolve("behavior_analyst", "lib-v1").prompt_hash
    assert v2.expected_output_contract == "finding"               # contract unchanged


def test_lib_v2_encodes_the_new_discipline_and_the_constitution():
    text = behavior_v2_prompt_spec().template
    assert "OMI CONSTITUTION" in text                             # constitutional compliance
    for phrase in ("hybrid", "insufficient", "benign twin", "window"):
        assert phrase in text, phrase
    # the benign-twin rule is a forbidden-reasoning constraint, not a suggestion.
    assert any("never treat regularity" in f for f in BEHAVIOR_V2.forbidden_reasoning)


# --------------------------------------------------------------------------- #
# 6. Evaluation Library — measured behavioral benchmarks
# --------------------------------------------------------------------------- #
def test_behavioral_benchmarks_measured_control_fpr_zero():
    corpus = default_gold_corpus()
    ids = {c.id for c in corpus.all()}
    assert {"engagement_farm_replies", "benign_scheduler_news", "hybrid_creator_mixed"} <= ids
    out = evaluate_corpus(corpus)
    assert out["summary"]["production_control_fpr"] == 0.0        # precision frontier holds
    assert out["summary"]["number_preserved_rate"] == 1.0
    by_id = {r["id"]: r for r in out["cases"]}
    assert by_id["benign_scheduler_news"]["production_false_positive"] is False
    assert by_id["benign_scheduler_news"]["production_label_agreement"]["verdict_match"] is True
    assert by_id["engagement_farm_replies"]["production_label_agreement"]["verdict_match"] is True
    assert by_id["hybrid_creator_mixed"]["production_label_agreement"]["verdict_match"] is True


def test_evaluation_library_names_replay_and_regression():
    assert "byte-stable" in EVALUATION_LIBRARY["replay"]
    assert "FPR" in EVALUATION_LIBRARY["regression"]


# --------------------------------------------------------------------------- #
# 7+9. Documentation + synchronization surface
# --------------------------------------------------------------------------- #
def test_behavioral_handbook_generated_and_drift_guarded():
    assert BEHAVIORAL_HANDBOOK_PATH.exists()
    assert behavioral_handbook_matches_committed() is True
    text = render_behavioral_handbook()
    for section in ("## 1. Mission", "Investigation Methodology", "Behavioral Knowledge Base",
                    "Failure Library", "Evaluation Library", "reasoning walkthrough",
                    "Prompt versions"):
        assert section in text, section
    # The worked counterexample must be present. Matched case-insensitively: whether "regularity"
    # opens a sentence or continues one is a punctuation choice, not the thing under test.
    assert "Counterexample" in text and "regularity is" in text.lower()


def test_catalog_and_manifest_carry_the_behavioral_library():
    m = prompt_manifest()
    rows = [p for p in m["prompts"] if p["analyst"] == "behavior_analyst"]
    assert {r["version"] for r in rows} == {"lib-v1", "lib-v2", "v1", "v2"}
    assert all(not r["active"] for r in rows if r["version"].startswith("lib"))
    c = prompt_catalog()
    entry = next(s for s in c["specialists"] if s["key"] == "behavior_analyst")
    fb = entry["framework"]
    assert fb["decision_workflow"][0].startswith("INVENTORY")     # deep library reaches HF
    assert "benign_scheduler_news" in fb["validation"]["benchmark_cases"]
