"""Feedback: any signed-in user submits; only admins read the searchable queue."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import app
from app.storage.db import reset_db_for_tests


@pytest.fixture(autouse=True)
def _fresh(monkeypatch):
    monkeypatch.setenv("OMI_REQUIRE_AUTH", "false")  # local mode: admin uid 0
    get_settings.cache_clear()
    reset_db_for_tests()
    yield
    get_settings.cache_clear()


def test_submit_then_admin_can_search():
    with TestClient(app) as tc:
        assert tc.post("/v1/feedback", json={"message": "mobile scanning is clunky", "category": "bug"}).status_code == 201
        tc.post("/v1/feedback", json={"message": "love the new investigate flow", "category": "praise"})
        allf = tc.get("/v1/feedback").json()
        assert allf["total"] == 2
        # keyword search
        hit = tc.get("/v1/feedback?q=mobile").json()
        assert hit["total"] == 1 and "mobile" in hit["feedback"][0]["message"]
        # unknown category is coerced, message preserved
        r = tc.post("/v1/feedback", json={"message": "x", "category": "weird"})
        assert r.status_code == 201


def test_empty_message_rejected():
    with TestClient(app) as tc:
        assert tc.post("/v1/feedback", json={"message": ""}).status_code == 422


def test_non_admin_cannot_list(monkeypatch):
    # Force auth on and stub a non-admin current user for the list endpoint.
    import app.routes.feedback as fb
    from app.core.auth import CurrentUser

    def _user():
        return CurrentUser(id=5, email="u@x.com", credits_remaining=1,
                           subscription_status=None, subscription_renews_at=None, is_admin=False)

    app.dependency_overrides[fb.require_user] = _user
    try:
        with TestClient(app) as tc:
            assert tc.get("/v1/feedback").status_code == 403
    finally:
        app.dependency_overrides.pop(fb.require_user, None)
