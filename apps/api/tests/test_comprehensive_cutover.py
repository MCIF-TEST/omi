"""Cutover regression — a valid comprehensive Mistral response reaches model_backed=true.

Certification proved the schema pre-filter rejected the six comprehensive reasoning sidecars as
"unexpected top-level field" BEFORE they were stripped, discarding every contract-following comprehensive
response to the deterministic Floor. This proves the fixed adjudication ordering (strip registered
sidecars -> validate the CORE wrapper -> Governor -> validate the six sections separately) through the
production-equivalent path (``assess_payload`` -> ``_assess_core``): a valid core wrapper + six valid
sidecars is accepted (model-authored, not the Floor), unknown fields still fail, malformed cores still
fail, malformed sections are surfaced, and the endpoint is hit exactly once.
"""
from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.reasoning import analyst
from app.storage.db import reset_db_for_tests

MISTRAL = "mistralai/Mistral-7B-Instruct-v0.3"

_PAYLOAD = {
    "overall_probability": 0.74, "overall_tier": "elevated", "confidence": 0.6,
    "inputs_provided": ["video"], "video_id": "v1",
    "contributions": [{"name": "temporal", "impact": 0.5, "direction": "raises"}],
    "video": {"video_id": "v1", "coordination_score": 0.7, "coordination_tier": "elevated",
              "clusters": [{"method": "co_engagement", "members": ["a", "b", "c"], "score": 0.7}],
              "thread_scan": {"overall_probability": 0.5, "tier": "moderate"},
              "commenters": [{"external_id": "a", "handle": "@a", "overall_probability": 0.8, "tier": "high",
                              "recent_activity": [{"text": "great!!", "created_at": "2026-01-01T00:00:00Z"}],
                              "signals": [{"name": "temporal", "probability": 0.8},
                                          {"name": "community", "probability": 0.18}]}]},
}

_SENTINEL_HEADLINE = "MODEL-AUTHORED-HEADLINE-ζ"
_SENTINEL_ASSESSMENT = "MODEL-AUTHORED-ASSESSMENT-ζ"


class _Resp:
    def __init__(self, body: bytes): self._body = body
    def __enter__(self): return self
    def __exit__(self, *a): return False
    def read(self): return self._body


@pytest.fixture(autouse=True)
def _fresh(monkeypatch):
    monkeypatch.setenv("HF_TOKEN", "hf_fake")
    reset_db_for_tests("sqlite:///:memory:")
    yield


def _settings():
    return SimpleNamespace(
        analyst_enabled=True, analyst_endpoint_url="https://ep.hf.cloud", analyst_hf_repo="Andrewexiga/omi-analyst-v1",
        analyst_hf_revision="sha1", analyst_prompt_version=None, analyst_model_id=MISTRAL,
        analyst_timeout_seconds=30.0, analyst_max_retries=0, analyst_endpoint_api="messages",
        analyst_cost_per_1k_tokens_usd=0.0, memory_persistence_enabled=False, memory_database_url=None)


def _valid_core_wrapper() -> dict:
    """A schema-valid analyst wrapper (the Floor's own response), tagged with model-authored sentinels
    so we can prove the MODEL's wrapper survived (not the deterministic Floor's)."""
    impl = analyst._impl()
    cfg = impl.load_analyst_config(repo_id="Andrewexiga/omi-analyst-v1", revision="sha1")
    bundle = analyst.build_bundle(_PAYLOAD, ref=analyst._ref("sub_cut"), platform="youtube", impl=impl)
    wrapper = impl.DeterministicAnalystProvider().generate(bundle, cfg).response
    wrapper["headline"] = _SENTINEL_HEADLINE
    wrapper["assessment"] = _SENTINEL_ASSESSMENT
    return wrapper


def _six_sidecars() -> dict:
    return {
        "comment_reasoning": {"assessment": "near-duplicate praise", "citations": ["A1"]},
        "commenter_history_reasoning": {"assessment": "thin history", "citations": []},
        "account_reasoning": {"assessment": "temporal vs community disagree", "citations": ["A1"]},
        "narrative_reasoning": {"assessment": "none", "citations": []},
        "coordination_reasoning": {"assessment": "one cluster", "citations": ["C1"]},
        "campaign_reasoning": {"assessment": "no gated campaign", "citations": []},
    }


def _run(model_obj: dict):
    """Drive the production-equivalent path with a mocked transport; return (governed, endpoint_calls)."""
    calls = {"n": 0}

    def _fake(req, timeout=None):
        calls["n"] += 1
        return _Resp(json.dumps({"model": MISTRAL,
                                 "choices": [{"message": {"content": json.dumps(model_obj)}}]}).encode())

    with patch("app.reasoning.model_providers.remote.urllib.request.urlopen", _fake):
        out = analyst.assess_payload(_PAYLOAD, ref="sub_cut", platform="youtube", settings=_settings())
    return out, calls["n"]


