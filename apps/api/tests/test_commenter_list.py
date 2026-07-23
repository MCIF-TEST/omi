"""Select-then-scan, Phase 1 — the FREE compile step lists + caches a post's commenters.

The user pastes a post and gets the list of commenters (handle + comment) WITHOUT any scoring: no
histories, no detection, no AI, no credits. Re-opening returns the cache instantly; "add more" pages
from the saved cursor and dedupes. These pin that behaviour with a stubbed Source (no network).
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import app.routes.scan_async as scan_async
from app.core.config import get_settings
from app.main import app
from app.storage.db import reset_db_for_tests

_URL = "https://x.com/someone/status/1980170228554903796"


@pytest.fixture(autouse=True)
def _fresh(monkeypatch):
    monkeypatch.setenv("OMI_REQUIRE_AUTH", "false")  # local mode: user id 0
    get_settings.cache_clear()
    reset_db_for_tests()
    # Deterministic classification (no dependence on the URL parser).
    monkeypatch.setattr(scan_async, "classify_link",
                        lambda url: {"platform": "x", "kind": "tweet", "tweet_id": "t1"})
    yield
    get_settings.cache_clear()


class _FakeSource:
    """A Source stub: fetch_content_engagers returns canned (commenters_meta, comments, next_cursor) pages."""

    def __init__(self, pages):
        self._pages = pages
        self.calls = 0

    def fetch_content_engagers(self, content_id, *, max_commenters, max_comments, start_page_token=None):
        page = self._pages[min(self.calls, len(self._pages) - 1)]
        self.calls += 1
        return page


def _pages():
    page1 = (
        [{"channel_id": "alice", "handle": "alice"}, {"channel_id": "bob", "handle": "bob"}],
        [{"comment_id": "c1", "author_external_id": "alice", "text": "great post", "created_at": None},
         {"comment_id": "c2", "author_external_id": "bob", "text": "agreed", "created_at": None}],
        "cursor-1",
    )
    page2 = (
        [{"channel_id": "bob", "handle": "bob"},          # duplicate — must be deduped
         {"channel_id": "carol", "handle": "carol"}],
        [{"comment_id": "c3", "author_external_id": "carol", "text": "nice", "created_at": None}],
        None,                                             # no cursor → exhausted
    )
    return [page1, page2]


def test_compile_lists_caches_pages_and_dedupes(monkeypatch):
    fake = _FakeSource(_pages())
    monkeypatch.setattr(scan_async, "_source_for_platform", lambda platform, settings: fake)

    with TestClient(app) as tc:
        # First call pulls the first page (free — no credits, no scoring).
        b1 = tc.post("/v1/scan/link/commenters", json={"url": _URL}).json()
        assert b1["platform"] == "x"
        assert [c["handle"] for c in b1["commenters"]] == ["alice", "bob"]
        assert b1["commenters"][0]["comment"] == "great post"
        assert b1["total"] == 2 and b1["has_more"] is True and b1["fetched_now"] == 2
        assert all(c["scanned"] is False for c in b1["commenters"])

        # Re-open WITHOUT asking for more → cached list, no new fetch.
        b_cache = tc.post("/v1/scan/link/commenters", json={"url": _URL}).json()
        assert b_cache["total"] == 2 and b_cache["fetched_now"] == 0
        assert fake.calls == 1

        # "Add more" pulls the next page, appends carol, dedupes bob, and marks exhausted.
        b2 = tc.post("/v1/scan/link/commenters", json={"url": _URL, "fetch": 25}).json()
        assert [c["handle"] for c in b2["commenters"]] == ["alice", "bob", "carol"]
        assert b2["total"] == 3 and b2["has_more"] is False and b2["fetched_now"] == 1

        # Exhausted → a further "add more" fetches nothing.
        b3 = tc.post("/v1/scan/link/commenters", json={"url": _URL, "fetch": 25}).json()
        assert b3["total"] == 3 and b3["fetched_now"] == 0
        assert fake.calls == 2


def test_refresh_rebuilds_the_list_from_scratch(monkeypatch):
    fake = _FakeSource(_pages())
    monkeypatch.setattr(scan_async, "_source_for_platform", lambda platform, settings: fake)
    with TestClient(app) as tc:
        tc.post("/v1/scan/link/commenters", json={"url": _URL})               # page1 cached
        fresh = _FakeSource(_pages())
        monkeypatch.setattr(scan_async, "_source_for_platform", lambda platform, settings: fresh)
        b = tc.post("/v1/scan/link/commenters", json={"url": _URL, "refresh": True}).json()
        assert [c["handle"] for c in b["commenters"]] == ["alice", "bob"]     # rebuilt from page1
        assert b["fetched_now"] == 2


def test_compile_with_no_commenters_returns_empty_ok(monkeypatch):
    """A post with comments off / no replies must return a clean empty list (total 0), NOT an error and
    NOT a blank — the UI renders an explicit "no commenters" state off this."""
    empty = _FakeSource([([], [], None)])
    monkeypatch.setattr(scan_async, "_source_for_platform", lambda platform, settings: empty)
    with TestClient(app) as tc:
        r = tc.post("/v1/scan/link/commenters", json={"url": _URL})
        assert r.status_code == 200, r.text
        b = r.json()
        assert b["commenters"] == [] and b["total"] == 0
        assert b["has_more"] is False and b["fetched_now"] == 0


def test_compile_fetch_error_is_a_clean_502_not_a_raw_500(monkeypatch):
    """Any unexpected error from the platform fetch is wrapped into a clean 502 with a helpful message,
    so the compile step never surfaces an opaque 500 (which the UI reads as "loads then cuts out")."""
    class _Boom:
        def fetch_content_engagers(self, *a, **k):
            raise RuntimeError("provider exploded")

    monkeypatch.setattr(scan_async, "_source_for_platform", lambda platform, settings: _Boom())
    with TestClient(app) as tc:
        r = tc.post("/v1/scan/link/commenters", json={"url": _URL})
        assert r.status_code == 502, r.text
        assert "try again" in r.json()["detail"].lower()


def test_missing_and_unrecognized_urls_are_rejected(monkeypatch):
    with TestClient(app) as tc:
        assert tc.post("/v1/scan/link/commenters", json={}).status_code == 400
        monkeypatch.setattr(scan_async, "classify_link",
                            lambda url: {"platform": "unknown", "kind": "unknown"})
        r = tc.post("/v1/scan/link/commenters", json={"url": "not a link"})
        assert r.status_code == 400


# --------------------------------------------------------------------------- #
# Phase 2 — the paid score step runs on ONLY the selected commenters.
# --------------------------------------------------------------------------- #
def test_score_charges_per_selected_and_injects_only_the_selection(monkeypatch):
    from app.core.auth import compute_scan_credits
    from app.core.config import get_settings

    fake = _FakeSource(_pages())
    monkeypatch.setattr(scan_async, "_source_for_platform", lambda platform, settings: fake)
    captured: dict = {}
    monkeypatch.setattr(scan_async.background, "submit",
                        lambda fn, **kw: (captured.update(kw), object())[1])
    charged: dict = {}
    monkeypatch.setattr(scan_async, "consume_credits",
                        lambda uid, cost, **kw: charged.update({"cost": cost}))

    with TestClient(app) as tc:
        tc.post("/v1/scan/link/commenters", json={"url": _URL})           # compile → alice, bob
        r = tc.post("/v1/scan/link/score", json={"url": _URL, "selected": ["alice"]})
        assert r.status_code == 202, r.text
        body = r.json()
        assert body["status"] == "queued" and body["investigation_slug"]

        creq = captured["creq"]
        assert [m["channel_id"] for m in creq.injected_commenters] == ["alice"]   # ONLY the selection
        assert captured["selected_ids"] == ["alice"]
        assert captured["candidate_list_id"]
        # paid for 1 selected commenter, not the whole cached list
        assert charged["cost"] == compute_scan_credits("x", 1, get_settings())
        # the free list step never triggered the per-commenter scoring source
        assert fake.calls == 1   # only the compile fetch


def test_score_requires_a_selection_and_a_compiled_list(monkeypatch):
    with TestClient(app) as tc:
        assert tc.post("/v1/scan/link/score", json={"url": _URL, "selected": []}).status_code == 400
        # a real selection but no compiled list yet
        assert tc.post("/v1/scan/link/score",
                       json={"url": _URL, "selected": ["alice"]}).status_code == 400
