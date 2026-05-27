"""Tests for Phase 9 — caching, rate limit, metrics, middleware."""

from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from app.core.cache import TTLCache, get_cache
from app.core.metrics import Counter, Histogram, Registry, get_registry
from app.core.rate_limit import SlidingWindowLimiter
from app.main import app
from app.storage.db import get_session, reset_db_for_tests
from app.storage.models import User


@pytest.fixture(autouse=True)
def _fresh():
    reset_db_for_tests()
    get_cache().clear()
    yield


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------


def test_ttl_cache_hit_then_expiry():
    c = TTLCache(max_entries=4)
    c.set("k", "v", ttl_seconds=0.05)
    assert c.get("k") == "v"
    time.sleep(0.08)
    assert c.get("k") is None


def test_ttl_cache_evicts_lru():
    c = TTLCache(max_entries=3)
    c.set("a", 1, ttl_seconds=60)
    c.set("b", 2, ttl_seconds=60)
    c.set("c", 3, ttl_seconds=60)
    # Touch 'a' so 'b' is now LRU
    _ = c.get("a")
    c.set("d", 4, ttl_seconds=60)
    assert c.get("b") is None
    assert c.get("a") == 1


# ---------------------------------------------------------------------------
# Rate limiter
# ---------------------------------------------------------------------------


def test_sliding_window_rejects_after_limit():
    rl = SlidingWindowLimiter(max_hits=3, per_seconds=60)
    assert rl.hit("ip-A")
    assert rl.hit("ip-A")
    assert rl.hit("ip-A")
    assert not rl.hit("ip-A")
    # Different key is independent
    assert rl.hit("ip-B")


def test_login_rate_limit_returns_429():
    """After 10 wrong-password attempts the limiter trips."""
    # Create a user so the first 10 hits are 401, then 11th is 429
    with get_session() as session:
        from app.core.auth import hash_password
        session.add(User(email="rl@x.com", password_hash=hash_password("password123"),
                         credits_remaining=3))
    # Reset limiter explicitly so prior tests don't bleed state
    from app.core.rate_limit import LOGIN_LIMITER
    LOGIN_LIMITER._windows.clear()  # type: ignore[attr-defined]
    with TestClient(app) as tc:
        for _ in range(10):
            tc.post("/v1/auth/login", json={"email": "rl@x.com", "password": "wrong"})
        r = tc.post("/v1/auth/login", json={"email": "rl@x.com", "password": "wrong"})
        assert r.status_code == 429


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------


def test_counter_increment():
    c = Counter()
    c.inc()
    c.inc(5)
    assert c.value == 6


def test_histogram_percentiles():
    h = Histogram(max_samples=100)
    for i in range(100):
        h.observe(float(i))
    snap = h.snapshot()
    assert snap["count"] == 100
    assert 45 <= snap["p50"] <= 55
    assert snap["p95"] >= 90
    assert snap["max"] == 99.0


def test_metrics_endpoint_requires_admin():
    with TestClient(app) as tc:
        # Local-mode user is admin=True → expect 200
        r = tc.get("/v1/metrics")
        assert r.status_code == 200, r.text
        body = r.json()
        assert "totals" in body
        assert "process" in body
        assert "cache" in body


# ---------------------------------------------------------------------------
# Middleware — security headers + request id
# ---------------------------------------------------------------------------


def test_security_headers_present():
    with TestClient(app) as tc:
        r = tc.get("/health")
        assert r.status_code == 200
        assert r.headers.get("x-content-type-options") == "nosniff"
        assert r.headers.get("x-frame-options") == "DENY"
        # Request id auto-attached
        assert r.headers.get("x-request-id")


def test_request_id_round_trips():
    with TestClient(app) as tc:
        r = tc.get("/health", headers={"x-request-id": "test-123"})
        assert r.headers.get("x-request-id") == "test-123"


# ---------------------------------------------------------------------------
# Cache wiring on /v1/status
# ---------------------------------------------------------------------------


def test_status_endpoint_cached():
    """Second consecutive call within TTL should hit the cache."""
    with TestClient(app) as tc:
        r1 = tc.get("/v1/status")
        r2 = tc.get("/v1/status")
        assert r1.status_code == 200
        assert r2.status_code == 200
        # Cache is small + bounded; size should be at least 1 after first call
        cstats = get_cache().stats()
        assert cstats["size"] >= 1
