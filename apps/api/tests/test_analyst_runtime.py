"""Sprint 003 — AI runtime activation tests.

Covers the mandatory Governor gate on the live analyst path (permit + reject->Floor),
the runtime-status diagnostic + endpoint, and the Qwen provider's timeout/retry/fallback
behavior (verified without a live endpoint by mocking the transport). The Governor is
never bypassed; the deterministic Floor is always the fallback.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.reasoning import analyst
from app.storage.db import reset_db_for_tests


@pytest.fixture(autouse=True)
def _fresh():
    reset_db_for_tests("sqlite:///:memory:")
    yield


def _payload() -> dict:
    return {
        "overall_probability": 0.72, "overall_tier": "elevated", "confidence": 0.6,
        "summary": "Elevated suspicion across multiple signals.",
        "weak_signals": ["only 8 posts — temporal abstained"], "single_axis_capped": False,
        "contributions": [
            {"name": "temporal", "impact": 0.5, "logit_delta": 0.8, "direction": "raises"},
            {"name": "community", "impact": 0.2, "logit_delta": -0.3, "direction": "lowers"},
            {"name": "ai_writing", "impact": 0.1, "logit_delta": 0.0,
             "direction": "neutral", "supplemental": True},
        ],
        "video": {
            "clusters": [{"method": "co_engagement", "members": ["@a", "@b", "@c"]}],
            "commenters": [
                {"handle": "@bot1", "tier": "high", "overall_probability": 0.91},
                {"handle": "@bot2", "tier": "elevated", "overall_probability": 0.7},
            ],
        },
        "cross_links": [{"kind": "focus_in_cluster", "summary": "Focus in cluster"}],
    }


def _enable(monkeypatch):
    monkeypatch.setattr(analyst, "analyst_enabled", lambda settings=None: True)


# --- mandatory Governor gate (permit) --------------------------------------- #
def test_assess_payload_attaches_governance_on_permit(monkeypatch):
    _enable(monkeypatch)
    out = analyst.assess_payload(_payload(), ref="sub_x", platform="youtube")
    assert out is not None
    gov = out["governance"]
    assert gov["verdict"] == "permit"
    assert gov["provider"]  # deterministic-analyst-v1 (no endpoint configured)
    assert gov["trace_id"].startswith("vt:")
    assert gov["latency_ms"] >= 0
    assert gov["constitution_version"] == 1
    # echo discipline preserved through the gate
    assert out["suspicion_probability"] == 0.72


# --- Governor reject -> deterministic Floor fallback ------------------------ #
def test_governor_reject_falls_back_to_floor(monkeypatch):
    _enable(monkeypatch)
    from app.governor import Governor
    from app.governor.audit import ValidationTrace

    real = Governor.validate
    calls = {"n": 0}

    def fake(self, ruling, bundle, *, corroboration=None):
        calls["n"] += 1
        t = real(self, ruling, bundle, corroboration=corroboration)
        if calls["n"] == 1:  # reject the first (provider) assessment
            return ValidationTrace(
                verdict="reject", violation_codes=["gate_breach"],
                stage_results=t.stage_results, version_binding=t.version_binding,
                input_digest=t.input_digest, bundle_id=t.bundle_id, fallback_path="floor",
            )
        return t  # permit the regenerated Floor

    monkeypatch.setattr(Governor, "validate", fake)
    out = analyst.assess_payload(_payload(), ref="sub_x", platform="youtube")
    assert out is not None
    gov = out["governance"]
    assert gov["provider"] == "deterministic-floor"
    assert gov["fallback_from"]              # the rejected provider is recorded
    assert gov["rejected_codes"] == ["gate_breach"]
    assert gov["verdict"] == "permit"        # the Floor passed on re-validation
    assert calls["n"] == 2                   # validated twice: reject -> Floor permit


# --- runtime status diagnostic ---------------------------------------------- #
def test_runtime_status_disabled_default():
    st = analyst.runtime_status()
    assert st["enabled"] is False
    assert st["impl_importable"] is None      # never imports the impl when off
    assert st["provider"] == "deterministic-floor"
    assert st["governor"] == "mandatory"
    assert st["deterministic_floor"] == "always-on"
    assert st["ready_for_live_qwen"] is False
    assert isinstance(st["hf_token_present"], bool)


def test_runtime_status_enabled_without_endpoint(monkeypatch):
    _enable(monkeypatch)
    st = analyst.runtime_status()
    assert st["enabled"] is True
    assert st["impl_importable"] is True
    assert st["endpoint_configured"] is False
    assert st["provider"] == "deterministic-floor"
    assert st["ready_for_live_qwen"] is False  # no endpoint -> not live


def test_analyst_status_endpoint():
    with TestClient(app) as tc:
        r = tc.get("/v1/investigations/analyst/status")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["governor"] == "mandatory"
        assert "enabled" in body and "ready_for_live_qwen" in body
        assert isinstance(body["hf_token_present"], bool)  # presence only, no secret


# --- Qwen provider: delegates to the ONE constitutional transport (Sprint 017) ------ #
def test_qwen_provider_delegates_to_injected_transport(monkeypatch):
    """The analyst provider no longer carries a bespoke HTTP client — it delegates to the ONE
    injected constitutional transport. A failing transport degrades to None (-> deterministic).
    The retry/timeout behavior is owned + tested on the shared RemoteReasoningProvider."""
    impl = analyst._impl()
    assert impl is not None
    monkeypatch.setenv("HF_TOKEN", "test-token")
    calls = {"n": 0}

    def _transport(system, user, config):
        calls["n"] += 1
        return None  # simulate endpoint failure

    prov = impl.QwenAnalystProvider(endpoint_url="http://x/y", transport=_transport)
    assert prov._call_model("sys", "user", impl.load_analyst_config()) is None
    assert calls["n"] == 1
    # with no transport injected (decoupled standalone use) there is no model client at all.
    prov2 = impl.QwenAnalystProvider(endpoint_url="http://x/y")
    assert prov2._call_model("sys", "user", impl.load_analyst_config()) is None


def test_qwen_provider_generate_falls_back_to_deterministic(monkeypatch):
    impl = analyst._impl()
    monkeypatch.setenv("HF_TOKEN", "test-token")
    # No model output from the transport -> graceful deterministic fallback.
    prov = impl.QwenAnalystProvider(
        endpoint_url="http://127.0.0.1:9/x", transport=lambda *a, **k: None)
    bundle = impl.evidence_bundle.project_investigation_bundle(
        ref="sub_x", platform="youtube",
        scan={"overall_probability": 0.5, "tier": "moderate", "confidence": 0.5},
        components=[], cross_links=[],
    )
    res = prov.generate(bundle, impl.load_analyst_config())
    assert res.provider.startswith("qwen-omi-analyst-v1->fallback")  # graceful degradation
    assert res.response["subject"]["grain"] == "comment_section"


def test_production_path_injects_constitutional_transport(monkeypatch):
    """assess_payload wires the analyst's model call through the ONE constitutional
    RemoteReasoningProvider — verified by capturing the request it would send."""
    _enable(monkeypatch)
    monkeypatch.setenv("HF_TOKEN", "test-token")
    monkeypatch.setattr(
        analyst, "get_settings",
        lambda: type("S", (), {"analyst_enabled": True, "analyst_hf_repo": "Andrewexiga/omi-analyst-v1",
                               "analyst_hf_revision": None, "analyst_endpoint_url": "https://ep.invalid/x",
                               "analyst_timeout_seconds": 5.0, "analyst_max_retries": 1,
                               "analyst_prompt_version": None})())
    captured = {}
    from app.reasoning.model_providers import RemoteReasoningProvider

    def _fake_complete(self, request):
        captured["system"] = request.system
        from app.reasoning.model_providers import ProviderUnavailable
        raise ProviderUnavailable("no live endpoint in test")  # force deterministic fallback

    monkeypatch.setattr(RemoteReasoningProvider, "complete", _fake_complete)
    out = analyst.assess_payload(_payload(), ref="sub_x", platform="youtube")
    assert out is not None and out["suspicion_probability"] == 0.72   # echo preserved via fallback
    assert "OMI ANALYST" in captured["system"]                        # registry prompt reached the ONE client
