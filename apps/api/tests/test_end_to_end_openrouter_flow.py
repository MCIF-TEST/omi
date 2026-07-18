"""End-to-end verification: YouTube / Twitter(X) evidence bundle → OpenRouter → UI shape.

Proves the whole production path with a MOCKED transport (no live call): a comprehensive scan payload
(YouTube OR X) is projected into the evidence bundle, dispatched to the OpenRouter preset ONLY when
``OPENROUTER_API_KEY`` is present (the Render variable), the model result is parsed + structurally
validated + persisted, and the exact fields the React UI consumes are present with the platform preserved.
When the key is absent, the ONE outbound gate does not fire and the deterministic Floor backs the
assessment gracefully (the product still works). Platform-agnostic: the same path serves both platforms
because a comprehensive scan wraps each platform's commenters into the ``video`` container.
"""
from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.reasoning import analyst
from app.reasoning.prompts.comprehensive_investigation_template import (
    COMPREHENSIVE_ASSESSMENT_SCHEMA_ID,
    COMPREHENSIVE_SECTION_KEYS,
)
from app.storage.db import reset_db_for_tests

_API_KEY = "sk-or-v1-SECRET-e2e-do-not-leak-0000"
_PRESET = "omi-master-v1"
_GPT5_MINI = "openai/gpt-5-mini"


@pytest.fixture(autouse=True)
def _fresh(monkeypatch):
    monkeypatch.delenv("HF_TOKEN", raising=False)
    monkeypatch.delenv("HUGGINGFACE_HUB_TOKEN", raising=False)
    reset_db_for_tests("sqlite:///:memory:")
    yield


def _prod_settings():
    """Production cutover config — provider=openrouter, the omi-master-v1 preset, no HF endpoint."""
    return SimpleNamespace(
        analyst_enabled=True, analyst_provider="openrouter", openrouter_preset=_PRESET,
        openrouter_model=None, openrouter_base_url="https://openrouter.ai/api/v1/chat/completions",
        openrouter_structured_output=True, openrouter_referer=None, openrouter_title=None,
        analyst_endpoint_url=None, analyst_hf_repo="Andrewexiga/omi-analyst-v1", analyst_hf_revision=None,
        analyst_prompt_version=None, analyst_model_id="mistralai/Mistral-7B-Instruct-v0.3",
        analyst_timeout_seconds=30.0, analyst_max_retries=0, analyst_endpoint_api="messages",
        analyst_cost_per_1k_tokens_usd=0.0, analyst_prompt_assembly="registry",
        memory_persistence_enabled=False, memory_database_url=None)


def _payload(platform: str) -> dict:
    """A comprehensive scan payload as the YouTube/X engine produces it — the platform's commenters ride
    in the ``video`` (FullVideoScanResult) container, which the analyst reads platform-agnostically."""
    return {
        "overall_probability": 0.68, "overall_tier": "elevated", "confidence": 0.55,
        "convergence_score": 0.3, "inputs_provided": ["video"], "video_id": "content-1",
        "video": {"video_id": "content-1", "platform": platform,
                  "coordination_score": 0.6, "coordination_tier": "elevated",
                  "clusters": [{"method": "co_engagement", "members": ["a", "b"], "score": 0.7,
                                "evidence": ["tight co-engagement window"]}],
                  "thread_scan": {"overall_probability": 0.5, "tier": "moderate"},
                  "commenters": [
                      {"external_id": "a", "handle": "@a", "platform": platform,
                       "overall_probability": 0.82, "tier": "high", "confidence": 0.6,
                       "recent_activity": [{"text": "great!!", "created_at": "2026-01-01T00:00:00Z"}],
                       "signals": [{"name": "temporal", "probability": 0.8, "evidence": ["low variance"]}]},
                      {"external_id": "b", "handle": "@b", "platform": platform,
                       "overall_probability": 0.54, "tier": "elevated",
                       "signals": [{"name": "temporal", "probability": 0.5}]}]},
    }


def _valid_model_output() -> dict:
    domains = {k: {"assessment": "reasoning present for this domain", "citations": ["A1"]}
               for k in COMPREHENSIVE_SECTION_KEYS}
    return {
        "verdict": "mixed", "omi_score": 68, "suspicion_tier": "elevated", "confidence_band": "moderate",
        "confidence_rationale": "single-axis temporal over thin data; no exculpatory signal was present.",
        "headline": "E2E-HEADLINE cadence is unusually regular.",
        "assessment": "Consistent with mechanical regularity; a single-axis result. Probabilistic; the "
                      "human analyst sets the verdict.",
        "evidence_for": [{"signal": "temporal", "claim": "low interval variance", "evidence_refs": ["A1"]}],
        "evidence_against": [], "uncertainty": ["thin data"],
        "what_would_change_this": ["more posts to corroborate the cadence"],
        "limits_statement": "This is a probabilistic assessment; the human analyst sets the final verdict.",
        "commenter_assessments": [
            {"ref": "A1", "assessment": "A1 posts on a mechanically regular cadence.", "citations": ["A1"]},
            {"ref": "A2", "assessment": "A2 shows a lighter footprint.", "citations": ["A2"]}],
        **domains,
    }


