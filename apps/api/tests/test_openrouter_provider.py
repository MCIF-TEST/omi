"""Phase 2 — OpenRouter as a first-class ReasoningProvider behind the existing seam.

Proves OmiSphere can send ONE Investigation Package through ONE configured OpenRouter Preset to ONE model
inference, receive ONE canonical ComprehensiveAssessment, validate it through the Phase-1 contract, overlay
Omi-owned metadata, and keep full forensic traceability — without duplicating the Master Analyst Protocol,
introducing a second schema, leaking the API key, or increasing inference count. The Hugging Face and Floor
paths must not regress.
"""
from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.reasoning import analyst
from app.reasoning.model_providers import OpenRouterReasoningProvider, ReasoningProvider
from app.reasoning.prompts.comprehensive_investigation_template import (
    COMPREHENSIVE_ASSESSMENT_SCHEMA_ID,
    COMPREHENSIVE_SECTION_KEYS,
)
from app.reasoning.prompts.master_protocol import compile_master_analyst_protocol
from app.storage.db import reset_db_for_tests

MISTRAL = "mistralai/Mistral-7B-Instruct-v0.3"
_API_KEY = "sk-or-v1-SECRET-testkey-do-not-leak-0000"
_PRESET = "omi-analyst-v1"

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


class _Resp:
    def __init__(self, body): self._body = body
    def __enter__(self): return self
    def __exit__(self, *a): return False
    def read(self): return self._body
    status = 200


