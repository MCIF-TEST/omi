"""Phase 5A — OpenRouter operational readiness: provider-aware diagnostics.

Proves the readiness / status / integrity surfaces report the OpenRouter path correctly, that the HF
diagnostics stay backward-compatible (existing keys unchanged), that the readiness checks send NO
network request and never read the API key value, and that the actually-served model is recorded in the
forensic trace. Phase 5A is observability only — no production cutover, no real OpenRouter request.
"""
from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.reasoning import analyst
from app.reasoning.model_providers.config import provider_status
from app.reasoning.trace import endpoint_health, system_health
from app.storage.db import reset_db_for_tests

MISTRAL = "mistralai/Mistral-7B-Instruct-v0.3"
_PRESET = "omi-master-analyst-v1"


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("HF_TOKEN", raising=False)
    monkeypatch.delenv("HUGGINGFACE_HUB_TOKEN", raising=False)
    reset_db_for_tests("sqlite:///:memory:")
    yield


def _hf_settings(**kw):
    base = dict(
        analyst_enabled=True, analyst_provider="huggingface", analyst_endpoint_url=None,
        analyst_hf_repo="Andrewexiga/omi-analyst-v1", analyst_hf_revision=None,
        analyst_model_id=MISTRAL, analyst_endpoint_api="messages",
        analyst_timeout_seconds=30.0, analyst_max_retries=0, analyst_prompt_version=None,
        analyst_cost_per_1k_tokens_usd=0.0, analyst_prompt_assembly="registry",
        memory_persistence_enabled=False, memory_database_url=None,
        openrouter_preset=None, openrouter_model=None,
        openrouter_base_url="https://openrouter.ai/api/v1/chat/completions",
        openrouter_structured_output=True, openrouter_referer=None, openrouter_title=None,
    )
    base.update(kw)
    return SimpleNamespace(**base)


def _or_settings(**kw):
    kw.setdefault("openrouter_preset", _PRESET)
    return _hf_settings(analyst_provider="openrouter", **kw)


# =========================================================================== #
# HF backward compatibility — the default path's keys/values are unchanged
# =========================================================================== #
def test_hf_diagnostics_backward_compatible(monkeypatch):
    monkeypatch.setenv("HF_TOKEN", "hf_fake")
    s = _hf_settings(analyst_endpoint_url="https://ep")
    rs = analyst.runtime_status(s)
    assert rs["selected_provider"] == "huggingface"
    assert rs["provider"] == "qwen"                          # active provider (legacy semantics)
    assert rs["ready_for_live_qwen"] is True                 # legacy key preserved
    assert rs["ready_for_live_model"] == rs["ready_for_live_qwen"]
    assert system_health(s)["active_provider"] == "remote-model"
    assert system_health(s)["active_model"] == MISTRAL
    assert provider_status(s)["ai_specialist_ready"] is True

    rp = analyst.runtime_path(s)
    steps = {n["step"] for n in rp["nodes"]}
    assert "hf_endpoint" in steps and "hf_token" in steps    # HF graph unchanged
    assert rp["active_provider"] == "qwen"


