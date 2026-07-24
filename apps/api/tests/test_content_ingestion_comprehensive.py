"""Content Database ingestion via the comprehensive scan path.

The Content DB (ContentEntity / CommentBatch / ContentComment) must populate
automatically from the scan flow the product actually uses — the unified
``/v1/scan/link`` -> ``_run_comprehensive`` -> ``orchestrator.scan_comprehensive``
path — not only the standalone ``/youtube/full`` endpoint. Before this wiring,
users scanned videos and the Content DB stayed empty.

These pin the contract:
  A. Comprehensive YouTube scan -> ContentEntity created
  B. Comprehensive YouTube scan -> CommentBatch created
  C. Comprehensive YouTube scan -> ContentComment rows stored
  D. Non-YouTube (X) scan       -> no ContentEntity created
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.core.config import get_settings
from app.main import app
from app.routes.scan import (
    set_client_factory_for_tests,
    set_twitter_client_factory_for_tests,
)
from app.storage.db import get_session, reset_db_for_tests
from app.storage.models import CommentBatch, ContentComment, ContentEntity, User
from tests.fakes import VID, _fake_client_with_n_commenters
from tests.test_twitter_link_scan import FakeTwitterScanClient


def _drain_background() -> None:
    """Run pending fire-and-forget content writes to completion before asserting.

    Content intelligence is recorded on the background pool (mirroring
    /youtube/full); draining is the same pattern the investigation-persistence
    test uses to assert a background write landed.
    """
    from app.core import background

    background.shutdown(wait_seconds=10.0)


def _grant_credits(email: str) -> None:
    with get_session() as s:
        u = s.execute(select(User).where(User.email == email)).scalar_one()
        u.credits_remaining = 50


@pytest.fixture
def yt_client(monkeypatch):
    monkeypatch.setenv("OMI_REQUIRE_AUTH", "true")
    monkeypatch.setenv("OMI_SESSION_SECRET", "x" * 64)
    monkeypatch.setenv("OMI_YOUTUBE_API_KEY", "test-key")
    get_settings.cache_clear()
    reset_db_for_tests("sqlite:///:memory:")
    from app.core.rate_limit import LOGIN_LIMITER, SIGNUP_LIMITER

    SIGNUP_LIMITER._windows.clear()
    LOGIN_LIMITER._windows.clear()
    set_client_factory_for_tests(lambda: _fake_client_with_n_commenters(8))
    with TestClient(app) as tc:
        tc.post("/v1/auth/signup", json={"email": "cdb@t.com", "password": "password12345"})
        _grant_credits("cdb@t.com")
        yield tc
    set_client_factory_for_tests(None)
    reset_db_for_tests("sqlite:///:memory:")
    get_settings.cache_clear()


@pytest.fixture
def x_client(monkeypatch):
    monkeypatch.setenv("OMI_REQUIRE_AUTH", "true")
    monkeypatch.setenv("OMI_SESSION_SECRET", "x" * 64)
    monkeypatch.setenv("OMI_TWITTER_API_KEY", "test-key")
    get_settings.cache_clear()
    reset_db_for_tests("sqlite:///:memory:")
    from app.core.rate_limit import LOGIN_LIMITER, SIGNUP_LIMITER

    SIGNUP_LIMITER._windows.clear()
    LOGIN_LIMITER._windows.clear()
    set_twitter_client_factory_for_tests(lambda: FakeTwitterScanClient())
    with TestClient(app) as tc:
        tc.post("/v1/auth/signup", json={"email": "cdbx@t.com", "password": "password12345"})
        _grant_credits("cdbx@t.com")
        yield tc
    set_twitter_client_factory_for_tests(None)
    reset_db_for_tests("sqlite:///:memory:")
    get_settings.cache_clear()


def _scan_youtube_video(tc) -> None:
    r = tc.post(
        "/v1/scan/link",
        json={"url": f"https://www.youtube.com/watch?v={VID}", "max_commenters": 8},
    )
    assert r.status_code == 200, r.text
    assert r.json()["video"]["commenter_count"] >= 1
    _drain_background()


def _entity(s):
    return s.execute(
        select(ContentEntity).where(
            ContentEntity.platform == "youtube",
            ContentEntity.content_id == VID,
        )
    ).scalar_one_or_none()


# --- Case A: ContentEntity created ------------------------------------------

def test_comprehensive_youtube_scan_creates_content_entity(yt_client):
    _scan_youtube_video(yt_client)
    with get_session() as s:
        assert _entity(s) is not None


# --- Case B: CommentBatch created -------------------------------------------

def test_comprehensive_youtube_scan_creates_comment_batch(yt_client):
    _scan_youtube_video(yt_client)
    with get_session() as s:
        entity = _entity(s)
        assert entity is not None
        batches = s.execute(
            select(func.count(CommentBatch.id)).where(
                CommentBatch.content_entity_id == entity.id
            )
        ).scalar_one()
    assert batches >= 1


# --- Case C: ContentComment rows stored -------------------------------------

def test_comprehensive_youtube_scan_stores_comments(yt_client):
    _scan_youtube_video(yt_client)
    with get_session() as s:
        entity = _entity(s)
        assert entity is not None
        comments = s.execute(
            select(func.count(ContentComment.id)).where(
                ContentComment.content_entity_id == entity.id
            )
        ).scalar_one()
    assert comments >= 1


# --- Case D: non-YouTube scan creates no ContentEntity ----------------------

def test_non_youtube_scan_creates_no_content_entity(x_client):
    # An X tweet scan produces a repliers batch (video_output IS present), so
    # this exercises the platform guard specifically — content recording must be
    # suppressed for X even though the comprehensive path ran a content scan.
    r = x_client.post(
        "/v1/scan/link",
        json={"url": "https://x.com/author/status/1788888888888", "max_commenters": 10},
    )
    assert r.status_code == 200, r.text
    assert r.json().get("video") is not None  # a repliers batch was produced
    _drain_background()
    with get_session() as s:
        total = s.execute(select(func.count(ContentEntity.id))).scalar_one()
    assert total == 0
