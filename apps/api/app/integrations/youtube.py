"""YouTube ingestion.

Fetches:

* Every commenter on a target video (``commentThreads.list`` paginated).
* Each commenter's channel metadata (``channels.list``).
* Each commenter's recent comment history (``commentThreads.list`` with
  ``allThreadsRelatedToChannelId``) — limited by ``scan_max_history_per_commenter``.

Quota math (v3, list calls cost 1 unit each):

* Per video scan: ⌈N_comments / 100⌉ for the initial fetch.
* Per fresh commenter: 1 (channel) + ⌈H / 100⌉ (history). Default H=50 → 2 units.

The official ``google-api-python-client`` package is loaded lazily so the
rest of the API runs without it installed (it pulls in a heavy googleapis
dependency tree). The route handler returns 503 if it isn't available.

For tests we accept any object that implements the small protocol in
``YouTubeClient`` — no network required.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Iterable, Protocol

from dateutil import parser as date_parser

from app.schemas import Post, Profile


_VIDEO_ID_PATTERNS = [
    re.compile(r"(?:v=|/shorts/|youtu\.be/|/embed/|/v/)([A-Za-z0-9_-]{11})"),
    re.compile(r"^([A-Za-z0-9_-]{11})$"),
]

_CHANNEL_ID_RE = re.compile(r"^(UC[A-Za-z0-9_-]{22})$")
_CHANNEL_URL_RE = re.compile(r"youtube\.com/channel/(UC[A-Za-z0-9_-]{22})")
_HANDLE_URL_RE = re.compile(r"youtube\.com/@([A-Za-z0-9_.\-]+)")
_LEGACY_RE = re.compile(r"youtube\.com/(?:c|user)/([A-Za-z0-9_.\-]+)")


def parse_video_id(url_or_id: str) -> str | None:
    """Extract the 11-character YouTube video ID from a URL or raw ID."""
    if not url_or_id:
        return None
    s = url_or_id.strip()
    for pat in _VIDEO_ID_PATTERNS:
        m = pat.search(s)
        if m:
            return m.group(1)
    return None


def classify_url(url: str) -> dict:
    """Classify any pasted social-media URL into a scan plan.

    Used by /v1/scan/link so the UI can be a single input box: paste
    anything, OMI figures out what to scan and runs the comprehensive
    flow automatically.

    Returns a dict with:
      * ``platform``: "youtube" | "unknown"
      * ``kind``:     "video" | "channel" | "unknown"
      * ``video_id``:      11-char video ID if kind=="video"
      * ``account_input``: original string if kind=="channel" (resolved server-side)
      * ``label``:    short human-readable description, for the live UI hint
    """
    url = (url or "").strip()
    if not url:
        return {"platform": "unknown", "kind": "unknown", "video_id": None,
                "account_input": None, "label": "Paste a link to begin."}

    # Try YouTube video first — more specific patterns (watch?v=, /shorts/, youtu.be/, etc.)
    video_id = parse_video_id(url)
    if video_id:
        return {
            "platform": "youtube",
            "kind": "video",
            "video_id": video_id,
            "account_input": None,
            "label": "YouTube video detected — will scan video, every commenter, their histories, and detect coordination across the batch.",
        }

    # Try channel patterns (handles, /channel/, /c/, /user/, raw UC ids, @handle)
    kind, _ = parse_channel_input(url)
    if kind != "unknown":
        return {
            "platform": "youtube",
            "kind": "channel",
            "video_id": None,
            "account_input": url,
            "label": "YouTube channel detected — will deep-scan the account, pull recent history, build a behavioral fingerprint, and match against the database.",
        }

    return {
        "platform": "unknown",
        "kind": "unknown",
        "video_id": None,
        "account_input": None,
        "label": "Unrecognized link. Paste a YouTube video or channel URL.",
    }


def parse_channel_input(s: str) -> tuple[str, str]:
    """Classify the user's channel-ish input.

    Returns ``(kind, value)`` where kind is one of:
      * ``"channel_id"`` — already a UC… ID, value is that ID
      * ``"handle"`` — a @handle (with the leading @)
      * ``"legacy"`` — an old /c/foo or /user/foo path
      * ``"unknown"`` — couldn't parse anything
    """
    if not s:
        return ("unknown", "")
    s = s.strip()
    m = _CHANNEL_ID_RE.match(s)
    if m:
        return ("channel_id", m.group(1))
    m = _CHANNEL_URL_RE.search(s)
    if m:
        return ("channel_id", m.group(1))
    m = _HANDLE_URL_RE.search(s)
    if m:
        return ("handle", "@" + m.group(1))
    if s.startswith("@"):
        return ("handle", s)
    m = _LEGACY_RE.search(s)
    if m:
        return ("legacy", m.group(1))
    return ("unknown", s)


def resolve_channel_id(
    client: YouTubeClient,
    input_str: str,
    *,
    stats: FetchStats | None = None,
) -> str | None:
    """Turn whatever the user pasted into a stable UC… channel ID."""
    stats = stats or FetchStats()
    kind, value = parse_channel_input(input_str)
    if kind == "channel_id":
        return value
    if kind == "handle":
        try:
            response = (
                client.channels()
                .list(part="id", forHandle=value, maxResults=1)
                .execute()
            )
        except Exception:
            return None
        stats.quota_used += 1
        items = response.get("items", [])
        return items[0].get("id") if items else None
    if kind == "legacy":
        try:
            response = (
                client.channels()
                .list(part="id", forUsername=value, maxResults=1)
                .execute()
            )
        except Exception:
            return None
        stats.quota_used += 1
        items = response.get("items", [])
        return items[0].get("id") if items else None
    return None


class YouTubeClient(Protocol):
    """Minimal surface we use. Both the real Google client and test fakes
    implement this via duck-typing on the ``.commentThreads()`` / ``.channels()``
    builder pattern."""

    def commentThreads(self) -> Any: ...
    def channels(self) -> Any: ...


def build_default_client(api_key: str) -> YouTubeClient:
    """Construct the production YouTube Data API v3 client.

    Lazy import — ``google-api-python-client`` is an optional extra.
    """
    try:
        from googleapiclient.discovery import build  # type: ignore
    except ImportError as e:
        raise RuntimeError(
            "google-api-python-client is not installed. "
            "Install with `pip install omi-api[youtube]`."
        ) from e
    return build("youtube", "v3", developerKey=api_key, cache_discovery=False)


# ---------------------------------------------------------------------------
# Fetch primitives
# ---------------------------------------------------------------------------


@dataclass
class FetchStats:
    quota_used: int = 0


def fetch_video_commenters(
    client: YouTubeClient,
    video_id: str,
    *,
    max_commenters: int = 100,
    stats: FetchStats | None = None,
) -> list[dict[str, Any]]:
    """Return a deduplicated list of commenter records ``{channel_id, handle, sample_text}``.

    Each commenter appears once even if they posted multiple comments under
    the video. We collect a short ``sample_text`` to give the operator
    something to eyeball; the full history is fetched per-commenter below.
    """
    stats = stats or FetchStats()
    seen: dict[str, dict[str, Any]] = {}
    next_token: str | None = None

    while len(seen) < max_commenters:
        params = {
            "part": "snippet",
            "videoId": video_id,
            "maxResults": min(100, max_commenters - len(seen)),
            "textFormat": "plainText",
        }
        if next_token:
            params["pageToken"] = next_token

        response = client.commentThreads().list(**params).execute()
        stats.quota_used += 1

        for item in response.get("items", []):
            snippet = item.get("snippet", {}).get("topLevelComment", {}).get("snippet", {})
            channel_id = snippet.get("authorChannelId", {}).get("value")
            if not channel_id or channel_id in seen:
                continue
            seen[channel_id] = {
                "channel_id": channel_id,
                "handle": snippet.get("authorDisplayName") or channel_id,
                "avatar_url": snippet.get("authorProfileImageUrl"),
                "sample_text": snippet.get("textDisplay", ""),
            }
            if len(seen) >= max_commenters:
                break

        next_token = response.get("nextPageToken")
        if not next_token:
            break

    return list(seen.values())


def fetch_channel_profile(
    client: YouTubeClient,
    channel_id: str,
    *,
    stats: FetchStats | None = None,
) -> Profile | None:
    """Look up the channel's metadata and normalize to a ``Profile``."""
    stats = stats or FetchStats()
    response = (
        client.channels()
        .list(part="snippet,statistics", id=channel_id, maxResults=1)
        .execute()
    )
    stats.quota_used += 1
    items = response.get("items", [])
    if not items:
        return None
    item = items[0]
    snippet = item.get("snippet", {})
    stats_block = item.get("statistics", {}) or {}
    return Profile(
        platform="youtube",
        handle=snippet.get("customUrl") or snippet.get("title") or channel_id,
        display_name=snippet.get("title"),
        bio=snippet.get("description"),
        follower_count=_int_or_none(stats_block.get("subscriberCount")),
        following_count=None,  # YouTube doesn't expose following counts.
        created_at=_iso_or_none(snippet.get("publishedAt")),
        avatar_url=(snippet.get("thumbnails") or {}).get("default", {}).get("url"),
    )


