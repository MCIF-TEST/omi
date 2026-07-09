"""Phase P2.0 → P3.3 — the AI Investigation Runtime's ONE inference primitive.

Proves ``AIInvestigationRuntime.infer`` (reached via ``run_stage_inference``) performs **exactly one
inference** via the ONE transport, captures the full execution provenance, always invokes the
Governor, and falls back to the deterministic Floor on failure/reject — reusing the single
implementations (no duplicated endpoint / retry / forensic / governor / fallback logic). The prompt it
reasons over is a :class:`PromptPackage` from the ONE Canonical Prompt Builder.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.core.config import get_settings
from app.evidence import Binder
from app.reasoning import analyst as _analyst
from app.reasoning import runtime as runtime_mod
from app.reasoning.comment_analysis import build_comment_prompt_package
from app.reasoning.context import build_investigation_context
from app.reasoning.evidence_bundles import build_comment_bundle
from app.reasoning.orchestrator.modules import build_ruling_assessment
from app.reasoning.runtime import RuntimeInference, run_stage_inference


def _payload() -> dict:
    return {
        "overall_probability": 0.72, "overall_tier": "elevated", "confidence": 0.55, "video_id": "v1",
        "video": {
            "thread_scan": {"overall_probability": 0.5, "tier": "moderate"},
            "coordination_score": 0.66, "coordination_tier": "elevated",
            "commenters": [{"external_id": "a", "handle": "@a", "overall_probability": 0.8, "tier": "high",
                            "confidence": 0.6,
                            "recent_activity": [{"text": "great video!!", "created_at": "2026-01-01T00:00:00Z",
                                                 "parent_id": "v9"}],
                            "signals": [{"name": "temporal", "probability": 0.8, "confidence": 0.7}]}]},
    }


def _pp_and_gov(payload=None):
    payload = payload or _payload()
    ctx = build_investigation_context(payload, ref="slug1", platform="youtube", slug="slug1", kind="video")
    pp = build_comment_prompt_package(build_comment_bundle(ctx))
    ref = ctx.investigation.ref or _analyst._ref(ctx.context_id)
    gov = Binder().bind(payload, grain="comment_section", subject_ref=ref, platform="youtube")
    return pp, gov


def _enabled_settings(**over):
    base = {"analyst_enabled": True, "analyst_endpoint_url": "http://endpoint/generate"}
    base.update(over)
    return get_settings().model_copy(update=base)


# --------------------------------------------------------------------------- #
# Floor path (no endpoint) — Governor-validated RuntimeInference, no endpoint call
# --------------------------------------------------------------------------- #
def test_floor_when_disabled_is_governed_and_captures_identity():
    pp, gov = _pp_and_gov()
    inf = run_stage_inference(pp, gov)
    assert isinstance(inf, RuntimeInference)
    assert inf.model_backed is False and inf.fallback is True and inf.endpoint_called is False
    assert inf.provider == "deterministic-analyst-v1"
    assert inf.trace.permitted and inf.trace.trace_id().startswith("vt:")
    # identity flows from the PromptPackage; no endpoint => zero forensic
    assert inf.package_hash == pp.manifest["package_hash"] and inf.prompt_hash == pp.manifest["prompt_hash"]
    assert inf.served_model == pp.model_id == "mistralai/Mistral-7B-Instruct-v0.3"
    assert inf.latency_ms == 0.0 and inf.attempts == 0 and inf.tokens is None


# --------------------------------------------------------------------------- #
# Model path — EXACTLY ONE inference, via the ONE transport, with full capture
# --------------------------------------------------------------------------- #
def test_exactly_one_inference_and_captures_metadata(monkeypatch):
    payload = _payload()
    pp, gov = _pp_and_gov(payload)
    valid = build_ruling_assessment(gov)                          # a Governor-valid wrapper
    calls: list[tuple[str, str]] = []

    def fake_qwen_transport(endpoint, **kw):
        cap = kw.get("capture")

        def _call(system, user, config):
            calls.append((system, user))
            if cap is not None:                                  # the ONE transport populates capture
                cap.update({"latency_ms": 12.3, "attempts": 1, "response_status": 200,
                            "endpoint_request_id": "req-abc-123",
                            "usage": {"prompt_tokens": 900, "completion_tokens": 120, "total_tokens": 1020}})
            return json.dumps(valid)

        return _call

    monkeypatch.setattr(_analyst, "_qwen_transport", fake_qwen_transport)
    inf = run_stage_inference(pp, gov, settings=_enabled_settings())

    assert len(calls) == 1                                        # exactly one inference
    assert inf.endpoint_called is True and inf.model_backed is True and inf.fallback is False
    assert inf.provider == "qwen-omi-analyst-v1" and inf.trace.permitted
    # the prompt sent is EXACTLY the canonically-built PromptPackage (system+user)
    assert calls[0][0] == pp.system and calls[0][1] == pp.user
    # full execution provenance captured + surfaced
    assert inf.latency_ms == pytest.approx(12.3) and inf.attempts == 1
    assert inf.tokens == {"prompt_tokens": 900, "completion_tokens": 120, "total_tokens": 1020}
    assert inf.endpoint_request_id == "req-abc-123" and inf.response_status == 200


def test_fallback_to_floor_when_endpoint_unreachable(monkeypatch):
    pp, gov = _pp_and_gov()
    calls = []

    def fake_qwen_transport(endpoint, **kw):
        def _call(system, user, config):
            calls.append(1)
            return None                                          # transport gave up (after its retries)
        return _call

    monkeypatch.setattr(_analyst, "_qwen_transport", fake_qwen_transport)
    inf = run_stage_inference(pp, gov, settings=_enabled_settings())
    assert len(calls) == 1                                        # one inference attempt, still
    assert inf.model_backed is False and inf.fallback is True
    assert inf.provider == "deterministic-analyst-v1" and inf.trace.permitted


def test_fallback_to_floor_when_model_output_invalid(monkeypatch):
    pp, gov = _pp_and_gov()

    def fake_qwen_transport(endpoint, **kw):
        def _call(system, user, config):
            return "this is not valid JSON"
        return _call

    monkeypatch.setattr(_analyst, "_qwen_transport", fake_qwen_transport)
    inf = run_stage_inference(pp, gov, settings=_enabled_settings())
    assert inf.model_backed is False and inf.fallback is True
    assert inf.provider.startswith("qwen-omi-analyst-v1->fallback:")   # model answered but was rejected
    assert inf.trace.permitted


# --------------------------------------------------------------------------- #
# The "single endpoint caller" + "single Governor" invariants (source-level)
# --------------------------------------------------------------------------- #
def test_runtime_owns_no_endpoint_or_governor_primitive():
    """The runtime orchestrates by delegation: it reaches the endpoint ONLY through the shared
    transport factory and must not open its own HTTP client or reimplement retries."""
    src = Path(runtime_mod.__file__).read_text(encoding="utf-8")
    assert "_qwen_transport" in src                               # reuses the ONE transport factory
    assert "urlopen(" not in src and "import urllib" not in src   # no bespoke endpoint code
    assert "for attempt in range" not in src                      # no duplicated retry loop
    assert "governor.validate(" in src                            # the Governor is invoked, not reimplemented


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
