"""Twitter/X ingestion (twitterapi.io adapter).

The detection engine is platform-agnostic — it scores the neutral ``Profile`` +
``Post`` schemas. This module is the *only* Twitter-specific code: it fetches a
user's profile and recent tweets from twitterapi.io and maps them onto those
schemas, after which the exact same detectors, decorrelation, community anchor,
single-axis cap, and contribution breakdown that power YouTube scoring apply
unchanged.

Twitter actually gives us a *richer* profile than YouTube — real follower AND
following counts, account age, verification, and per-tweet engagement — which
directly strengthens the community-anchor (GAP-07) and engagement detectors that
ran data-starved on YouTube.

The HTTP surface is intentionally tiny: a :class:`TwitterClient` is anything with
a ``get(path, params) -> dict`` method, so tests inject a fake with canned JSON
and no network is required. ``httpx`` is imported lazily inside the default
client so the rest of the API runs without it.
"""

from __future__ import annotations

import random
import re
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol

from dateutil import parser as date_parser

from app.integrations.twitter_errors import (
    TwitterClientError,
    translate_body_status,
    translate_status,
)
from app.schemas import Post, Profile

_DEFAULT_BASE_URL = "https://api.twitterapi.io"

# twitterapi.io paths.
_USER_INFO_PATH = "/twitter/user/info"
_USER_TWEETS_PATH = "/twitter/user/last_tweets"
# Tweet replies ("comments" on a tweet). NOTE: confirm this path/params against
# your twitterapi.io plan — the response envelope + pagination match the other
# endpoints, so only the path string should ever need adjusting.
_TWEET_REPLIES_PATH = "/twitter/tweet/replies"
_TWEETS_BY_ID_PATH = "/twitter/tweets"


def fetch_tweet_text(client: TwitterClient, tweet_id: str, stats: "FetchStats | None" = None) -> str | None:
    """Best-effort: the text of a single tweet, used to title an investigation. Returns None on any
    failure (the caller falls back to a generic label), so this never blocks a scan."""
    from app.integrations.twitter import FetchStats as _FS  # local import keeps module import light

    stats = stats or _FS()
    try:
        payload = client.get(_TWEETS_BY_ID_PATH, {"tweet_ids": tweet_id})
        stats.bump()
        data = _unwrap(payload)
        tweets = _extract_tweets(data) or _extract_tweets(payload)
        for tw in tweets:
            post = _map_tweet(tw, handle="")
            if post is not None and post.text:
                return post.text
    except Exception:
        return None
    return None


# ---------------------------------------------------------------------------
# Client surface
# ---------------------------------------------------------------------------


class TwitterClient(Protocol):
    """Minimal duck-typed surface. Real impl hits twitterapi.io over HTTPS;
    tests implement this directly."""

    def get(self, path: str, params: dict) -> dict: ...


@dataclass
class FetchStats:
    """Tracks how many upstream calls a scan made (for cost/observability).

    Thread-safe: the per-commenter fetch is bounded-concurrent, so the call
    counter is guarded — the count (and the per-call billing/quota proxy) stays
    accurate under parallel fetches. Use :meth:`bump`, not ``+= 1``.
    """

    api_calls: int = 0
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False, compare=False)

    def bump(self, n: int = 1) -> None:
        with self._lock:
            self.api_calls += n

    @property
    def quota_used(self) -> int:
        """Alias so Twitter stats satisfy the same `.quota_used` contract the
        shared scan path reads (twitterapi.io bills per call)."""
        return self.api_calls


