"""Phase B — the Prompt Builder assembles the final prompt EXCLUSIVELY from the HF analyst package.

Proves: the builder appends the constitution (governance/reasoning rules) and the Knowledge Library
to the base system prompt, from package assets only, content-addressed and deterministic; the
``registry`` mode is a byte-identical no-op (backwards compatible); the flag switches the system
prompt the model actually receives; and the field-provenance contract (items 8/9) holds — the model
generates the analytical conclusions while the engine's numbers are echoed, never overridden.
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
# The flag switches the system prompt the MODEL actually receives
# --------------------------------------------------------------------------- #
def _settings(assembly):
    return SimpleNamespace(
        analyst_enabled=True, analyst_endpoint_url="https://ep", analyst_hf_repo="Andrewexiga/omi-analyst-v1",
        analyst_hf_revision="sha1", analyst_prompt_version=None, analyst_model_id=MISTRAL,
        analyst_timeout_seconds=30.0, analyst_max_retries=0, analyst_endpoint_api="messages",
        analyst_cost_per_1k_tokens_usd=0.0, analyst_prompt_assembly=assembly,
        memory_persistence_enabled=False, memory_database_url=None)


@pytest.mark.parametrize("assembly, expect_framework", [("registry", False), ("package", True)])
def test_assess_payload_sends_the_assembled_system_prompt(assembly, expect_framework):
    captured = {}

    def _fake(req, timeout=None):
        captured["body"] = json.loads(req.data.decode())
        return _Resp(json.dumps({"model": MISTRAL,
                                 "choices": [{"message": {"content": '{"x":1}'}}]}).encode())

    with patch("app.reasoning.model_providers.remote.urllib.request.urlopen", _fake):
        out = analyst.assess_payload(_PAYLOAD, ref="sub_pb", platform="youtube", settings=_settings(assembly))
    system_sent = captured["body"]["messages"][0]["content"]
    assert ("REASONING & GOVERNANCE FRAMEWORK" in system_sent) is expect_framework
    # provenance recorded on the assessment either way
    assert out["prompt_build"]["mode"] == assembly


# --------------------------------------------------------------------------- #
# Items 8/9 — field provenance contract
# --------------------------------------------------------------------------- #
def test_field_provenance_contract():
    fp = analyst.field_provenance()
    assert "verdict" in fp["model_generated"]                    # the model reasons the conclusions
    assert "assessment" in fp["model_generated"]
    assert "evidence_for" in fp["model_generated"]
    assert set(fp["deterministic_echoed"]) == {"suspicion_probability", "suspicion_tier"}
    # the two sets are disjoint — no field is both model-generated and deterministic
    assert not (set(fp["model_generated"]) & set(fp["deterministic_echoed"]))
