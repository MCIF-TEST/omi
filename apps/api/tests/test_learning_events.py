"""Founder-learning system (master-plan Phase 4).

Pins the contract of the smallest learning loop: five event kinds, each tied
to one of the five questions (value / return / share / trust / pay); a
whitelisted, never-breaks recorder; WTP capture shown only to returners and
asked once; and an admin read surface keyed literally by the five questions.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.analytics.event_log import EVENT_KINDS, record
from app.campaigns.service import CampaignService
from app.content.featured import seed_featured_campaigns
from app.core.config import get_settings
from app.detection.coordination._types import CoordinationCluster
from app.main import app
from app.storage.db import get_session, reset_db_for_tests
from app.storage.models import EventLog, Investigation, ScanLog, User


@pytest.fixture(autouse=True)
def _fresh_db():
    reset_db_for_tests()
    yield


def _events(kind: str | None = None) -> list[EventLog]:
    with get_session() as s:
        q = select(EventLog)
        if kind:
            q = q.where(EventLog.kind == kind)
        return s.execute(q).scalars().all()


def _cluster(method="fingerprint_cluster", members=("a", "b", "c"), score=0.9):
    return CoordinationCluster(method=method, members=list(members), score=score,
                               evidence=[f"{method} evidence"])


def _seed_campaign(key_context="vid1") -> str:
    with get_session() as s:
        camps = CampaignService(s).record_clusters(
            platform="x", context_id=key_context, clusters=[_cluster()],
            coordination_score=0.9)
        return camps[0].campaign_key


# ---------------------------------------------------------------------------
# Recorder — whitelist + never-breaks contract
# ---------------------------------------------------------------------------


def test_recorder_filters_payload_to_the_whitelist():
    with get_session() as s:
        record(s, "campaign_export", user_id=7, campaign_key="k", format="markdown",
               ip="1.2.3.4", user_agent="evil", anything="else")
    rows = _events("campaign_export")
    assert len(rows) == 1
    assert rows[0].payload_json == {"campaign_key": "k", "format": "markdown"}
    assert rows[0].user_id == 7


def test_recorder_drops_unknown_kind_and_never_raises():
    with get_session() as s:
        record(s, "page_view", user_id=1, path="/anything")  # rejected kind
    assert _events() == []
    # A broken session must not raise either — learning never breaks a request.
    record(None, "campaign_export", user_id=1, campaign_key="k")  # type: ignore[arg-type]


def test_recorder_caps_wtp_text_and_nulls_local_user():
    with get_session() as s:
        record(s, "wtp_answer", user_id=0, text="x" * 5000)  # 0 = local mode
    row = _events("wtp_answer")[0]
    assert len(row.payload_json["text"]) == 2000
    assert row.user_id is None


# ---------------------------------------------------------------------------
# Emits — Q1 (value surface + artifact) and Q3 (share + read)
# ---------------------------------------------------------------------------


def test_featured_view_logged_only_for_featured_campaigns():
    with get_session() as s:
        seed_featured_campaigns(s)
    own_key = _seed_campaign()
    with TestClient(app) as tc:
        tc.get("/v1/campaigns/feat_cn_xinjiang?ref=featured")
        tc.get(f"/v1/campaigns/{own_key}")          # own campaign: NOT logged
    rows = _events("featured_viewed")
    assert len(rows) == 1
    assert rows[0].payload_json == {"campaign_key": "feat_cn_xinjiang", "ref": "featured"}


def test_export_and_share_and_public_view_are_logged():
    key = _seed_campaign()
    with TestClient(app) as tc:
        tc.get(f"/v1/campaigns/{key}/export?format=json")
        token = tc.post(f"/v1/campaigns/{key}/share").json()["share_token"]
        tc.get(f"/rc/{token}")                       # anonymous read
    exp = _events("campaign_export")
    assert len(exp) == 1 and exp[0].payload_json["format"] == "json"
    assert len(_events("campaign_share_minted")) == 1
    views = _events("public_report_view")
    assert len(views) == 1
    assert views[0].user_id is None                  # anonymous by design
    assert views[0].payload_json == {"token": token, "report_kind": "campaign"}


def test_investigation_public_report_view_is_logged():
    with get_session() as s:
        s.add(User(email="u@x.com", password_hash="h"))
        s.flush()
        s.add(Investigation(
            user_id=1, slug="inv_test1234", label="t", input_url="u",
            kind="comprehensive", payload_json={}, share_token="rpt_testtoken123",
            is_public=1,
        ))
    with TestClient(app) as tc:
        assert tc.get("/r/rpt_testtoken123").status_code == 200
    views = _events("public_report_view")
    assert len(views) == 1
    assert views[0].payload_json["report_kind"] == "investigation"


# ---------------------------------------------------------------------------
# WTP (Q5) — returners only, once ever
# ---------------------------------------------------------------------------


@pytest.fixture
def authed(monkeypatch):
    monkeypatch.setenv("OMI_REQUIRE_AUTH", "true")
    monkeypatch.setenv("OMI_SESSION_SECRET", "x" * 64)
    monkeypatch.setenv("OMI_YOUTUBE_API_KEY", "test-key")
    monkeypatch.setenv("OMI_SUPER_ADMIN_EMAILS", "admin@x.com")
    get_settings.cache_clear()
    reset_db_for_tests("sqlite:///:memory:")
    from app.core.rate_limit import LOGIN_LIMITER, SIGNUP_LIMITER
    SIGNUP_LIMITER._windows.clear()
    LOGIN_LIMITER._windows.clear()
    yield
    reset_db_for_tests("sqlite:///:memory:")
    get_settings.cache_clear()


def _add_investigations(user_email: str, n: int) -> None:
    with get_session() as s:
        uid = s.execute(select(User.id).where(User.email == user_email)).scalar_one()
        for i in range(n):
            s.add(Investigation(
                user_id=uid, slug=f"inv_{user_email[:3]}{i}", label="t",
                input_url="u", kind="comprehensive", payload_json={},
            ))


def test_wtp_prompt_only_for_returners_and_only_once(authed):
    with TestClient(app) as tc:
        tc.post("/v1/auth/signup", json={"email": "u@x.com", "password": "12345678"})
        # New user: no prompt.
        assert tc.get("/v1/learning/prompt").json()["show_wtp"] is False
        # Returner (>=2 investigations): prompt shows.
        _add_investigations("u@x.com", 2)
        assert tc.get("/v1/learning/prompt").json()["show_wtp"] is True
        # Answer -> stored verbatim (capped), never asked again.
        r = tc.post("/v1/learning/wtp", json={"text": "  Would pay for PDF court-ready exports.  "})
        assert r.status_code == 200
        assert tc.get("/v1/learning/prompt").json()["show_wtp"] is False
        rows = _events("wtp_answer")
        assert len(rows) == 1
        assert rows[0].payload_json["text"] == "Would pay for PDF court-ready exports."
        assert rows[0].user_id is not None


def test_wtp_dismiss_is_permanent(authed):
    with TestClient(app) as tc:
        tc.post("/v1/auth/signup", json={"email": "d@x.com", "password": "12345678"})
        _add_investigations("d@x.com", 2)
        assert tc.get("/v1/learning/prompt").json()["show_wtp"] is True
        tc.post("/v1/learning/wtp/dismiss")
        assert tc.get("/v1/learning/prompt").json()["show_wtp"] is False


# ---------------------------------------------------------------------------
# Admin read surface — the five questions, literally
# ---------------------------------------------------------------------------


def test_learning_report_answers_the_five_questions(authed):
    with TestClient(app) as tc:
        tc.post("/v1/auth/signup", json={"email": "admin@x.com", "password": "12345678"})
        # Give the admin a value moment + a share + a read + a WTP answer.
        key = _seed_campaign()
        tc.get(f"/v1/campaigns/{key}/export")
        token = tc.post(f"/v1/campaigns/{key}/share").json()["share_token"]
        tc.get(f"/rc/{token}")
        _add_investigations("admin@x.com", 2)
        tc.post("/v1/learning/wtp", json={"text": "alerts on recurring campaigns"})

        report = tc.get("/v1/admin/learning").json()
        q1 = report["q1_did_users_experience_value"]
        assert q1["users_total"] == 1 and q1["activated_users"] == 1
        assert q1["activation_rate"] == 1.0
        q3 = report["q3_did_users_share"]
        assert q3["campaign_shares_minted"] == 1
        assert q3["public_report_views"] == 1
        assert q3["views_per_share"] == 1.0
        q4 = report["q4_did_users_trust_the_result"]
        assert q4["investigations_total"] == 2 and q4["verdict_concluded"] == 0
        q5 = report["q5_would_users_pay"]
        assert q5["wtp_answers"][0]["text"] == "alerts on recurring campaigns"
        assert "q2_did_users_come_back" in report


def test_learning_report_is_admin_only(authed):
    with TestClient(app) as tc:
        tc.post("/v1/auth/signup", json={"email": "pleb@x.com", "password": "12345678"})
        assert tc.get("/v1/admin/learning").status_code == 403
