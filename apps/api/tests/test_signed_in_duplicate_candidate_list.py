"""The SIGNED-IN compile/score paths must survive duplicate candidate lists too.

Same root cause as ``test_demo_duplicate_candidate_list.py``, reached through the authenticated
routes. ``CandidateList`` carries ``UniqueConstraint("user_id", "platform", "content_id")``, and there
are two independent ways that fails to prevent a second row:

1. **NULL owners.** SQL treats NULLs as DISTINCT, so the constraint is inert whenever ``user_id`` is
   NULL. The signed-in routes map their owner to NULL in local mode
   (``OMI_REQUIRE_AUTH=false`` → the id=0 user → ``uid = None``), which is what these tests exercise.

2. **Databases predating the constraint.** ``create_all`` leaves existing tables alone, and the boot
   upgrade pass backfills columns and ``table.indexes`` only — a ``UniqueConstraint`` lives in
   ``table.constraints``, so it is never added to a ``candidate_lists`` table that already existed.
   On such a database duplicates are possible for REAL user ids as well, which is why this is not
   merely a local-mode concern. That case is asserted directly below rather than by faking a
   production schema.

Either way ``.scalar_one_or_none()`` raised ``MultipleResultsFound`` out of the route as a raw 500.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import inspect, select

import app.routes.scan_async as scan_async
from app.core.config import get_settings
from app.main import app
from app.storage.db import get_session, reset_db_for_tests
from app.storage.models import CandidateList, CommenterCandidate

_URL = "https://x.com/someone/status/t1"
_CONTENT_ID = "t1"


@pytest.fixture(autouse=True)
def _fresh(monkeypatch):
    monkeypatch.setenv("OMI_REQUIRE_AUTH", "false")  # local mode: user id 0 -> uid None
    get_settings.cache_clear()
    reset_db_for_tests()
    monkeypatch.setattr(
        scan_async, "classify_link",
        lambda url: {"platform": "x", "kind": "tweet", "tweet_id": _CONTENT_ID},
    )
    yield
    get_settings.cache_clear()


class _FakeSource:
    def __init__(self):
        self.calls = 0

    def fetch_content_engagers(self, content_id, *, max_commenters, max_comments, start_page_token=None):
        self.calls += 1
        return (
            [{"channel_id": "u_alice", "handle": "alice"}, {"channel_id": "u_bob", "handle": "bob"}],
            [
                {"author_external_id": "u_alice", "text": "great post", "created_at": "2026-01-01T00:00:00+00:00"},
                {"author_external_id": "u_bob", "text": "same", "created_at": "2026-01-01T00:01:00+00:00"},
            ],
            None,
        )

    def fetch_content_title(self, content_id):
        return "a post"


def _seed_duplicate_lists(uid=None) -> None:
    """Two lists for one (platform, content, owner) — what a lost race leaves behind."""
    for _ in range(2):
        with get_session() as s:
            s.add(CandidateList(
                user_id=uid, platform="x", content_id=_CONTENT_ID, content_url=_URL,
            ))
            s.flush()


def test_the_unique_constraint_is_absent_from_table_indexes():
    """Why real user ids are exposed on older databases, asserted against the schema itself.

    ``_ensure_indexes`` (app/storage/db.py) walks ``table.indexes`` to backfill anything missing from
    a pre-existing table. ``uq_candidate_list`` is a ``UniqueConstraint``, which lives in
    ``table.constraints`` instead, so that pass cannot see it and a database created before the
    constraint was added never receives it.

    If someone later backfills it properly (a migration, or a partial unique index for the NULL case),
    this test failing is the signal.
    """
    t = CandidateList.__table__
    index_names = {i.name for i in t.indexes}
    constraint_names = {
        c.name for c in t.constraints if type(c).__name__ == "UniqueConstraint"
    }
    assert "uq_candidate_list" in constraint_names, "expected the model to declare the constraint"
    assert "uq_candidate_list" not in index_names, (
        "uq_candidate_list is now in table.indexes, so _ensure_indexes would backfill it on existing "
        "databases; the duplicate-row window for real user ids may be closed"
    )


def test_signed_in_compile_survives_duplicate_lists(monkeypatch):
    fake = _FakeSource()
    monkeypatch.setattr(scan_async, "_source_for_platform", lambda platform, settings: fake)
    _seed_duplicate_lists()

    with TestClient(app) as tc:
        resp = tc.post("/v1/scan/link/commenters", json={"url": _URL})

    assert resp.status_code == 200, (
        f"the signed-in compile returned {resp.status_code} with duplicate candidate lists present. "
        f"Body: {resp.text[:300]}"
    )
    assert len(resp.json()["commenters"]) > 0


def test_signed_in_compile_prefers_the_populated_duplicate(monkeypatch):
    """Recovery must not silently re-fetch: choosing the empty duplicate costs an upstream call."""
    fake = _FakeSource()
    monkeypatch.setattr(scan_async, "_source_for_platform", lambda platform, settings: fake)
    _seed_duplicate_lists()

    # Cache commenters on the SECOND list, so "take the first row" would miss them.
    with get_session() as s:
        lists = s.execute(
            select(CandidateList).where(CandidateList.content_id == _CONTENT_ID)
            .order_by(CandidateList.id)
        ).scalars().all()
        newer = lists[-1]
        for i in range(2):
            s.add(CommenterCandidate(
                list_id=newer.id, external_id=f"cached_{i}", handle=f"cached_{i}",
                comment_text=f"cached {i}", comment_count=1, seq=i,
                meta_json='{"handle": "cached"}', comments_json="[]",
            ))
        newer.exhausted = True
        s.flush()

    with TestClient(app) as tc:
        body = tc.post("/v1/scan/link/commenters", json={"url": _URL}).json()

    handles = {c["external_id"] for c in body["commenters"]}
    assert any(h.startswith("cached_") for h in handles), (
        "the compile recovered but returned the empty duplicate's list, so it will re-fetch from the "
        "platform on every call"
    )
    assert fake.calls == 0, "an already-populated, exhausted list must not trigger a new fetch"


def test_signed_in_score_survives_duplicate_lists(monkeypatch):
    """The score step reads the same row and needs the same tolerance."""
    fake = _FakeSource()
    monkeypatch.setattr(scan_async, "_source_for_platform", lambda platform, settings: fake)
    _seed_duplicate_lists()

    with TestClient(app) as tc:
        listing = tc.post("/v1/scan/link/commenters", json={"url": _URL})
        assert listing.status_code == 200, listing.text
        ids = [c["external_id"] for c in listing.json()["commenters"]]
        assert ids

        resp = tc.post("/v1/scan/link/score", json={"url": _URL, "selected": ids})

    # The point is that it resolved the list rather than 500ing on the duplicate. Whatever the scan
    # itself then does (it runs the real engine against a stub source) must not be a server error.
    assert resp.status_code < 500, (
        f"the signed-in score returned {resp.status_code} with duplicate candidate lists present. "
        f"Body: {resp.text[:300]}"
    )
    assert "MultipleResultsFound" not in resp.text


def test_empty_duplicates_are_collapsed(monkeypatch):
    """Recovery also tidies: ambiguity should not persist for the next request."""
    fake = _FakeSource()
    monkeypatch.setattr(scan_async, "_source_for_platform", lambda platform, settings: fake)
    _seed_duplicate_lists()

    with get_session() as s:
        before = len(s.execute(
            select(CandidateList).where(CandidateList.content_id == _CONTENT_ID)
        ).scalars().all())
    assert before == 2

    with TestClient(app) as tc:
        assert tc.post("/v1/scan/link/commenters", json={"url": _URL}).status_code == 200

    with get_session() as s:
        after = s.execute(
            select(CandidateList).where(CandidateList.content_id == _CONTENT_ID)
        ).scalars().all()
    assert len(after) == 1, (
        f"expected the empty duplicate to be collapsed, still have {len(after)} lists"
    )
    # And the survivor is the one now holding the fetched commenters.
    with get_session() as s:
        kept = s.execute(
            select(CommenterCandidate).where(CommenterCandidate.list_id == after[0].id)
        ).scalars().all()
    assert kept, "the surviving list should hold the compiled commenters"
