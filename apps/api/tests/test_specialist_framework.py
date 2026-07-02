"""The Specialist Intelligence Framework (Omi Intelligence Program — Phase A1).

Verifies the permanent framework every specialist inherits: complete profiles for all 13 library
specialists (LIFTED from their authored SpecialistSpecs — single source, zero duplication) plus the
two code-backed Tier-3 guarantees (Governor, Floor — never prompt- or model-driven); the template
path for future specialists (worked example: investigation_planner, INERT); framework-level
completeness validation; the catalog extension that synchronizes the framework to Hugging Face
through the EXISTING export + publish pipeline; the generated handbook; and the improved (not
replaced) publish workflow — mode banner + auto-upload on main so GitHub and HF cannot drift.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from app.reasoning.prompts import (
    SPECIALISTS,
    default_registry,
    framework_hash,
    framework_profiles,
    lift,
    new_specialist,
    validate_framework,
)
from app.reasoning.prompts.framework import (
    EXECUTION_CODE,
    EXECUTION_MODEL,
    FLOOR_PROFILE,
    GOVERNOR_PROFILE,
    example_investigation_planner,
    validate_profile,
)
from app.reasoning.prompts.export import (
    handbook_matches_committed,
    prompt_catalog,
    HANDBOOK_PATH,
)
from app.reasoning.prompts.specialists import SpecialistSpec

_REPO_ROOT = Path(__file__).resolve().parents[3]


# --------------------------------------------------------------------------- #
# The framework: complete, validated, tier-covering
# --------------------------------------------------------------------------- #
def test_framework_has_all_profiles_and_zero_issues():
    profiles = framework_profiles()
    assert len(profiles) == 15                                   # 13 lifted + governor + floor
    assert validate_framework() == []
    tiers = {t: sum(1 for p in profiles if p.identity.tier == t) for t in (1, 2, 3)}
    assert tiers == {1: 8, 2: 4, 3: 3}
    assert framework_hash().startswith("sf:")


def test_lift_derives_from_the_authored_spec_without_duplication():
    """The framework NEVER re-authors: identity/reasoning/governance content is the spec's own."""
    for spec in SPECIALISTS:
        p = lift(spec)
        assert p.identity.mission == spec.mission
        assert p.identity.responsibilities == spec.responsibilities
        assert p.quality.failure_modes == spec.failure_modes      # authored once, inherited
        assert p.reasoning.memory_usage == spec.memory_usage
        assert p.governance.citation_rules == spec.citation
        assert p.execution == EXECUTION_MODEL
        assert validate_profile(p) == []


def test_model_backed_profiles_resolve_in_the_one_registry():
    reg = default_registry()
    for p in framework_profiles():
        if p.execution != EXECUTION_MODEL:
            continue
        spec = reg.resolve(p.key, p.technical.prompt_version)
        assert spec.prompt_hash == p.technical.prompt_hash        # hash comes FROM the registry
        assert p.technical.token_budget > 0


def test_governor_and_floor_are_code_backed_never_model_driven():
    for p in (GOVERNOR_PROFILE, FLOOR_PROFILE):
        assert p.execution == EXECUTION_CODE and p.identity.tier == 3
        assert p.technical.prompt_hash is None and p.technical.prompt_version is None
        assert "code" in p.governance.hallucination_prevention.lower()
        assert validate_profile(p) == []
    # the counterexample encodes the constitutional rule.
    assert "prompt-driven governor" in GOVERNOR_PROFILE.documentation.counterexample


def test_every_profile_carries_every_mandated_dimension():
    for p in framework_profiles():
        rec = p.to_record()
        for section in ("identity", "reasoning", "governance", "technical", "quality",
                        "validation", "documentation"):
            assert rec[section], f"{p.key} missing {section}"
        assert rec["reasoning"]["escalation"] and rec["reasoning"]["termination"]
        assert rec["quality"]["anti_patterns"] and rec["quality"]["edge_cases"]
        assert rec["validation"]["replay"] and rec["validation"]["shadow_mode"]
        assert rec["documentation"]["example"] and rec["documentation"]["counterexample"]


def test_knowledge_reading_list_feeds_retrieval_and_gold_coverage():
    p = lift(next(s for s in SPECIALISTS if s.key == "coordination_analyst"))
    assert "KnowledgeIndex.for_specialist('coordination_analyst')" in p.technical.retrieval_strategy
    assert "coordination_techniques" in p.validation.gold_corpus_coverage


