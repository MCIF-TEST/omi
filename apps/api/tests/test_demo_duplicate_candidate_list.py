"""The free pre-login scan must survive duplicate anonymous candidate lists.

The bug this pins, in full:

Anonymous compiles deliberately share one bucket, ``CandidateList.user_id IS NULL``, so two visitors
scanning the same post reuse a single replier fetch. Both demo routes then look that bucket up with
``.scalar_one_or_none()``.

``CandidateList`` does carry ``UniqueConstraint("user_id", "platform", "content_id")``, which looks
like it makes a duplicate impossible. It does not: ``user_id`` is nullable, and SQL UNIQUE treats
NULLs as DISTINCT (true in PostgreSQL, which is production, and in SQLite). So the constraint is
silently inert for exactly the rows the demo uses, and two concurrent compiles of the same post —
two visitors, two tabs, or one impatient double-click — both see "no list yet" and both insert.

From then on ``.scalar_one_or_none()`` raises ``MultipleResultsFound``. Nothing in either demo route
catches it, so it surfaces as a raw HTTP 500. Three things make that worse than a normal race:

* it is PERMANENT — the duplicate rows persist, so that post 500s forever, not just once;
* it is SHARED — the anonymous bucket is global, so one visitor's race breaks that post for
  everyone who tries it afterwards;
* it hits the FRONT PAGE, which is the product's first impression and its only free sample.

These tests seed the duplicate directly rather than racing threads, because the duplicate is the
state that breaks the route and a thread race would be flaky about producing it.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.config import get_settings
from app.main import create_app
from app.routes.scan import set_twitter_client_factory_for_tests
from app.storage.db import get_session, reset_db_for_tests
from app.storage.models import CandidateList, CommenterCandidate
from tests.fakes import FakeXScanClient

TWEET_URL = "https://x.com/someone/status/1790000000000000000"
TWEET_ID = "1790000000000000000"


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("OMI_TWITTER_API_KEY", "test-key")
    get_settings.cache_clear()
    reset_db_for_tests("sqlite:///:memory:")
    set_twitter_client_factory_for_tests(lambda: FakeXScanClient())
    app = create_app()
    yield TestClient(app)
    set_twitter_client_factory_for_tests(None)
    reset_db_for_tests("sqlite:///:memory:")
    get_settings.cache_clear()


def _compile(client, ip: str, url: str = TWEET_URL):
    return client.post(
        "/v1/scan/demo/commenters", json={"url": url}, headers={"x-forwarded-for": ip}
    )


def _score(client, ip: str, selected: list[str], url: str = TWEET_URL):
    return client.post(
        "/v1/scan/demo/score",
        json={"url": url, "selected": selected},
        headers={"x-forwarded-for": ip},
    )


def _seed_duplicate_anonymous_lists() -> None:
    """Write the state a lost race leaves behind: two anonymous lists for one post."""
    with get_session() as s:
        s.add(CandidateList(user_id=None, platform="x", content_id=TWEET_ID, content_url=TWEET_URL))
        s.flush()
    with get_session() as s:
        s.add(CandidateList(user_id=None, platform="x", content_id=TWEET_ID, content_url=TWEET_URL))
        s.flush()


def test_the_unique_constraint_does_not_prevent_duplicate_anonymous_lists():
    """Documents WHY this bug is reachable: the constraint is inert when user_id IS NULL.

    If a future migration makes it actually enforce (a partial/filtered unique index, or a sentinel
    user_id instead of NULL), this test failing is the signal that the duplicate is now impossible and
    the defensive handling below may be simplified.
    """
    reset_db_for_tests("sqlite:///:memory:")
    try:
        _seed_duplicate_anonymous_lists()
        with get_session() as s:
            rows = s.execute(
                select(CandidateList).where(
                    CandidateList.platform == "x",
                    CandidateList.content_id == TWEET_ID,
                    CandidateList.user_id.is_(None),
                )
            ).scalars().all()
        assert len(rows) == 2, (
            "expected UNIQUE(user_id, platform, content_id) to permit duplicates when user_id is "
            "NULL (SQL treats NULLs as distinct); if this now fails, the schema changed"
        )
    finally:
        reset_db_for_tests("sqlite:///:memory:")


def test_compile_survives_duplicate_anonymous_lists(client):
    """The compile step must still return a usable replier list, not a 500."""
    _seed_duplicate_anonymous_lists()

    resp = _compile(client, "10.0.0.31")

    assert resp.status_code == 200, (
        f"the free compile returned {resp.status_code} with duplicate anonymous candidate lists "
        f"present; the front page's only free sample must not 500. Body: {resp.text[:300]}"
    )
    body = resp.json()
    assert body["platform"] == "x"
    assert len(body["commenters"]) > 0, "a recovered compile must still list repliers to pick from"


def test_score_survives_duplicate_anonymous_lists(client):
    """The analyze step reads the same bucket, so it needs the same resilience."""
    _seed_duplicate_anonymous_lists()

    listing = _compile(client, "10.0.0.32")
    assert listing.status_code == 200, listing.text
    ids = [c["external_id"] for c in listing.json()["commenters"]]
    assert ids

    resp = _score(client, "10.0.0.32", ids)
    assert resp.status_code == 200, (
        f"the free analyze returned {resp.status_code} with duplicate anonymous candidate lists "
        f"present. Body: {resp.text[:300]}"
    )


def test_recovery_does_not_strand_already_cached_repliers(client):
    """Whichever duplicate the route settles on must be the one holding the cached repliers.

    Picking the empty duplicate would technically avoid the 500 while quietly re-fetching from X on
    every compile — a paid call per request, and the reason to prefer the populated row rather than
    just the first one.
    """
    _seed_duplicate_anonymous_lists()

    # Attach cached repliers to the SECOND list, so "just take the lowest id" would miss them.
    with get_session() as s:
        lists = s.execute(
            select(CandidateList)
            .where(CandidateList.user_id.is_(None), CandidateList.content_id == TWEET_ID)
            .order_by(CandidateList.id)
        ).scalars().all()
        newer = lists[-1]
        for i in range(3):
            s.add(CommenterCandidate(
                list_id=newer.id, external_id=f"seeded_{i}", handle=f"seeded_{i}",
                comment_text=f"cached replier {i}", comment_count=1, seq=i,
                meta_json='{"handle": "seeded"}', comments_json="[]",
            ))
        newer.exhausted = True
        s.flush()

    resp = _compile(client, "10.0.0.33")
    assert resp.status_code == 200, resp.text
    handles = {c["external_id"] for c in resp.json()["commenters"]}
    assert any(h.startswith("seeded_") for h in handles), (
        "the compile recovered from the duplicate but returned a list without the already-cached "
        "repliers, which means it chose the empty duplicate and will re-fetch from X every time"
    )
