"""Phase 5B — OpenRouter production cutover verification (preset ``omi-master-v1`` + GPT-5 Mini).

Locks the production configuration and proves the end-to-end contract for the cutover WITHOUT any live
call (urlopen is always mocked): the backend submits the Investigation Package through the preset with
the required response format, GPT-5 Mini reaches the request when configured, a valid response follows
the canonical validation → persistence path in the UI-consumed shape, and every failure mode (malformed
JSON, timeout, OpenRouter HTTP error, invalid schema, empty response) degrades gracefully to the
deterministic Floor with the failure forensically visible and NO second inference.
"""
from __future__ import annotations

import json
import socket
import urllib.error
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.reasoning import analyst
from app.reasoning.prompts.comprehensive_investigation_template import (
    COMPREHENSIVE_ASSESSMENT_SCHEMA_ID,
    COMPREHENSIVE_SECTION_KEYS,
)
from app.storage.db import reset_db_for_tests

_API_KEY = "sk-or-v1-SECRET-testkey-do-not-leak-0000"
_PRESET = "omi-master-v1"                 # the production preset
_GPT5_MINI = "openai/gpt-5-mini"          # the production model (defined inside the preset)

_PAYLOAD = {
    "overall_probability": 0.72, "overall_tier": "elevated", "confidence": 0.55,
    "convergence_score": 0.3, "inputs_provided": ["video"], "video_id": "v1",
    "video": {"video_id": "v1", "coordination_score": 0.66, "coordination_tier": "elevated",
              "clusters": [{"method": "co_engagement", "members": ["a", "b", "c"], "score": 0.7,
                            "evidence": ["tight"]}],
              "thread_scan": {"overall_probability": 0.5, "tier": "moderate"},
              "commenters": [
                  {"external_id": "a", "handle": "@a", "overall_probability": 0.8, "tier": "high",
                   "confidence": 0.6,
                   "recent_activity": [{"text": "great video!!", "created_at": "2026-01-01T00:00:00Z"}],
                   "signals": [{"name": "temporal", "probability": 0.8, "evidence": ["low variance"]},
                               {"name": "community", "probability": 0.18}]},
                  {"external_id": "b", "handle": "@b", "overall_probability": 0.55, "tier": "elevated",
                   "signals": [{"name": "temporal", "probability": 0.5}]}]},
}


