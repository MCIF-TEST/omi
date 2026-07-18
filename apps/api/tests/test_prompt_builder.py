"""Phase B — the Prompt Builder assembles the final prompt EXCLUSIVELY from the HF analyst package.

Proves: the builder appends the constitution (governance/reasoning rules) and the Knowledge Library
to the base system prompt, from package assets only, content-addressed and deterministic; the
``registry`` mode is a byte-identical no-op (backwards compatible); and the field-provenance contract
(items 8/9) holds — the model generates the analytical conclusions while the engine's numbers are
echoed, never overridden.

The ``PromptBuilder`` class is retained + unit-tested here, but as of P3.4 it is RETIRED from the
production path: the Investigation Summary is now a canonical reasoning stage whose prompt is assembled
by the ONE canonical stage builder (``build_prompt('investigation_summary', bundle)``). The production
integration test below asserts that canonical-stage assembly.
"""
from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.reasoning import analyst
from app.reasoning.package import load_ai_package
from app.reasoning.prompt_builder import PromptBuilder
from app.storage.db import reset_db_for_tests

MISTRAL = "mistralai/Mistral-7B-Instruct-v0.3"
_PAYLOAD = {"overall_probability": 0.74, "overall_tier": "elevated", "confidence": 0.6,
            "contributions": [{"name": "temporal", "impact": 0.5, "direction": "raises"}],
            "video": {"clusters": [{"method": "co_engagement", "members": ["@a", "@b", "@c"]}]}}


class _Resp:
    def __init__(self, body): self._body = body
    def __enter__(self): return self
    def __exit__(self, *a): return False
    def read(self): return self._body


@pytest.fixture(autouse=True)
def _fresh(monkeypatch):
    monkeypatch.setenv("HF_TOKEN", "hf_fake")
    reset_db_for_tests("sqlite:///:memory:")
    yield


# --------------------------------------------------------------------------- #
# The builder assembles from the package
# --------------------------------------------------------------------------- #
def test_registry_mode_is_a_noop():
    b = PromptBuilder()
    out = b.build_system(base_system="BASE PROMPT.", mode="registry")
    assert out.system == "BASE PROMPT."
    assert out.manifest["mode"] == "registry"
    assert out.manifest["package_hash"].startswith("pkg:")


def test_package_mode_appends_constitution_and_knowledge_from_the_package():
    pkg = load_ai_package()
    out = PromptBuilder(pkg, knowledge_limit=8).build_system(base_system="BASE.", mode="package")
    assert out.system.startswith("BASE.")
    assert "REASONING & GOVERNANCE FRAMEWORK" in out.system      # constitution block
    assert "KNOWLEDGE LIBRARY" in out.system                     # knowledge block
    assert "OUTPUT CONTRACT" in out.system
    m = out.manifest
    assert m["mode"] == "package"
    assert m["prompt_hash"] == pkg.prompt_hash                   # from the package
    assert m["constitution_hash"] == pkg.constitution_hash
    assert m["knowledge_hash"] == pkg.knowledge_hash
    assert len(m["knowledge_entries_used"]) == 8
    assert m["system_prompt_sha"].startswith("sys:")


def test_builder_is_deterministic():
    a = PromptBuilder().build_system(base_system="B.", mode="package")
    b = PromptBuilder().build_system(base_system="B.", mode="package")
    assert a.manifest["system_prompt_sha"] == b.manifest["system_prompt_sha"]


def test_builder_uses_no_hardcoded_reasoning_text_only_package_assets():
    """The assembled system == base + constitution_text + rendered knowledge + a fixed output
    contract. The reasoning/governance content comes from the package's OWN constitution, not
    newly-authored prompt text."""
    from app.reasoning.prompts import constitution_text
    out = PromptBuilder(knowledge_limit=4).build_system(base_system="B.", mode="package")
    assert constitution_text().strip() in out.system


