"""Tests for the YouTube integration and the /v1/scan/youtube/video route.

We never hit the network: a fake client implements the small surface that
``app.integrations.youtube`` calls (``.commentThreads().list(...).execute()``
and ``.channels().list(...).execute()``). Fixture builders below let each
test stage exactly the data it cares about.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.integrations.youtube import (
    FetchStats,
    fetch_channel_profile,
    fetch_channel_recent_comments,
    fetch_video_commenters,
    parse_video_id,
)
from app.main import app
from app.routes.scan import set_client_factory_for_tests
from app.storage.db import reset_db_for_tests


# ---------------------------------------------------------------------------
# Fake YouTube client
# ---------------------------------------------------------------------------


class _Request:
    def __init__(self, response: dict):
        self._response = response

    def execute(self):
        return self._response


class _CommentThreads:
    def __init__(self, video_pages, channel_history):
        self.video_pages = video_pages
        self.channel_history = channel_history
        self._calls = 0

    def list(self, **params):
        self._calls += 1
        if "videoId" in params:
            video_id = params["videoId"]
            page_token = params.get("pageToken")
            pages = self.video_pages.get(video_id, [])
            idx = int(page_token) if page_token else 0
            if idx >= len(pages):
                return _Request({"items": []})
            return _Request(pages[idx])
        if "allThreadsRelatedToChannelId" in params:
            cid = params["allThreadsRelatedToChannelId"]
            return _Request({"items": self.channel_history.get(cid, [])})
        return _Request({"items": []})


class _Channels:
    def __init__(self, profiles):
        self.profiles = profiles

    def list(self, **params):
        cid = params.get("id")
        item = self.profiles.get(cid)
        return _Request({"items": [item]} if item else {"items": []})


class FakeYouTubeClient:
    def __init__(self, *, video_pages, channel_profiles, channel_history):
        self._comment_threads = _CommentThreads(video_pages, channel_history)
        self._channels = _Channels(channel_profiles)

    def commentThreads(self):
        return self._comment_threads

    def channels(self):
        return self._channels


def _video_comment_item(channel_id: str, text: str, handle: str | None = None) -> dict:
    return {
        "snippet": {
            "topLevelComment": {
                "id": f"comment_{channel_id}",
                "snippet": {
                    "authorChannelId": {"value": channel_id},
                    "authorDisplayName": handle or f"author_{channel_id}",
                    "authorProfileImageUrl": f"https://example.com/{channel_id}.png",
                    "textDisplay": text,
                    "publishedAt": "2025-05-01T12:00:00Z",
                },
            }
        }
    }


def _history_item(channel_id: str, text: str, when: str) -> dict:
    return {
        "snippet": {
            "topLevelComment": {
                "id": f"hist_{channel_id}_{when}",
                "snippet": {
                    "authorChannelId": {"value": channel_id},
                    "authorDisplayName": f"author_{channel_id}",
                    "textDisplay": text,
                    "publishedAt": when,
                    "likeCount": 0,
                },
            }
        }
    }


def _channel_profile(channel_id: str, *, title: str, sub_count: int, created_at: str) -> dict:
    return {
        "snippet": {
            "title": title,
            "customUrl": "@" + title.lower().replace(" ", ""),
            "description": "test bio",
            "publishedAt": created_at,
            "thumbnails": {"default": {"url": f"https://example.com/{channel_id}.jpg"}},
        },
        "statistics": {"subscriberCount": str(sub_count)},
    }


# ---------------------------------------------------------------------------
# Unit-ish tests on the fetch primitives
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "url,expected",
    [
        ("dQw4w9WgXcQ", "dQw4w9WgXcQ"),
        ("https://www.youtube.com/watch?v=dQw4w9WgXcQ", "dQw4w9WgXcQ"),
        ("https://youtu.be/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
        ("https://www.youtube.com/shorts/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
        ("not a video", None),
    ],
)
def test_parse_video_id(url, expected):
    assert parse_video_id(url) == expected


def test_fetch_video_commenters_deduplicates_and_paginates():
    video_pages = {
        "videoOne001": [
            {
                "items": [
                    _video_comment_item("UC_a", "hello"),
                    _video_comment_item("UC_b", "world"),
                    _video_comment_item("UC_a", "again"),  # duplicate
                ],
                "nextPageToken": "1",
            },
            {
                "items": [_video_comment_item("UC_c", "third")],
            },
        ]
    }
    client = FakeYouTubeClient(
        video_pages=video_pages, channel_profiles={}, channel_history={}
    )
    stats = FetchStats()
    out = fetch_video_commenters(client, "videoOne001", max_commenters=100, stats=stats)
    assert [c["channel_id"] for c in out] == ["UC_a", "UC_b", "UC_c"]
    assert stats.quota_used == 2  # two pages fetched


def test_fetch_video_commenters_respects_cap():
    video_pages = {
        "videoOne001": [
            {
                "items": [_video_comment_item(f"UC_{i}", f"msg{i}") for i in range(10)],
            }
        ]
    }
    client = FakeYouTubeClient(
        video_pages=video_pages, channel_profiles={}, channel_history={}
    )
    out = fetch_video_commenters(client, "videoOne001", max_commenters=3)
    assert len(out) == 3


def test_fetch_channel_profile_normalizes_to_profile_schema():
    client = FakeYouTubeClient(
        video_pages={},
        channel_profiles={
            "UC_x": _channel_profile(
                "UC_x", title="Real Person", sub_count=1234, created_at="2020-01-01T00:00:00Z"
            )
        },
        channel_history={},
    )
    profile = fetch_channel_profile(client, "UC_x")
    assert profile is not None
    assert profile.platform == "youtube"
    assert profile.display_name == "Real Person"
    assert profile.follower_count == 1234
    assert profile.created_at == datetime(2020, 1, 1, tzinfo=timezone.utc)


def test_fetch_channel_history_filters_to_author():
    client = FakeYouTubeClient(
        video_pages={},
        channel_profiles={},
        channel_history={
            "UC_x": [
                _history_item("UC_x", "mine", "2025-05-01T00:00:00Z"),
                _history_item("UC_other", "not mine", "2025-05-02T00:00:00Z"),
                _history_item("UC_x", "mine too", "2025-05-03T00:00:00Z"),
            ]
        },
    )
    posts = fetch_channel_recent_comments(client, "UC_x", max_comments=10)
    assert [p.text for p in posts] == ["mine", "mine too"]


# ---------------------------------------------------------------------------
# End-to-end /v1/scan/youtube/video
# ---------------------------------------------------------------------------


@pytest.fixture
def client_with_db():
    get_settings.cache_clear()
    reset_db_for_tests("sqlite:///:memory:")
    with TestClient(app) as tc:
        yield tc
    set_client_factory_for_tests(None)
    reset_db_for_tests("sqlite:///:memory:")


def _make_bot_history(channel_id: str) -> list[dict]:
    base = datetime(2025, 1, 1, tzinfo=timezone.utc)
    text = (
        "Big news today — the establishment doesn't want you to see this. "
        "Share to spread the truth. Follow for more."
    )
    return [
        _history_item(channel_id, text, (base + timedelta(minutes=15 * i)).isoformat())
        for i in range(60)
    ]


def _make_human_history(channel_id: str) -> list[dict]:
    base = datetime(2025, 1, 1, 9, tzinfo=timezone.utc)
    texts = [
        "good morning everyone",
        "this song slaps",
        "anyone else having mic problems on the latest update",
        "lol the editing on this one is wild",
        "respectfully, nope. did not work for me.",
        "thanks for the tutorial!! cleared up so much",
        "wait what theme is your editor",
    ]
    out = []
    for i in range(40):
        ts = base + timedelta(hours=i * 3, minutes=i * 7 % 60)
        out.append(_history_item(channel_id, texts[i % len(texts)] + f" #{i}", ts.isoformat()))
    return out


def test_scan_youtube_video_end_to_end(client_with_db):
    bot_id = "UC_bot_zzz_9999"
    human_id = "UC_normal_user_aaa"

    video_pages = {
        "videoDemo01": [
            {
                "items": [
                    _video_comment_item(bot_id, "Big news!"),
                    _video_comment_item(human_id, "this video is great"),
                ]
            }
        ]
    }
    channel_profiles = {
        bot_id: _channel_profile(
            bot_id, title="zzz_9999", sub_count=2, created_at="2025-05-01T00:00:00Z"
        ),
        human_id: _channel_profile(
            human_id, title="Normal Person", sub_count=420, created_at="2019-03-15T00:00:00Z"
        ),
    }
    channel_history = {
        bot_id: _make_bot_history(bot_id),
        human_id: _make_human_history(human_id),
    }
    fake = FakeYouTubeClient(
        video_pages=video_pages,
        channel_profiles=channel_profiles,
        channel_history=channel_history,
    )
    set_client_factory_for_tests(lambda: fake)

    resp = client_with_db.post("/v1/scan/youtube/video", json={"video_url_or_id": "videoDemo01"})
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["video_id"] == "videoDemo01"
    assert body["commenter_count"] == 2
    assert body["fresh_count"] == 2
    assert body["cached_count"] == 0
    assert body["quota_used"] >= 3  # 1 commentThreads + 2x (channels + history)

    by_handle = {c["external_id"]: c for c in body["commenters"]}
    assert by_handle[bot_id]["tier"] in ("elevated", "high")
    assert by_handle[human_id]["tier"] in ("low", "moderate")

    # The bot should appear in the high-suspicion list.
    assert any(bot_id in h or "zzz" in h for h in body["high_suspicion_handles"])
    assert "probabilistic" in body["summary"].lower()


def test_scan_youtube_video_uses_cache_on_replay(client_with_db):
    bot_id = "UC_repeat_offender"
    video_pages = {
        "videoAlpha1": [{"items": [_video_comment_item(bot_id, "hi")]}],
        "videoBravo1": [{"items": [_video_comment_item(bot_id, "hi again")]}],
    }
    channel_profiles = {
        bot_id: _channel_profile(
            bot_id, title="repeat", sub_count=1, created_at="2025-05-01T00:00:00Z"
        )
    }
    channel_history = {bot_id: _make_bot_history(bot_id)}
    fake = FakeYouTubeClient(
        video_pages=video_pages,
        channel_profiles=channel_profiles,
        channel_history=channel_history,
    )
    set_client_factory_for_tests(lambda: fake)

    first = client_with_db.post(
        "/v1/scan/youtube/video", json={"video_url_or_id": "videoAlpha1"}
    ).json()
    assert first["fresh_count"] == 1
    assert first["cached_count"] == 0
    quota_after_first = first["quota_used"]

    second = client_with_db.post(
        "/v1/scan/youtube/video", json={"video_url_or_id": "videoBravo1"}
    ).json()
    assert second["cached_count"] == 1
    assert second["fresh_count"] == 0
    # The replay should be cheaper: only the initial commentThreads.list page.
    assert second["quota_used"] < quota_after_first


def test_scan_youtube_video_missing_key_returns_503(client_with_db, monkeypatch):
    # Simulate the production resolver: no api key configured AND no test override.
    set_client_factory_for_tests(None)
    monkeypatch.setenv("OMI_YOUTUBE_API_KEY", "")
    get_settings.cache_clear()
    resp = client_with_db.post("/v1/scan/youtube/video", json={"video_url_or_id": "abcdefghijk"})
    assert resp.status_code == 503
    assert "youtube" in resp.json()["detail"].lower()


def test_scan_youtube_video_bad_url_returns_400(client_with_db):
    set_client_factory_for_tests(lambda: FakeYouTubeClient(video_pages={}, channel_profiles={}, channel_history={}))
    resp = client_with_db.post("/v1/scan/youtube/video", json={"video_url_or_id": "not a video"})
    assert resp.status_code == 400
