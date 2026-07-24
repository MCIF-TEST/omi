"""Integration tests for the Omi Analyst production wiring (OMI_ANALYST_PRODUCTION_WIRING_V1).

Covers: OFF by default, feature-flagged route (503), the enabled path running the REAL
completed implementation (ml/analyst/omi_analyst), async (background) + cached behavior,
SAVEPOINT-isolated persistence, and that nothing here touches detection/scoring/OmiScore.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.core import background
from app.main import app
from app.reasoning import analyst
from app.storage.db import get_session, reset_db_for_tests
from app.storage.models import Investigation, User

REQUIRED_ELEMENTS = ("evidence_for", "evidence_against", "confidence_band",
                     "confidence_rationale", "uncertainty", "what_would_change_this")


@pytest.fixture(autouse=True)
def _fresh():
    reset_db_for_tests("sqlite:///:memory:")
    yield


def _payload() -> dict:
    return {
        "overall_probability": 0.72,
        "overall_tier": "elevated",
        "confidence": 0.6,
        "summary": "Elevated suspicion across multiple signals.",
        "cross_links": [{"kind": "focus_in_cluster", "summary": "Focus in cluster"}],
        "video": {
            "commenters": [
                {"handle": "@bot1", "tier": "high", "overall_probability": 0.91,
                 "intent_label": "Engagement farming", "summary": "Spam"},
                {"handle": "@bot2", "tier": "elevated", "overall_probability": 0.7,
                 "intent_label": "Amplification", "summary": "Repetitive praise"},
            ],
            "clusters": [{"method": "co_engagement", "members": ["A", "B", "C"]}],
        },
    }


def _seed(slug: str = "inv_analyst") -> None:
    with get_session() as session:
        u = User(email="a@x.com", password_hash="x", credits_remaining=3)
        session.add(u); session.flush()
        session.add(Investigation(
            user_id=u.id, slug=slug, label="Video xyz",
            input_url="https://youtube.com/watch?v=xyz", kind="video",
            overall_probability=0.72, overall_tier="elevated",
            summary="Elevated suspicion.", payload_json=_payload(),
        ))


def _enable(monkeypatch):
    monkeypatch.setattr(analyst, "analyst_enabled", lambda settings=None: True)


# --- OFF by default --------------------------------------------------------- #
def test_disabled_by_default():
    assert analyst.analyst_enabled() is False
    assert analyst.available() is False  # never imports omi_analyst when off
    assert analyst.assess_payload(_payload(), ref="sub_x") is None


def test_route_503_when_disabled():
    _seed()
    with TestClient(app) as tc:
        r = tc.post("/v1/investigations/inv_analyst/analyst")
        assert r.status_code == 503
        assert "disabled" in r.json()["detail"].lower()


# --- enabled path runs the REAL completed implementation -------------------- #
def test_assess_payload_runs_real_impl_and_is_schema_valid(monkeypatch):
    _enable(monkeypatch)
    assert analyst.available() is True  # omi_analyst imported lazily
    out = analyst.assess_payload(_payload(), ref="sub_x", platform="youtube")
    assert out is not None
    assert out["subject"]["grain"] == "comment_section"
    assert out["analyst_version"] == "v1"
    for el in REQUIRED_ELEMENTS:
        assert el in out and out[el] not in (None, ""), el
    # co_engagement is discriminative -> corroboration carries it
    assert "co_engagement" in out["corroboration"]["discriminative_methods"]
    # the flagged commenters were folded in as supporting evidence
    assert any("assessment" in e["signal"] for e in out["evidence_for"])


def test_route_async_202_then_cached_200(monkeypatch):
    _enable(monkeypatch)
    _seed()
    captured: list = []
    monkeypatch.setattr(background, "submit_slow", lambda fn, *a, **k: captured.append((fn, a)))

    with TestClient(app) as tc:
        r1 = tc.post("/v1/investigations/inv_analyst/analyst")
        assert r1.status_code == 202, r1.text
        b1 = r1.json()
        assert b1["status"] == "generating" and b1["cached"] is False and b1["assessment"] is None
        assert captured and captured[0][0] is analyst.generate_and_persist

        # Run the background job synchronously (its own session), then poll -> 200.
        analyst.generate_and_persist(*captured[0][1])
        r2 = tc.post("/v1/investigations/inv_analyst/analyst")
        assert r2.status_code == 200, r2.text
        b2 = r2.json()
        assert b2["status"] == "ready" and b2["cached"] is True
        assert b2["assessment"]["subject"]["grain"] == "comment_section"
        for el in REQUIRED_ELEMENTS:
            assert el in b2["assessment"]


def test_generate_and_persist_caches_savepoint_isolated(monkeypatch):
    _enable(monkeypatch)
    _seed()
    entry = analyst.generate_and_persist("inv_analyst", None, False)
    assert entry and entry["assessment"]
    # cached inside payload_json under CACHE_KEY, survives a reload
    with get_session() as session:
        inv = session.query(Investigation).filter_by(slug="inv_analyst").one()
        cached = analyst.cached_assessment(inv)
        assert cached is not None
        assert cached["assessment"]["verdict"] in (
            "confirmed_bot_ring", "likely_inauthentic", "mixed",
            "likely_authentic", "inconclusive",
        )
        # original engine fields are untouched (no scoring mutation)
        assert inv.payload_json["overall_probability"] == 0.72


def test_route_404_unknown_slug_when_enabled(monkeypatch):
    _enable(monkeypatch)
    monkeypatch.setattr(background, "submit_slow", lambda fn, *a, **k: None)
    with TestClient(app) as tc:
        r = tc.post("/v1/investigations/inv_nope/analyst")
        assert r.status_code == 404


def test_refresh_triggers_regeneration(monkeypatch):
    _enable(monkeypatch)
    _seed()
    analyst.generate_and_persist("inv_analyst", None, False)
    captured: list = []
    monkeypatch.setattr(background, "submit_slow", lambda fn, *a, **k: captured.append((fn, a)))
    with TestClient(app) as tc:
        # refresh=true bypasses the cache -> 202 (regenerate), not a cached 200
        r = tc.post("/v1/investigations/inv_analyst/analyst?refresh=true")
        assert r.status_code == 202
        assert captured  # a regeneration job was submitted


def test_floored_cache_auto_regenerates_once_when_a_live_model_is_ready(monkeypatch):
    """A cached FLOOR self-heals: when a live model call is possible, viewing a floored investigation
    auto-triggers ONE fresh generation (a real OpenRouter call) instead of serving the stale Floor forever
    — and it does so at most once, so a persistent floor can't hammer the gateway on every poll."""
    _enable(monkeypatch)
    _seed(slug="inv_floor")
    # Persist a FLOORED assessment (model_backed=False) directly into the cache.
    monkeypatch.setattr(analyst, "runtime_status", lambda settings=None: {"ready_for_live_model": True})
    floored = {"assessment": {"verdict": "inconclusive",
                              "investigation_trace": {"model_backed": False, "provider": "openrouter"}},
               "provider": "openrouter->fallback:deterministic-analyst-v1",
               "generated_at": "2026-07-19T00:00:00Z"}
    with get_session() as session:
        inv = session.query(Investigation).filter_by(slug="inv_floor").one()
        inv.payload_json = {**(inv.payload_json or {}), analyst.CACHE_KEY: floored}
        session.add(inv)
    analyst._floor_autorefreshed.discard("inv_floor")            # fresh process state for the assertion
    captured: list = []
    monkeypatch.setattr(background, "submit_slow", lambda fn, *a, **k: captured.append((fn, a)))
    with TestClient(app) as tc:
        # first view of the floored cache → auto-regenerate (202), a fresh model call is submitted
        r1 = tc.post("/v1/investigations/inv_floor/analyst")
        assert r1.status_code == 202, r1.text
        assert captured and captured[0][0] is analyst.generate_and_persist
        assert captured[0][1][2] is True                        # refresh=True was forced
        # second view → already retried this slug → serve the honest Floor (200), no second call
        r2 = tc.post("/v1/investigations/inv_floor/analyst")
        assert r2.status_code == 200, r2.text
        assert r2.json()["assessment"]["investigation_trace"]["model_backed"] is False
        assert len(captured) == 1                               # NOT re-submitted