class HttpTwitterClient:
    """Default twitterapi.io client. Auth via the ``X-API-Key`` header.

    Resilient to rate limits and transient blips: a 429 (or a network
    timeout/transport error) is retried up to ``max_retries`` times, honoring
    the ``Retry-After`` header when present, with capped, jittered backoff. This
    matters under the bounded-concurrency fetch (C>1), where a brief 429 burst
    would otherwise drop commenters from a large scan — the directive's
    optimize-for-completion goal. Backoff is bounded so a scan can't hang.
    """

    def __init__(self, api_key: str, *, base_url: str = _DEFAULT_BASE_URL,
                 timeout: float = 15.0, max_retries: int = 2,
                 max_backoff: float = 5.0) -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._max_retries = max_retries
        self._max_backoff = max_backoff

    def _backoff_seconds(self, attempt: int, retry_after: str | None) -> float:
        """Capped exponential backoff (0.5, 1, 2, …s) + jitter; the provider's
        Retry-After header wins when present and parseable."""
        wait = min(self._max_backoff, 0.5 * (2 ** attempt))
        if retry_after:
            try:
                wait = min(self._max_backoff, float(retry_after))
            except (TypeError, ValueError):
                pass
        return wait + random.uniform(0.0, 0.25)

    def get(self, path: str, params: dict) -> dict:
        try:
            import httpx
        except ImportError as e:  # pragma: no cover - guarded by build_default_client preflight
            # Typed (not a bare RuntimeError) so if this is ever reached mid-scan
            # it maps to a clean refund + specific message via
            # _handle_twitter_error, never the generic "scan failed unexpectedly".
            raise TwitterClientError(
                "Twitter/X scanning is temporarily unavailable on this server "
                "(a required component isn't installed). You were not charged.",
                admin_detail="httpx not installed; add it to the production dependencies.",
            ) from e

        url = f"{self._base_url}{path}"
        headers = {"X-API-Key": self._api_key}
        attempt = 0
        while True:
            try:
                resp = httpx.get(url, params=params, headers=headers, timeout=self._timeout)
            except (httpx.TimeoutException, httpx.TransportError) as e:
                if attempt < self._max_retries:
                    time.sleep(self._backoff_seconds(attempt, None))
                    attempt += 1
                    continue
                raise TwitterClientError(
                    "The Twitter data provider is unreachable or timed out.",
                    admin_detail=f"{type(e).__name__}: {e}",
                ) from e

            if resp.status_code == 429 and attempt < self._max_retries:
                time.sleep(self._backoff_seconds(attempt, resp.headers.get("Retry-After")))
                attempt += 1
                continue
            if resp.status_code >= 400:
                raise translate_status(resp.status_code, resp.text)
            try:
                return resp.json()
            except ValueError as e:
                raise TwitterClientError(
                    "The Twitter data provider returned a malformed response.",
                    admin_detail=resp.text[:500],
                ) from e


def httpx_available() -> bool:
    """True when httpx (required for live Twitter scanning) is importable.

    Powers a pre-charge preflight in :func:`build_default_client` + the
    ``/v1/status`` diagnostic, so a missing dependency surfaces as a clean,
    free 503 instead of a generic mid-scan crash that charges then refunds.
    """
    import importlib.util

    return importlib.util.find_spec("httpx") is not None


def build_default_client(api_key: str, *, base_url: str = _DEFAULT_BASE_URL) -> TwitterClient:
    if not api_key:
        raise RuntimeError("Twitter API key is not configured.")
    if not httpx_available():
        # Surfaced at client-construction time (which the routes do BEFORE
        # charging credits), so the user gets a clean 503 and is never billed.
        raise RuntimeError(
            "httpx is not installed, so live Twitter/X scanning is unavailable. "
            "Add httpx to the production dependencies and redeploy."
        )
    return HttpTwitterClient(api_key, base_url=base_url)


# ---------------------------------------------------------------------------
# URL / handle classification
# ---------------------------------------------------------------------------

_TWITTER_HOST_RE = re.compile(r"(?:^|\.)(twitter\.com|x\.com)$", re.I)
_HANDLE_RE = re.compile(r"^@?([A-Za-z0-9_]{1,15})$")
# Reserved path segments that are not user handles.
_RESERVED = {"home", "explore", "search", "i", "messages", "notifications",
             "settings", "compose", "hashtag", "intent"}


