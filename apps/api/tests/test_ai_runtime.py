"""Phase P2.0 — the AI Investigation Runtime (the ONE orchestration layer for AI execution).

Proves the runtime chains InvestigationContext → Package Loader → Prompt Builder → HF endpoint →
capture → Governor → fallback → one immutable result, that it performs **exactly one inference** via
the ONE transport, captures the full execution provenance, always invokes the Governor, and falls
back to the deterministic Floor on failure/reject — reusing the single implementations (no duplicated
endpoint / retry / forensic / governor / fallback logic).
"""
from __future__ import annotations

import dataclasses
import json
from pathlib import Path

import pytest

from app.core.config import get_settings
from app.reasoning import analyst as _analyst
from app.reasoning import runtime as runtime_mod
from app.reasoning.context import build_investigation_context
from app.reasoning.runtime import AIInvestigationResult, run_investigation


def _payload() -> dict:
    return {
        "overall_probability": 0.72, "overall_tier": "elevated", "confidence": 0.55,
        "summary": "Elevated suspicion.", "video_id": "v1",
        "contributions": [{"name": "temporal", "impact": 0.4, "direction": "raises", "headline": "bursty"}],
        "video": {
            "coordination_score": 0.66, "coordination_tier": "elevated",
            "clusters": [{"method": "co_engagement", "members": ["a", "b", "c"], "score": 0.7,
                          "evidence": ["tight"]}],
            "commenters": [{"external_id": "a", "handle": "@a", "overall_probability": 0.8, "tier": "high",
                            "confidence": 0.6, "reasons": ["bursty posting"],
                            "signals": [{"name": "temporal", "probability": 0.8, "confidence": 0.7}]}],
        },
    }


def _ctx(payload=None):
    return build_investigation_context(payload or _payload(), ref="slug1", platform="youtube",
                                       slug="slug1", kind="video")


def _valid_model_response(payload) -> dict:
    """A schema-valid analyst response (generated via the deterministic provider) to stand in for a
    good Mistral output in the model-backed path."""
    impl = _analyst._impl()
    ref = _analyst._ref("slug1")
    lossy = _analyst.build_bundle(payload, ref=ref, platform="youtube", impl=impl)
    config = impl.load_analyst_config(repo_id=get_settings().analyst_hf_repo, revision=None)
    return impl.DeterministicAnalystProvider().generate(lossy, config).response


def _enabled_settings(**over):
    base = {"analyst_enabled": True, "analyst_endpoint_url": "http://endpoint/v1/chat/completions"}
    base.update(over)
    return get_settings().model_copy(update=base)


# --------------------------------------------------------------------------- #
# Floor path (no endpoint) — always returns an immutable, Governor-validated result
# --------------------------------------------------------------------------- #
def test_returns_immutable_result_via_floor_when_disabled():
    res = run_investigation(_ctx(), payload=_payload(), platform="youtube")
    assert isinstance(res, AIInvestigationResult)
    with pytest.raises(dataclasses.FrozenInstanceError):
        res.provider = "x"
    assert res.model_backed is False and res.fallback is True
    assert res.endpoint_called is False
    assert res.governor_verdict in ("permit", "reject")
    assert res.governor_trace_id.startswith("vt:")
    # the identity + provenance is always captured
    assert res.package_hash.startswith("pkg:") and res.prompt_hash.startswith("ph:")
    assert res.template_hash.startswith("tmpl:") and res.model_id == "mistralai/Mistral-7B-Instruct-v0.3"
    assert res.context_id == _ctx().context_id and res.result_id.startswith("air:")
    # the engine number is echoed, never moved
    assert res.assessment["suspicion_probability"] == pytest.approx(0.72)