class _Resp:
    def __init__(self, body): self._body = body
    def __enter__(self): return self
    def __exit__(self, *a): return False
    def read(self): return self._body
    status = 200


def _or_body(model_obj: dict) -> bytes:
    return json.dumps({
        "id": "gen-e2e-1", "model": _GPT5_MINI,
        "choices": [{"message": {"role": "assistant", "content": json.dumps(model_obj)},
                     "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 1800, "completion_tokens": 420, "total_tokens": 2220, "cost": 0.0022},
    }).encode()


def _run(platform: str, *, key_present: bool, monkeypatch):
    if key_present:
        monkeypatch.setenv("OPENROUTER_API_KEY", _API_KEY)
    else:
        monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    captured: dict = {}
    calls = {"n": 0}

    def _fake(req, timeout=None):
        calls["n"] += 1
        captured["url"] = req.full_url
        captured["headers"] = {k.lower(): v for k, v in dict(req.headers).items()}
        captured["body"] = json.loads(req.data.decode())
        return _Resp(_or_body(_valid_model_output()))

    with patch("app.reasoning.model_providers.openrouter.urllib.request.urlopen", _fake):
        out = analyst.assess_payload(_payload(platform), ref=f"sub_{platform}", platform=platform,
                                     settings=_prod_settings())
    return out, captured, calls["n"]


# =========================================================================== #
# Key present → the evidence reaches OpenRouter and the result reaches the UI
# =========================================================================== #
@pytest.mark.parametrize("platform", ["youtube", "twitter"])
def test_platform_flow_reaches_openrouter_and_returns_ui_shape(platform, monkeypatch):
    out, captured, calls = _run(platform, key_present=True, monkeypatch=monkeypatch)

    # 1) exactly ONE request went to the OpenRouter endpoint, keyed by the render variable
    assert calls == 1
    assert captured["url"] == "https://openrouter.ai/api/v1/chat/completions"
    assert captured["headers"].get("authorization") == f"Bearer {_API_KEY}"

    # 2) it used the production preset + the canonical schema, and carried THIS investigation's evidence
    body = captured["body"]
    assert body["model"] == f"@preset/{_PRESET}"
    assert body["response_format"]["json_schema"]["name"] == COMPREHENSIVE_ASSESSMENT_SCHEMA_ID
    assert "A1" in body["messages"][0]["content"]          # the aliased commenter evidence reached the model

    # 3) the model result was parsed + structurally validated + is model-backed
    tr = out["investigation_trace"]
    assert tr["model_backed"] is True and tr["provider"] == "openrouter"
    assert tr["served_model"] == _GPT5_MINI
    assert out["headline"].startswith("E2E-HEADLINE")

    # 4) the exact fields the React UI consumes are present, with the platform preserved
    for f in ("verdict", "omi_score", "suspicion_tier", "confidence_band",
              "evidence_for", "evidence_against", "comprehensive_sections", "commenter_assessments",
              "completion"):
        assert f in out
    assert out["omi_score"] == 68            # the analyst's OWN OMI score survives (AI-first, not echoed)
    assert out["subject"]["platform"] == platform
    # per-account AI results joined back to real identity (echo)
    handles = {r.get("handle") for r in out["commenter_assessments"] if r.get("resolved")}
    assert handles == {"@a", "@b"}
    # secrets never leak into the served assessment
    assert _API_KEY not in json.dumps(out)


# =========================================================================== #
# Key absent → the ONE gate does not fire; graceful deterministic Floor
# =========================================================================== #
@pytest.mark.parametrize("platform", ["youtube", "twitter"])
def test_no_key_does_not_dispatch_and_floors_gracefully(platform, monkeypatch):
    out, captured, calls = _run(platform, key_present=False, monkeypatch=monkeypatch)
    assert calls == 0                                       # no OpenRouter request without the render key
    assert not captured                                    # the transport was never invoked
    tr = out["investigation_trace"]
    assert tr["model_backed"] is False                     # deterministic Floor stood in
    assert tr["endpoint_called"] is False
    # the product still works: a governed, UI-renderable assessment exists
    assert out.get("verdict") and out.get("suspicion_tier")
    assert out["subject"]["platform"] == platform
