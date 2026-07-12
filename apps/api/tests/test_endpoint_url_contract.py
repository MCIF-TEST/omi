"""The HF endpoint request-contract: the messages API must target /v1/chat/completions.

Production certification found the live investigation fell back to the Floor because the transport
POSTed the OpenAI chat body to the BARE endpoint URL (the operator configured the base URL), while HF
TGI / vLLM serve the OpenAI-compatible route at ``/v1/chat/completions``. This proves the fix: the
messages API targets the chat route (appended idempotently), the raw generate API is unchanged, and an
error status is now captured for forensics.
"""
from __future__ import annotations

import json
import urllib.error

from unittest.mock import patch

from app.reasoning.model_providers.remote import ReasoningRequest, RemoteReasoningProvider

_BASE = "https://mr04i6z88ltad86s.us-east-1.aws.endpoints.huggingface.cloud"


def test_messages_api_targets_chat_completions_from_a_bare_url():
    p = RemoteReasoningProvider(endpoint_url=_BASE, api="messages")
    assert p._target_url() == _BASE + "/v1/chat/completions"


def test_messages_api_is_idempotent_when_url_already_has_the_path():
    p = RemoteReasoningProvider(endpoint_url=_BASE + "/v1/chat/completions", api="messages")
    assert p._target_url() == _BASE + "/v1/chat/completions"
    # trailing slash tolerated
    p2 = RemoteReasoningProvider(endpoint_url=_BASE + "/v1/chat/completions/", api="messages")
    assert p2._target_url() == _BASE + "/v1/chat/completions"


def test_generate_api_url_is_unchanged():
    p = RemoteReasoningProvider(endpoint_url=_BASE, api="generate")
    assert p._target_url() == _BASE


def test_actual_request_is_posted_to_chat_completions():
    """End-to-end through complete(): the real urllib request goes to /v1/chat/completions."""
    captured: dict = {}

    class _Resp:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self): return json.dumps(
            {"model": "mistralai/Mistral-7B-Instruct-v0.3",
             "choices": [{"message": {"content": "{\"ok\":1}"}}]}).encode()
        headers = {}
        status = 200
        def getcode(self): return 200

    def _fake(req, timeout=None):
        captured["url"] = req.full_url
        return _Resp()

    p = RemoteReasoningProvider(endpoint_url=_BASE, api="messages", token_env=("HF_TOKEN",))
    with patch.dict("os.environ", {"HF_TOKEN": "hf_fake"}), \
         patch("app.reasoning.model_providers.remote.urllib.request.urlopen", _fake):
        p.complete(ReasoningRequest(system="s", user="u"))
    assert captured["url"] == _BASE + "/v1/chat/completions"


def test_http_error_status_is_captured_for_forensics():
    """A 404 (wrong route) is now recorded in the capture sidecar so the trace shows WHY it fell back
    — previously response_status stayed null on any HTTP error."""
    cap: dict = {}

    def _raise_404(req, timeout=None):
        raise urllib.error.HTTPError(req.full_url, 404, "Not Found", {}, None)

    p = RemoteReasoningProvider(endpoint_url=_BASE, api="messages", token_env=("HF_TOKEN",),
                               max_retries=0, capture=cap)
    with patch.dict("os.environ", {"HF_TOKEN": "hf_fake"}), \
         patch("app.reasoning.model_providers.remote.urllib.request.urlopen", _raise_404):
        try:
            p.complete(ReasoningRequest(system="s", user="u"))
        except Exception:
            pass
    assert cap.get("response_status") == 404