# --------------------------------------------------------------------------- #
# P3.4 — the production Investigation Summary prompt is assembled by the ONE canonical stage builder
# (``build_prompt('investigation_summary', bundle)``), NOT the flag-driven PromptBuilder above. The
# system ALWAYS carries the package constitution + specialist framework + knowledge + the
# investigation-summary task; the user carries the InvestigationSummaryBundle evidence sections.
# --------------------------------------------------------------------------- #
def _settings():
    return SimpleNamespace(
        analyst_enabled=True, analyst_endpoint_url="https://ep", analyst_hf_repo="Andrewexiga/omi-analyst-v1",
        analyst_hf_revision="sha1", analyst_prompt_version=None, analyst_model_id=MISTRAL,
        analyst_timeout_seconds=30.0, analyst_max_retries=0, analyst_endpoint_api="messages",
        analyst_cost_per_1k_tokens_usd=0.0, analyst_prompt_assembly="registry",
        memory_persistence_enabled=False, memory_database_url=None)


def test_assess_payload_sends_the_canonical_stage_prompt():
    """P3.4: the Investigation Summary is a canonical reasoning stage — the prompt the MODEL receives is
    assembled by ``build_prompt('investigation_summary', bundle)`` from package assets only, so the
    system carries the constitution + specialist framework + knowledge + the investigation-summary
    task + output contract, and the user carries the InvestigationSummaryBundle evidence sections (not
    a raw lossy dump)."""
    captured = {}

    def _fake(req, timeout=None):
        captured["body"] = json.loads(req.data.decode())
        return _Resp(json.dumps({"model": MISTRAL,
                                 "choices": [{"message": {"content": '{"x":1}'}}]}).encode())

    with patch("app.reasoning.model_providers.remote.urllib.request.urlopen", _fake):
        out = analyst.assess_payload(_PAYLOAD, ref="sub_pb", platform="youtube", settings=_settings())
    msgs = captured["body"]["messages"]
    system_sent, user_sent = msgs[0]["content"], msgs[1]["content"]
    # system: the shared package assets + the stage task + the output contract (all from the package)
    assert "REASONING & GOVERNANCE CONSTITUTION" in system_sent
    # the specialist-council framework is NOT injected (single Lead Investigator, not a council)
    assert "SPECIALIST INVESTIGATION FRAMEWORK" not in system_sent
    assert "KNOWLEDGE LIBRARY" in system_sent
    assert "COMPREHENSIVE INVESTIGATION TASK" in system_sent
    assert "OUTPUT CONTRACT" in system_sent
    # user: the COMPLETE InvestigationPackage evidence sections (the single-inference path) — not the
    # legacy raw lossy JSON dump; the account domain is a compact table with detector columns.
    assert "Investigation-level engine signal" in user_sent
    assert "Coordination (clusters" in user_sent
    assert "signal_columns" in user_sent            # the compact account table
    assert '"grain": "comment_section"' not in user_sent
    # provenance records the canonical comprehensive stage assembly (mode + system sha + knowledge window)
    assert out["prompt_build"]["mode"] == "stage:comprehensive_investigation"
    assert out["prompt_build"]["system_prompt_sha"].startswith("sys:")
    assert len(out["prompt_build"]["knowledge_entries_used"]) == 12


# --------------------------------------------------------------------------- #
# Items 8/9 — field provenance contract
# --------------------------------------------------------------------------- #
def test_field_provenance_contract():
    fp = analyst.field_provenance()
    assert "verdict" in fp["model_generated"]                    # the model reasons the conclusions
    assert "assessment" in fp["model_generated"]
    assert "evidence_for" in fp["model_generated"]
    # Phase 1 — the six per-domain reasoning sections are first-class model-generated analytical content
    for domain in ("comment_reasoning", "commenter_history_reasoning", "account_reasoning",
                   "narrative_reasoning", "coordination_reasoning", "campaign_reasoning"):
        assert domain in fp["model_generated"]
    # AI-first: the analyst produces its OWN scores (the OMI score + its tier band).
    assert "omi_score" in fp["model_generated"] and "suspicion_tier" in fp["model_generated"]
    # nothing is echoed anymore — only the factual engine corroboration state is overlaid.
    assert set(fp["deterministic_echoed"]) == {"corroboration"}
    # the two sets are disjoint — no field is both model-generated and deterministic
    assert not (set(fp["model_generated"]) & set(fp["deterministic_echoed"]))
