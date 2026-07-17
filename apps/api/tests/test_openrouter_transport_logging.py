"""Phase 5E — OpenRouter transport verification (lifecycle logging + failure classification).

Proves the transport emits a START / OK / FAIL log lifecycle around the ONE model inference, that the
logs carry sizes/status/ids ONLY (never the API key, the prompt, or the investigation body), that
``response_bytes`` is captured on the forensic record, and that every failure mode maps to a stable
operational failure class. All tests mock ``urlopen`` — no live call is ever made.
"""
from __future__ import annotations

import json
import logging
import socket
import urllib.error
from unittest.mock import patch

import pytest

from app.reasoning.model_providers.base import (
    ProviderError,
    ProviderProtocolError,
    ProviderTimeout,
    ProviderUnavailable,
    ReasoningRequest,
)
from app.reasoning.model_providers.openrouter import (
    OpenRouterReasoningProvider,
    classify_transport_failure,
)

_API_KEY = "sk-or-v1-SECRET-testkey-do-not-leak-0000"
_PRESET = "omi-master-v1"
_SERVED = "openai/gpt-5-mini"


@pytest.fixture(autouse=True)
def _key(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", _API_KEY)
    yield


class _Resp:
    def __init__(self, body): self._body = body
    def __enter__(self): return self
    def __exit__(self, *a): return False
    def read(self): return self._body
    status = 200


def _ok_body(content='{"ok": true}', gen_id="gen-5e-1") -> bytes:
    return json.dumps({
        "id": gen_id, "model": _SERVED,
        "choices": [{"message": {"role": "assistant", "content": content}}],
        "usage": {"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120},
    }).encode()


def _provider(**kw) -> OpenRouterReasoningProvider:
    kw.setdefault("max_retries", 0)
    return OpenRouterReasoningProvider(
        preset=_PRESET, structured_output=False, capture={},
        **kw,
    )


def _request(fmt="text") -> ReasoningRequest:
    return ReasoningRequest(
        system="SYSTEM-PROMPT-SECRET-DOCTRINE", user="INVESTIGATION-PACKAGE-SECRET-EVIDENCE",
        max_tokens=8000, response_format=fmt,
    )


# =========================================================================== #
# classify_transport_failure — the operational failure taxonomy
# =========================================================================== #
def test_classify_covers_every_failure_class():
    assert classify_transport_failure(ProviderTimeout("t"), None) == "timeout"
    assert classify_transport_failure(ProviderProtocolError("j"), None) == "invalid_json"
    assert classify_transport_failure(ProviderUnavailable("u"), None) == "not_configured"
    # HTTP-status-driven classes
    assert classify_transport_failure(ProviderError("x"), 401) == "authentication"
    assert classify_transport_failure(ProviderError("x"), 403) == "authentication"
    assert classify_transport_failure(ProviderError("x"), 429) == "rate_limit"
    assert classify_transport_failure(ProviderError("x"), 404) == "invalid_preset_or_model"
    assert classify_transport_failure(ProviderError("x"), 400) == "invalid_request"
    assert classify_transport_failure(ProviderError("x"), 503) == "http_error"
    # message-driven fallbacks when no typed status is available
    assert classify_transport_failure(socket.timeout("timed out"), None) == "timeout"
    assert classify_transport_failure(Exception("Connection refused"), None) == "transport"
    assert classify_transport_failure(ProviderError("openrouter unreachable: x"), None) == "transport"
    assert classify_transport_failure(Exception("weird"), None) == "unexpected_response"


# =========================================================================== #
# Successful transport — START + OK logs, response_bytes captured, no secrets
# =========================================================================== #
def test_success_emits_start_and_ok_logs_and_captures_response_bytes(caplog):
    body = _ok_body()
    provider = _provider()

    def _fake(req, timeout=None):
        return _Resp(body)

    with caplog.at_level(logging.INFO, logger="app.reasoning.model_providers.openrouter"):
        with patch("app.reasoning.model_providers.openrouter.urllib.request.urlopen", _fake):
            resp = provider.complete(_request())

    assert resp.text  # completed
    assert provider.capture["response_bytes"] == len(body)
    msgs = [r.getMessage() for r in caplog.records]
    start = next(m for m in msgs if "openrouter.transport START" in m)
    ok = next(m for m in msgs if "openrouter.transport OK" in m)
    # START carries provider/endpoint/preset/model_ref/request_bytes/structured_output — sizes & ids only
    assert "provider=openrouter" in start
    assert "preset=omi-master-v1" in start
    assert "request_bytes=" in start
    # OK carries status/request_id/latency/bytes_received/attempts/completion
    assert "status=200" in ok
    assert "request_id=gen-5e-1" in ok
    assert "bytes_received=%d" % len(body) in ok
    assert "completion=success" in ok


def test_transport_logs_never_leak_key_prompt_or_investigation(caplog):
    provider = _provider()

    def _fake(req, timeout=None):
        return _Resp(_ok_body())

    with caplog.at_level(logging.INFO, logger="app.reasoning.model_providers.openrouter"):
        with patch("app.reasoning.model_providers.openrouter.urllib.request.urlopen", _fake):
            provider.complete(_request())

    blob = "\n".join(r.getMessage() for r in caplog.records)
    assert _API_KEY not in blob
    assert "SYSTEM-PROMPT-SECRET-DOCTRINE" not in blob
    assert "INVESTIGATION-PACKAGE-SECRET-EVIDENCE" not in blob


# =========================================================================== #
# Failure transport — one classified FAIL log per failure mode, then re-raise
# =========================================================================== #
def _run_raising(exc, caplog, fmt="text"):
    provider = _provider()

    def _boom(req, timeout=None):
        raise exc

    with caplog.at_level(logging.WARNING, logger="app.reasoning.model_providers.openrouter"):
        with patch("app.reasoning.model_providers.openrouter.urllib.request.urlopen", _boom):
            with pytest.raises(ProviderError):
                provider.complete(_request(fmt))
    return next(r.getMessage() for r in caplog.records if "openrouter.transport FAIL" in r.getMessage())


def test_fail_log_classifies_timeout(caplog):
    msg = _run_raising(socket.timeout("timed out"), caplog)
    assert "class=timeout" in msg


def test_fail_log_classifies_authentication(caplog):
    err = urllib.error.HTTPError("https://openrouter.ai", 401, "Unauthorized", {}, None)
    msg = _run_raising(err, caplog)
    assert "class=authentication" in msg
    assert "status=401" in msg


def test_fail_log_classifies_rate_limit(caplog):
    # 429 with no retries budget surfaces as an HTTP error carrying the 429 status in the capture.
    provider = _provider(max_retries=0)
    err = urllib.error.HTTPError("https://openrouter.ai", 429, "Too Many Requests", {}, None)

    def _boom(req, timeout=None):
        raise err

    with caplog.at_level(logging.WARNING, logger="app.reasoning.model_providers.openrouter"):
        with patch("app.reasoning.model_providers.openrouter.urllib.request.urlopen", _boom):
            with pytest.raises(ProviderError):
                provider.complete(_request())
    msg = next(r.getMessage() for r in caplog.records if "FAIL" in r.getMessage())
    assert "class=rate_limit" in msg
    assert "status=429" in msg


def test_fail_log_classifies_http_error(caplog):
    err = urllib.error.HTTPError("https://openrouter.ai", 500, "Server Error", {}, None)
    msg = _run_raising(err, caplog, )
    assert "class=http_error" in msg


def test_fail_log_classifies_transport(caplog):
    msg = _run_raising(urllib.error.URLError("[Errno 111] Connection refused"), caplog)
    assert "class=transport" in msg


def test_fail_log_classifies_invalid_json(caplog):
    # 200 with non-JSON content while JSON was requested → ProviderProtocolError → invalid_json.
    provider = _provider()
    bad = json.dumps({
        "id": "gen-bad", "model": _SERVED,
        "choices": [{"message": {"role": "assistant", "content": "not json {{{"}}],
    }).encode()

    def _fake(req, timeout=None):
        return _Resp(bad)

    with caplog.at_level(logging.WARNING, logger="app.reasoning.model_providers.openrouter"):
        with patch("app.reasoning.model_providers.openrouter.urllib.request.urlopen", _fake):
            with pytest.raises(ProviderProtocolError):
                provider.complete(_request(fmt="json"))
    msg = next(r.getMessage() for r in caplog.records if "FAIL" in r.getMessage())
    assert "class=invalid_json" in msg


def test_fail_log_never_leaks_secrets(caplog):
    err = urllib.error.HTTPError("https://openrouter.ai", 401, "Unauthorized", {}, None)
    msg = _run_raising(err, caplog)
    assert _API_KEY not in msg
    assert "INVESTIGATION-PACKAGE-SECRET-EVIDENCE" not in msg