# --------------------------------------------------------------------------- #
# Model path — EXACTLY ONE inference, via the ONE transport, with full capture
# --------------------------------------------------------------------------- #
def test_exactly_one_inference_and_captures_metadata(monkeypatch):
    payload = _payload()
    valid = _valid_model_response(payload)
    calls: list[tuple[str, str]] = []

    def fake_qwen_transport(endpoint, **kw):
        cap = kw.get("capture")

        def _call(system, user, config):
            calls.append((system, user))
            if cap is not None:  # the ONE transport populates the capture sidecar
                cap.update({"latency_ms": 12.3, "attempts": 1, "response_status": 200,
                            "endpoint_request_id": "req-abc-123",
                            "usage": {"prompt_tokens": 900, "completion_tokens": 120, "total_tokens": 1020}})
            return json.dumps(valid)

        return _call

    monkeypatch.setattr(_analyst, "_qwen_transport", fake_qwen_transport)
    res = run_investigation(_ctx(payload), payload=payload, platform="youtube", settings=_enabled_settings())

    assert len(calls) == 1                                        # exactly one inference
    assert res.endpoint_called is True and res.model_backed is True and res.fallback is False
    assert res.provider == "qwen-omi-analyst-v1"
    assert res.governor_verdict == "permit"
    # the prompt sent is the canonically-built PromptPackage (system+user), not a bespoke prompt
    from app.reasoning.prompt import build_prompt_package
    pp = build_prompt_package(_ctx(payload))
    assert calls[0][0] == pp.system and calls[0][1] == pp.user
    # full execution provenance captured
    assert res.latency_ms == pytest.approx(12.3) and res.attempts == 1
    assert res.tokens == {"prompt_tokens": 900, "completion_tokens": 120, "total_tokens": 1020}
    assert res.endpoint_request_id == "req-abc-123" and res.response_status == 200


def test_fallback_to_floor_when_endpoint_unreachable(monkeypatch):
    payload = _payload()
    calls = []

    def fake_qwen_transport(endpoint, **kw):
        def _call(system, user, config):
            calls.append(1)
            return None  # transport returns None on endpoint failure (after its own retries)
        return _call

    monkeypatch.setattr(_analyst, "_qwen_transport", fake_qwen_transport)
    res = run_investigation(_ctx(payload), payload=payload, settings=_enabled_settings())
    assert len(calls) == 1                                        # one inference attempt, still
    assert res.model_backed is False and res.fallback is True
    assert res.provider == "deterministic-analyst-v1"            # clean floor (endpoint never answered)
    assert res.governor_verdict == "permit"


def test_fallback_to_floor_when_model_output_invalid(monkeypatch):
    payload = _payload()

    def fake_qwen_transport(endpoint, **kw):
        def _call(system, user, config):
            return "this is not valid JSON"
        return _call

    monkeypatch.setattr(_analyst, "_qwen_transport", fake_qwen_transport)
    res = run_investigation(_ctx(payload), payload=payload, settings=_enabled_settings())
    assert res.model_backed is False and res.fallback is True
    assert res.provider.startswith("qwen-omi-analyst-v1->fallback:")   # model answered but was rejected
    assert res.governor_verdict == "permit"


# --------------------------------------------------------------------------- #
# Determinism + the "single endpoint caller" invariant
# --------------------------------------------------------------------------- #
def test_result_is_content_addressed():
    a = run_investigation(_ctx(), payload=_payload())
    b = run_investigation(_ctx(), payload=_payload())
    assert a.result_id == b.result_id and a.result_id.startswith("air:")


def test_runtime_owns_no_endpoint_or_governor_primitive():
    """The runtime orchestrates by delegation: it reaches the endpoint ONLY through the shared
    transport factory and must not open its own HTTP client or reimplement retries."""
    src = Path(runtime_mod.__file__).read_text(encoding="utf-8")
    assert "_qwen_transport" in src                               # reuses the ONE transport factory
    assert "urlopen(" not in src and "import urllib" not in src   # no bespoke endpoint code
    assert "for attempt in range" not in src                      # no duplicated retry loop
    # the Governor is invoked, not reimplemented
    assert "governor.validate(" in src


def test_capture_helper_records_usage_and_request_id():
    """The additive transport capture surfaces token usage + the endpoint request id for the runtime."""
    from app.reasoning.model_providers.remote import _capture_endpoint_meta

    class _Resp:
        status = 200
        class headers:  # noqa: N801
            @staticmethod
            def get(k):
                return "req-xyz" if k == "x-request-id" else None
        def getcode(self):
            return 200
    cap: dict = {}
    body = json.dumps({"choices": [{"message": {"content": "{}"}}],
                       "usage": {"prompt_tokens": 5, "completion_tokens": 7, "total_tokens": 12}}).encode()
    _capture_endpoint_meta(cap, _Resp(), body)
    assert cap["response_status"] == 200 and cap["endpoint_request_id"] == "req-xyz"
    assert cap["usage"] == {"prompt_tokens": 5, "completion_tokens": 7, "total_tokens": 12}