@pytest.fixture(autouse=True)
def _fresh(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", _API_KEY)
    monkeypatch.delenv("HF_TOKEN", raising=False)              # production OpenRouter must not need HF
    monkeypatch.delenv("HUGGINGFACE_HUB_TOKEN", raising=False)
    reset_db_for_tests("sqlite:///:memory:")
    yield


def _prod_settings(preset=_PRESET, model=None, structured=True):
    """The production cutover settings — provider=openrouter, the omi-master-v1 preset, no HF endpoint."""
    return SimpleNamespace(
        analyst_enabled=True, analyst_provider="openrouter",
        openrouter_preset=preset, openrouter_model=model,
        openrouter_base_url="https://openrouter.ai/api/v1/chat/completions",
        openrouter_structured_output=structured, openrouter_referer=None, openrouter_title=None,
        analyst_endpoint_url=None,                              # no HF endpoint in production
        analyst_hf_repo="Andrewexiga/omi-analyst-v1", analyst_hf_revision=None,
        analyst_prompt_version=None, analyst_model_id="mistralai/Mistral-7B-Instruct-v0.3",
        analyst_timeout_seconds=30.0, analyst_max_retries=0, analyst_endpoint_api="messages",
        analyst_cost_per_1k_tokens_usd=0.0, analyst_prompt_assembly="registry",
        memory_persistence_enabled=False, memory_database_url=None)


def _valid_model_output() -> dict:
    domains = {k: {"assessment": "reasoning present for this domain", "citations": ["A1"]}
               for k in COMPREHENSIVE_SECTION_KEYS}
    return {
        "verdict": "mixed", "confidence_band": "moderate",
        "confidence_rationale": "single-axis temporal signal over thin data",
        "headline": "GPT5MINI-PROD-HEADLINE cadence is unusually regular.",
        "assessment": ("Consistent with mechanical posting regularity; a single-axis result. These "
                       "findings are probabilistic; the human analyst sets the verdict."),
        "evidence_for": [{"signal": "temporal", "claim": "low interval variance", "evidence_refs": ["A1"]}],
        "evidence_against": [{"signal": "community", "claim": "modest footprint", "evidence_refs": ["A1"]}],
        "uncertainty": ["thin data — most detectors abstained"],
        "what_would_change_this": ["more posts to corroborate the cadence"],
        "limits_statement": "This is a probabilistic assessment; the human analyst sets the final verdict.",
        **domains,
    }


class _Resp:
    def __init__(self, body): self._body = body
    def __enter__(self): return self
    def __exit__(self, *a): return False
    def read(self): return self._body
    status = 200


def _or_body(model_obj: dict, *, served=_GPT5_MINI, gen_id="gen-prod-1", cost=0.0021) -> bytes:
    return json.dumps({
        "id": gen_id, "model": served,
        "choices": [{"message": {"role": "assistant", "content": json.dumps(model_obj)}}],
        "usage": {"prompt_tokens": 1800, "completion_tokens": 320, "total_tokens": 2120, "cost": cost},
    }).encode()


def _run(response_bytes: bytes, settings=None):
    settings = settings or _prod_settings()
    captured: dict = {}
    calls = {"n": 0}

    def _fake(req, timeout=None):
        calls["n"] += 1
        captured["url"] = req.full_url
        captured["headers"] = {k.lower(): v for k, v in dict(req.headers).items()}
        captured["body"] = json.loads(req.data.decode())
        return _Resp(response_bytes)

    with patch("app.reasoning.model_providers.openrouter.urllib.request.urlopen", _fake):
        out = analyst.assess_payload(_PAYLOAD, ref="sub_prod", platform="youtube", settings=settings)
    return out, captured, calls["n"]


def _run_raising(exc, settings=None):
    settings = settings or _prod_settings()

    def _boom(req, timeout=None):
        raise exc

    with patch("app.reasoning.model_providers.openrouter.urllib.request.urlopen", _boom):
        out = analyst.assess_payload(_PAYLOAD, ref="sub_prod_err", platform="youtube", settings=settings)
    return out


# =========================================================================== #
# Task 3 — the backend submits package + preset + model + response format
# =========================================================================== #
def test_production_preset_config_reaches_the_request_exactly():
    out, captured, calls = _run(_or_body(_valid_model_output()))
    body = captured["body"]
    # preset mode: model references the production preset, ONLY the user message is sent (preset holds
    # the system prompt), and the canonical schema is requested as native structured output.
    assert body["model"] == f"@preset/{_PRESET}"
    assert [m["role"] for m in body["messages"]] == ["user"]
    assert body["response_format"]["type"] == "json_schema"
    assert body["response_format"]["json_schema"]["name"] == COMPREHENSIVE_ASSESSMENT_SCHEMA_ID
    assert body["stream"] is False
    # The production output-token budget (analyst_config.json decoding.max_new_tokens) reaches the wire —
    # comfortably high for GPT-5 Mini reasoning + the full 7-section JSON, so no truncation → Floor.
    assert body["max_tokens"] >= 8000
    assert calls == 1                                              # exactly ONE inference
    # the Investigation Package evidence (normalized, aliased) reaches the provider as the user message
    assert "A1" in body["messages"][0]["content"]
    assert captured["url"] == "https://openrouter.ai/api/v1/chat/completions"


def test_gpt5_mini_model_selection_reaches_the_request():
    # Explicit model selection (direct mode) proves the GPT-5 Mini slug flows through the code path;
    # in production the same model is defined INSIDE the omi-master-v1 preset, so preset mode leaves it null.
    out, captured, _ = _run(_or_body(_valid_model_output()), settings=_prod_settings(preset=None, model=_GPT5_MINI))
    assert captured["body"]["model"] == _GPT5_MINI
    assert [m["role"] for m in captured["body"]["messages"]] == ["system", "user"]
    # And a preset with an explicit base-model override layers the slug onto the preset reference.
    _, captured2, _ = _run(_or_body(_valid_model_output()), settings=_prod_settings(model=_GPT5_MINI))
    assert captured2["body"]["model"] == f"{_GPT5_MINI}@preset/{_PRESET}"


# =========================================================================== #
# Tasks 4-6 — parse canonical JSON, validate, persist (UI-consumed shape)
# =========================================================================== #
def test_valid_production_assessment_validates_persists_in_ui_shape():
    out, _, _ = _run(_or_body(_valid_model_output()))
    # canonical parse + validation succeeded → the MODEL's analytical wrapper survived
    assert out["investigation_trace"]["model_backed"] is True
    assert out["headline"].startswith("GPT5MINI-PROD-HEADLINE")
    assert set(out["comprehensive_sections"]) == set(COMPREHENSIVE_SECTION_KEYS)
    # the exact structured fields the React UI consumes (Phase 4A) are present + provider-labeled
    for f in ("verdict", "suspicion_tier", "suspicion_probability", "confidence_band",
              "evidence_for", "evidence_against", "corroboration", "governance"):
        assert f in out
    assert out["governance"]["provider"] == "openrouter-omi-analyst-v1"
    # Omi-owned metadata overlaid AFTER validation (never model-fabricated)
    assert isinstance(out["subject"], dict) and out["subject"]["platform"] == "youtube"


def test_forensic_trace_records_production_identity_and_served_model():
    out, _, _ = _run(_or_body(_valid_model_output()))
    tr = out["investigation_trace"]
    assert tr["provider"] == "openrouter"
    assert tr["openrouter_preset"] == _PRESET
    assert tr["requested_model"] == f"@preset/{_PRESET}"
    assert tr["served_model"] == _GPT5_MINI                        # the model the preset routed to
    assert tr["endpoint_request_id"] == "gen-prod-1"
    assert tr["endpoint_cost_usd"] == 0.0021
    assert tr["canonical_schema_id"] == COMPREHENSIVE_ASSESSMENT_SCHEMA_ID
    # Phase 5C production-verification metadata (authoritative gateway usage + pipeline-stage flags)
    assert tr["input_tokens"] == 1800 and tr["output_tokens"] == 320 and tr["total_tokens"] == 2120
    assert tr["request_completed"] is True
    assert tr["json_received"] is True
    assert tr["validation_passed"] is True
    assert tr["master_prompt_version"] and tr["master_prompt_hash"].startswith("map:")


def test_api_key_never_leaks_in_production_path():
    out, captured, _ = _run(_or_body(_valid_model_output()))
    assert captured["headers"].get("authorization") == f"Bearer {_API_KEY}"
    assert _API_KEY not in json.dumps(captured["body"])
    assert _API_KEY not in json.dumps(out)


# =========================================================================== #
# Task 8 — graceful degradation to the Floor (each failure, forensically visible, ONE inference)
# =========================================================================== #
def _assert_floored(out, *, endpoint_called=True):
    tr = out["investigation_trace"]
    assert tr["model_backed"] is False
    assert "fallback" in str(out["governance"]["provider"]) or "deterministic" in str(out["governance"]["provider"])
    assert tr["endpoint_called"] is endpoint_called
    # a served, schema-valid Floor assessment still exists (the UI always has something governed to show)
    assert out.get("verdict") and out.get("suspicion_tier")


def test_degrade_malformed_json():
    # HTTP 200 but the assistant content is not valid JSON → canonical parse fails → Floor.
    malformed = json.dumps({
        "id": "gen-bad", "model": _GPT5_MINI,
        "choices": [{"message": {"role": "assistant", "content": "this is not json {{{ truncated"}}],
    }).encode()
    out, _, _ = _run(malformed)
    _assert_floored(out)
    assert out["investigation_trace"]["inference_count"] == 1


def test_degrade_invalid_schema():
    bad = _valid_model_output()
    del bad["campaign_reasoning"]                                  # missing a required reasoning domain
    out, _, calls = _run(_or_body(bad))
    _assert_floored(out)
    assert calls == 1                                             # no repair inference


def test_degrade_empty_response():
    empty = json.dumps({"id": "gen-empty", "model": _GPT5_MINI,
                        "choices": [{"message": {"role": "assistant", "content": ""}}]}).encode()
    out, _, _ = _run(empty)
    _assert_floored(out)


def test_degrade_timeout():
    out = _run_raising(socket.timeout("timed out"))
    _assert_floored(out)
    assert out["investigation_trace"]["endpoint_error"]           # the timeout is forensically visible


def test_degrade_openrouter_http_error():
    err = urllib.error.HTTPError("https://openrouter.ai", 500, "Internal Server Error", {}, None)
    out = _run_raising(err)
    _assert_floored(out)
    assert "500" in str(out["investigation_trace"]["endpoint_error"])


def test_degrade_connection_error():
    out = _run_raising(urllib.error.URLError("[Errno 111] Connection refused"))
    _assert_floored(out)
    assert "Connection refused" in str(out["investigation_trace"]["endpoint_error"])


# =========================================================================== #
# The committed paste-ready preset artifact == the compiled Master Analyst Protocol (drift guard)
# =========================================================================== #
def test_committed_preset_artifact_is_byte_identical_to_compiled_protocol():
    """The operator pastes ml/analyst/omi_master_v1_preset.txt into the OpenRouter preset. It must be
    BYTE-IDENTICAL to compile_master_analyst_protocol().text (the repo is the source of truth; the
    trace records that hash as what it expects the preset to hold), and the companion manifest must
    carry the matching identity. Any protocol change that forgets to regenerate the artifact fails here."""
    from app.reasoning.prompts.export import (
        MASTER_PRESET_MANIFEST_PATH,
        MASTER_PRESET_PATH,
        master_preset_matches_committed,
    )
    from app.reasoning.prompts.master_protocol import compile_master_analyst_protocol

    assert master_preset_matches_committed() is True
    p = compile_master_analyst_protocol()
    assert MASTER_PRESET_PATH.read_text(encoding="utf-8") == p["text"]
    manifest = json.loads(MASTER_PRESET_MANIFEST_PATH.read_text(encoding="utf-8"))
    assert manifest["preset_name"] == "omi-master-v1"
    assert manifest["protocol"]["hash"] == p["hash"]
    assert manifest["protocol"]["chars"] == p["chars"]
    # the pasted doctrine itself stays provider/vendor-neutral
    low = p["text"].lower()
    for vendor in ("openrouter", "openai", "gpt", "anthropic", "claude", "gemini", "qwen",
                   "mistral", "hugging face", "huggingface"):
        assert vendor not in low