def fetch_channel_recent_comments(
    client: YouTubeClient,
    channel_id: str,
    *,
    max_comments: int = 50,
    stats: FetchStats | None = None,
) -> list[Post]:
    """Pull this channel's recent top-level comments across YouTube."""
    stats = stats or FetchStats()
    out: list[Post] = []
    next_token: str | None = None

    while len(out) < max_comments:
        params = {
            "part": "snippet",
            "allThreadsRelatedToChannelId": channel_id,
            "maxResults": min(100, max_comments - len(out)),
            "textFormat": "plainText",
        }
        if next_token:
            params["pageToken"] = next_token

        try:
            response = client.commentThreads().list(**params).execute()
        except Exception:
            # Some channels have comments disabled or restricted; treat as no history.
            break
        stats.quota_used += 1

        for item in response.get("items", []):
            top = item.get("snippet", {}).get("topLevelComment", {})
            sn = top.get("snippet", {})
            author_channel = sn.get("authorChannelId", {}).get("value")
            # Filter to comments *by* this channel; the API also returns
            # comments on this channel's videos written by others.
            if author_channel != channel_id:
                continue
            text = sn.get("textDisplay") or ""
            ts = _iso_or_none(sn.get("publishedAt"))
            if not ts:
                continue
            video_id = sn.get("videoId") or item.get("snippet", {}).get("videoId")
            out.append(
                Post(
                    id=top.get("id") or f"yt:{len(out)}",
                    author_handle=sn.get("authorDisplayName") or channel_id,
                    text=text,
                    created_at=ts,
                    parent_id=video_id,
                    like_count=_int_or_none(sn.get("likeCount")),
                )
            )
            if len(out) >= max_comments:
                break

        next_token = response.get("nextPageToken")
        if not next_token:
            break

    return out


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------