def classify_twitter_url(url: str) -> dict:
    """Classify a pasted string as a Twitter/X account (and extract the handle).

    Returns ``{platform, kind, handle}``. ``platform`` is ``"x"`` when this is a
    recognizable Twitter input, else ``"unknown"``. ``kind`` is ``"account"`` or
    ``"unknown"``. A bare ``@handle`` or ``handle`` is accepted too.
    """
    raw = (url or "").strip()
    if not raw:
        return {"platform": "unknown", "kind": "unknown", "handle": None}

    # Bare handle form.
    m = _HANDLE_RE.match(raw)
    if m and m.group(1).lower() not in _RESERVED:
        return {"platform": "x", "kind": "account", "handle": m.group(1)}

    # URL form.
    candidate = raw if "//" in raw else f"https://{raw}"
    try:
        from urllib.parse import urlparse

        parsed = urlparse(candidate)
    except ValueError:
        return {"platform": "unknown", "kind": "unknown", "handle": None}

    host = (parsed.netloc or "").lower().split(":")[0]
    if not _TWITTER_HOST_RE.search(host):
        return {"platform": "unknown", "kind": "unknown", "handle": None}

    segments = [s for s in (parsed.path or "").split("/") if s]
    if not segments:
        return {"platform": "x", "kind": "unknown", "handle": None}

    first = segments[0]
    # Tweet/status URL: /<handle>/status/<id> (the handle is the tweet author).
    if (
        len(segments) >= 3
        and segments[1].lower() in ("status", "statuses")
        and segments[2].isdigit()
    ):
        author = first if _HANDLE_RE.match(first) and first.lower() not in _RESERVED else None
        return {"platform": "x", "kind": "tweet", "tweet_id": segments[2], "handle": author}
    if first.lower() in _RESERVED:
        return {"platform": "x", "kind": "unknown", "handle": None}
    hm = _HANDLE_RE.match(first)
    if hm:
        return {"platform": "x", "kind": "account", "handle": hm.group(1)}
    return {"platform": "x", "kind": "unknown", "handle": None}


def parse_tweet_id(url_or_id: str) -> str | None:
    """Extract a numeric tweet id from a status URL or a bare id."""
    raw = (url_or_id or "").strip()
    if raw.isdigit():
        return raw
    info = classify_twitter_url(raw)
    return info.get("tweet_id") if info.get("kind") == "tweet" else None


def normalize_handle(value: str) -> str | None:
    """Extract a bare handle from a URL, @handle, or plain handle."""
    info = classify_twitter_url(value)
    return info.get("handle")


# ---------------------------------------------------------------------------
# Fetch + map
# ---------------------------------------------------------------------------


def _unwrap(payload: dict) -> dict:
    """twitterapi.io wraps results as ``{"status","msg","data":{...}}`` for some
    endpoints and returns flat objects for others. Raise on an error envelope;
    otherwise return the most useful object."""
    if not isinstance(payload, dict):
        raise TwitterClientError("Malformed provider response.",
                                 admin_detail=repr(payload)[:300])
    status = str(payload.get("status", "")).lower()
    if status == "error":
        raise translate_body_status(payload.get("msg") or payload.get("message") or "")
    data = payload.get("data")
    return data if isinstance(data, dict) else payload


def fetch_user_profile(
    client: TwitterClient, handle: str, *, stats: FetchStats | None = None
) -> Profile | None:
    """Look up a user's metadata and normalize to a ``Profile``."""
    stats = stats or FetchStats()
    payload = client.get(_USER_INFO_PATH, {"userName": handle})
    stats.bump()
    data = _unwrap(payload)

    user = data.get("user") if isinstance(data.get("user"), dict) else data
    username = user.get("userName") or user.get("screen_name") or user.get("username")
    if not username:
        return None

    return Profile(
        platform="x",
        handle=username,
        display_name=user.get("name"),
        bio=user.get("description"),
        follower_count=_int_or_none(user.get("followers") or user.get("followers_count")),
        following_count=_int_or_none(user.get("following") or user.get("friends_count")),
        created_at=_parse_twitter_date(user.get("createdAt") or user.get("created_at")),
        avatar_url=user.get("profilePicture") or user.get("profile_image_url_https"),
        verified=bool(user.get("isBlueVerified") or user.get("verified") or user.get("isVerified")),
    )


