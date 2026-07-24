"""Shared fake platform clients for tests.

These used to live inside whichever test module happened to need them first, which meant unrelated
suites imported fixtures from each other (``test_scan_link_async`` importing from ``test_demo_scan``).
Anything used by more than one module belongs here.
"""

from __future__ import annotations

from tests.test_coordination import (
    FakeYouTubeClient,
    _channel_profile,
    _make_human_history,
)


VID = "aaaaaaaaaaa"  # 11-char valid YouTube video id format


def _fake_client_with_n_commenters(n: int) -> FakeYouTubeClient:
    """A YouTube client serving one video with ``n`` distinct commenters, each with a profile and a
    human-looking comment history — enough for a full comprehensive scan."""
    items = []
    for i in range(n):
        items.append({
            "snippet": {
                "topLevelComment": {
                    "id": f"c{i}",
                    "snippet": {
                        "authorChannelId": {"value": f"UC_u_{i}"},
                        "authorDisplayName": f"user_{i}",
                        "authorProfileImageUrl": f"https://x/{i}",
                        "textDisplay": f"comment number {i}",
                        "publishedAt": f"2025-05-01T12:{i:02d}:00Z",
                    },
                },
            },
        })
    return FakeYouTubeClient(
        video_pages={VID: [{"items": items}]},
        channel_profiles={
            f"UC_u_{i}": _channel_profile(
                f"UC_u_{i}", title=f"u{i}", sub_count=100,
                created_at="2020-01-01T00:00:00Z",
            )
            for i in range(n)
        },
        channel_history={f"UC_u_{i}": _make_human_history(f"UC_u_{i}") for i in range(n)},
    )


class FakeXScanClient:
    """An X/Twitter client serving user/info (echoes the handle), tweet/replies (``n_repliers``
    distinct repliers), and last_tweets (per-account history) — enough for a full comprehensive scan."""

    def __init__(self, n_repliers: int = 40) -> None:
        self.n = n_repliers
        self.calls: list[tuple[str, dict]] = []

    def get(self, path: str, params: dict) -> dict:
        self.calls.append((path, dict(params)))
        if "user/info" in path:
            uname = params.get("userName") or "user"
            return {"data": {"user": {
                "userName": uname, "name": uname.title(),
                "followers": 120, "following": 60,
                "createdAt": "Mon Jan 15 00:00:00 +0000 2018",
            }}}
        if "tweet/replies" in path:
            return {"has_next_page": False, "data": {"tweets": [
                {"id": f"r{i}", "text": f"reply number {i}",
                 "createdAt": f"2024-03-01T12:{i:02d}:00Z",
                 "author": {"userName": f"replier_{i}", "profilePicture": "u"}}
                for i in range(self.n)
            ]}}
        # last_tweets (per-account history)
        return {"has_next_page": False, "data": {"tweets": [
            {"id": "t1", "text": "a normal tweet about my day", "createdAt": "2024-02-01T00:00:00Z"},
        ]}}
