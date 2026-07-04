"""Temporary forensic HF logging — OMI_FORENSIC_CAPTURE=true logs the exact request + raw response.

Proves: OFF by default (no logs, byte-identical behavior); ON -> a HF REQUEST banner (endpoint,
model, prompt hash, package hash, request body) before sending and a HF RESPONSE banner (status,
headers, RAW body verbatim — unparsed) after receiving; secrets are redacted; and the returned
result is identical whether the flag is on or off (instrumentation only, never alters the response).

Critically, the banners are emitted straight to **stdout** (not through the logging level stack), so
they survive whatever ``OMI_LOG_LEVEL`` production runs at — the regression that made them invisible
in the deployed Render logs. ``test_banners_survive_warning_root_logger`` is the proof of that fix.
"""
from __future__ import annotations

import json
import logging

import pytest
from unittest.mock import patch

from app.reasoning.model_providers import ReasoningRequest
from app.reasoning.model_providers.remote import RemoteReasoningProvider, forensic_on

_RAW = json.dumps({"model": "mistralai/Mistral-7B-Instruct-v0.3",
                   "choices": [{"message": {"content": '{"ok": 1}'}}]}).encode()


class _Resp:
    def __init__(self, body=_RAW, status=200, headers=None):
        self._body = body
        self.status = status
        self.headers = headers or {"Content-Type": "application/json", "Authorization": "hf_secret_xyz"}

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self):
        return self._body

    def getcode(self):
        return self.status


@pytest.fixture(autouse=True)
def _tok(monkeypatch):
    monkeypatch.setenv("HF_TOKEN", "hf_fake_token")
    monkeypatch.delenv("OMI_FORENSIC_CAPTURE", raising=False)
    yield


def _complete():
    p = RemoteReasoningProvider(endpoint_url="http://ep/v1/chat/completions", api="messages",
                                model="mistralai/Mistral-7B-Instruct-v0.3", max_retries=0,
                                prompt_hash="ph:abc123", package_hash="pkg:def456")
    with patch("app.reasoning.model_providers.remote.urllib.request.urlopen", return_value=_Resp()):
        return p.complete(ReasoningRequest(system="SYS_PROMPT", user="USR_MSG", response_format="json"))


def test_forensic_off_by_default(capsys):
    assert forensic_on() is False
    out = _complete()
    captured = capsys.readouterr().out
    assert "HF REQUEST" not in captured and "HF RESPONSE" not in captured
    assert out.structured == {"ok": 1}                       # behaves exactly as today


def test_forensic_on_logs_request_then_raw_response(monkeypatch, capsys):
    monkeypatch.setenv("OMI_FORENSIC_CAPTURE", "true")
    assert forensic_on() is True
    out = _complete()
    t = capsys.readouterr().out
    # request banner + fields
    assert "HF REQUEST" in t
    assert "http://ep/v1/chat/completions" in t
    assert "mistralai/Mistral-7B-Instruct-v0.3" in t
    assert "ph:abc123" in t and "pkg:def456" in t
    assert "SYS_PROMPT" in t and "USR_MSG" in t               # request body (the prompt) logged
    # response banner + RAW body verbatim (unparsed) + status + redacted secret header
    assert "HF RESPONSE" in t
    assert "HTTP status : 200" in t
    assert '"choices"' in t and '"content": "{\\"ok\\": 1}"' in t  # raw JSON as returned
    assert "<redacted>" in t                                  # Authorization header scrubbed
    assert "hf_secret_xyz" not in t                           # the secret value never leaks
    # request banner precedes response banner (order preserved)
    assert t.index("HF REQUEST") < t.index("HF RESPONSE")
    # the response is UNCHANGED by logging
    assert out.structured == {"ok": 1}


def test_banners_survive_warning_root_logger(monkeypatch, capsys):
    """The regression proof: with the root logger at WARNING (production default), the old
    ``_forensic_log.info(...)`` banners were dropped. The stdout emit must still appear."""
    monkeypatch.setenv("OMI_FORENSIC_CAPTURE", "true")
    root = logging.getLogger()
    prior = root.level
    root.setLevel(logging.WARNING)
    try:
        out = _complete()
    finally:
        root.setLevel(prior)
    t = capsys.readouterr().out
    assert "HF REQUEST" in t and "HF RESPONSE" in t           # visible despite WARNING-level root
    assert out.structured == {"ok": 1}


def test_request_body_redacts_token_shapes(monkeypatch, capsys):
    monkeypatch.setenv("OMI_FORENSIC_CAPTURE", "true")
    # a prompt that accidentally contains a token-shaped string must be scrubbed in the log
    p = RemoteReasoningProvider(endpoint_url="http://ep", api="messages", model="M", max_retries=0)
    with patch("app.reasoning.model_providers.remote.urllib.request.urlopen", return_value=_Resp()):
        p.complete(ReasoningRequest(system="leak hf_ABCDEF123456 here", user="U", response_format="json"))
    t = capsys.readouterr().out
    assert "hf_ABCDEF123456" not in t and "<redacted>" in t


def test_result_identical_on_vs_off(monkeypatch):
    monkeypatch.delenv("OMI_FORENSIC_CAPTURE", raising=False)
    off = _complete().structured
    monkeypatch.setenv("OMI_FORENSIC_CAPTURE", "true")
    on = _complete().structured
    assert off == on == {"ok": 1}