def _int_or_none(v: Any) -> int | None:
    if v is None:
        return None
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _iso_or_none(v: Any) -> datetime | None:
    if not v:
        return None
    try:
        return date_parser.isoparse(v)
    except (TypeError, ValueError):
        return None


def fetch_video_full(
    client: YouTubeClient,
    video_id: str,
    *,
    max_commenters: int = 100,
    max_comments: int | None = None,
    stats: FetchStats | None = None,
    start_page_token: str | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], str | None]:
    """Iterate the video's comment pages; return commenters + all comments +
    the YouTube ``nextPageToken`` (or None if we've exhausted the thread).

    Pass the returned token back as ``start_page_token`` on a follow-up call
    to resume pagination — i.e. scan the next batch of commenters without
    re-fetching the ones already scanned.

    Returns ``(commenters, all_comments, next_page_token)``.
    """
    stats = stats or FetchStats()
    max_comments = max_comments or max(max_commenters * 3, 200)
    seen: dict[str, dict[str, Any]] = {}
    all_items: list[dict[str, Any]] = []
    next_token: str | None = start_page_token

    while len(seen) < max_commenters and len(all_items) < max_comments:
        params = {
            "part": "snippet",
            "videoId": video_id,
            "maxResults": 100,
            "textFormat": "plainText",
        }
        if next_token:
            params["pageToken"] = next_token
        response = client.commentThreads().list(**params).execute()
        stats.quota_used += 1

        for item in response.get("items", []):
            snippet = item.get("snippet", {}).get("topLevelComment", {}).get("snippet", {})
            channel_id = snippet.get("authorChannelId", {}).get("value")
            if not channel_id:
                continue
            ts = _iso_or_none(snippet.get("publishedAt"))
            if ts is None:
                continue
            all_items.append({
                "comment_id": item.get("snippet", {}).get("topLevelComment", {}).get("id")
                              or f"yt:{len(all_items)}",
                "author_external_id": channel_id,
                "text": snippet.get("textDisplay", "") or "",
                "created_at": ts,
            })
            if channel_id not in seen and len(seen) < max_commenters:
                seen[channel_id] = {
                    "channel_id": channel_id,
                    "handle": snippet.get("authorDisplayName") or channel_id,
                    "avatar_url": snippet.get("authorProfileImageUrl"),
                    "sample_text": snippet.get("textDisplay", ""),
                }
            if len(all_items) >= max_comments:
                break

        next_token = response.get("nextPageToken")
        if not next_token:
            break

    return list(seen.values()), all_items, next_token


# A "real" client is heavy; expose a Protocol checker for the route handler.
__all__ = [
    "YouTubeClient",
    "FetchStats",
    "parse_video_id",
    "parse_channel_input",
    "resolve_channel_id",
    "classify_url",
    "build_default_client",
    "fetch_video_commenters",
    "fetch_video_full",
    "fetch_channel_profile",
    "fetch_channel_recent_comments",
]


# Iterable kept for type compat in case someone implements an async fetcher.
_ = Iterable