def fetch_user_recent_tweets(
    client: TwitterClient,
    handle: str,
    *,
    max_tweets: int = 50,
    stats: FetchStats | None = None,
) -> list[Post]:
    """Pull a user's most recent original tweets + replies, newest first.

    Paginates via the provider's cursor until ``max_tweets`` is reached or the
    feed is exhausted. Maps per-tweet engagement onto the ``Post`` schema so the
    engagement/temporal detectors get real signal.
    """
    stats = stats or FetchStats()
    out: list[Post] = []
    cursor: str | None = None
    seen_cursors: set[str] = set()

    while len(out) < max_tweets:
        params: dict[str, Any] = {"userName": handle}
        if cursor:
            params["cursor"] = cursor
        payload = client.get(_USER_TWEETS_PATH, params)
        stats.bump()
        data = _unwrap(payload)

        tweets = _extract_tweets(data)
        if not tweets:
            break

        for tw in tweets:
            post = _map_tweet(tw, handle)
            if post is not None:
                out.append(post)
                if len(out) >= max_tweets:
                    break

        # Pagination: look for has_next_page / next_cursor in both the envelope
        # and the data object.
        has_next = payload.get("has_next_page")
        if has_next is None:
            has_next = data.get("has_next_page")
        cursor = payload.get("next_cursor") or data.get("next_cursor")
        if not has_next or not cursor or cursor in seen_cursors:
            break
        seen_cursors.add(cursor)

    return out


def _extract_tweets(data: dict) -> list[dict]:
    """Find the tweet list across the provider's response shapes."""
    if isinstance(data.get("tweets"), list):
        return data["tweets"]
    inner = data.get("data")
    if isinstance(inner, dict) and isinstance(inner.get("tweets"), list):
        return inner["tweets"]
    if isinstance(data.get("results"), list):
        return data["results"]
    return []


# X wraps EVERY outbound link in a t.co short URL, so a bare t.co in tweet text
# is a platform artifact, not a promotional signal — yet the engagement detector
# (correctly) treats t.co as a link shortener. Leaving raw t.co in the text makes
# a legitimate link-sharer read as spam-like (measured ~0.72 engagement prob).
# We restore the real destination from the tweet's URL entities so the detector
# judges the ACTUAL domain (reuters.com vs bit.ly) — which preserves affiliate
# detection (a spammer's t.co expands back to its bit.ly/linktr.ee target) while
# clearing the false positive. A t.co with no expansion data carries no signal,
# so it is dropped rather than left to read as a shortener.
_TCO_TOKEN_RE = re.compile(r"https?://t\.co/\w+", re.I)


def _tco_expansions(tw: dict) -> dict[str, str]:
    """Map each t.co short URL to its expanded destination, reading whatever
    entity shape twitterapi.io returns (defensive across known variants)."""
    out: dict[str, str] = {}

    def _collect(items: Any) -> None:
        if not isinstance(items, list):
            return
        for it in items:
            if not isinstance(it, dict):
                continue
            short = it.get("url")
            full = (
                it.get("expanded_url") or it.get("expandedUrl")
                or it.get("unwound_url") or it.get("display_url") or it.get("displayUrl")
            )
            if isinstance(short, str) and "t.co/" in short and isinstance(full, str) and full:
                out[short] = full

    for container in (tw.get("entities"), tw.get("extendedEntities"), tw.get("extended_entities")):
        if isinstance(container, dict):
            _collect(container.get("urls"))
            _collect(container.get("media"))
    _collect(tw.get("urls"))  # some shapes expose a flat list on the tweet
    return out


def _expand_tco(text: str, tw: dict) -> str:
    """Replace t.co-wrapped URLs in tweet text with their real destination; drop
    any that have no expansion data (a bare t.co carries no promotional signal)."""
    if "t.co/" not in text:
        return text
    for short, full in _tco_expansions(tw).items():
        text = text.replace(short, full)
    return _TCO_TOKEN_RE.sub("", text).strip()


def _map_tweet(tw: dict, handle: str) -> Post | None:
    if not isinstance(tw, dict):
        return None
    text = _expand_tco(tw.get("text") or tw.get("full_text") or "", tw)
    ts = _parse_twitter_date(tw.get("createdAt") or tw.get("created_at"))
    if not ts:
        return None
    author = tw.get("author") if isinstance(tw.get("author"), dict) else {}
    author_handle = author.get("userName") or handle
    return Post(
        id=str(tw.get("id") or tw.get("id_str") or f"tw:{id(tw)}"),
        author_handle=author_handle,
        text=text,
        created_at=ts,
        reply_to_id=_str_or_none(tw.get("inReplyToId") or tw.get("in_reply_to_status_id_str")),
        like_count=_int_or_none(tw.get("likeCount") or tw.get("favorite_count")),
        reply_count=_int_or_none(tw.get("replyCount") or tw.get("reply_count")),
        repost_count=_int_or_none(tw.get("retweetCount") or tw.get("retweet_count")),
        source_client=_clean_source(tw.get("source")),
    )