# =========================================================================== #
# OpenRouter readiness — configured preset + key present => ready
# =========================================================================== #
def test_openrouter_ready_when_preset_and_key_present(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-FAKE-not-used")
    s = _or_settings()

    rs = analyst.runtime_status(s)
    assert rs["selected_provider"] == "openrouter"
    assert rs["provider"] == "openrouter"                    # active provider
    assert rs["ready_for_live_openrouter"] is True
    assert rs["ready_for_live_model"] is True
    assert rs["ready_for_live_qwen"] is False                # HF not configured
    assert rs["openrouter_configured"] is True and rs["openrouter_api_key_present"] is True

    rp = analyst.runtime_path(s)
    steps = {n["step"] for n in rp["nodes"]}
    assert {"openrouter_config", "openrouter_api_key"} <= steps
    assert "hf_endpoint" not in steps and "hf_token" not in steps
    assert rp["blockers"] == [] and rp["active_provider"] == "openrouter"

    assert provider_status(s)["model_provider_ready"] is True
    assert provider_status(s)["openrouter_ready"] is True
    assert system_health(s)["active_provider"] == "openrouter-model"
    assert system_health(s)["active_model"] == f"@preset/{_PRESET}"


def test_openrouter_direct_model_ready(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-FAKE-not-used")
    s = _or_settings(openrouter_preset=None, openrouter_model="anthropic/claude-3.5-sonnet")
    rs = analyst.runtime_status(s)
    assert rs["openrouter_model_configured"] is True and rs["ready_for_live_model"] is True
    assert system_health(s)["active_model"] == "anthropic/claude-3.5-sonnet"


# =========================================================================== #
# OpenRouter NOT ready — missing key or missing config are surfaced as blockers
# =========================================================================== #
def test_openrouter_blocked_missing_key():
    s = _or_settings()  # no OPENROUTER_API_KEY in env (fixture cleared it)
    rs = analyst.runtime_status(s)
    assert rs["ready_for_live_openrouter"] is False and rs["ready_for_live_model"] is False
    assert "openrouter_api_key" in analyst.runtime_path(s)["blockers"]


def test_openrouter_blocked_missing_config(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-FAKE-not-used")
    s = _or_settings(openrouter_preset=None, openrouter_model=None)
    rs = analyst.runtime_status(s)
    assert rs["openrouter_configured"] is False and rs["ready_for_live_model"] is False
    assert "openrouter_config" in analyst.runtime_path(s)["blockers"]


# =========================================================================== #
# Readiness sends NO network request and never reads the key value
# =========================================================================== #
def test_readiness_never_probes_or_sends_a_request(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-FAKE-not-used")
    s = _or_settings()

    def _boom(*a, **k):
        raise AssertionError("Phase 5A readiness must not send a network request")

    with patch("app.reasoning.model_providers.openrouter.urllib.request.urlopen", _boom), \
         patch("app.reasoning.model_providers.remote.urllib.request.urlopen", _boom):
        eh = endpoint_health(s)
        sh = system_health(s)
        analyst.runtime_status(s)
        analyst.runtime_path(s)
        provider_status(s)

    assert eh["provider"] == "openrouter"
    assert eh["reachable"] is None                    # explicitly not probed
    assert eh["status"] == "configured"
    assert eh["openrouter_api_key_present"] is True    # presence only — the value is never surfaced
    assert eh["served_model"] is None
    assert sh["endpoint"]["provider"] == "openrouter"


# =========================================================================== #
# served_model provenance — the actually-served model is recorded in the trace
# =========================================================================== #
class _Resp:
    def __init__(self, body): self._body = body
    def __enter__(self): return self
    def __exit__(self, *a): return False
    def read(self): return self._body
    status = 200


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


def _valid_model_output() -> dict:
    from app.reasoning.prompts.comprehensive_investigation_template import COMPREHENSIVE_SECTION_KEYS
    domains = {k: {"assessment": "reasoning present for this domain", "citations": ["A1"]}
               for k in COMPREHENSIVE_SECTION_KEYS}
    return {
        "verdict": "mixed", "omi_score": 68, "suspicion_tier": "elevated", "confidence_band": "moderate",
        "confidence_rationale": "single-axis temporal signal over thin data",
        "headline": "cadence is unusually regular.",
        "assessment": ("Consistent with mechanical posting regularity; a single-axis result. These "
                       "findings are probabilistic; the human analyst sets the verdict."),
        "evidence_for": [{"signal": "temporal", "claim": "low interval variance", "evidence_refs": ["A1"]}],
        "evidence_against": [{"signal": "community", "claim": "modest footprint", "evidence_refs": ["A1"]}],
        "uncertainty": ["thin data — most detectors abstained"],
        "what_would_change_this": ["more posts to corroborate the cadence"],
        "limits_statement": "This is a probabilistic assessment; the human analyst sets the final verdict.",
        **domains,
    }


def _or_response(model_obj: dict, served="anthropic/claude-3.5-sonnet") -> bytes:
    return json.dumps({
        "id": "gen-xyz789", "model": served,
        "choices": [{"message": {"role": "assistant", "content": json.dumps(model_obj)}}],
        "usage": {"prompt_tokens": 1200, "completion_tokens": 240, "total_tokens": 1440, "cost": 0.0012},
    }).encode()


def test_served_model_recorded_in_trace(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-FAKE-not-used")

    def _fake(req, timeout=None):
        return _Resp(_or_response(_valid_model_output()))

    with patch("app.reasoning.model_providers.openrouter.urllib.request.urlopen", _fake):
        out = analyst.assess_payload(_PAYLOAD, ref="sub_or5a", platform="youtube", settings=_or_settings())

    assert out is not None
    tr = out["investigation_trace"]
    assert tr["provider"] == "openrouter" and tr["model_backed"] is True
    # The model the gateway ACTUALLY served (the preset routed to it) is captured as provenance —
    # distinct from the configured/requested model.
    assert tr["served_model"] == "anthropic/claude-3.5-sonnet"
    assert tr["requested_model"] == f"@preset/{_PRESET}"