def test_openrouter_probe_reports_a_real_call(monkeypatch):
    """The admin probe makes ONE real minimal OpenRouter call with the configured key/preset and reports
    connectivity — the definitive 'does it reach OpenRouter?' check, independent of the pipeline/cache."""
    import json as _json

    from app.core.config import get_settings
    monkeypatch.setenv("OMI_REQUIRE_AUTH", "true")
    monkeypatch.setenv("OMI_SESSION_SECRET", "x" * 64)
    monkeypatch.setenv("OMI_SUPER_ADMIN_EMAILS", "admin@x.com")
    monkeypatch.setenv("OMI_ANALYST_ENABLED", "true")
    monkeypatch.setenv("OMI_ANALYST_PROVIDER", "openrouter")
    monkeypatch.setenv("OMI_OPENROUTER_PRESET", "omi-master-v1")
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-v1-SECRET-probe-do-not-leak")
    get_settings.cache_clear()

    class _Resp:
        status = 200
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self):
            return _json.dumps({"id": "gen-probe-1", "model": "openai/gpt-5-mini",
                                "choices": [{"message": {"role": "assistant", "content": "pong"}}],
                                "usage": {"total_tokens": 12, "cost": 0.00001}}).encode()

    captured: dict = {}
    def _fake(req, timeout=None):
        captured["url"] = req.full_url
        captured["auth"] = dict(req.headers).get("Authorization")
        return _Resp()

    with TestClient(app) as tc:
        tc.post("/v1/auth/signup", json={"email": "admin@x.com", "password": "12345678"})
        with patch("app.reasoning.model_providers.openrouter.urllib.request.urlopen", _fake):
            r = tc.post("/v1/investigations/analyst/probe")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["reached_openrouter"] is True
        assert body["active_provider"] == "openrouter"
        assert body["http_status"] == 200
        assert body["served_model"] == "openai/gpt-5-mini"
        assert body["generation_id"] == "gen-probe-1"
        assert "SECRET" not in _json.dumps(body)               # the key is NEVER echoed back
    # the call actually went to OpenRouter with the configured key in the Authorization header
    assert captured["url"] == "https://openrouter.ai/api/v1/chat/completions"
    assert captured["auth"] == "Bearer sk-or-v1-SECRET-probe-do-not-leak"
    get_settings.cache_clear()