def fetch_tweet_engagers(
    client: TwitterClient,
    tweet_id: str,
    *,
    max_commenters: int = 100,
    max_comments: int | None = None,
    stats: FetchStats | None = None,
    start_page_token: str | None = None,
) -> tuple[list[dict], list[dict], str | None]:
    """Fetch the accounts replying to a tweet (its "commenters") + the raw reply
    items, shaped to mirror YouTube's ``fetch_video_full`` output so the shared
    ``scan_video_full`` consumes it unchanged.

    Pass the returned cursor back as ``start_page_token`` to resume from where the
    last call stopped — this is what makes "add more commenters" page deeper into a
    big reply thread instead of re-fetching the first replies.

    Returns ``(commenters_meta, all_comments, next_cursor)`` where:
      * ``commenters_meta`` — one entry per unique replying account
        (``{"channel_id": handle, "handle": handle, "avatar_url": …}``); the
        ``channel_id`` is the handle so per-commenter profile/history fetches
        resolve through :class:`TwitterSource`.
      * ``all_comments`` — every reply (``{"comment_id","author_external_id",
        "text","created_at"}``), the thread corpus + co-engagement input.
    """
    stats = stats or FetchStats()
    max_comments = max_comments or max(max_commenters * 3, 100)
    commenters: dict[str, dict] = {}
    all_comments: list[dict] = []
    cursor: str | None = start_page_token
    seen_cursors: set[str] = set()
    next_cursor: str | None = None

    while len(commenters) < max_commenters and len(all_comments) < max_comments:
        params: dict[str, Any] = {"tweetId": tweet_id}
        if cursor:
            params["cursor"] = cursor
        payload = client.get(_TWEET_REPLIES_PATH, params)
        stats.bump()
        data = _unwrap(payload)

        tweets = _extract_tweets(data)
        if not tweets:
            break

        for tw in tweets:
            post = _map_tweet(tw, handle="")
            if post is None or not post.author_handle:
                continue
            author = post.author_handle
            all_comments.append({
                "comment_id": post.id,
                "author_external_id": author,
                "text": post.text,
                "created_at": post.created_at,
            })
            if author not in commenters and len(commenters) < max_commenters:
                a = tw.get("author") if isinstance(tw.get("author"), dict) else {}
                commenters[author] = {
                    "channel_id": author,
                    "handle": author,
                    "avatar_url": a.get("profilePicture") or a.get("profile_image_url_https"),
                }
            if len(all_comments) >= max_comments:
                break

        has_next = payload.get("has_next_page")
        if has_next is None:
            has_next = data.get("has_next_page")
        cursor = payload.get("next_cursor") or data.get("next_cursor")
        next_cursor = cursor
        if not has_next or not cursor or cursor in seen_cursors:
            break
        seen_cursors.add(cursor)

    return list(commenters.values()), all_comments, next_cursor


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


def _str_or_none(v: Any) -> str | None:
    if v is None:
        return None
    s = str(v).strip()
    return s or None


_SOURCE_TAG_RE = re.compile(r"<[^>]+>")


def _clean_source(v: Any) -> str | None:
    """Twitter's ``source`` is sometimes an anchor tag (``<a ...>Twitter for
    iPhone</a>``); strip to the label."""
    if not v:
        return None
    return _SOURCE_TAG_RE.sub("", str(v)).strip() or None


def _parse_twitter_date(v: Any) -> datetime | None:
    """Parse both the classic Twitter format ('Tue Jun 02 20:12:29 +0000 2009')
    and ISO-8601, returning a timezone-aware datetime."""
    if not v:
        return None
    try:
        return date_parser.parse(str(v))
    except (ValueError, OverflowError, TypeError):
        return None
