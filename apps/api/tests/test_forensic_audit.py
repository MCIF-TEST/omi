"""Forensic single-investigation audit — the Hugging Face endpoint is untrusted until proven.

Proves the capture instrumentation records, for ONE real investigation, all six required items:
(1) exact final prompt sent, (2) prompt version/hash from the AI package, (3) served model id,
(4) raw model response before the Governor, (5) Governor verdict + exact fallback reason,
(6) whether the report renders the model answer or the deterministic floor — across a TRUSTED
endpoint (valid Mistral answer), an UNTRUSTED endpoint (wrong model + non-JSON garbage -> floor),
and no endpoint (floor). The audit runs the REAL production path (assess_payload) with a sidecar,
so the evidence reflects real behavior, not a reimplementation.
"""
from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.reasoning import analyst
from app.reasoning.trace import audit_investigation
from app.storage.db import reset_db_for_tests

MISTRAL = "mistralai/Mistral-7B-Instruct-v0.3"
_PAYLOAD = {"overall_probability": 0.74, "overall_tier": "elevated", "confidence": 0.6,
            "contributions": [{"name": "temporal", "impact": 0.5, "direction": "raises"}],
            "video": {"clusters": [{"method": "co_engagement", "members": ["@a", "@b", "@c"]}]}}


class _Resp:
    def __init__(self, body: bytes):
        self._body = body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self):
        return self._body


def _settings(endpoint="https://ep.hf.cloud"):
    return SimpleNamespace(
        analyst_enabled=True, analyst_endpoint_url=endpoint, analyst_hf_repo="Andrewexiga/omi-analyst-v1",
        analyst_hf_revision="sha1", analyst_prompt_version=None, analyst_model_id=MISTRAL,
        analyst_timeout_seconds=30.0, analyst_max_retries=0, analyst_endpoint_api="messages",
        analyst_cost_per_1k_tokens_usd=0.0, memory_persistence_enabled=False, memory_database_url=None)


@pytest.fixture(autouse=True)
def _fresh(monkeypatch):
    monkeypatch.setenv("HF_TOKEN", "hf_fake")
    reset_db_for_tests("sqlite:///:memory:")
    yield


def _valid_analyst_json_for(payload) -> str:
    impl = analyst._impl()
    cfg = impl.load_analyst_config(repo_id="Andrewexiga/omi-analyst-v1", revision="sha1")
    bundle = analyst.build_bundle(payload, ref=analyst._ref("sub_audit"), platform="youtube", impl=impl)
    w = impl.DeterministicAnalystProvider().generate(bundle, cfg).response
    w.update({k: {"assessment": "reasoning present", "citations": []} for k in (  # Phase 1: 6 domains
        "comment_reasoning", "commenter_history_reasoning", "account_reasoning",
        "narrative_reasoning", "coordination_reasoning", "campaign_reasoning")})
    return json.dumps(w)


# --------------------------------------------------------------------------- #
# TRUSTED endpoint — valid Mistral answer, model verified, all six PROVEN
# --------------------------------------------------------------------------- #
def test_audit_trusted_endpoint_all_six_proven():
    reply = json.dumps({"model": MISTRAL,
                        "choices": [{"message": {"content": _valid_analyst_json_for(_PAYLOAD)}}]}).encode()
    with patch("app.reasoning.model_providers.remote.urllib.request.urlopen", return_value=_Resp(reply)):
        out = audit_investigation(_PAYLOAD, ref="sub_audit", platform="youtube", settings=_settings())

    assert out["status"] == "ok"
    it = out["items"]
    # 1 — exact final prompt sent (single-inference: assembled by the canonical comprehensive stage
    # builder over the COMPLETE InvestigationPackage)
    assert it["1_final_prompt_sent"]["status"] == "PROVEN"
    assert "COMPREHENSIVE INVESTIGATION TASK" in it["1_final_prompt_sent"]["system_prompt"]
    assert "INVESTIGATION EVIDENCE" in it["1_final_prompt_sent"]["user_message"]
    # 2 — prompt version/hash from the package
    assert it["2_prompt_version_hash"]["status"] == "PROVEN"
    assert it["2_prompt_version_hash"]["prompt_hash"].startswith("ph:")
    assert it["2_prompt_version_hash"]["ai_package"]["package_hash"].startswith("pkg:")
    # 3 — served model id, verified against expected
    assert it["3_served_model_id"]["status"].startswith("PROVEN")
    assert it["3_served_model_id"]["served_model"] == MISTRAL
    # 4 — raw model response before the Governor
    assert it["4_raw_model_response"]["status"] == "PROVEN"
    assert it["4_raw_model_response"]["raw_text_pre_governor"]
    # 5 — Governor permitted, no fallback
    assert it["5_governor"]["verdict"] == "permit"
    assert it["5_governor"]["fallback_occurred"] is False
    assert it["5_governor"]["fallback_reason"] is None
    # 6 — the report renders the MODEL answer
    assert it["6_report_renders"]["status"] == "MODEL"
    assert it["6_report_renders"]["model_backed"] is True
    assert out["endpoint_trust_verdict"].startswith("TRUSTED")


