"""Production runtime model = mistralai/Mistral-7B-Instruct-v0.3 (endpoint live).

Verifies the runtime-model switch: the new ``OMI_ANALYST_MODEL_ID`` setting, the provider wired to
it (abstraction intact — the model is configuration, never architecture), an end-to-end governed
assessment against a Mistral-shaped endpoint response (no ``<think>`` trace — the strip is an inert
safeguard), the consolidated ``system_health`` diagnostics, and — the constitutional core — that the
Prompt Registry, Specialist Framework, Governor, Memory, Context Builder, Shadow Mode, Evaluation,
and Gold Corpus behave IDENTICALLY regardless of the underlying runtime model.
"""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.core.config import Settings
from app.reasoning import analyst
from app.reasoning.model_providers import ReasoningRequest
from app.reasoning.model_providers.config import build_remote_provider, provider_status
from app.reasoning.model_providers.remote import RemoteReasoningProvider
from app.reasoning.trace import system_health
from app.storage.db import reset_db_for_tests

_REPO_ROOT = Path(__file__).resolve().parents[3]
MISTRAL = "mistralai/Mistral-7B-Instruct-v0.3"


class _Resp:
    def __init__(self, body: bytes):
        self._body = body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self):
        return self._body


@pytest.fixture(autouse=True)
def _fresh(monkeypatch):
    monkeypatch.setenv("HF_TOKEN", "hf_fake_for_tests")
    reset_db_for_tests("sqlite:///:memory:")
    yield


# --------------------------------------------------------------------------- #
# Configuration — exact env names, Mistral as the runtime model
# --------------------------------------------------------------------------- #
def test_settings_default_runtime_model_is_mistral():
    assert Settings().analyst_model_id == MISTRAL


def test_env_var_is_omi_analyst_model_id(monkeypatch):
    monkeypatch.setenv("OMI_ANALYST_MODEL_ID", "some/other-model")
    assert Settings().analyst_model_id == "some/other-model"


def test_provider_carries_the_runtime_model_not_the_registry_repo():
    s = SimpleNamespace(analyst_endpoint_url="https://ep", analyst_model_id=MISTRAL,
                        analyst_hf_repo="Andrewexiga/omi-analyst-v1", analyst_hf_revision="sha1",
                        analyst_timeout_seconds=30.0, analyst_max_retries=1,
                        analyst_endpoint_api="messages")
    p = build_remote_provider(s)
    assert p.model == MISTRAL and p.api == "messages"
    st = provider_status(s)
    assert st["model"] == MISTRAL
    assert st["registry_repo"] == "Andrewexiga/omi-analyst-v1"     # contract repo, distinct


def test_messages_body_names_the_mistral_model():
    captured = {}

    def _fake(req, timeout=None):
        captured["body"] = json.loads(req.data.decode())
        return _Resp(json.dumps({"choices": [{"message": {"content": '{"ok": 1}'}}]}).encode())

    with patch("app.reasoning.model_providers.remote.urllib.request.urlopen", _fake):
        prov = RemoteReasoningProvider(endpoint_url="http://ep", api="messages", model=MISTRAL,
                                       max_retries=0)
        prov.complete(ReasoningRequest(system="S", user="U", response_format="json"))
    assert captured["body"]["model"] == MISTRAL


# --------------------------------------------------------------------------- #
# End-to-end: Mistral-shaped response (no <think>) -> governed assessment
# --------------------------------------------------------------------------- #
def test_e2e_governed_assessment_with_mistral_response():
    impl = analyst._impl()
    payload = {"overall_probability": 0.74, "overall_tier": "elevated", "confidence": 0.6,
               "contributions": [{"name": "temporal", "impact": 0.5, "direction": "raises"}],
               "video": {"clusters": [{"method": "co_engagement", "members": ["@a", "@b", "@c"]}]}}
    config = impl.load_analyst_config(repo_id="Andrewexiga/omi-analyst-v1", revision="msha1")
    bundle = analyst.build_bundle(payload, ref="sub_m", platform="youtube", impl=impl)
    valid = json.dumps(impl.DeterministicAnalystProvider().generate(bundle, config).response)
    # Mistral emits the JSON directly — no thinking trace. The strip must be a no-op.
    reply = json.dumps({"choices": [{"message": {"content": valid}}]}).encode()
    settings = SimpleNamespace(
        analyst_enabled=True, analyst_endpoint_url="https://ep.hf.cloud",
        analyst_model_id=MISTRAL, analyst_hf_repo="Andrewexiga/omi-analyst-v1",
        analyst_hf_revision="msha1", analyst_timeout_seconds=30.0, analyst_max_retries=0,
        analyst_prompt_version=None, analyst_endpoint_api="messages",
        memory_persistence_enabled=False, memory_database_url=None)
    with patch("app.reasoning.model_providers.remote.urllib.request.urlopen",
               return_value=_Resp(reply)):
        out = analyst.assess_payload(payload, ref="sub_m", platform="youtube", settings=settings)
    gov = out["governance"]
    assert "fallback" not in gov["provider"]                       # genuinely model-backed
    assert gov["verdict"] == "permit" and out["suspicion_probability"] == 0.74
    assert gov["model_revision"] == "msha1" and gov["prompt"]["source"] == "registry"


