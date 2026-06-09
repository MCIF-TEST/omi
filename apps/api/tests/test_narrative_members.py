"""Narrative drill-in: GET /v1/narratives/{id}/members.

A narrative should be investigable down to the actual comments + commenters —
not just aggregate "there's a narrative" stats. Each member carries the
commenter's own scan verdict (tier/score) and a `scanned` flag for deep-linking.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import app
from app.storage.db import get_session, reset_db_for_tests
from app.storage.models import Account, Narrative, NarrativeMembership


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("OMI_REQUIRE_AUTH", "true")
    monkeypatch.setenv("OMI_SESSION_SECRET", "x" * 64)
    monkeypatch.setenv("OMI_YOUTUBE_API_KEY", "test-key")
    get_settings.cache_clear()
    reset_db_for_tests("sqlite:///:memory:")
    from app.core.rate_limit import LOGIN_LIMITER, SIGNUP_LIMITER
    SIGNUP_LIMITER._windows.clear()
    LOGIN_LIMITER._windows.clear()
    with TestClient(app) as tc:
        tc.post("/v1/auth/signup", json={"email": "u@x.com", "password": "12345678"})
        yield tc
    reset_db_for_tests("sqlite:///:memory:")
    get_settings.cache_clear()


def _seed() -> int:
    """A narrative with 3 comments from 2 authors; one author is scanned."""
    t0 = datetime(2024, 1, 1, tzinfo=timezone.utc)
    with get_session() as session:
        n = Narrative(label="vote integrity", centroid_json=[0.1, 0.2, 0.3],
                      member_count=3, distinct_authors=2)
        session.add(n)
        session.add(Account(platform="youtube", external_id="UCbot", handle="botty",
                            last_tier="high", last_score=0.91))
        session.flush()
        for i, (acc, txt) in enumerate([
            ("UCbot", "the system is rigged, share this everywhere"),
            ("UCbot", "rigged system, spread the word now"),
            ("UCreal", "i just think turnout was low this year"),
        ]):
            session.add(NarrativeMembership(
                narrative_id=n.id, platform="youtube", account_external_id=acc,
                parent_id="vidA", comment_text=txt, observed_at=t0 + timedelta(hours=i),
            ))
        return n.id


def test_members_lists_comments_and_commenters_with_verdicts(client):
    nid = _seed()
    r = client.get(f"/v1/narratives/{nid}/members")
    assert r.status_code == 200
    body = r.json()
    assert body["label"] == "vote integrity"
    assert body["total"] == 3 and body["distinct_authors"] == 2
    assert len(body["members"]) == 3
    # Newest first; every member carries the actual comment text + author.
    assert all(m["comment_text"] and m["account_external_id"] for m in body["members"])
    by_acc = {m["account_external_id"]: m for m in body["members"]}
    # The scanned commenter carries their OWN scan verdict + is deep-linkable.
    assert by_acc["UCbot"]["scanned"] is True
    assert by_acc["UCbot"]["tier"] == "high" and by_acc["UCbot"]["score"] == 0.91
    assert by_acc["UCbot"]["handle"] == "botty"
    # The unscanned commenter is surfaced honestly (no fabricated verdict).
    assert by_acc["UCreal"]["scanned"] is False
    assert by_acc["UCreal"]["tier"] is None and by_acc["UCreal"]["score"] is None


def test_members_filter_by_account_and_paginate(client):
    nid = _seed()
    r = client.get(f"/v1/narratives/{nid}/members", params={"account_external_id": "UCbot"})
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 2  # only UCbot's contributions
    assert {m["account_external_id"] for m in body["members"]} == {"UCbot"}

    page = client.get(f"/v1/narratives/{nid}/members", params={"limit": 1, "offset": 0})
    assert page.status_code == 200 and len(page.json()["members"]) == 1
    assert page.json()["total"] == 3  # total reflects all, not the page


def test_members_404_for_unknown_narrative(client):
    assert client.get("/v1/narratives/999999/members").status_code == 404
