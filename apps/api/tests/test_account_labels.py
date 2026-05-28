"""Ground-truth labeling end-to-end + the YouTube-suspension auto-labeler.

The /v1/labels surface is admin-only; tests promote the signed-up user to
admin to exercise the CRUD + calibration endpoints.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import app
from app.routes.scan import set_client_factory_for_tests
from app.storage.db import get_session, reset_db_for_tests
from app.storage.models import Account, AccountLabel, Scan, User


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def admin_client(monkeypatch):
    """A TestClient with auth on, an admin user signed in, and a clean DB."""
    monkeypatch.setenv("OMI_REQUIRE_AUTH", "true")
    monkeypatch.setenv("OMI_SESSION_SECRET", "x" * 64)
    monkeypatch.setenv("OMI_YOUTUBE_API_KEY", "test-key")
    monkeypatch.setenv("OMI_SUPER_ADMIN_EMAILS", "admin@x.com")
    get_settings.cache_clear()
    reset_db_for_tests("sqlite:///:memory:")
    from app.core.rate_limit import SIGNUP_LIMITER, LOGIN_LIMITER
    SIGNUP_LIMITER._windows.clear()
    LOGIN_LIMITER._windows.clear()
    with TestClient(app) as tc:
        tc.post("/v1/auth/signup", json={"email": "admin@x.com", "password": "12345678"})
        yield tc
    set_client_factory_for_tests(None)
    reset_db_for_tests("sqlite:///:memory:")
    get_settings.cache_clear()


def _seed_account_with_scan(
    *, platform="youtube", external_id="UCseeded123", handle="seeded",
    tier="elevated", probability=0.65,
) -> int:
    """Plant an Account + a Scan row so labels have something to attach to."""
    with get_session() as session:
        acc = Account(
            platform=platform, external_id=external_id, handle=handle,
            display_name="Seeded Test Channel",
        )
        session.add(acc)
        session.flush()
        session.add(Scan(
            account_id=acc.id,
            scanned_at=datetime.now(timezone.utc),
            overall_probability=probability,
            confidence=0.7,
            tier=tier,
            summary="test scan",
            signals_json=[{"name": "temporal", "probability": 0.6, "confidence": 0.5,
                           "evidence": [], "sub_signals": {}}],
        ))
        return acc.id


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------


def test_create_label_succeeds_for_admin(admin_client):
    account_id = _seed_account_with_scan()
    r = admin_client.post("/v1/labels", json={
        "account_id": account_id,
        "label": "bot",
        "expected_tier": "high",
        "confidence": "high",
        "rationale": "Posts every 15 minutes, 24/7, identical templates.",
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["label"] == "bot"
    assert body["expected_tier"] == "high"
    assert body["source"] == "manual"
    assert body["user_email"] == "admin@x.com"


def test_create_label_rejects_non_admin(monkeypatch):
    monkeypatch.setenv("OMI_REQUIRE_AUTH", "true")
    monkeypatch.setenv("OMI_SESSION_SECRET", "x" * 64)
    monkeypatch.setenv("OMI_YOUTUBE_API_KEY", "test-key")
    get_settings.cache_clear()
    reset_db_for_tests("sqlite:///:memory:")
    from app.core.rate_limit import SIGNUP_LIMITER, LOGIN_LIMITER
    SIGNUP_LIMITER._windows.clear()
    LOGIN_LIMITER._windows.clear()
    with TestClient(app) as tc:
        tc.post("/v1/auth/signup", json={"email": "regular@x.com", "password": "12345678"})
        account_id = _seed_account_with_scan()
        r = tc.post("/v1/labels", json={
            "account_id": account_id,
            "label": "bot",
            "expected_tier": "high",
        })
    assert r.status_code == 403
    assert "admin-only" in r.json()["detail"]
    get_settings.cache_clear()
    reset_db_for_tests("sqlite:///:memory:")


def test_create_label_rejects_unknown_kind(admin_client):
    account_id = _seed_account_with_scan()
    r = admin_client.post("/v1/labels", json={
        "account_id": account_id,
        "label": "definitely_not_a_real_label",
        "expected_tier": "high",
    })
    assert r.status_code == 400
    assert "label must be one of" in r.json()["detail"]


def test_create_label_rejects_bad_tier(admin_client):
    account_id = _seed_account_with_scan()
    r = admin_client.post("/v1/labels", json={
        "account_id": account_id,
        "label": "bot",
        "expected_tier": "catastrophic",  # not a real tier
    })
    assert r.status_code == 400


def test_create_label_rejects_bad_confidence(admin_client):
    account_id = _seed_account_with_scan()
    r = admin_client.post("/v1/labels", json={
        "account_id": account_id,
        "label": "bot",
        "expected_tier": "high",
        "confidence": "definitely",
    })
    assert r.status_code == 400


def test_create_label_by_platform_external_id(admin_client):
    """The script-facing path: refer to an account by (platform, external_id)
    instead of the DB id."""
    _seed_account_with_scan(external_id="UCalt", handle="alt")
    r = admin_client.post("/v1/labels", json={
        "platform": "youtube",
        "external_id": "UCalt",
        "label": "human",
        "expected_tier": "low",
    })
    assert r.status_code == 200
    assert r.json()["external_id"] == "UCalt"


def test_create_label_404_when_account_doesnt_exist(admin_client):
    r = admin_client.post("/v1/labels", json={
        "platform": "youtube",
        "external_id": "UCnotreal",
        "label": "bot",
        "expected_tier": "high",
    })
    assert r.status_code == 404


def test_label_is_idempotent_per_user(admin_client):
    """Re-posting with the same account_id updates rather than duplicating."""
    account_id = _seed_account_with_scan()
    admin_client.post("/v1/labels", json={
        "account_id": account_id, "label": "bot", "expected_tier": "high",
    })
    admin_client.post("/v1/labels", json={
        "account_id": account_id, "label": "human", "expected_tier": "low",
        "rationale": "On second look this is a real person.",
    })

    with get_session() as session:
        rows = session.query(AccountLabel).filter(
            AccountLabel.account_id == account_id,
        ).all()

    assert len(rows) == 1  # not 2
    assert rows[0].label == "human"
    assert "second look" in (rows[0].rationale or "")


def test_delete_label(admin_client):
    account_id = _seed_account_with_scan()
    create = admin_client.post("/v1/labels", json={
        "account_id": account_id, "label": "bot", "expected_tier": "high",
    }).json()
    r = admin_client.delete(f"/v1/labels/{create['id']}")
    assert r.status_code == 204
    with get_session() as session:
        assert session.query(AccountLabel).count() == 0


def test_list_labels_aggregates_by_label_and_source(admin_client):
    a1 = _seed_account_with_scan(external_id="UC1", handle="a")
    a2 = _seed_account_with_scan(external_id="UC2", handle="b")
    a3 = _seed_account_with_scan(external_id="UC3", handle="c")
    admin_client.post("/v1/labels", json={"account_id": a1, "label": "bot", "expected_tier": "high"})
    admin_client.post("/v1/labels", json={"account_id": a2, "label": "bot", "expected_tier": "high"})
    admin_client.post("/v1/labels", json={"account_id": a3, "label": "human", "expected_tier": "low"})

    r = admin_client.get("/v1/labels").json()
    assert r["total"] == 3
    assert r["by_label"]["bot"] == 2
    assert r["by_label"]["human"] == 1
    assert r["by_source"]["manual"] == 3


def test_list_labels_filter_by_label(admin_client):
    a1 = _seed_account_with_scan(external_id="UC1", handle="a")
    a2 = _seed_account_with_scan(external_id="UC2", handle="b")
    admin_client.post("/v1/labels", json={"account_id": a1, "label": "bot", "expected_tier": "high"})
    admin_client.post("/v1/labels", json={"account_id": a2, "label": "human", "expected_tier": "low"})

    r = admin_client.get("/v1/labels?label=bot").json()
    assert len(r["labels"]) == 1
    assert r["labels"][0]["label"] == "bot"


# ---------------------------------------------------------------------------
# Calibration export + evaluate
# ---------------------------------------------------------------------------


def test_calibration_export_empty_when_no_labels(admin_client):
    r = admin_client.get("/v1/labels/calibration").json()
    assert r["n_cases"] == 0
    assert r["cases"] == []


def test_calibration_export_includes_labeled_accounts(admin_client):
    a1 = _seed_account_with_scan(external_id="UC1", handle="a")
    a2 = _seed_account_with_scan(external_id="UC2", handle="b")
    admin_client.post("/v1/labels", json={
        "account_id": a1, "label": "bot", "expected_tier": "high",
        "confidence": "high",
    })
    admin_client.post("/v1/labels", json={
        "account_id": a2, "label": "human", "expected_tier": "low",
        "confidence": "medium",
    })

    r = admin_client.get("/v1/labels/calibration").json()
    assert r["n_cases"] == 2
    labels_in_export = {c["label"] for c in r["cases"]}
    assert labels_in_export == {"bot", "human"}


def test_calibration_export_filter_min_confidence_high(admin_client):
    a1 = _seed_account_with_scan(external_id="UC1", handle="a")
    a2 = _seed_account_with_scan(external_id="UC2", handle="b")
    admin_client.post("/v1/labels", json={
        "account_id": a1, "label": "bot", "expected_tier": "high",
        "confidence": "high",
    })
    admin_client.post("/v1/labels", json={
        "account_id": a2, "label": "human", "expected_tier": "low",
        "confidence": "medium",
    })

    r = admin_client.get("/v1/labels/calibration?min_confidence=high").json()
    assert r["n_cases"] == 1
    assert r["cases"][0]["label"] == "bot"


def test_calibration_evaluate_returns_metrics_when_labels_agree(admin_client):
    """A 'bot' labeled high should agree with a scan that returned high."""
    a1 = _seed_account_with_scan(
        external_id="UC1", handle="a", tier="high", probability=0.88,
    )
    admin_client.post("/v1/labels", json={
        "account_id": a1, "label": "bot", "expected_tier": "high",
    })
    r = admin_client.get("/v1/labels/calibration/evaluate").json()
    assert r["n_cases"] == 1
    assert r["tier_accuracy"] == 1.0
    assert r["per_tier"]["high"]["precision"] == 1.0
    assert r["per_tier"]["high"]["recall"] == 1.0


def test_calibration_evaluate_reports_disagreement(admin_client):
    """Engine predicted low but operator says it was bot/high → disagreement."""
    a1 = _seed_account_with_scan(
        external_id="UC1", handle="a", tier="low", probability=0.10,
    )
    admin_client.post("/v1/labels", json={
        "account_id": a1, "label": "bot", "expected_tier": "high",
    })
    r = admin_client.get("/v1/labels/calibration/evaluate").json()
    assert r["tier_accuracy"] == 0.0
    assert r["brier_score"] > 0.5  # huge gap
    # high tier was missed entirely
    assert r["per_tier"]["high"]["recall"] == 0.0


def test_calibration_evaluate_empty_message(admin_client):
    r = admin_client.get("/v1/labels/calibration/evaluate").json()
    assert r["n_cases"] == 0
    assert "Label a few" in r["message"]


# ---------------------------------------------------------------------------
# YouTube-suspension auto-labeler
# ---------------------------------------------------------------------------


class _FakeResp:
    def __init__(self, status: int):
        self.status = status


class _FakeHttpError(Exception):
    def __init__(self, status: int, body: dict):
        super().__init__("FakeHttpError")
        self.resp = _FakeResp(status)
        self.content = json.dumps(body).encode("utf-8")


class _SuspendedChannels:
    """Every channels.list call raises channelSuspended."""

    def list(self, **_params):
        class _Bad:
            def execute(self):
                raise _FakeHttpError(403, {
                    "error": {"code": 403, "message": "Channel suspended",
                              "errors": [{"reason": "channelSuspended",
                                          "message": "Channel suspended"}]}
                })
        return _Bad()


class _SuspendedClient:
    def commentThreads(self):
        class _Inner:
            def list(self, **_params):
                class _Bad:
                    def execute(self):
                        return {"items": []}
                return _Bad()
        return _Inner()

    def channels(self):
        return _SuspendedChannels()


def test_youtube_suspension_creates_autolabel_for_known_account(admin_client):
    """When a rescan hits channelSuspended on an account we already know,
    auto-create a 'suspended' label with source=youtube_suspension."""
    suspended_id = "UCsuspended123XXXXXXXXX1"
    _seed_account_with_scan(external_id=suspended_id, handle="will-be-suspended")
    set_client_factory_for_tests(lambda: _SuspendedClient())

    r = admin_client.post(
        "/v1/scan/youtube/account",
        json={"account_url_or_handle": suspended_id},
    )
    # Suspension surfaces as 404 to the user with friendly copy.
    assert r.status_code == 404
    assert "suspended" in r.json()["detail"].lower() or "closed" in r.json()["detail"].lower()

    # And the auto-label landed.
    with get_session() as session:
        labels = session.query(AccountLabel).filter(
            AccountLabel.source == "youtube_suspension"
        ).all()
    assert len(labels) == 1
    assert labels[0].label == "suspended"
    assert labels[0].expected_tier == "high"
    assert labels[0].confidence == "high"
    assert labels[0].user_id is None  # YouTube is the labeler


def test_youtube_suspension_skips_when_account_unknown(admin_client):
    """If the suspended channel was never scanned by us, there's nothing to
    label (and the auto-labeler must not crash trying)."""
    set_client_factory_for_tests(lambda: _SuspendedClient())
    r = admin_client.post(
        "/v1/scan/youtube/account",
        json={"account_url_or_handle": "UCneverscanned999XX9XXXX"},
    )
    assert r.status_code == 404

    with get_session() as session:
        labels = session.query(AccountLabel).count()
    assert labels == 0


def test_youtube_suspension_is_idempotent(admin_client):
    """Two suspensions on the same account must not create two labels."""
    suspended_id = "UCsuspended123XXXXXXXXX1"
    _seed_account_with_scan(external_id=suspended_id, handle="x")
    set_client_factory_for_tests(lambda: _SuspendedClient())

    admin_client.post("/v1/scan/youtube/account",
                      json={"account_url_or_handle": suspended_id})
    admin_client.post("/v1/scan/youtube/account",
                      json={"account_url_or_handle": suspended_id})

    with get_session() as session:
        rows = session.query(AccountLabel).filter(
            AccountLabel.source == "youtube_suspension",
        ).all()
    assert len(rows) == 1
