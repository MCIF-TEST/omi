"""ML scorer observability — the /v1/intelligence/ml-status admin endpoint.

The learned scorer ships dormant. This endpoint makes that state legible so
an operator can deploy a model and confirm it took. Tests cover the default
(disabled) reason, the admin guard, and the structured shape.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import app
from app.ml.features import FEATURE_SCHEMA_VERSION
from app.ml.scorer import get_scorer
from app.storage.db import reset_db_for_tests


@pytest.fixture
def admin_client(monkeypatch):
    monkeypatch.setenv("OMI_REQUIRE_AUTH", "true")
    monkeypatch.setenv("OMI_SESSION_SECRET", "x" * 64)
    monkeypatch.setenv("OMI_SUPER_ADMIN_EMAILS", "admin@x.com")
    get_settings.cache_clear()
    reset_db_for_tests("sqlite:///:memory:")
    from app.core.rate_limit import SIGNUP_LIMITER, LOGIN_LIMITER
    SIGNUP_LIMITER._windows.clear()
    LOGIN_LIMITER._windows.clear()
    with TestClient(app) as tc:
        tc.post("/v1/auth/signup", json={"email": "admin@x.com", "password": "password123"})
        yield tc
    reset_db_for_tests("sqlite:///:memory:")
    get_settings.cache_clear()


def test_ml_status_default_disabled(admin_client):
    r = admin_client.get("/v1/intelligence/ml-status")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["active"] is False
    assert body["enabled_flag"] is False
    assert body["expected_feature_schema"] == FEATURE_SCHEMA_VERSION
    assert "OMI_USE_ML_SCORER" in body["reason"]


def test_ml_status_reports_missing_artifact(admin_client, monkeypatch):
    # Flag on but no model path configured → reason names the missing env var.
    monkeypatch.setenv("OMI_USE_ML_SCORER", "true")
    get_settings.cache_clear()
    # Reset the singleton's load state so it re-evaluates under the new settings.
    s = get_scorer()
    s._loaded = None
    s._load_attempted = False
    try:
        r = admin_client.get("/v1/intelligence/ml-status")
        body = r.json()
        assert body["enabled_flag"] is True
        assert body["active"] is False
        assert "OMI_ML_MODEL_PATH" in body["reason"]
    finally:
        get_settings.cache_clear()


def test_ml_status_requires_admin(monkeypatch):
    monkeypatch.setenv("OMI_REQUIRE_AUTH", "true")
    monkeypatch.setenv("OMI_SESSION_SECRET", "x" * 64)
    get_settings.cache_clear()
    reset_db_for_tests("sqlite:///:memory:")
    from app.core.rate_limit import SIGNUP_LIMITER, LOGIN_LIMITER
    SIGNUP_LIMITER._windows.clear()
    LOGIN_LIMITER._windows.clear()
    with TestClient(app) as tc:
        tc.post("/v1/auth/signup", json={"email": "plain@x.com", "password": "password123"})
        r = tc.get("/v1/intelligence/ml-status")
        assert r.status_code == 403
    reset_db_for_tests("sqlite:///:memory:")
    get_settings.cache_clear()