# --------------------------------------------------------------------------- #
def test_valid_comprehensive_response_is_model_backed_and_survives():
    """(1) model_backed=true, (2) Governor permit, (3) comprehensive validation succeeds, (4) the
    model-authored wrapper survives, (5) the six model-authored sections survive, (6) Floor NOT
    substituted, (10) exactly one endpoint request."""
    model_obj = {**_valid_core_wrapper(), **_six_sidecars()}
    out, calls = _run(model_obj)
    assert out is not None
    gov = out["governance"]
    prov = str(gov["provider"])
    # (1)+(6) model-backed, Floor NOT substituted
    assert "fallback" not in prov and "deterministic" not in prov, f"expected model-backed, got {prov}"
    assert out["investigation_trace"]["model_backed"] is True
    assert out["investigation_trace"]["fallback_reason"] is None
    # (2) Governor permit
    assert gov["verdict"] == "permit"
    # (4) the MODEL's wrapper survived (sentinels), not the Floor's synthesized prose
    assert out["headline"] == _SENTINEL_HEADLINE
    assert out["assessment"] == _SENTINEL_ASSESSMENT
    # (5) all six model-authored reasoning sections survive
    sections = out["comprehensive_sections"]
    assert set(sections) == {"comment_reasoning", "commenter_history_reasoning", "account_reasoning",
                             "narrative_reasoning", "coordination_reasoning", "campaign_reasoning"}
    assert sections["coordination_reasoning"]["assessment"] == "one cluster"
    # (3) comprehensive validation ran + succeeded
    cval = out["comprehensive_validation"]
    assert cval["structurally_valid"] is True and cval["unresolved_total"] == 0
    # (10) exactly one endpoint request
    assert calls == 1
    assert out["investigation_trace"]["inference_count"] == 1


def test_unknown_top_level_field_is_still_rejected_to_floor():
    """(7) An unknown top-level field (NOT a registered sidecar) must still fail core schema validation
    → the model candidate is discarded → deterministic Floor. Unknown fields are never silently
    accepted."""
    model_obj = {**_valid_core_wrapper(), **_six_sidecars(),
                 "fabricated_reasoning_section": {"assessment": "smuggled", "citations": []}}
    out, calls = _run(model_obj)
    prov = str(out["governance"]["provider"])
    assert "fallback" in prov or "deterministic" in prov, "unknown top-level field must reject to Floor"
    assert out["investigation_trace"]["model_backed"] is False
    # the Floor's wrapper is served — the model sentinels do NOT survive
    assert out["headline"] != _SENTINEL_HEADLINE
    assert calls == 1  # still exactly one endpoint request


def test_malformed_core_wrapper_still_fails_to_floor():
    """(8) A malformed core wrapper (missing required analyst fields) still fails schema validation →
    Floor, even though the six sidecars are well-formed."""
    broken_core = {"verdict": "monitor"}  # missing evidence_for/against/uncertainty/etc.
    model_obj = {**broken_core, **_six_sidecars()}
    out, calls = _run(model_obj)
    prov = str(out["governance"]["provider"])
    assert "fallback" in prov or "deterministic" in prov
    assert out["investigation_trace"]["model_backed"] is False
    assert calls == 1


def test_accepted_response_persists_and_reads_back_through_the_api_contract():
    """CUTOVER-2 — the accepted model-backed comprehensive assessment is persisted at
    ``payload_json['analyst_assessment_v1']`` (the EXISTING persistence path) and reads back through the
    existing analyst API contract with the model wrapper + all six sections intact. No second
    persistence path, no new table."""
    from app.storage.db import get_session
    from app.storage.repository import AccountRepository

    with get_session() as s:
        AccountRepository(s).create_investigation(
            user_id=1, slug="inv_cut_persist", label="c", input_url="https://youtube.com/watch?v=v1",
            target_id="v1", kind="comprehensive", overall_probability=0.74, overall_tier="elevated",
            summary="c", quota_used=0, payload_json=_PAYLOAD)

    model_obj = {**_valid_core_wrapper(), **_six_sidecars()}
    calls = {"n": 0}

    def _fake(req, timeout=None):
        calls["n"] += 1
        return _Resp(json.dumps({"model": MISTRAL,
                                 "choices": [{"message": {"content": json.dumps(model_obj)}}]}).encode())

    with patch("app.reasoning.model_providers.remote.urllib.request.urlopen", _fake), \
         patch("app.reasoning.analyst.get_settings", return_value=_settings()):
        analyst.generate_and_persist("inv_cut_persist", user_id=1, refresh=False)

    assert calls["n"] == 1, "exactly one endpoint request for the whole investigation"
    # persisted at the EXISTING cache key, model-backed, wrapper + six sections intact
    with get_session() as s:
        inv = AccountRepository(s).get_investigation(slug="inv_cut_persist", user_id=1)
        assert "analyst_assessment_v1" in (inv.payload_json or {})
        entry = analyst.cached_assessment(inv)
    a = entry["assessment"]
    assert "fallback" not in str((a["governance"])["provider"])          # model-backed persisted
    assert a["investigation_trace"]["model_backed"] is True
    assert a["headline"] == _SENTINEL_HEADLINE                            # model wrapper persisted
    assert set(a["comprehensive_sections"]) == {                         # six sections persisted
        "comment_reasoning", "commenter_history_reasoning", "account_reasoning",
        "narrative_reasoning", "coordination_reasoning", "campaign_reasoning"}

    # read back through the EXISTING analyst API contract: reasoning.py returns
    # AnalystResponse(assessment=entry["assessment"]) for a cached entry, and AnalystResponse.assessment
    # is a passthrough dict — so the model wrapper + six sections survive the API boundary intact.
    from app.schemas import AnalystResponse
    resp = AnalystResponse(slug="inv_cut_persist", enabled=True, status="ready", cached=True,
                           assessment=a, provider=entry.get("provider"))
    assert resp.assessment["comprehensive_sections"]["coordination_reasoning"]["assessment"] == "one cluster"
    assert resp.assessment["headline"] == _SENTINEL_HEADLINE


