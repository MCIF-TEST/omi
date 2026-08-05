"""`GET /v1/investigations/analyst/preflight` — can this deployment produce an AI analysis right now?

Every investigation came back with the deterministic Floor and nothing anywhere said why. The config
check that was supposed to catch it (`/analyst/status`) reports `ready_for_live_model` when the API key
is merely PRESENT and a preset name is set, so a revoked key, a renamed or truncated preset, and an
exhausted balance all read as ready and then fail on every scan.

That is the same hole `/v1/billing/preflight` exists to close for Stripe, where the lesson is already
written down: the key being set is not the same as the key working. These tests pin the live half.

The probe is never allowed to raise: a diagnostic that 500s during an incident is worse than no
diagnostic, because it sends the operator looking in the wrong place.
"""
from __future__ import annotations

import urllib.error

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.reasoning.model_providers.openrouter import OpenRouterReasoningProvider
from app.routes.reasoning import _PROBE_REMEDIES
from app.storage.db import reset_db_for_tests


@pytest.fixture(autouse=True)
def _fresh():
    reset_db_for_tests("sqlite:///:memory:")
    yield


# --------------------------------------------------------------------------- #
# The probe itself: one minimal call, every failure classified, never raising
# --------------------------------------------------------------------------- #
def test_a_missing_key_is_reported_not_raised(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    out = OpenRouterReasoningProvider(preset="omi-master-v1").probe()
    assert out["ok"] is False and out["reason"] == "no_api_key"
    # No call was attempted, so there is no status to report.
    assert out["status"] is None


def test_no_preset_and_no_model_is_reported(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
    out = OpenRouterReasoningProvider().probe()
    assert out["ok"] is False and out["reason"] == "no_preset_or_model"


@pytest.mark.parametrize("code,reason", [
    (401, "bad_api_key"),
    (403, "bad_api_key"),
    (402, "no_credit"),
    (404, "preset_or_model_not_found"),
    (429, "rate_limited"),
    (418, "http_error"),
])
def test_every_gateway_refusal_is_classified(monkeypatch, code, reason):
    """A revoked key and a renamed preset are different problems with different fixes, and the operator
    should not have to tell them apart from a stack trace. 401 vs 404 is the whole diagnosis."""
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")

    def _raise(*_a, **_k):
        raise urllib.error.HTTPError("u", code, "no", {}, None)

    monkeypatch.setattr("urllib.request.urlopen", _raise)
    out = OpenRouterReasoningProvider(preset="omi-master-v1").probe()
    assert out["ok"] is False
    assert out["reason"] == reason
    assert out["status"] == code


def test_a_transport_failure_is_reported_not_raised(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")

    def _raise(*_a, **_k):
        raise OSError("connection refused")

    monkeypatch.setattr("urllib.request.urlopen", _raise)
    out = OpenRouterReasoningProvider(preset="omi-master-v1").probe()
    assert out["ok"] is False and out["reason"] == "unreachable"


def test_a_healthy_gateway_reports_the_served_model(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")

    class _Resp:
        status = 200

        def read(self):
            return b'{"model": "openai/gpt-5-mini", "choices": []}'

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

    monkeypatch.setattr("urllib.request.urlopen", lambda *_a, **_k: _Resp())
    out = OpenRouterReasoningProvider(preset="omi-master-v1").probe()
    assert out["ok"] is True
    assert out["served_model"] == "openai/gpt-5-mini"
    assert out["model_ref"] == "@preset/omi-master-v1"


def test_the_probe_never_returns_the_api_key(monkeypatch):
    """It is rendered straight to an operator and may be pasted into a chat or an issue."""
    secret = "sk-or-v1-DEADBEEFsupersecretvalue"
    monkeypatch.setenv("OPENROUTER_API_KEY", secret)

    def _raise(*_a, **_k):
        raise urllib.error.HTTPError("u", 401, "no", {}, None)

    monkeypatch.setattr("urllib.request.urlopen", _raise)
    out = OpenRouterReasoningProvider(preset="omi-master-v1").probe()
    assert secret not in repr(out)


def test_the_probe_asks_for_one_token_so_a_health_check_is_never_expensive(monkeypatch):
    """It runs on demand during an incident, possibly repeatedly. It must not bill like a scan."""
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
    seen: dict = {}

    def _capture(req, *_a, **_k):
        import json
        seen.update(json.loads(req.data.decode()))
        raise OSError("stop here")

    monkeypatch.setattr("urllib.request.urlopen", _capture)
    OpenRouterReasoningProvider(preset="omi-master-v1").probe()
    assert seen["max_tokens"] == 1
    assert seen["stream"] is False


# --------------------------------------------------------------------------- #
# The route
# --------------------------------------------------------------------------- #
def test_every_probe_reason_has_an_operator_remedy():
    """The route turns a reason into an action. A reason added to the probe without a remedy here would
    render as a bare failure with no next step, which is the state this whole route exists to end."""
    reasons = {"no_api_key", "no_preset_or_model", "bad_api_key", "no_credit",
               "preset_or_model_not_found", "rate_limited", "timeout", "unreachable",
               "http_error", "provider_build_failed"}
    assert reasons <= set(_PROBE_REMEDIES)
    for text in _PROBE_REMEDIES.values():
        assert text.strip() and not text.endswith((".." , " "))


def test_preflight_reports_not_ready_and_names_the_next_step(monkeypatch):
    monkeypatch.setenv("OMI_ANALYST_ENABLED", "true")
    monkeypatch.setenv("OMI_ANALYST_PROVIDER", "openrouter")
    monkeypatch.setenv("OMI_OPENROUTER_PRESET", "omi-master-v1")
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    from app.core.config import get_settings
    get_settings.cache_clear()

    with TestClient(app) as client:
        r = client.get("/v1/investigations/analyst/preflight")
    assert r.status_code == 200
    body = r.json()
    assert body["ready"] is False
    assert any("OPENROUTER_API_KEY" in s for s in body["next_steps"])
    get_settings.cache_clear()


def test_preflight_shows_the_config_only_answer_beside_the_live_one(monkeypatch):
    """The entire point: /analyst/status can say ready while this says not ready. Showing both side by
    side is what makes the discrepancy legible instead of confusing."""
    monkeypatch.setenv("OMI_ANALYST_ENABLED", "true")
    monkeypatch.setenv("OMI_ANALYST_PROVIDER", "openrouter")
    monkeypatch.setenv("OMI_OPENROUTER_PRESET", "omi-master-v1")
    from app.core.config import get_settings
    get_settings.cache_clear()

    with TestClient(app) as client:
        body = client.get("/v1/investigations/analyst/preflight").json()
    assert "config_only_status" in body
    assert "ready_for_live_model" in body["config_only_status"]
    assert "note" in body
    get_settings.cache_clear()