# --------------------------------------------------------------------------- #
# #6 — consolidated health diagnostics
# --------------------------------------------------------------------------- #
def test_system_health_reports_all_required_fields():
    s = SimpleNamespace(analyst_enabled=True, analyst_endpoint_url="https://ep",
                        analyst_model_id=MISTRAL, analyst_endpoint_api="messages",
                        analyst_hf_revision="sha9", analyst_timeout_seconds=30.0)
    h = system_health(s)
    assert h["active_provider"] == "remote-model"
    assert h["active_model"] == MISTRAL
    assert h["endpoint"]["status"] in ("reachable", "unreachable")  # token present in fixture
    assert h["prompt_registry"]["omi_analyst_active"] == "v1"
    assert h["prompt_registry"]["analysts"] == 14
    assert h["specialist_framework"]["version"] == "v1"
    assert h["specialist_framework"]["hash"].startswith("sf:")
    off = system_health(SimpleNamespace(analyst_enabled=False, analyst_endpoint_url=None,
                                        analyst_model_id=MISTRAL))
    assert off["active_provider"] == "deterministic-floor"


def test_integrity_endpoint_includes_system_health():
    from fastapi.testclient import TestClient
    from app.main import app
    with TestClient(app) as tc:
        body = tc.get("/v1/investigations/analyst/integrity").json()
    assert body["system_health"]["active_model"] == MISTRAL
    assert body["system_health"]["specialist_framework"]["hash"].startswith("sf:")


# --------------------------------------------------------------------------- #
# #5 — the constitutional stack is model-independent
# --------------------------------------------------------------------------- #
def test_constitutional_stack_is_identical_regardless_of_model(monkeypatch):
    """Registry hashes, framework hash, Gold-Corpus evaluation, and the deterministic governed
    output are byte-identical whatever OMI_ANALYST_MODEL_ID says — the model is configuration."""
    from app.reasoning.evaluation import default_gold_corpus, evaluate_corpus
    from app.reasoning.prompts import default_registry, framework_hash

    def _snapshot():
        reg = default_registry()
        ev = evaluate_corpus(default_gold_corpus())["summary"]
        return {
            "omi_hash": reg.resolve("omi_analyst").prompt_hash,
            "behavior_hash": reg.resolve("behavior_analyst").prompt_hash,
            "framework": framework_hash(),
            "control_fpr": ev["production_control_fpr"],
            "number_preserved": ev["number_preserved_rate"],
            "n": ev["n"],
        }

    monkeypatch.setenv("OMI_ANALYST_MODEL_ID", MISTRAL)
    a = _snapshot()
    monkeypatch.setenv("OMI_ANALYST_MODEL_ID", "entirely/different-model")
    b = _snapshot()
    assert a == b                                                   # model swap changes nothing
    assert a["control_fpr"] == 0.0 and a["number_preserved"] == 1.0


def test_memory_and_context_paths_do_not_read_the_model_id():
    """Memory + Context Builder + Shadow are model-blind: their inputs are the bundle + store."""
    import inspect
    from app.memory.graph import retrieval as mem_retrieval
    from app.reasoning.context import builder as ctx_builder
    from app.reasoning.shadow import runner as shadow_runner
    for mod in (mem_retrieval, ctx_builder, shadow_runner):
        assert "analyst_model_id" not in inspect.getsource(mod)


# --------------------------------------------------------------------------- #
# HF package — Mistral everywhere it declares a model
# --------------------------------------------------------------------------- #
def test_hf_package_declares_mistral_consistently():
    import tomllib
    manifest = tomllib.loads((_REPO_ROOT / "ml/analyst/hf_repo_manifest.toml").read_text())
    assert manifest["target"]["base_model"] == MISTRAL
    cfg = json.loads((_REPO_ROOT / "ml/analyst/hf_repo/config/analyst_config.json").read_text())
    assert cfg["base_model"] == MISTRAL
    assert cfg["thinking"]["enabled"] is False
    card = (_REPO_ROOT / "ml/analyst/hf_repo/README.md").read_text()
    assert f"base_model: {MISTRAL}" in card
    assert "Qwen" not in card                                       # runtime references retired