# --------------------------------------------------------------------------- #
# UNTRUSTED endpoint — wrong model + non-JSON garbage -> floor, but captured
# --------------------------------------------------------------------------- #
def test_audit_untrusted_endpoint_falls_back_but_captures_everything():
    reply = json.dumps({"model": "evil/wrong-model-13b",
                        "choices": [{"message": {"content": "I will not answer in JSON. Trust me."}}]}).encode()
    with patch("app.reasoning.model_providers.remote.urllib.request.urlopen", return_value=_Resp(reply)):
        out = audit_investigation(_PAYLOAD, ref="sub_audit", platform="youtube", settings=_settings())

    it = out["items"]
    # the request WAS sent (we still prove the prompt) ...
    assert it["1_final_prompt_sent"]["status"] == "PROVEN"
    # ... and we captured the untrusted RAW response verbatim (before any processing)
    assert "will not answer in JSON" in it["4_raw_model_response"]["raw_text_pre_governor"]
    # served model is the WRONG one -> disproven
    assert it["3_served_model_id"]["served_model"] == "evil/wrong-model-13b"
    assert it["3_served_model_id"]["status"].startswith("DISPROVEN")
    # fallback occurred because the output wasn't schema-valid JSON (pre-Governor)
    assert it["5_governor"]["fallback_occurred"] is True
    assert "not_schema_valid_json" in it["5_governor"]["fallback_reason"]
    # the report renders the DETERMINISTIC FLOOR, not the model
    assert it["6_report_renders"]["status"] == "DETERMINISTIC_FLOOR"
    assert it["6_report_renders"]["model_backed"] is False
    assert out["endpoint_trust_verdict"].startswith("NOT TRUSTED")


# --------------------------------------------------------------------------- #
# No endpoint — floor, item 1 disproven (no model call)
# --------------------------------------------------------------------------- #
def test_audit_no_endpoint_is_floor():
    out = audit_investigation(_PAYLOAD, ref="sub_audit", platform="youtube",
                              settings=_settings(endpoint=None))
    it = out["items"]
    assert it["1_final_prompt_sent"]["status"].startswith("DISPROVEN")
    assert it["4_raw_model_response"]["raw_text_pre_governor"] is None
    assert it["5_governor"]["fallback_reason"].startswith("no_model_call")
    assert it["6_report_renders"]["status"] == "DETERMINISTIC_FLOOR"
    assert out["endpoint_trust_verdict"].startswith("NOT TRUSTED")


def test_audit_endpoint_route_admin_only_and_shapes():
    from fastapi.testclient import TestClient
    from app.main import app
    from app.storage.db import get_session
    from app.storage.repository import AccountRepository
    with get_session() as s:
        AccountRepository(s).create_investigation(
            user_id=1, slug="inv_audit_1", label="a", input_url="https://youtube.com/watch?v=x",
            target_id="x", kind="comprehensive", overall_probability=0.74, overall_tier="elevated",
            summary="a", quota_used=0, payload_json=_PAYLOAD)
    with TestClient(app) as tc:  # local mode -> synthetic admin
        body = tc.post("/v1/investigations/inv_audit_1/analyst/audit").json()
    assert body["slug"] == "inv_audit_1"
    keys = set(body["audit"]["items"])
    assert {"1_final_prompt_sent", "2_prompt_version_hash", "3_served_model_id",
            "4_raw_model_response", "5_governor", "6_report_renders",
            "7_deterministic_fallback", "8_9_field_provenance", "10_identity"} <= keys
    # items 8/9 — field provenance is present and non-empty
    fp = body["audit"]["items"]["8_9_field_provenance"]
    assert fp["model_generated"] and fp["deterministic_echoed"]