def test_openrouter_probe_is_admin_only(monkeypatch):
    from app.core.config import get_settings
    monkeypatch.setenv("OMI_REQUIRE_AUTH", "true")
    monkeypatch.setenv("OMI_SESSION_SECRET", "x" * 64)
    monkeypatch.setenv("OMI_SUPER_ADMIN_EMAILS", "admin@x.com")
    get_settings.cache_clear()
    with TestClient(app) as tc:
        tc.post("/v1/auth/signup", json={"email": "pleb@x.com", "password": "12345678"})
        assert tc.post("/v1/investigations/analyst/probe").status_code == 403
    get_settings.cache_clear()


def test_floored_cache_is_served_as_is_when_no_live_model(monkeypatch):
    """Without a live model configured, floorng is expected and permanent — the floored cache is served
    as 200 (no auto-refresh churn)."""
    _enable(monkeypatch)
    _seed(slug="inv_floor2")
    monkeypatch.setattr(analyst, "runtime_status", lambda settings=None: {"ready_for_live_model": False})
    floored = {"assessment": {"verdict": "inconclusive",
                              "investigation_trace": {"model_backed": False}},
               "provider": "deterministic-analyst-v1", "generated_at": "2026-07-19T00:00:00Z"}
    with get_session() as session:
        inv = session.query(Investigation).filter_by(slug="inv_floor2").one()
        inv.payload_json = {**(inv.payload_json or {}), analyst.CACHE_KEY: floored}
        session.add(inv)
    captured: list = []
    monkeypatch.setattr(background, "submit_slow", lambda fn, *a, **k: captured.append((fn, a)))
    with TestClient(app) as tc:
        r = tc.post("/v1/investigations/inv_floor2/analyst")
        assert r.status_code == 200
        assert not captured                                     # no regeneration attempted


# --- guardrail: disabled assess never raises / never touches scoring -------- #
def test_assess_payload_never_raises_on_garbage(monkeypatch):
    _enable(monkeypatch)
    # Malformed payload must degrade to None or a valid assessment, never raise.
    out = analyst.assess_payload({"nonsense": True}, ref="sub_x")
    assert out is None or out["subject"]["grain"] == "comment_section"


# --- inference-pipeline fallback (Sprint 001 runtime foundation) ------------ #
def test_qwen_endpoint_unreachable_falls_back_to_deterministic(monkeypatch):
    """When an HF inference endpoint is configured but unreachable (and no
    HF_TOKEN), the Qwen provider must degrade to the deterministic Floor —
    never raise, always schema-valid, echo preserved. This is the runtime
    guarantee the Sprint-001 path depends on."""
    _enable(monkeypatch)
    monkeypatch.delenv("HF_TOKEN", raising=False)
    monkeypatch.delenv("HUGGINGFACE_HUB_TOKEN", raising=False)
    settings = SimpleNamespace(
        analyst_hf_repo="Andrewexiga/omi-analyst-v1",
        analyst_hf_revision=None,
        analyst_endpoint_url="http://127.0.0.1:9/unreachable",
    )
    out = analyst.assess_payload(
        _payload(), ref="sub_x", platform="youtube", settings=settings,
    )
    assert out is not None  # graceful fallback, never None on good evidence
    assert out["subject"]["grain"] == "comment_section"
    for el in REQUIRED_ELEMENTS:
        assert el in out and out[el] not in (None, ""), el
    # echo discipline survives the fallback: the engine's number is not recomputed
    assert out["suspicion_probability"] == 0.72