def test_endpoint_failure_self_reports_in_the_trace():
    """When the endpoint returns no HTTP response (connection/timeout), the persisted trace now
    records the exact failure (``endpoint_error`` + real latency) so a production DB read diagnoses
    itself — timeout vs connection vs DNS/TLS — without needing the Render log. Fallback behaviour is
    unchanged (model_backed=false, response_status stays null on a connection-level failure)."""
    import urllib.error

    def _boom(req, timeout=None):
        raise urllib.error.URLError("[Errno 111] Connection refused")

    with patch("app.reasoning.model_providers.remote.urllib.request.urlopen", _boom):
        out = analyst.assess_payload(_PAYLOAD, ref="sub_boom", platform="youtube", settings=_settings())
    tr = out["investigation_trace"]
    assert tr["model_backed"] is False
    assert tr["endpoint_called"] is True
    assert tr["response_status"] is None                     # no HTTP response — not an HTTP error
    # the transport wraps the network error in ProviderError; the exact class + message survive
    assert tr["endpoint_error"] and "ProviderError" in tr["endpoint_error"]
    assert "Connection refused" in tr["endpoint_error"]


def test_repeated_generation_does_not_cause_multiple_inferences():
    """FOURTH — the browser cannot cause multiple Mistral inferences for one investigation by
    refreshing / reopening the panel: the durable on-row cache short-circuits every subsequent
    ``generate_and_persist`` (refresh=false) with NO model call. Two generations → ONE endpoint
    request. (The six domain panels are client-side views over this one persisted assessment.)"""
    from app.storage.db import get_session
    from app.storage.repository import AccountRepository

    with get_session() as s:
        AccountRepository(s).create_investigation(
            user_id=1, slug="inv_once", label="c", input_url="https://youtube.com/watch?v=v1",
            target_id="v1", kind="comprehensive", overall_probability=0.74, overall_tier="elevated",
            summary="c", quota_used=0, payload_json=_PAYLOAD)

    model_obj = {**_valid_core_wrapper(), **_six_sidecars()}
    calls = {"n": 0}

    def _fake(req, timeout=None):
        calls["n"] += 1
        return _Resp(json.dumps({"model": MISTRAL,
                                 "choices": [{"message": {"content": json.dumps(model_obj)}}]}).encode())

    with patch("app.reasoning.model_providers.remote.urllib.request.urlopen", _fake), \
         patch("app.reasoning.analyst.get_settings", return_value=_settings()):
        analyst.generate_and_persist("inv_once", user_id=1, refresh=False)   # first: one model call
        analyst.generate_and_persist("inv_once", user_id=1, refresh=False)   # reopen: cache hit, no call
        analyst.generate_and_persist("inv_once", user_id=1, refresh=False)   # refresh page: cache hit

    assert calls["n"] == 1, f"expected exactly ONE endpoint request across reopens, got {calls['n']}"


def test_malformed_comprehensive_section_is_surfaced_by_comprehensive_validation():
    """(9) A malformed comprehensive section (missing 'assessment') is surfaced by comprehensive
    validation as structurally invalid — while the core wrapper can still be model-backed."""
    sidecars = _six_sidecars()
    sidecars["account_reasoning"] = {"citations": ["A1"]}  # missing 'assessment' string
    model_obj = {**_valid_core_wrapper(), **sidecars}
    out, calls = _run(model_obj)
    # core wrapper still model-backed + permit
    assert "fallback" not in str(out["governance"]["provider"])
    # comprehensive validation flags the malformed section
    cval = out["comprehensive_validation"]
    assert cval["structurally_valid"] is False
    assert cval["sections"]["account_reasoning"]["shape_ok"] is False
    assert calls == 1