# --------------------------------------------------------------------------- #
# The template — future specialists need only their authored sections
# --------------------------------------------------------------------------- #
def test_worked_example_is_complete_and_inert():
    ex = example_investigation_planner()
    assert ex.key == "investigation_planner" and ex.identity.tier == 2
    assert validate_profile(ex) == []
    assert ex.technical.prompt_hash.startswith("ph:")             # content-addressed via template
    # INERT: not registered, not in the catalog, not in the council.
    assert "investigation_planner" not in default_registry().analysts()
    assert all(s["key"] != "investigation_planner" for s in prompt_catalog()["specialists"])


def test_template_rejects_an_incomplete_specialist():
    incomplete = SpecialistSpec(
        key="strategy_analyst", title="OMI STRATEGY ANALYST", tier=2, output_kind="critique",
        mission="m", responsibilities=("r",), available_evidence=("e",),
        allowed_reasoning=("a",), forbidden_reasoning=("f",), memory_usage="m", citation="c",
        confidence_calibration="c", hallucination_prevention="h", output_contract="o",
        interactions=("i",), governor_constraints="g",
        failure_modes=(),                                          # <- incomplete: no failure modes
    )
    with pytest.raises(ValueError, match="incomplete specialist"):
        new_specialist(incomplete)


def test_template_registers_through_the_one_registry_when_asked():
    from app.reasoning.prompts import PromptRegistry
    spec = SpecialistSpec(
        key="strategy_analyst", title="OMI STRATEGY ANALYST", tier=2, output_kind="critique",
        mission="Advise on investigative strategy without ruling.",
        responsibilities=("rank hypotheses",), available_evidence=("bundle inventory",),
        allowed_reasoning=("prioritize decisive evidence",), forbidden_reasoning=("no verdicts",),
        memory_usage="background only", citation="cite bundle ids only",
        confidence_calibration="tracks decisiveness", hallucination_prevention="reference only real facets",
        output_contract='{"critiques":[...]} JSON only', interactions=("advises the Judge",),
        governor_constraints="critiques never raise", failure_modes=("busywork plans",),
    )
    reg = PromptRegistry()
    profile = new_specialist(spec, registry=reg)
    assert validate_profile(profile) == []
    assert reg.analysts() == ["strategy_analyst"]                 # versioned through the registry
    assert "strategy_analyst" not in default_registry().analysts()  # and still inert globally


# --------------------------------------------------------------------------- #
# Synchronization surface — catalog (HF) + handbook (GitHub) + workflow
# --------------------------------------------------------------------------- #
def test_catalog_carries_the_framework_for_every_specialist():
    c = prompt_catalog()
    assert c["framework"]["hash"] == framework_hash()
    assert c["framework"]["profiles"] == 15
    assert c["framework"]["code_backed_tier3"] == ["floor", "governor"]
    for entry in c["specialists"]:
        fb = entry["framework"]
        for key in ("execution", "authority", "decision_workflow", "escalation", "termination",
                    "quality", "validation", "token_budget", "retrieval_strategy", "documentation"):
            assert fb.get(key), f"{entry['key']} framework missing {key}"
        assert fb["execution"] == EXECUTION_MODEL


def test_handbook_is_generated_and_drift_guarded():
    assert HANDBOOK_PATH.exists()
    assert handbook_matches_committed() is True
    text = HANDBOOK_PATH.read_text(encoding="utf-8")
    assert "Creating a new specialist (the template)" in text
    assert "OMI GOVERNOR" in text and "none (code-backed)" in text
    assert "example_investigation_planner" in text


def test_publish_workflow_improved_not_replaced():
    """The EXISTING workflow gained: visible mode in the run name, a validate-publishes-nothing
    banner, and auto-upload on main scoped to the package sources — no competing pipeline."""
    wf = (_REPO_ROOT / ".github" / "workflows" / "hf-analyst-register.yml").read_text(encoding="utf-8")
    assert "workflow_dispatch" in wf                              # manual path preserved
    assert "push:" in wf and "branches: [main]" in wf             # auto-sync on main
    assert "ml/analyst/hf_repo/**" in wf and "hf_repo_manifest.toml" in wf
    assert "inputs.mode || 'upload'" in wf                        # push events auto-upload
    assert "run-name:" in wf and "VALIDATE ONLY" in wf            # the 1 Jul misfire cannot recur silently
    assert "register_hf_model.py" in wf                           # same script — pipeline reused
    # exactly one workflow publishes to the model repo.
    workflows = list((_REPO_ROOT / ".github" / "workflows").glob("*.yml"))
    publishers = [w.name for w in workflows if "register_hf_model.py --upload" in w.read_text(encoding="utf-8")
                  or ("register_hf_model" in w.read_text(encoding="utf-8") and "upload" in w.read_text(encoding="utf-8"))]
    assert publishers == ["hf-analyst-register.yml"]
