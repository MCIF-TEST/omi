"""Production Integration Verification — prove each seam of the live analyst path, with evidence.

This sprint's mandate: assume the integration is broken until every stage is proven. Two concrete
defects were found and fixed here, and are regression-guarded below:

1.  ``endpoint_health`` probed the endpoint with the *default* ``generate`` wire contract regardless
    of ``OMI_ANALYST_ENDPOINT_API``. Against the recommended ``messages`` (chat) deployment for
    Mistral that sends a ``/generate``-shaped body to a chat route → rejection → a **healthy
    endpoint mis-reported as ``unreachable``**. The health probe now honors the configured API.

2.  Nothing verified the model the endpoint is **actually serving** — only the *configured* id was
    echoed. ``RemoteReasoningProvider.probe_served_model`` now reports the served model (chat
    ``model`` field, or TGI ``/info``), and ``endpoint_health`` / ``endpoint_smoke_test`` surface
    ``served_model`` + ``model_matches`` so an operator can prove the endpoint is
    ``mistralai/Mistral-7B-Instruct-v0.3`` — not merely up, and not some other model.

Plus a contract guard that the backend ``AnalystResponse`` still carries every field the website's
``AnalystPanel`` reads (the Website → Render API arrow this sprint audited end-to-end).
"""
from __future__ import annotations

import json
import urllib.error
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.reasoning import analyst
from app.reasoning.model_providers.remote import RemoteReasoningProvider
from app.reasoning.trace import (
    _models_match,
    endpoint_health,
    endpoint_smoke_test,
    system_health,
)
from app.storage.db import reset_db_for_tests

MISTRAL = "mistralai/Mistral-7B-Instruct-v0.3"


class _Resp:
    """Reusable urlopen stand-in (context manager + .read()); safe for multiple calls."""

    def __init__(self, body: bytes):
        self._body = body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self):
        return self._body


@pytest.fixture(autouse=True)
def _fresh(monkeypatch):
    monkeypatch.setenv("HF_TOKEN", "hf_fake_for_tests")
    reset_db_for_tests("sqlite:///:memory:")
    yield


# --------------------------------------------------------------------------- #
# Tolerant model-id matching
# --------------------------------------------------------------------------- #
def test_models_match_exact_barename_and_unknown():
    assert _models_match(MISTRAL, MISTRAL) is True
    assert _models_match("Mistral-7B-Instruct-v0.3", MISTRAL) is True   # bare name vs repo id
    assert _models_match("mistralai/mistral-7b-instruct-v0.3", MISTRAL) is True  # case-insensitive
    assert _models_match("meta-llama/Llama-3-8B-Instruct", MISTRAL) is False
    assert _models_match(None, MISTRAL) is None                         # unknown → not a claim
    assert _models_match(MISTRAL, None) is None


# --------------------------------------------------------------------------- #
# probe_served_model — the served-model evidence, both serving APIs
# --------------------------------------------------------------------------- #
def test_probe_served_model_messages_reads_the_model_field():
    def _fake(req, timeout=None):
        body = req.data.decode()
        assert '"messages"' in body                                    # chat contract, not generate
        return _Resp(json.dumps({"model": MISTRAL,
                                 "choices": [{"message": {"content": "hi"}}]}).encode())

    p = RemoteReasoningProvider(endpoint_url="https://ep/v1/chat/completions", api="messages", model=MISTRAL)
    with patch("app.reasoning.model_providers.remote.urllib.request.urlopen", _fake):
        out = p.probe_served_model()
    assert out["served_model"] == MISTRAL
    assert out["source"] == "chat_completion_model_field" and out["reachable"] is True


def test_probe_served_model_generate_uses_tgi_info():
    def _fake(req, timeout=None):
        assert req.get_method() == "GET"                               # /info is a GET, no body
        assert req.full_url.endswith("/info")                          # derived from the root
        return _Resp(json.dumps({"model_id": MISTRAL}).encode())

    p = RemoteReasoningProvider(endpoint_url="https://ep.hf.cloud/generate", api="generate", model=MISTRAL)
    with patch("app.reasoning.model_providers.remote.urllib.request.urlopen", _fake):
        out = p.probe_served_model()
    assert out["served_model"] == MISTRAL and out["source"] == "tgi_info_endpoint"


def test_probe_served_model_not_configured(monkeypatch):
    monkeypatch.delenv("HF_TOKEN", raising=False)
    monkeypatch.delenv("HUGGINGFACE_HUB_TOKEN", raising=False)
    out = RemoteReasoningProvider(endpoint_url="", api="messages").probe_served_model()
    assert out["served_model"] is None and out["source"] == "not_configured"


def test_probe_served_model_reports_failure_without_raising():
    def _boom(req, timeout=None):
        raise urllib.error.URLError("connection refused")

    p = RemoteReasoningProvider(endpoint_url="https://ep", api="messages", model=MISTRAL, max_retries=0)
    with patch("app.reasoning.model_providers.remote.urllib.request.urlopen", _boom):
        out = p.probe_served_model()
    assert out["served_model"] is None and out["source"] == "probe_failed" and out["reachable"] is False


