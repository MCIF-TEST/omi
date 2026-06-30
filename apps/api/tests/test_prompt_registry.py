"""Prompt Registry tests (Sprint 008).

Covers content-addressed prompt hashing, versioning, config-driven selection, rollback, the
registry listing, and prompt comparison — the version-control substrate for measurable prompt
evolution.
"""
from __future__ import annotations

import pytest

from app.reasoning.prompts import PromptRegistry, PromptSpec, compare_prompts, default_registry


def _spec(**kw) -> PromptSpec:
    base = dict(analyst="behavior_analyst", prompt_version="v1", template="TEMPLATE",
                constraints=("cite only evidence",), expected_output_contract="finding")
    base.update(kw)
    return PromptSpec(**base)


# --- content-addressed hashing ---------------------------------------------- #
def test_prompt_hash_is_content_addressed():
    s1 = _spec()
    assert s1.prompt_hash.startswith("ph:")
    assert _spec(author="someone", created_at="2026").prompt_hash == s1.prompt_hash   # metadata: no change
    assert _spec(prompt_version="v9").prompt_hash == s1.prompt_hash                    # version label: no change
    assert _spec(template="DIFFERENT").prompt_hash != s1.prompt_hash                   # template: changes hash
    assert _spec(constraints=("a", "b")).prompt_hash != s1.prompt_hash                 # constraints: change hash


# --- registry mechanics ----------------------------------------------------- #
def test_register_resolve_and_active_selection():
    reg = PromptRegistry()
    reg.register(_spec(prompt_version="v1"))
    reg.register(_spec(prompt_version="v2", template="T2"))
    assert reg.active_version("behavior_analyst") == "v1"          # first registered is active
    assert reg.resolve("behavior_analyst").prompt_version == "v1"  # active by default
    assert reg.resolve("behavior_analyst", "v2").template == "T2"  # explicit selection
    assert reg.versions("behavior_analyst") == ["v1", "v2"]


def test_set_active_and_rollback():
    reg = PromptRegistry()
    reg.register(_spec(prompt_version="v1"))
    reg.register(_spec(prompt_version="v2", template="T2"))
    reg.set_active("behavior_analyst", "v2")
    assert reg.resolve("behavior_analyst").prompt_version == "v2"
    reg.rollback("behavior_analyst", "v1")                         # rollback is selection of a prior version
    assert reg.resolve("behavior_analyst").prompt_version == "v1"


def test_unknown_prompt_raises():
    reg = PromptRegistry()
    reg.register(_spec())
    with pytest.raises(KeyError):
        reg.resolve("behavior_analyst", "v404")
    with pytest.raises(KeyError):
        reg.set_active("behavior_analyst", "v404")


def test_records_listing_flags_active():
    recs = default_registry().records("behavior_analyst")
    by_v = {r["prompt_version"]: r for r in recs}
    assert by_v["v1"]["active"] is True and by_v["v2"]["active"] is False
    assert by_v["v1"]["prompt_hash"].startswith("ph:")
    assert by_v["v1"]["expected_output_contract"] == "finding"
    assert "template" in by_v["v1"] and by_v["v1"]["constraints"]


# --- default registry + comparison ------------------------------------------ #
def test_default_registry_seeds_behavior_prompts():
    reg = default_registry()
    # Sprint 016: the production OMI ANALYST prompt is now registry-owned alongside the council's
    # behavior_analyst prompts (the registry is the single runtime source of truth).
    assert sorted(reg.analysts()) == ["behavior_analyst", "omi_analyst"]
    assert reg.versions("behavior_analyst") == ["v1", "v2"]
    assert reg.active_version("behavior_analyst") == "v1"          # conservative default
    assert reg.active_version("omi_analyst") == "v1"


def test_compare_prompts_diffs_versions():
    reg = default_registry()
    diff = compare_prompts(reg.resolve("behavior_analyst", "v1"), reg.resolve("behavior_analyst", "v2"))
    assert diff["template_changed"] is True
    assert diff["hash"]["identical"] is False
    assert diff["expected_output_contract"]["match"] is True       # both produce findings
    assert diff["version"] == {"a": "v1", "b": "v2"}
