"""HttpTwitterClient retry/backoff — rate-limit + transient resilience.

Under the bounded-concurrency fetch a brief 429 burst must not drop commenters;
the client retries (honoring Retry-After) with bounded, capped backoff.
"""
from __future__ import annotations

import httpx
import pytest

from app.integrations.twitter import HttpTwitterClient
from app.integrations.twitter_errors import TwitterClientError, TwitterRateLimitError


class _Resp:
    def __init__(self, status, json_val=None, text="", headers=None):
        self.status_code = status
        self._json = json_val
        self.text = text
        self.headers = headers or {}

    def json(self):
        if self._json is None:
            raise ValueError("no json")
        return self._json


def _fake_get(items):
    state = {"calls": 0}

    def fake_get(url, params=None, headers=None, timeout=None):
        state["calls"] += 1
        item = items[min(state["calls"] - 1, len(items) - 1)]
        if isinstance(item, Exception):
            raise item
        return item

    return fake_get, state


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    # Make backoff instant so the tests don't actually wait.
    monkeypatch.setattr(HttpTwitterClient, "_backoff_seconds", lambda self, a, r: 0.0)


def test_retries_429_then_succeeds(monkeypatch):
    fake, state = _fake_get([
        _Resp(429, headers={"Retry-After": "1"}),
        _Resp(200, json_val={"ok": True}),
    ])
    monkeypatch.setattr(httpx, "get", fake)
    client = HttpTwitterClient("key")
    assert client.get("/x", {}) == {"ok": True}
    assert state["calls"] == 2  # one retry


def test_persistent_429_raises_typed_ratelimit(monkeypatch):
    fake, state = _fake_get([_Resp(429)])  # always rate-limited
    monkeypatch.setattr(httpx, "get", fake)
    client = HttpTwitterClient("key", max_retries=2)
    with pytest.raises(TwitterRateLimitError):
        client.get("/x", {})
    assert state["calls"] == 3  # initial + 2 retries, then give up


def test_retries_transient_timeout_then_succeeds(monkeypatch):
    fake, state = _fake_get([
        httpx.TimeoutException("timed out"),
        _Resp(200, json_val={"ok": 1}),
    ])
    monkeypatch.setattr(httpx, "get", fake)
    client = HttpTwitterClient("key")
    assert client.get("/x", {}) == {"ok": 1}
    assert state["calls"] == 2


def test_persistent_timeout_raises_typed_error(monkeypatch):
    fake, state = _fake_get([httpx.ConnectError("down")])
    monkeypatch.setattr(httpx, "get", fake)
    client = HttpTwitterClient("key", max_retries=1)
    with pytest.raises(TwitterClientError):
        client.get("/x", {})
    assert state["calls"] == 2  # initial + 1 retry
