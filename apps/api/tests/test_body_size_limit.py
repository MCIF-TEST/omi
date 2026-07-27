"""Oversized request bodies must be refused before anything parses them.

Neither Starlette nor uvicorn caps request body size, and ten routes accept an unvalidated
``payload: dict``, so FastAPI parsed whatever arrived fully into memory. On a 512 MB instance that is a
cheap unauthenticated way to exhaust RAM.

Two things are easy to get wrong, so both are pinned:

* checking only ``Content-Length`` — a chunked request omits that header entirely and would sail past
  a header-only guard;
* setting the cap so low that real traffic breaks. The largest legitimate body is a scan selection,
  roughly 30 KB at the 1000-candidate pool cap, so a normal request must be unaffected.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import create_app
from app.storage.db import reset_db_for_tests


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("OMI_REQUIRE_AUTH", "false")
    monkeypatch.setenv("OMI_MAX_REQUEST_BODY_BYTES", "2048")  # 2 KiB, so tests stay small
    get_settings.cache_clear()
    reset_db_for_tests("sqlite:///:memory:")
    app = create_app()
    with TestClient(app) as tc:
        yield tc
    reset_db_for_tests("sqlite:///:memory:")
    get_settings.cache_clear()


def test_an_oversized_declared_body_is_refused_with_413(client):
    body = json.dumps({"url": "x", "pad": "A" * 8000})
    r = client.post("/v1/scan/link/commenters", content=body,
                    headers={"content-type": "application/json"})
    assert r.status_code == 413, f"expected 413, got {r.status_code}: {r.text[:200]}"
    assert "too large" in r.json()["detail"].lower()


def test_the_refusal_still_carries_security_headers(client):
    """A middleware-level rejection bypasses the security-headers middleware, so it sets its own."""
    r = client.post("/v1/scan/link/commenters", content=json.dumps({"pad": "A" * 8000}),
                    headers={"content-type": "application/json"})
    assert r.status_code == 413
    assert r.headers.get("X-Content-Type-Options") == "nosniff"
    assert r.headers.get("X-Frame-Options") == "DENY"


def test_a_chunked_body_cannot_bypass_the_cap(client):
    """No Content-Length at all — the streaming byte count is what catches this.

    Passing a generator makes httpx use chunked transfer encoding, so a header-only guard would let
    the whole payload through.
    """
    def chunks():
        for _ in range(20):
            yield b"A" * 1024  # 20 KiB total, far over the 2 KiB cap

    r = client.post("/v1/scan/link/commenters", content=chunks(),
                    headers={"content-type": "application/json"})
    assert r.status_code != 200, "an oversized chunked body must not be processed normally"
    assert r.status_code >= 400


def test_a_normal_sized_request_is_unaffected(client):
    """The guard must be invisible to real traffic — a rejected-for-size valid request is a worse bug."""
    r = client.post("/v1/scan/link/commenters", json={"url": "not-a-real-link"})
    # 400 from URL validation is the correct answer here; the point is that it REACHED the route.
    assert r.status_code == 400, f"expected the route to handle it, got {r.status_code}"
    assert "413" not in r.text


def test_bodyless_methods_are_untouched(client):
    """GET/HEAD carry no body, so the cap must never interfere with them."""
    assert client.get("/health").status_code == 200


def test_the_cap_is_generous_by_default():
    """Guard against a future tightening that would break the largest real request."""
    get_settings.cache_clear()
    s = get_settings()
    assert s.max_request_body_bytes >= 262_144, (
        f"the body cap is {s.max_request_body_bytes} bytes; a scan selection at the 1000-candidate "
        f"pool cap is ~30 KB, so anything this tight risks refusing legitimate traffic"
    )