# --------------------------------------------------------------------------- #
# THE BUG FIX — endpoint_health honors the messages contract (was generate-only)
# --------------------------------------------------------------------------- #
def test_endpoint_health_probes_a_messages_endpoint_with_the_chat_contract():
    """A chat-only endpoint rejects a raw generate body. The OLD health probe always sent generate
    → this endpoint would have been mis-reported ``unreachable``. It must now probe with ``messages``
    and come back ``reachable`` with the served model verified."""
    captured: list[str] = []

    def _fake(req, timeout=None):
        body = req.data.decode() if req.data is not None else ""
        captured.append(body)
        if req.data is not None and '"messages"' not in body:
            raise urllib.error.HTTPError(req.full_url, 422, "Unprocessable Entity", {}, None)
        return _Resp(json.dumps({"model": MISTRAL,
                                 "choices": [{"message": {"content": "ok"}}]}).encode())

    settings = SimpleNamespace(analyst_endpoint_url="https://ep.hf.cloud", analyst_model_id=MISTRAL,
                               analyst_endpoint_api="messages", analyst_hf_revision="sha1",
                               analyst_timeout_seconds=5.0)
    with patch("app.reasoning.model_providers.remote.urllib.request.urlopen", _fake):
        h = endpoint_health(settings)

    assert h["status"] == "reachable"                                  # broken under the old probe
    assert captured and all('"messages"' in b for b in captured)       # every call used the chat contract
    assert h["endpoint_api"] == "messages"
    assert h["served_model"] == MISTRAL and h["model_matches"] is True
    assert h["expected_model"] == MISTRAL


def test_endpoint_health_flags_a_wrong_model():
    def _fake(req, timeout=None):
        return _Resp(json.dumps({"model": "meta-llama/Llama-3-8B-Instruct",
                                 "choices": [{"message": {"content": "ok"}}]}).encode())

    settings = SimpleNamespace(analyst_endpoint_url="https://ep", analyst_model_id=MISTRAL,
                               analyst_endpoint_api="messages", analyst_hf_revision="s",
                               analyst_timeout_seconds=5.0)
    with patch("app.reasoning.model_providers.remote.urllib.request.urlopen", _fake):
        h = endpoint_health(settings)
    assert h["status"] == "reachable"
    assert h["served_model"] == "meta-llama/Llama-3-8B-Instruct"
    assert h["model_matches"] is False and "model_mismatch_detail" in h


def test_endpoint_health_not_configured_still_reports_identity_fields():
    h = endpoint_health(SimpleNamespace(analyst_endpoint_url=None, analyst_model_id=MISTRAL,
                                        analyst_endpoint_api="messages"))
    assert h["status"] == "not_configured" and h["reachable"] is None
    assert h["expected_model"] == MISTRAL and h["served_model"] is None
    assert h["model_matches"] is None                                  # unknown, never a false claim


# --------------------------------------------------------------------------- #
# Smoke test — the operator green light now also proves the model identity
# --------------------------------------------------------------------------- #
def test_smoke_test_surfaces_served_model_and_match():
    impl = analyst._impl()
    assert impl is not None
    payload = {"overall_probability": 0.74, "overall_tier": "elevated", "confidence": 0.6,
               "contributions": [{"name": "temporal", "impact": 0.5, "direction": "raises"}],
               "video": {"clusters": [{"method": "co_engagement", "members": ["@a", "@b", "@c"]}]}}
    config = impl.load_analyst_config(repo_id="Andrewexiga/omi-analyst-v1", revision="sha123")
    bundle = analyst.build_bundle(payload, ref="smoke_subject", platform="youtube", impl=impl)
    _w = impl.DeterministicAnalystProvider().generate(bundle, config).response
    _w.update({k: {"assessment": "reasoning present", "citations": []} for k in (  # Phase 1: 6 domains
        "comment_reasoning", "commenter_history_reasoning", "account_reasoning",
        "narrative_reasoning", "coordination_reasoning", "campaign_reasoning")})
    valid = json.dumps(_w)
    # chat completion carries BOTH the analyst JSON and the served-model field.
    reply = json.dumps({"model": MISTRAL, "choices": [{"message": {"content": valid}}]}).encode()

    settings = SimpleNamespace(
        analyst_enabled=True, analyst_endpoint_url="https://ep.hf.cloud", analyst_model_id=MISTRAL,
        analyst_hf_repo="Andrewexiga/omi-analyst-v1", analyst_hf_revision="sha123",
        analyst_timeout_seconds=30.0, analyst_max_retries=0, analyst_prompt_version=None,
        analyst_endpoint_api="messages", memory_persistence_enabled=False, memory_database_url=None)

    with patch("app.reasoning.model_providers.remote.urllib.request.urlopen",
               return_value=_Resp(reply)):
        out = endpoint_smoke_test(payload, ref="smoke_subject", settings=settings)

    assert out["status"] == "qwen_backed" and out["model_backed"] is True   # genuinely model-backed
    assert out["active_model"] == MISTRAL                                    # configured runtime model
    assert out["served_model"] == MISTRAL and out["model_matches"] is True   # ACTUALLY serving Mistral
    assert out["governor_verdict"] == "permit" and out["number_echoed"] is True


# --------------------------------------------------------------------------- #
# Website → Render API contract — the backend response the AnalystPanel reads
# --------------------------------------------------------------------------- #
def test_analyst_response_contract_matches_the_website_panel():
    """apps/web AnalystPanel drives its ready/generating/disabled states off these exact fields
    (apps/web/lib/api.ts ``AnalystResponse``). Guard the backend contract against silent drift."""
    from app.schemas import AnalystResponse

    fields = set(AnalystResponse.model_fields)
    assert {"slug", "enabled", "status", "cached", "assessment", "provider", "generated_at"} <= fields


def test_system_health_endpoint_block_inherits_served_model_fields():
    """system_health embeds endpoint_health, so /integrity now carries the served-model evidence."""
    h = system_health(SimpleNamespace(analyst_enabled=True, analyst_endpoint_url=None,
                                      analyst_model_id=MISTRAL, analyst_endpoint_api="messages"))
    assert h["active_model"] == MISTRAL
    assert "served_model" in h["endpoint"] and "model_matches" in h["endpoint"]
