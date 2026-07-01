"""Hugging Face production readiness (Sprint 023).

Covers the deployment-layer work that makes the moment-of-activation seamless: the dual serving-API
support in the ONE Qwen client (raw ``generate`` vs OpenAI ``messages``, operator-selected so the
code never guesses the endpoint type), the prompt-synchronization manifest that keeps the HF package
in lockstep with the GitHub Prompt Registry (drift-guarded, hash-bearing), the HF registration
manifest validation, and the post-deploy smoke test that proves a real investigation reaches Qwen.

Constitutional guarantees hold: ``generate`` is byte-shape-identical to before, the deterministic
floor still catches failures, the Governor is still mandatory, and no specialist is activated.
"""
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.reasoning import analyst
from app.reasoning.model_providers import ReasoningRequest
from app.reasoning.model_providers.remote import (
    RemoteReasoningProvider,
    assemble_message_stream,
    assemble_stream,
)
from app.reasoning.prompts.export import (
    MANIFEST_PATH,
    manifest_matches_committed,
    prompt_manifest,
    render_manifest_json,
)
from app.reasoning.trace import endpoint_smoke_test
from app.storage.db import reset_db_for_tests

_REPO_ROOT = Path(__file__).resolve().parents[3]
_VALID_JSON = '{"suspicion_probability": 0.7}'


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
def _token(monkeypatch):
    monkeypatch.setenv("HF_TOKEN", "hf_fake_for_tests")
    reset_db_for_tests("sqlite:///:memory:")
    yield


# --------------------------------------------------------------------------- #
# Phase 4 — dual-format Qwen client (generate | messages)
# --------------------------------------------------------------------------- #
def _run(api: str, response_body: bytes):
    captured: dict = {}

    def _fake(req, timeout=None):
        captured["body"] = req.data.decode("utf-8")
        return _Resp(response_body)

    with patch("app.reasoning.model_providers.remote.urllib.request.urlopen", _fake):
        prov = RemoteReasoningProvider(endpoint_url="http://ep", api=api, model="omi", max_retries=0)
        resp = prov.complete(ReasoningRequest(system="SYS", user="USER", response_format="json", max_tokens=64))
    return captured["body"], resp


def test_generate_mode_is_byte_shape_preserved_and_parses():
    body, resp = _run("generate", json.dumps([{"generated_text": "<think>t</think>\n" + _VALID_JSON}]).encode())
    assert '"inputs"' in body and "<|system|>" in body and "max_new_tokens" in body
    assert "messages" not in body
    assert resp.structured == {"suspicion_probability": 0.7}
    assert resp.diagnostics["api"] == "generate"


def test_messages_mode_posts_chat_body_and_parses_openai_shape():
    reply = json.dumps({"choices": [{"message": {"content": "<think>t</think>\n" + _VALID_JSON}}]}).encode()
    body, resp = _run("messages", reply)
    payload = json.loads(body)
    assert [m["role"] for m in payload["messages"]] == ["system", "user"]
    assert payload["max_tokens"] == 64 and "inputs" not in payload
    assert resp.structured == {"suspicion_probability": 0.7}
    assert resp.diagnostics["api"] == "messages"


def test_default_api_is_generate():
    assert RemoteReasoningProvider(endpoint_url="http://ep").api == "generate"
    from app.core.config import Settings
    assert Settings().analyst_endpoint_api == "generate"


def test_both_streaming_assemblers():
    gen = assemble_stream(['data: ' + json.dumps({"token": {"text": "He"}}),
                           'data: ' + json.dumps({"token": {"text": "llo"}}), "data: [DONE]"])
    msg = assemble_message_stream(['data: ' + json.dumps({"choices": [{"delta": {"content": "He"}}]}),
                                   'data: ' + json.dumps({"choices": [{"delta": {"content": "llo"}}]}),
                                   "data: [DONE]"])
    assert gen == "Hello" and msg == "Hello"


# --------------------------------------------------------------------------- #
# Phase 2/3 — prompt synchronization manifest (GitHub registry -> HF)
# --------------------------------------------------------------------------- #
def test_prompt_manifest_matches_committed_and_is_registry_derived():
    """Drift guard: the committed HF manifest equals a freshly generated one, so the HF package can
    never drift from what the runtime registry actually resolves."""
    assert manifest_matches_committed() is True
    assert MANIFEST_PATH.exists()
    assert MANIFEST_PATH.read_text(encoding="utf-8") == render_manifest_json()


