"""Tests for the persistent investigation layer (Phase 5)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.storage.db import reset_db_for_tests


@pytest.fixture(autouse=True)
def _fresh_db():
    reset_db_for_tests()
    yield


def test_list_investigations_empty_for_new_user():
    with TestClient(app) as tc:
        # Local mode by default — endpoint returns empty list
        r = tc.get("/v1/investigations")
        assert r.status_code == 200
        assert r.json() == {"investigations": []}


def test_get_unknown_investigation_returns_404():
    with TestClient(app) as tc:
        r = tc.get("/v1/investigations/inv_doesnotexist")
        assert r.status_code == 404


def test_investigation_create_and_fetch_roundtrip():
    """Direct repository roundtrip — confirms the storage layer works."""
    from app.storage.db import get_session
    from app.storage.models import User
    from app.storage.repository import AccountRepository

    with get_session() as session:
        user = User(email="x@example.com", password_hash="x", credits_remaining=3)
        session.add(user)
        session.flush()
        repo = AccountRepository(session)
        inv = repo.create_investigation(
            user_id=user.id,
            slug="inv_test1234",
            label="Video abc",
            input_url="https://youtube.com/watch?v=abc",
            target_id="abc",
            kind="video",
            overall_probability=0.42,
            overall_tier="moderate",
            summary="Test summary",
            quota_used=12,
            payload_json={"foo": "bar"},
        )
        assert inv.slug == "inv_test1234"

        # Re-fetch
        got = repo.get_investigation(slug="inv_test1234", user_id=user.id)
        assert got is not None
        assert got.overall_probability == 0.42
        assert got.label == "Video abc"

        # List for that user
        rows = repo.list_user_investigations(user.id)
        assert len(rows) == 1
        assert rows[0].slug == "inv_test1234"

        # Update
        repo.update_investigation_payload(
            got,
            payload_json={"foo": "baz"},
            quota_used_delta=8,
            overall_probability=0.55,
            overall_tier="elevated",
            summary="Updated summary",
        )
        assert got.quota_used == 20
        assert got.batch_count == 2
        assert got.overall_probability == 0.55
        assert got.payload_json == {"foo": "baz"}


def test_merge_payloads_dedupes_commenters():
    """The continuation-batch merge function should never duplicate a commenter."""
    from app.routes.scan import _merge_payloads

    existing = {
        "overall_probability": 0.5,
        "video": {
            "commenters": [
                {"external_id": "A", "tier": "low"},
                {"external_id": "B", "tier": "moderate"},
            ],
            "commenter_count": 2,
        },
    }
    new = {
        "overall_probability": 0.6,
        "video": {
            "commenters": [
                {"external_id": "B", "tier": "elevated"},  # dup
                {"external_id": "C", "tier": "high"},
            ],
            "commenter_count": 2,
        },
    }
    merged = _merge_payloads(existing, new)
    ids = [c["external_id"] for c in merged["video"]["commenters"]]
    assert ids == ["A", "B", "C"]
    assert merged["video"]["commenter_count"] == 3
    # Top-level synthesis takes the new values
    assert merged["overall_probability"] == 0.6