@pytest.fixture(autouse=True)
def _fresh(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", _API_KEY)
    monkeypatch.delenv("HF_TOKEN", raising=False)                 # OpenRouter must not need the HF token
    monkeypatch.delenv("HUGGINGFACE_HUB_TOKEN", raising=False)
    reset_db_for_tests("sqlite:///:memory:")
    yield


def _or_settings(preset=_PRESET, model=None, structured=True, provider="openrouter"):
    return SimpleNamespace(
        analyst_enabled=True, analyst_provider=provider,
        openrouter_preset=preset, openrouter_model=model,
        openrouter_base_url="https://openrouter.ai/api/v1/chat/completions",
        openrouter_structured_output=structured, openrouter_referer=None, openrouter_title=None,
        analyst_endpoint_url=None,
        analyst_hf_repo="Andrewexiga/omi-analyst-v1", analyst_hf_revision="sha1",
        analyst_prompt_version=None, analyst_model_id=MISTRAL,
        analyst_timeout_seconds=30.0, analyst_max_retries=0, analyst_endpoint_api="messages",
        analyst_cost_per_1k_tokens_usd=0.0, analyst_prompt_assembly="registry",
        memory_persistence_enabled=False, memory_database_url=None)


def _six_domains() -> dict:
    return {k: {"assessment": "reasoning present for this domain", "citations": ["A1"]}
            for k in COMPREHENSIVE_SECTION_KEYS}


def _valid_model_output() -> dict:
    """A canonically-valid comprehensive MODEL output — analytical wrapper + six domains, NO Omi-owned
    provenance/subject/echo."""
    return {
        "verdict": "mixed", "omi_score": 68, "suspicion_tier": "elevated", "confidence_band": "moderate",
        "confidence_rationale": "single-axis temporal signal over thin data",
        "headline": "OPENROUTER-MODEL-HEADLINE cadence is unusually regular.",
        "assessment": ("The evidence is consistent with mechanical posting regularity; a single-axis "
                       "result. These findings are probabilistic; the human analyst sets the verdict."),
        "evidence_for": [{"signal": "temporal", "claim": "low interval variance", "evidence_refs": ["A1"]}],
        "evidence_against": [{"signal": "community", "claim": "modest footprint", "evidence_refs": ["A1"]}],
        "uncertainty": ["thin data — most detectors abstained"],
        "what_would_change_this": ["more posts to corroborate the cadence"],
        "limits_statement": "This is a probabilistic assessment; the human analyst sets the final verdict.",
        **_six_domains(),
    }


def _or_response(model_obj: dict, *, gen_id="gen-abc123", cost=0.0012) -> bytes:
    return json.dumps({
        "id": gen_id, "model": "anthropic/claude-3.5-sonnet",
        "choices": [{"message": {"role": "assistant", "content": json.dumps(model_obj)}}],
        "usage": {"prompt_tokens": 1200, "completion_tokens": 240, "total_tokens": 1440, "cost": cost},
    }).encode()


def _run(model_obj: dict, settings=None):
    settings = settings or _or_settings()
    captured: dict = {}
    calls = {"n": 0}

    def _fake(req, timeout=None):
        calls["n"] += 1
        captured["url"] = req.full_url
        captured["headers"] = {k.lower(): v for k, v in dict(req.headers).items()}
        captured["body"] = json.loads(req.data.decode())
        return _Resp(_or_response(model_obj))

    with patch("app.reasoning.model_providers.openrouter.urllib.request.urlopen", _fake):
        out = analyst.assess_payload(_PAYLOAD, ref="sub_or", platform="youtube", settings=settings)
    return out, captured, calls["n"]


# =========================================================================== #
# 1-2. Seam + selection
# =========================================================================== #
def test_openrouter_implements_the_reasoning_provider_seam():
    p = OpenRouterReasoningProvider(preset=_PRESET, model=None)
    assert isinstance(p, ReasoningProvider)          # runtime-checkable Protocol
    assert p.name == "openrouter"


def test_provider_selection_routes_to_openrouter_without_changing_callers():
    out, captured, calls = _run(_valid_model_output())
    assert calls == 1
    assert captured["url"] == "https://openrouter.ai/api/v1/chat/completions"
    assert out["investigation_trace"]["provider"] == "openrouter"
    assert out["investigation_trace"]["model_backed"] is True


# =========================================================================== #
# 3-5. Preset reaches request; package reaches provider; master prompt NOT resent
# =========================================================================== #
def test_configured_preset_reaches_the_request_exactly():
    _, captured, _ = _run(_valid_model_output())
    assert captured["body"]["model"] == f"@preset/{_PRESET}"


# ── OpenRouter-first auto-preference: key + preset present overrides the huggingface default ─────
def test_provider_auto_prefers_openrouter_when_configured_but_provider_left_default(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", _API_KEY)
    s = SimpleNamespace(analyst_provider="huggingface", openrouter_preset=_PRESET, openrouter_model=None)
    assert analyst.reasoning_provider(s) == "openrouter"          # key + preset ⇒ OpenRouter, despite default


def test_provider_stays_huggingface_without_openrouter_config(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", _API_KEY)            # key alone is not enough…
    s = SimpleNamespace(analyst_provider="huggingface", openrouter_preset=None, openrouter_model=None)
    assert analyst.reasoning_provider(s) == "huggingface"         # …no preset/model ⇒ still HF


def test_provider_auto_preference_requires_the_key(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    s = SimpleNamespace(analyst_provider="huggingface", openrouter_preset=_PRESET, openrouter_model=None)
    assert analyst.reasoning_provider(s) == "huggingface"         # preset but no key ⇒ do not switch


# ── _model_ref hardening: a bad OMI_OPENROUTER_MODEL can't brick the preset path ──────────────────
def test_model_ref_preset_only_when_no_model():
    p = OpenRouterReasoningProvider(preset="omi-master-v1", model=None)
    assert p._model_ref() == "@preset/omi-master-v1"


def test_model_ref_layers_a_real_slug_onto_the_preset():
    p = OpenRouterReasoningProvider(preset="omi-master-v1", model="openai/gpt-5-mini")
    assert p._model_ref() == "openai/gpt-5-mini@preset/omi-master-v1"


def test_model_ref_ignores_a_display_name_and_falls_back_to_preset_only():
    # A human display name ("GPT-5 Mini") is NOT a slug — layering it would produce the invalid ref
    # "GPT-5 Mini@preset/omi-master-v1" that OpenRouter rejects with HTTP 400, floorng every scan.
    p = OpenRouterReasoningProvider(preset="omi-master-v1", model="GPT-5 Mini")
    assert p._model_ref() == "@preset/omi-master-v1"
    # direct mode (no preset) still passes the model through verbatim — that path has no fallback
    assert OpenRouterReasoningProvider(preset=None, model="GPT-5 Mini")._model_ref() == "GPT-5 Mini"


def test_dynamic_investigation_package_reaches_the_provider():
    _, captured, _ = _run(_valid_model_output())
    user_msg = captured["body"]["messages"][-1]["content"]
    # actual budgeted evidence content (compact tables + aliasing) is the user message
    assert "near_duplicate_groups" in user_msg and "contribution_columns" in user_msg
    assert "A1" in user_msg


def test_master_analyst_protocol_is_not_resent_in_preset_mode():
    _, captured, _ = _run(_valid_model_output())
    messages = captured["body"]["messages"]
    # preset supplies the system prompt: the request carries ONLY the user message
    assert len(messages) == 1 and messages[0]["role"] == "user"
    # the master protocol text does NOT appear anywhere in the wire body
    master = compile_master_analyst_protocol()["text"]
    assert "You are OMI ANALYST" in master                       # sanity: that's the master text
    assert "You are OMI ANALYST" not in json.dumps(captured["body"])


# =========================================================================== #
# 6-7. Structured output uses OpenAI-compatible JSON mode (not strict json_schema)
# =========================================================================== #
def test_structured_output_uses_json_object_mode_not_strict_schema():
    _, captured, _ = _run(_valid_model_output())
    rf = captured["body"]["response_format"]
    # JSON mode: the gateway must return a JSON object. We do NOT send a strict json_schema response
    # format — the canonical schema is AI-first/permissive (optional properties + additionalProperties:
    # false), a shape GPT-5-class strict mode rejects with HTTP 400. The exact object shape is specified
    # by the preset/protocol; the local canonical validator enforces it downstream.
    assert rf == {"type": "json_object"}
    # the canonical schema is NOT leaked onto the wire as a strict structured-output schema
    assert "json_schema" not in rf
    assert COMPREHENSIVE_ASSESSMENT_SCHEMA_ID not in json.dumps(captured["body"])


def test_structured_output_can_be_disabled_without_a_second_schema():
    out, captured, _ = _run(_valid_model_output(), settings=_or_settings(structured=False))
    assert "response_format" not in captured["body"]             # not sent...
    assert out["investigation_trace"]["model_backed"] is True    # ...but local validation still governs


# =========================================================================== #
# 8-11. Valid -> existing path; invalid -> Floor; Omi overlay after validation; ONE inference
# =========================================================================== #
def test_valid_output_follows_the_existing_canonical_validation_path():
    out, _, _ = _run(_valid_model_output())
    assert out["investigation_trace"]["model_backed"] is True
    assert out["headline"].startswith("OPENROUTER-MODEL-HEADLINE")     # the model's wrapper survived
    assert set(out["comprehensive_sections"]) == set(COMPREHENSIVE_SECTION_KEYS)
    assert "fallback" not in str(out["governance"]["provider"])
    assert out["governance"]["provider"] == "openrouter-omi-analyst-v1"


def test_invalid_output_falls_to_the_existing_floor_path():
    # AI-first coercion repairs harmless shape gaps; a Floor now requires missing CORE substance the model
    # alone produces (coercion never invents it) — here the verdict.
    bad = _valid_model_output()
    del bad["verdict"]                                           # missing core substance → un-coercible
    out, _, calls = _run(bad)
    assert out["investigation_trace"]["model_backed"] is False
    assert "fallback" in str(out["governance"]["provider"]) or "deterministic" in str(out["governance"]["provider"])
    assert out["headline"] != _valid_model_output()["headline"]  # Floor wrapper served
    assert calls == 1                                            # no repair inference


def test_omi_owned_metadata_is_overlaid_after_canonical_validation():
    out, captured, _ = _run(_valid_model_output())
    # the model output carried none of these; Omi injected them from the Floor AFTER validation
    body_user = captured["body"]["messages"][-1]["content"]
    assert '"analyst_version"' not in body_user
    assert isinstance(out.get("subject"), dict) and out["subject"]["platform"] == "youtube"
    for f in ("analyst_version", "prompt_version", "schema_version", "model_revision"):
        assert f in out


def test_exactly_one_inference_for_the_openrouter_path():
    out, _, calls = _run(_valid_model_output())
    assert calls == 1
    assert out["investigation_trace"]["inference_count"] == 1


# =========================================================================== #
# 12-13. Errors forensically visible; API key never leaks
# =========================================================================== #
def test_openrouter_connection_error_is_forensically_visible():
    import urllib.error

    def _boom(req, timeout=None):
        raise urllib.error.URLError("[Errno 111] Connection refused")

    with patch("app.reasoning.model_providers.openrouter.urllib.request.urlopen", _boom):
        out = analyst.assess_payload(_PAYLOAD, ref="sub_boom", platform="youtube", settings=_or_settings())
    tr = out["investigation_trace"]
    assert tr["provider"] == "openrouter"
    assert tr["model_backed"] is False and tr["endpoint_called"] is True
    assert tr["endpoint_error"] and "Connection refused" in tr["endpoint_error"]


def test_api_key_never_appears_in_wire_body_trace_or_persisted_assessment():
    out, captured, _ = _run(_valid_model_output())
    # the key rides in the Authorization header ONLY
    assert captured["headers"].get("authorization") == f"Bearer {_API_KEY}"
    assert _API_KEY not in json.dumps(captured["body"])
    assert _API_KEY not in json.dumps(out)                       # never persisted
    assert _API_KEY not in json.dumps(out["investigation_trace"])


def test_forensic_trace_records_openrouter_identity():
    out, _, _ = _run(_valid_model_output())
    tr = out["investigation_trace"]
    assert tr["provider"] == "openrouter"
    assert tr["openrouter_preset"] == _PRESET
    assert tr["requested_model"] == f"@preset/{_PRESET}"
    assert tr["endpoint_request_id"] == "gen-abc123"             # OpenRouter generation id
    assert tr["endpoint_cost_usd"] == 0.0012                     # inline USD cost
    assert tr["canonical_schema_id"] == COMPREHENSIVE_ASSESSMENT_SCHEMA_ID
    assert tr["master_prompt_hash"] and tr["master_prompt_hash"].startswith("map:")


# =========================================================================== #
# Direct mode (no preset) + 14-15 no regression
# =========================================================================== #
def test_direct_mode_sends_system_and_user_with_explicit_model():
    settings = _or_settings(preset=None, model="anthropic/claude-3.5-sonnet")
    out, captured, calls = _run(_valid_model_output(), settings=settings)
    messages = captured["body"]["messages"]
    assert [m["role"] for m in messages] == ["system", "user"]   # no preset -> send the compiled system
    assert "You are OMI ANALYST" in messages[0]["content"]
    assert captured["body"]["model"] == "anthropic/claude-3.5-sonnet"
    assert out["investigation_trace"]["model_backed"] is True


def test_missing_api_key_degrades_to_floor():
    import os as _os
    settings = _or_settings()

    def _fake(req, timeout=None):
        raise AssertionError("must not reach the network without a key")

    with patch.dict(_os.environ, {}, clear=False):
        _os.environ.pop("OPENROUTER_API_KEY", None)
        with patch("app.reasoning.model_providers.openrouter.urllib.request.urlopen", _fake):
            out = analyst.assess_payload(_PAYLOAD, ref="sub_nokey", platform="youtube", settings=settings)
    # no key -> the model path is not attempted; deterministic Floor is served
    assert out["investigation_trace"]["model_backed"] is False
    assert out["investigation_trace"]["inference_count"] == 0


def test_master_protocol_equals_compiled_system_and_is_the_repo_source_of_truth():
    from app.reasoning.comprehensive_investigation_analysis import (
        build_comprehensive_investigation_prompt_package,
    )
    from app.reasoning.evidence_repository import EvidenceRepository
    from app.reasoning.investigation_composer import InvestigationComposer

    snap = EvidenceRepository().snapshot(_PAYLOAD, ref="r", platform="youtube")
    pp = build_comprehensive_investigation_prompt_package(InvestigationComposer().compose(snap))
    master = compile_master_analyst_protocol()
    # the preset content Omi expects == the exact compiled system instructions (zero drift)
    assert master["text"] == pp.system
    assert master["hash"].split(":")[1] == pp.manifest["system_prompt_sha"].split(":")[1]