def test_prompt_manifest_carries_hashes_constitution_and_library_status():
    m = prompt_manifest()
    assert m["constitution"]["hash"].startswith("cx:")
    assert m["production_prompt"]["prompt_hash"].startswith("ph:")
    assert m["production_prompt"]["active_version"] == "v1"
    assert m["specialist_library"]["count"] == 13 and m["specialist_library"]["activated"] is False
    # every prompt row is content-addressed; the lib-v1 specialists compose the constitution.
    assert all(p["prompt_hash"].startswith("ph:") for p in m["prompts"])
    judge_lib = next(p for p in m["prompts"] if p["analyst"] == "judge" and p["version"] == "lib-v1")
    assert judge_lib["composes_constitution"] is True
    omi = next(p for p in m["prompts"] if p["analyst"] == "omi_analyst")
    assert omi["composes_constitution"] is False        # live prompt honors rules via constraints


def test_hf_registration_manifest_validates_including_prompt_manifest():
    """The HF publish manifest resolves every source (now including prompt_manifest.json) and its
    base_model metadata agrees — so register_hf_model.py will publish cleanly."""
    spec = importlib.util.spec_from_file_location(
        "register_hf_model", _REPO_ROOT / "ml" / "analyst" / "register_hf_model.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    target, files = mod.load_manifest(_REPO_ROOT / "ml" / "analyst" / "hf_repo_manifest.toml")
    ok, resolved, errors = mod.validate(target, files)
    assert ok, errors
    assert any(dst == "prompts/prompt_manifest.json" for _src, dst, _kind in resolved)


# --------------------------------------------------------------------------- #
# Phase 5 — post-deploy smoke test
# --------------------------------------------------------------------------- #
def test_smoke_test_reports_not_configured_without_endpoint(monkeypatch):
    monkeypatch.delenv("HF_TOKEN", raising=False)
    monkeypatch.delenv("HUGGINGFACE_HUB_TOKEN", raising=False)
    out = endpoint_smoke_test(settings=SimpleNamespace(analyst_endpoint_url=None))
    assert out["status"] == "not_configured" and out["endpoint_configured"] is False


def test_smoke_test_qwen_backed_end_to_end_in_messages_mode():
    """Full path: smoke test -> assess_payload -> Qwen transport (messages API) -> mocked HF ->
    Governor. Proves a genuinely Qwen-backed, permitted, number-preserving assessment."""
    impl = analyst._impl()
    assert impl is not None
    payload = {"overall_probability": 0.74, "overall_tier": "elevated", "confidence": 0.6,
               "contributions": [{"name": "temporal", "impact": 0.5, "direction": "raises"}],
               "video": {"clusters": [{"method": "co_engagement", "members": ["@a", "@b", "@c"]}]}}
    # a schema-valid analyst response for the smoke bundle, returned by the mocked chat endpoint.
    config = impl.load_analyst_config(repo_id="Andrewexiga/omi-analyst-v1", revision="sha123")
    bundle = analyst.build_bundle(payload, ref="smoke_subject", platform="youtube", impl=impl)
    valid = json.dumps(impl.DeterministicAnalystProvider().generate(bundle, config).response)
    reply = json.dumps({"choices": [{"message": {"content": "<think>weigh</think>\n" + valid}}]}).encode()

    settings = SimpleNamespace(
        analyst_enabled=True, analyst_endpoint_url="https://ep.hf.cloud",
        analyst_hf_repo="Andrewexiga/omi-analyst-v1", analyst_hf_revision="sha123",
        analyst_timeout_seconds=30.0, analyst_max_retries=0, analyst_prompt_version=None,
        analyst_endpoint_api="messages", memory_persistence_enabled=False, memory_database_url=None)

    with patch("app.reasoning.model_providers.remote.urllib.request.urlopen",
               return_value=_Resp(reply)):
        out = endpoint_smoke_test(payload, ref="smoke_subject", settings=settings)
    assert out["status"] == "qwen_backed", out
    assert out["qwen_backed"] is True and out["endpoint_api"] == "messages"
    assert out["governor_verdict"] == "permit" and out["number_echoed"] is True
    assert out["model_revision"] == "sha123" and out["prompt"].get("source") == "registry"
