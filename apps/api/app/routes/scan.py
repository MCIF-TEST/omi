"""Multi-account scan endpoints.

The marquee route is ``POST /v1/scan/youtube/video``: paste a video URL,
get back a probabilistic authenticity assessment for every commenter,
backed by Omi's growing fingerprint store. Commenters seen in any prior
scan within the cache TTL are reused — and every fresh scan adds to the
intelligence base that future scans benefit from.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select

from app.core.auth import CurrentUser, compute_scan_credits, consume_credits, refund_credits, require_user
from app.core.config import Settings, get_settings
from app.integrations import youtube as yt
from app.integrations.source import Source, TwitterSource, YouTubeSource, classify_link
from app.integrations.youtube import (
    FetchStats,
    YouTubeClient,
    build_default_client,
    classify_url,
    fetch_channel_profile,
    fetch_channel_recent_comments,
    fetch_video_commenters,
    fetch_video_full,
    fetch_video_metadata,
    parse_video_id,
    resolve_channel_id,
)
from app.integrations.youtube_errors import (
    YouTubeAccessError,
    YouTubeAuthError,
    YouTubeClientError,
    YouTubeNotFoundError,
    YouTubeQuotaExceededError,
)
from app.integrations.twitter import (
    FetchStats as TwitterFetchStats,
    TwitterClient,
    build_default_client as build_default_twitter_client,
    fetch_user_profile as fetch_twitter_profile,
    fetch_user_recent_tweets,
    normalize_handle,
)
from app.integrations.twitter_errors import (
    TwitterAccessError,
    TwitterAuthError,
    TwitterClientError,
    TwitterNotFoundError,
    TwitterRateLimitError,
)
from app.orchestrator import (
    scan_account_with_memory,
    scan_comprehensive,
    scan_video_full,
)
from app.schemas import (
    AccountScanOut,
    CommenterScanResult,
    ComprehensiveScanRequest,
    ComprehensiveScanResult,
    CoordinationClusterOut,
    CrossLink,
    FullVideoScanRequest,
    FullVideoScanResult,
    MatrixRow,
    Tier,
    VideoScanRequest,
    VideoScanSummary,
)
from app.storage.db import get_session
from app.storage.repository import AccountRepository


router = APIRouter(prefix="/v1/scan", tags=["scan"])


def _handle_youtube_error(
    e: YouTubeClientError,
    *,
    user_id: int,
    credits_to_refund: int,
    target_input: str,
) -> "HTTPException":
    """Translate a typed YouTube error into an HTTPException, refunding the
    user's credit unless the failure was their fault (private content etc.).

    The audit log is updated by ``refund_credits`` so the analytics view
    can distinguish a real charge from a refunded one.
    """
    import logging
    log = logging.getLogger("omi.scan.youtube")

    if isinstance(e, YouTubeQuotaExceededError):
        refund_credits(user_id, credits_to_refund, reason="yt_quota")
        log.warning("YouTube quota exhausted: %s", e.admin_detail)
        # Pacific midnight reset; tell client to back off for a bit.
        return HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=e.user_message,
            headers={"Retry-After": "3600"},
        )
    if isinstance(e, YouTubeAuthError):
        refund_credits(user_id, credits_to_refund, reason="yt_auth")
        log.error("YouTube auth/config error: %s", e.admin_detail)
        return HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=e.user_message,
        )
    if isinstance(e, YouTubeNotFoundError):
        refund_credits(user_id, credits_to_refund, reason="yt_404")
        return HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=e.user_message,
        )
    if isinstance(e, YouTubeAccessError):
        # The lookup ran (we used quota). The user's URL was syntactically
        # fine, but YouTube refused to return data — private channel,
        # comments disabled, geo-block. Do not refund: the work happened.
        log.info("YouTube access denied for %s: %s", target_input[:80], e.admin_detail)
        # Suspension auto-labelling: YouTube's own moderation action is
        # high-quality ground truth. If this channel exists in our DB,
        # tag it 'suspended' so calibration can use it.
        if e.is_suspension:
            try:
                _autolabel_suspension(target_input)
            except Exception:
                log.exception("auto-label on suspension failed")
        return HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=e.user_message,
        )
    # Generic YouTubeClientError — assume transient.
    refund_credits(user_id, credits_to_refund, reason="yt_other")
    log.exception("Unexpected YouTube error: %s", e.admin_detail)
    return HTTPException(
        status_code=status.HTTP_502_BAD_GATEWAY,
        detail=e.user_message,
    )


def _autolabel_suspension(target_input: str) -> None:
    """When YouTube tells us a channel is suspended/closed, record that as
    a high-confidence ground-truth label on the local Account row (if any).

    Idempotent: existing suspension labels are touched rather than
    duplicated. Uses user_id=None because YouTube is the labeler, not a
    person — the source field carries that provenance.
    """
    from datetime import datetime, timezone
    from sqlalchemy import select
    from app.storage.db import get_session
    from app.storage.models import Account, AccountLabel

    # Pull the bare channel ID out of whatever the user pasted.
    channel_id = yt.parse_channel_input(target_input)[1] if target_input else None
    if not channel_id or not channel_id.startswith("UC"):
        return

    with get_session() as session:
        account = session.execute(
            select(Account).where(
                Account.platform == "youtube",
                Account.external_id == channel_id,
            )
        ).scalar_one_or_none()
        if account is None:
            return  # never seen this channel; nothing to label

        existing = session.execute(
            select(AccountLabel).where(
                AccountLabel.account_id == account.id,
                AccountLabel.source == "youtube_suspension",
            )
        ).scalar_one_or_none()
        if existing is not None:
            existing.created_at = datetime.now(timezone.utc)
            return

        session.add(AccountLabel(
            account_id=account.id,
            user_id=None,
            label="suspended",
            expected_tier="high",
            confidence="high",
            source="youtube_suspension",
            rationale="Auto-recorded: YouTube returned channelSuspended/channelClosed on rescan.",
        ))


# How many of an account's pulled posts ride along on a scan result. The evidence composer reads its
# per-account samples from here, so this is the ceiling on the history the Omi Analyst can ever see —
# anything dropped at this line is gone before the coverage budget (120k tokens, and its disclosed
# omission manifest) gets a say. Sized to the history we actually fetch per account
# (scan_max_history_per_commenter), so in practice nothing is dropped at all.
ACTIVITY_SAMPLE_LIMIT = 50


def _activity_payload(
    posts: list,
    tier: Tier,
    *,
    limit: int = ACTIVITY_SAMPLE_LIMIT,
    include_low: bool = True,
) -> tuple[list[dict], int]:
    """Build the recent_activity samples (the account's pulled posts/comments).

    Returns ``(samples, total)``. EVERY account with history gets samples: an empty list means the
    account genuinely has no pulled posts, and nothing else.

    This used to return no samples at all for low-tier accounts, to keep bulk payloads small. That was
    a UI-shaped decision applied to the model's evidence: the analyst was asked to say whether an
    account is a real person while being shown nothing that account ever wrote — and "reads like a
    real person" is exactly what exonerates the ~80% of commenters who are genuine. It also made the
    absence of history ambiguous, since "no posts" and "posts withheld" looked identical downstream.
    ``include_low`` is kept for callers that explicitly want the old narrow behaviour.
    """
    if not posts:
        return [], 0
    if tier == Tier.LOW and not include_low:
        return [], len(posts)
    samples: list[dict] = []
    for p in posts[:limit]:
        text = (getattr(p, "text", "") or "").strip()
        # 280 -> 600: the evidence layer renders up to 600 chars, so a tighter cut here was silently
        # deciding what the model could read. Long posts are where the tells live (copypasta, spun
        # phrasing, an engagement-farm CTA at the end).
        if len(text) > 600:
            text = text[:600] + "…"
        ts = getattr(p, "created_at", None)
        samples.append({
            "text": text,
            "created_at": ts.isoformat() if ts is not None else None,
            "parent_id": getattr(p, "parent_id", None),
            "like_count": getattr(p, "like_count", None),
            # Three fields the provider already parsed and this line used to throw away. They cost
            # roughly thirty bytes beside a 600-char text and no extra fetch, and each is
            # cross-account evidence the per-account signals cannot use but the coordination
            # detector can: `source_client` is the publishing tool (a shared third-party scheduler
            # is infrastructure, not style), and the two ids are who the account was talking to.
            "source_client": getattr(p, "source_client", None),
            "reply_to_id": getattr(p, "reply_to_id", None),
            "repost_of_id": getattr(p, "repost_of_id", None),
        })
    return samples, len(posts)


# How many of an account's comments UNDER THE SCANNED POST ride along on its scan result. Distinct
# from recent_activity, which is the account's own timeline: co-timing is only evidence when two
# accounts were commenting on the same thing, and this is the only place that is recorded.
THREAD_COMMENT_LIMIT = 20


def _thread_comment_payload(comments: list[dict] | None) -> list[dict]:
    """The account's own comments under the scanned post, with their real timestamps.

    These were collected on every scan, used by one in-process detector, and then dropped before
    persistence, so nothing after the scan could ever ask when an account commented. Kept small and
    text-truncated to match ``_activity_payload``.
    """
    if not comments:
        return []
    out: list[dict] = []
    for c in comments[:THREAD_COMMENT_LIMIT]:
        if not isinstance(c, dict):
            continue
        text = (c.get("text") or "").strip()
        if len(text) > 600:
            text = text[:600] + "…"
        ts = c.get("created_at")
        out.append({
            "text": text,
            "created_at": ts.isoformat() if hasattr(ts, "isoformat") else (ts or None),
            "comment_id": c.get("comment_id"),
            "parent_comment_id": c.get("parent_comment_id"),
        })
    return out


# Ceiling on the persisted arrival list. The true total and span ride alongside, so a truncated
# list still yields the exact global rate; only the local (per-neighbourhood) estimate degrades,
# and it degrades toward the global rate, which is the conservative direction.
THREAD_ARRIVAL_CAP = 5000


def _thread_arrivals(comments: list[dict] | None) -> tuple[list[int], int]:
    """Sorted epoch seconds for every comment under the post, plus the true count.

    Numbers only: no text, no author id, nothing about who said what. This exists so the
    coordination detector's arrival-rate null survives the scan, and it must stay complete over
    ALL authors rather than the scored subset. See ``FullVideoScanResult.thread_arrivals``.
    """
    if not comments:
        return [], 0
    stamps: list[int] = []
    for c in comments:
        if not isinstance(c, dict):
            continue
        ts = c.get("created_at")
        if hasattr(ts, "timestamp"):
            try:
                stamps.append(int(ts.timestamp()))
            except (OverflowError, ValueError, OSError):
                continue
    stamps.sort()
    total = len(stamps)
    if total > THREAD_ARRIVAL_CAP:
        # Keep a uniform sample so the SPAN is preserved; the total beside it restores the rate.
        step = total / THREAD_ARRIVAL_CAP
        stamps = [stamps[min(total - 1, int(i * step))] for i in range(THREAD_ARRIVAL_CAP)]
    return stamps, total


def _profile_fields(profile) -> dict:
    """The raw account metadata a scan result carries to the Omi Analyst.

    Returns keys the evidence composer reads by name (``follower_count``, ``following_count``,
    ``account_created_at``, ``bio``, ``verified``). A missing profile yields all-None — the honest
    "the platform didn't give us this", which the model is told to read as low confidence rather than
    as a signal.
    """
    if profile is None:
        return {"follower_count": None, "following_count": None, "account_created_at": None,
                "bio": None, "verified": None}
    return {
        "follower_count": getattr(profile, "follower_count", None),
        "following_count": getattr(profile, "following_count", None),
        "account_created_at": getattr(profile, "created_at", None),
        "bio": getattr(profile, "bio", None),
        "verified": getattr(profile, "verified", None),
    }


def _attach_content_titles(platform: str, samples: list[dict]) -> None:
    """Annotate recent-activity samples with the human-readable title of their
    parent content, when that content is already in our store.

    Readability only: it adds ``parent_title`` from the existing ContentEntity
    rows (no external fetch, no new persistence). Read-only and best-effort —
    it never raises into a scan, and samples whose parent isn't on file keep
    just their id/link, exactly as before.
    """
    ids = {s.get("parent_id") for s in samples if s.get("parent_id")}
    if not ids:
        return
    try:
        from app.storage.models import ContentEntity
        with get_session() as session:
            rows = session.execute(
                select(ContentEntity.content_id, ContentEntity.title).where(
                    ContentEntity.platform == platform,
                    ContentEntity.content_id.in_(ids),
                )
            ).all()
        titles = {cid: t for cid, t in rows if t}
        for s in samples:
            pid = s.get("parent_id")
            if pid and titles.get(pid):
                s["parent_title"] = titles[pid]
    except Exception:  # noqa: BLE001 — readability enrichment must never break a scan
        return


# Tests inject a fake client through this hook; production builds the real one.
def _resolve_client(settings: Settings) -> YouTubeClient:
    """Build the live YouTube client, or raise a clean, user-facing 503.

    Mirrors ``_resolve_twitter_client``: the admin-actionable cause (missing
    key / missing client library) goes to the logs, never to the user — an
    env-var name in an error message reads as an unfinished product.
    """
    import logging
    log = logging.getLogger("omi.scan.youtube")
    key = (settings.youtube_api_key or "").strip()
    if not key:
        log.error("YouTube scan requested but OMI_YOUTUBE_API_KEY is not set.")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "YouTube scanning isn't configured on this server yet. "
                "Please try again later."
            ),
        )
    try:
        return build_default_client(key)
    except RuntimeError as e:
        log.error("YouTube client unavailable: %s", e)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "YouTube scanning is temporarily unavailable on this server. "
                "Please try again later."
            ),
        )


# Module-level override for tests. Set to a callable returning a client and
# the route will use it instead of `_resolve_client`. Cleared in test teardown.
_client_factory_override = None


def set_client_factory_for_tests(factory) -> None:
    global _client_factory_override
    _client_factory_override = factory


@router.post("/youtube/video", response_model=VideoScanSummary)
def scan_youtube_video(
    req: VideoScanRequest,
    settings: Settings = Depends(get_settings),
    current: CurrentUser = Depends(require_user),
) -> VideoScanSummary:
    max_commenters = req.max_commenters or settings.scan_max_commenters
    cost = compute_scan_credits("youtube", max_commenters, settings)
    consume_credits(current.id, cost,
        platform="youtube", scan_type="youtube_video",
        target_input=req.video_url_or_id[:500], settings=settings)
    video_id = parse_video_id(req.video_url_or_id)
    if not video_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Could not parse a YouTube video ID from the input.",
        )

    factory = _client_factory_override or (lambda: _resolve_client(settings))
    client = factory()

    stats = FetchStats()
    try:
        commenters = fetch_video_commenters(
            client, video_id, max_commenters=max_commenters, stats=stats
        )
    except YouTubeClientError as e:
        raise _handle_youtube_error(
            e, user_id=current.id, credits_to_refund=cost,
            target_input=req.video_url_or_id,
        )

    results: list[CommenterScanResult] = []
    fresh = 0
    cached = 0

    with get_session() as session:
        for c in commenters:
            channel_id = c["channel_id"]
            try:
                # Cache fast path: avoid even fetching the profile if recent.
                if not req.force_refresh:
                    repo = AccountRepository(session)
                    hit = repo.cached_scan_within(
                        "youtube", channel_id, settings.scan_cache_ttl_days
                    )
                    if hit is not None:
                        acc, scan_row = hit
                        results.append(
                            CommenterScanResult(
                                external_id=channel_id,
                                handle=acc.handle or c["handle"],
                                display_name=acc.display_name,
                                avatar_url=c.get("avatar_url"),
                                overall_probability=scan_row.overall_probability,
                                confidence=scan_row.confidence,
                                tier=Tier(scan_row.tier),
                                summary=scan_row.summary,
                                from_cache=True,
                            )
                        )
                        cached += 1
                        continue

                profile = fetch_channel_profile(client, channel_id, stats=stats)
                if profile is None:
                    results.append(
                        CommenterScanResult(
                            external_id=channel_id,
                            handle=c["handle"],
                            avatar_url=c.get("avatar_url"),
                            overall_probability=0.5,
                            confidence=0.0,
                            tier=Tier.LOW,
                            summary="Channel metadata unavailable; no scan performed.",
                            from_cache=False,
                            error="channel_not_found",
                        )
                    )
                    continue

                history = fetch_channel_recent_comments(
                    client,
                    channel_id,
                    max_comments=settings.scan_max_history_per_commenter,
                    stats=stats,
                )

                scan = scan_account_with_memory(
                    session,
                    platform="youtube",
                    external_id=channel_id,
                    profile=profile,
                    posts=history,
                    force_refresh=req.force_refresh,
                )
                fresh += 1 if not scan.from_cache else 0
                cached += 1 if scan.from_cache else 0

                activity_samples, activity_total = _activity_payload(history, scan.result.tier)
                results.append(
                    CommenterScanResult(
                        external_id=channel_id,
                        handle=profile.handle,
                        display_name=profile.display_name,
                        avatar_url=c.get("avatar_url"),
                        overall_probability=scan.result.overall_probability,
                        confidence=scan.result.confidence,
                        tier=scan.result.tier,
                        summary=scan.result.summary,
                        from_cache=scan.from_cache,
                        matched_prior_neighbors=scan.matched_neighbors,
                        suspected_intent=scan.result.suspected_intent,
                        intent_label=scan.result.intent_label,
                        reasons=list(scan.result.reasons or []),
                        recent_activity=activity_samples,
                        activity_total=activity_total,
                        history_size=activity_total,
                        **_profile_fields(profile),
                    )
                )
            except YouTubeClientError:
                # Quota / auth errors are not per-commenter problems —
                # they affect the whole batch. Bail out and refund so
                # the rest of the commenters don't all log as failed.
                raise
            except Exception as e:  # noqa: BLE001 — quarantine per-commenter failures
                results.append(
                    CommenterScanResult(
                        external_id=channel_id,
                        handle=c["handle"],
                        avatar_url=c.get("avatar_url"),
                        overall_probability=0.5,
                        confidence=0.0,
                        tier=Tier.LOW,
                        summary="Scan failed for this commenter.",
                        from_cache=False,
                        error=type(e).__name__,
                    )
                )

        tier_counts = Counter(r.tier.value for r in results)
        with get_session() as logging_session:
            AccountRepository(logging_session).record_video_scan(
                platform="youtube",
                video_id=video_id,
                commenter_count=len(results),
                fresh_count=fresh,
                cached_count=cached,
                quota_used=stats.quota_used,
                tier_counts=dict(tier_counts),
            )

    # If the loop raised a typed YouTube error mid-flight, catch + refund
    # at the route boundary so partial progress doesn't strand the user.
    high_handles = sorted(
        (r.handle for r in results if r.tier in (Tier.HIGH, Tier.ELEVATED)),
    )

    summary_text = _video_summary_text(video_id, len(results), tier_counts, cached, fresh)

    return VideoScanSummary(
        video_id=video_id,
        commenter_count=len(results),
        fresh_count=fresh,
        cached_count=cached,
        quota_used=stats.quota_used,
        tier_distribution=dict(tier_counts),
        high_suspicion_handles=high_handles,
        summary=summary_text,
        commenters=results,
    )


@router.post("/youtube/full", response_model=FullVideoScanResult)
def scan_youtube_video_full(
    req: FullVideoScanRequest,
    settings: Settings = Depends(get_settings),
    current: CurrentUser = Depends(require_user),
) -> FullVideoScanResult:
    """Unified scan: every commenter (account-level), the whole comment thread
    (content-level), and cross-account coordination analysis, all in one
    call. The three perspectives cross-pollinate — commenters flagged in
    coordination clusters get adjusted scores, the video gets its own
    coordination verdict, and high-suspicion handles surface to the top.
    """
    max_commenters = req.max_commenters or settings.scan_max_commenters
    cost = compute_scan_credits("youtube", max_commenters, settings)
    consume_credits(current.id, cost,
        platform="youtube", scan_type="youtube_full",
        target_input=req.video_url_or_id[:500], settings=settings)
    video_id = parse_video_id(req.video_url_or_id)
    if not video_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Could not parse a YouTube video ID from the input.",
        )

    factory = _client_factory_override or (lambda: _resolve_client(settings))
    client = factory()

    stats = FetchStats()
    try:
        commenters_meta, all_comments, next_page_token = fetch_video_full(
            client, video_id,
            max_commenters=max_commenters,
            max_comments=max_commenters * 3,
            stats=stats,
            start_page_token=req.start_page_token,
        )

        def _profile(channel_id):
            return fetch_channel_profile(client, channel_id, stats=stats)

        def _history(channel_id, max_comments):
            return fetch_channel_recent_comments(
                client, channel_id, max_comments=max_comments, stats=stats
            )

        with get_session() as session:
            full = scan_video_full(
                session,
                platform="youtube",
                video_id=video_id,
                commenters_meta=commenters_meta,
                all_comments_under_video=all_comments,
                fetch_profile=_profile,
                fetch_history=_history,
                stats=stats,
                force_refresh=req.force_refresh,
            )
    except YouTubeClientError as e:
        raise _handle_youtube_error(
            e, user_id=current.id, credits_to_refund=cost,
            target_input=req.video_url_or_id,
        )

    with get_session() as session:

        commenter_results: list[CommenterScanResult] = []
        for r in full.commenter_records:
            activity_samples, activity_total = _activity_payload(r.posts, r.scan_result.tier)
            commenter_results.append(CommenterScanResult(
                external_id=r.external_id,
                handle=r.handle,
                display_name=r.display_name,
                avatar_url=r.avatar_url,
                overall_probability=r.scan_result.overall_probability,
                confidence=r.scan_result.confidence,
                tier=r.scan_result.tier,
                summary=r.scan_result.summary,
                from_cache=r.from_cache,
                matched_prior_neighbors=r.matched_neighbors,
                error=r.error,
                coordination_adjusted_probability=r.coordination_adjusted_probability,
                coordination_evidence=r.coordination_evidence,
                suspected_intent=r.scan_result.suspected_intent,
                intent_label=r.scan_result.intent_label,
                reasons=list(r.scan_result.reasons or []),
                weak_signals=list(r.scan_result.weak_signals or []),
                score_adjustments=list(r.scan_result.score_adjustments or []),
                signals=list(r.scan_result.signals or []),
                contributions=list(r.scan_result.contributions or []),
                recent_activity=activity_samples,
                activity_total=activity_total,
                history_size=activity_total,
                thread_comments=_thread_comment_payload(r.thread_comments),
                **_profile_fields(r.profile),
            ))

        tier_counts = Counter(r.tier.value for r in commenter_results)
        high_handles = sorted(
            r.handle for r in commenter_results
            if r.tier in (Tier.HIGH, Tier.ELEVATED)
            or (r.coordination_adjusted_probability or 0) >= 0.5
        )

        # Persist the aggregate VideoScan row.
        with get_session() as logging_session:
            AccountRepository(logging_session).record_video_scan(
                platform="youtube",
                video_id=video_id,
                commenter_count=len(commenter_results),
                fresh_count=full.fresh_count,
                cached_count=full.cached_count,
                quota_used=full.quota_used,
                tier_counts=dict(tier_counts),
                coordination_score=full.coordination_score,
            )

        # Phase 10 — persist content intelligence (fire-and-forget background).
        from app.core import background as _bg
        _bg.submit(
            _record_content_intelligence_async,
            "youtube",
            video_id,
            all_comments,
            {r.external_id: r.handle for r in full.commenter_records},
            dict(tier_counts),
            full.coordination_score,
            full.coordination_tier.value,
            current.id,
            client,
            stats,
            next_page_token,
        )

        # Phase C: run reply-pod detection on the live comment list and surface
        # pods as additional coordination clusters in the response.
        from app.detection.coordination.reply_pods import (
            ReplyEvent as _ReplyEvent,
            detect_reply_pods as _detect_reply_pods,
        )
        _pod_events = [
            _ReplyEvent(
                comment_id=c["comment_id"],
                parent_comment_id=c.get("parent_comment_id"),
                author_external_id=c["author_external_id"],
                posted_at=c["created_at"],
            )
            for c in all_comments
            if c.get("comment_id") and c.get("author_external_id") and c.get("created_at")
        ]
        _raw_pods = _detect_reply_pods(_pod_events) if _pod_events else []
        pod_clusters = [
            CoordinationClusterOut(
                method="reply_pod",
                members=pod.members,
                score=pod.score,
                evidence=pod.evidence,
                metadata={"interaction_count": float(sum(pod.pair_counts.values()))},
            )
            for pod in _raw_pods
        ]
        all_clusters = [
            CoordinationClusterOut(
                method=cl.method,
                members=cl.members,
                score=cl.score,
                evidence=cl.evidence,
                metadata=cl.metadata,
            )
            for cl in full.coordination_clusters
        ] + pod_clusters

        focus = None
        if req.focus_account_external_id:
            focus = next(
                (c for c in commenter_results
                 if c.external_id == req.focus_account_external_id),
                None,
            )

        summary = _full_summary_text(
            video_id=video_id,
            total=len(commenter_results),
            tier_counts=tier_counts,
            coord_score=full.coordination_score,
            cached=full.cached_count,
            fresh=full.fresh_count,
            n_clusters=len(all_clusters),
            thread_prob=full.thread_scan.overall_probability,
        )

        return FullVideoScanResult(
            video_id=video_id,
            platform="youtube",
            commenter_count=len(commenter_results),
            fresh_count=full.fresh_count,
            cached_count=full.cached_count,
            quota_used=full.quota_used,
            tier_distribution=dict(tier_counts),
            high_suspicion_handles=high_handles,
            commenters=commenter_results,
            thread_scan=full.thread_scan,
            coordination_score=full.coordination_score,
            coordination_tier=full.coordination_tier,
            clusters=all_clusters,
            focus_account=focus,
            summary=summary,
            next_page_token=next_page_token,
        )


@router.post("/youtube/account", response_model=AccountScanOut)
def scan_youtube_account(
    payload: dict,
    settings: Settings = Depends(get_settings),
    current: CurrentUser = Depends(require_user),
) -> AccountScanOut:
    """Deep-scan a single YouTube account by URL/handle/channel ID.

    Costs 1 credit per call.
    """
    account_input = (payload or {}).get("account_url_or_handle") or ""
    force_refresh = bool((payload or {}).get("force_refresh", False))
    if not account_input.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="account_url_or_handle is required.",
        )
    consume_credits(current.id, 1,
        platform="youtube", scan_type="youtube_account",
        target_input=account_input[:500], settings=settings)

    factory = _client_factory_override or (lambda: _resolve_client(settings))
    client = factory()
    stats = FetchStats()

    try:
        channel_id = resolve_channel_id(client, account_input, stats=stats)
        if not channel_id:
            # Refund and 404 — user input couldn't be matched to a channel,
            # but the lookup itself ran cleanly (no quota burned).
            refund_credits(current.id, 1, reason="yt_unresolved")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Could not resolve a YouTube channel from '{account_input}'.",
            )
        profile = fetch_channel_profile(client, channel_id, stats=stats)
        if profile is None:
            refund_credits(current.id, 1, reason="yt_no_profile")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="YouTube returned no profile for the resolved channel.",
            )
        history = fetch_channel_recent_comments(
            client, channel_id,
            max_comments=settings.scan_max_history_per_commenter,
            stats=stats,
        )
    except YouTubeClientError as e:
        raise _handle_youtube_error(
            e, user_id=current.id, credits_to_refund=1,
            target_input=account_input,
        )

    with get_session() as session:
        orch = scan_account_with_memory(
            session,
            platform="youtube",
            external_id=channel_id,
            profile=profile,
            posts=history,
            force_refresh=force_refresh,
        )

    # A single-account scan is an explicit deep dive — always surface the
    # pulled comment history (any tier) and show more of it than the bulk view.
    activity_samples, activity_total = _activity_payload(
        history, orch.result.tier, limit=30, include_low=True
    )
    _attach_content_titles("youtube", activity_samples)
    return AccountScanOut(
        external_id=channel_id,
        handle=profile.handle,
        display_name=profile.display_name,
        avatar_url=profile.avatar_url,
        bio=profile.bio,
        follower_count=profile.follower_count,
        account_created_at=profile.created_at,
        overall_probability=orch.result.overall_probability,
        confidence=orch.result.confidence,
        tier=orch.result.tier,
        summary=orch.result.summary,
        signals=list(orch.result.signals),
        from_cache=orch.from_cache,
        matched_prior_neighbors=orch.matched_neighbors,
        history_size=len(history),
        suspected_intent=orch.result.suspected_intent,
        intent_label=orch.result.intent_label,
        reasons=list(orch.result.reasons or []),
        recent_activity=activity_samples,
        activity_total=activity_total,
    )


def _handle_twitter_error(
    e: TwitterClientError,
    *,
    user_id: int,
    credits_to_refund: int,
    target_input: str,
) -> "HTTPException":
    """Translate a typed Twitter error into an HTTPException, refunding the
    user's credit unless the failure was their fault (access/suspension)."""
    import logging
    log = logging.getLogger("omi.scan.twitter")

    if isinstance(e, TwitterRateLimitError):
        refund_credits(user_id, credits_to_refund, reason="tw_ratelimit")
        log.warning("Twitter rate limit hit: %s", e.admin_detail)
        return HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=e.user_message,
            headers={"Retry-After": "60"},
        )
    if isinstance(e, TwitterAuthError):
        refund_credits(user_id, credits_to_refund, reason="tw_auth")
        log.error("Twitter auth error: %s", e.admin_detail)
        return HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=e.user_message,
        )
    if isinstance(e, TwitterNotFoundError):
        refund_credits(user_id, credits_to_refund, reason="tw_404")
        return HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=e.user_message,
        )
    if isinstance(e, TwitterAccessError):
        # Lookup ran — the user's handle was valid but the account is
        # protected or suspended. Do not refund: the work happened.
        log.info("Twitter access denied for %s: %s", target_input[:80], e.admin_detail)
        return HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=e.user_message,
        )
    # Generic TwitterClientError — assume transient.
    refund_credits(user_id, credits_to_refund, reason="tw_other")
    log.exception("Unexpected Twitter error: %s", e.admin_detail)
    return HTTPException(
        status_code=status.HTTP_502_BAD_GATEWAY,
        detail=e.user_message,
    )


def _resolve_twitter_client(settings: Settings) -> TwitterClient:
    """Build the live Twitter client, or raise a clean, user-friendly 503.

    Called while constructing the Source — which the scan routes do BEFORE
    charging credits — so any failure here means the user is never billed. The
    user-facing message states that explicitly; the admin-actionable cause
    (missing key / missing httpx) goes to the logs, never to the user.
    """
    import logging
    log = logging.getLogger("omi.scan.twitter")

    key = (settings.twitter_api_key or "").strip()
    if not key:
        log.error("Twitter scan requested but OMI_TWITTER_API_KEY is not set.")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Twitter/X scanning isn't configured on this server yet. "
                "You have not been charged."
            ),
        )
    try:
        return build_default_twitter_client(key, base_url=settings.twitter_api_base_url)
    except RuntimeError as e:
        # Server-side construction failure (e.g. httpx not installed). A config
        # problem on our side, surfaced before any credit is charged.
        log.error("Twitter client unavailable: %s", e)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Twitter/X scanning is temporarily unavailable on this server. "
                "You have not been charged — this is a configuration issue on "
                "our side, not a problem with your link. Please try again later."
            ),
        )


# Module-level override for tests — mirrors the YouTube pattern.
_twitter_client_factory_override = None


def set_twitter_client_factory_for_tests(factory) -> None:
    global _twitter_client_factory_override
    _twitter_client_factory_override = factory


@router.post("/twitter/account", response_model=AccountScanOut)
def scan_twitter_account(
    payload: dict,
    settings: Settings = Depends(get_settings),
    current: CurrentUser = Depends(require_user),
) -> AccountScanOut:
    """Deep-scan a single Twitter/X account by URL or @handle.

    Costs 1 credit per call. The same platform-agnostic detection engine
    that scores YouTube commenters is applied here; Twitter's richer
    profile data (follower/following counts, account age, verification,
    per-tweet engagement) fully powers the community-anchor, profile,
    engagement, and temporal detectors.
    """
    account_input = (payload or {}).get("account_url_or_handle") or ""
    force_refresh = bool((payload or {}).get("force_refresh", False))
    if not account_input.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="account_url_or_handle is required.",
        )

    handle = normalize_handle(account_input)
    if not handle:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Could not parse a Twitter/X handle from the input. "
                "Provide a handle (e.g. '@elonmusk'), URL, or bare username."
            ),
        )

    # Resolve the client BEFORE charging: a missing key / missing httpx then
    # 503s for free (never billing the user, keeping the "not charged" message
    # true) instead of charging at line 1 and stranding the credit on a config
    # error that escapes the refund path below.
    factory = _twitter_client_factory_override or (lambda: _resolve_twitter_client(settings))
    client = factory()

    consume_credits(current.id, settings.credits_per_twitter_account,
        platform="x", scan_type="twitter_account",
        target_input=account_input[:500], settings=settings)
    stats = TwitterFetchStats()

    try:
        profile = fetch_twitter_profile(client, handle, stats=stats)
        if profile is None:
            refund_credits(current.id, settings.credits_per_twitter_account, reason="tw_no_profile")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No Twitter/X profile found for '{handle}'.",
            )
        posts = fetch_user_recent_tweets(
            client, handle,
            max_tweets=settings.scan_twitter_max_history,
            stats=stats,
        )
    except TwitterClientError as e:
        raise _handle_twitter_error(
            e, user_id=current.id,
            credits_to_refund=settings.credits_per_twitter_account,
            target_input=account_input,
        )

    with get_session() as session:
        orch = scan_account_with_memory(
            session,
            platform="x",
            external_id=handle,
            profile=profile,
            posts=posts,
            force_refresh=force_refresh,
        )

    activity_samples, activity_total = _activity_payload(
        posts, orch.result.tier, limit=30, include_low=True
    )
    _attach_content_titles("x", activity_samples)
    return AccountScanOut(
        external_id=handle,
        handle=profile.handle,
        display_name=profile.display_name,
        avatar_url=profile.avatar_url,
        bio=profile.bio,
        follower_count=profile.follower_count,
        account_created_at=profile.created_at,
        overall_probability=orch.result.overall_probability,
        confidence=orch.result.confidence,
        tier=orch.result.tier,
        summary=orch.result.summary,
        signals=list(orch.result.signals),
        from_cache=orch.from_cache,
        matched_prior_neighbors=orch.matched_neighbors,
        history_size=len(posts),
        suspected_intent=orch.result.suspected_intent,
        intent_label=orch.result.intent_label,
        reasons=list(orch.result.reasons or []),
        recent_activity=activity_samples,
        activity_total=activity_total,
    )


@router.get("/classify")
def classify_link_endpoint(url: str = "") -> dict:
    """Live URL classification for the UI: tells the operator what OMI will
    do with a pasted URL before they commit to scanning. No quota cost.
    Platform-aware (YouTube + X/Twitter)."""
    return classify_link(url)


def _hash_ip(ip: str | None) -> str:
    """Hash an IP for the demo log so we don't store raw addresses."""
    import hashlib
    h = hashlib.sha256()
    h.update((ip or "unknown").encode("utf-8"))
    h.update(b"omi-demo-salt-v1")
    return h.hexdigest()


def _client_ip(request) -> str | None:
    """Extract the originating client IP. Trusts X-Forwarded-For when present
    (Render terminates TLS in front of the app)."""
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else None


DEMO_MAX_COMMENTERS = 25  # free pre-login X scan: up to 25 repliers analyzed
# The anonymous free-scan flow (compile → select → analyze, X-only, 2 per IP) lives in scan_async.py
# as /v1/scan/demo/commenters + /v1/scan/demo/score — the SAME select-then-scan machinery the signed-in
# workspace uses. _hash_ip / _client_ip / DEMO_MAX_COMMENTERS below are shared by those endpoints.


@router.post("/link", response_model=ComprehensiveScanResult)
def scan_link(
    payload: dict,
    settings: Settings = Depends(get_settings),
    current: CurrentUser = Depends(require_user),
) -> ComprehensiveScanResult:
    """Single-input dispatcher. Paste any supported social-media URL; OMI
    classifies it (video vs. channel vs. …) and runs the appropriate
    comprehensive scan — the post, every commenter, their histories, and
    cross-account coordination — all in one shot.

    Credit cost: ceil(max_commenters / scan_batch_unit) × credits_per_batch[platform].
    YouTube default: 1 credit per 50 commenters. Twitter: 10 per 50.
    """
    url = (payload.get("url") or "").strip() if isinstance(payload, dict) else ""
    if not url:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="url is required.",
        )
    classification = classify_link(url)
    platform = classification.get("platform", "unknown")
    if platform == "unknown" or classification.get("kind") == "unknown":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Unrecognized link. Paste a YouTube video/channel URL or an "
                "X (Twitter) profile or tweet URL."
            ),
        )

    # max_commenters arrives via a raw dict (not the Pydantic ScanRequest), so
    # clamp it to the operator cap and parse defensively (bad input never 500s).
    try:
        requested_commenters = int(payload.get("max_commenters", 25) or 25)
    except (TypeError, ValueError):
        requested_commenters = 25
    max_commenters = max(1, min(requested_commenters, settings.scan_max_commenters))
    force_refresh = bool(payload.get("force_refresh", False))
    start_token = payload.get("start_page_token") or None

    # Build the platform-appropriate inputs + Source BEFORE charging, so a
    # mis-config (missing API key → 503) never bills the user. scan_comprehensive
    # is platform-agnostic (T0): the SAME engine runs for every platform.
    if platform == "x":
        creq = ComprehensiveScanRequest(
            video_url_or_id=classification.get("tweet_id"),      # a tweet → scan its repliers
            account_url_or_handle=classification.get("handle"),  # a profile/author → deep-scan it
            comments_text=None, max_commenters=max_commenters,
            force_refresh=force_refresh, start_page_token=start_token,
        )
        tw_factory = _twitter_client_factory_override or (lambda: _resolve_twitter_client(settings))
        source: Source = TwitterSource(tw_factory())
    else:  # youtube
        creq = ComprehensiveScanRequest(
            video_url_or_id=classification.get("video_id"),
            account_url_or_handle=classification.get("account_input"),
            comments_text=None, max_commenters=max_commenters,
            force_refresh=force_refresh, start_page_token=start_token,
        )
        yt_factory = _client_factory_override or (lambda: _resolve_client(settings))
        source = YouTubeSource(yt_factory())

    # Deduct credits (refunded on ANY failure below).
    cost = compute_scan_credits(platform, max_commenters, settings)
    consume_credits(
        current.id, cost,
        platform=platform, scan_type="link",
        target_input=url[:500], settings=settings,
    )

    import logging
    import time as _time
    log = logging.getLogger("omi.scan")
    t_scan = _time.time()
    # A failed scan must never cost a credit. Typed platform errors keep their
    # specific status (+ the no-refund policies inside the handlers); anything
    # else returns a clean 502 with a full refund.
    try:
        result = _run_comprehensive(
            creq, settings, current, _charge_credit=False, source=source,
        )
    except YouTubeClientError as e:
        raise _handle_youtube_error(
            e, user_id=current.id, credits_to_refund=cost, target_input=url[:500],
        )
    except TwitterClientError as e:
        raise _handle_twitter_error(
            e, user_id=current.id, credits_to_refund=cost, target_input=url[:500],
        )
    except HTTPException:
        refund_credits(current.id, cost, reason="scan_failed")
        raise
    except Exception:
        log.exception("comprehensive scan failed for %s", url[:120])
        refund_credits(current.id, cost, reason="scan_error")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="The scan failed unexpectedly and your credit was refunded. Please try again.",
        )
    log.info(
        "comprehensive scan finished in %.1fs (commenters=%s, tier=%s)",
        _time.time() - t_scan,
        (result.video.commenter_count if result.video else 0),
        result.overall_tier.value if hasattr(result.overall_tier, "value") else result.overall_tier,
    )

    # A scan where EVERY commenter errored is a systemic failure, not a result —
    # don't persist a uniformly-empty investigation or charge for it. (A partial
    # failure, where only some commenters errored, is a legitimate saveable result.)
    if _all_commenters_failed(result):
        refund_credits(current.id, cost, reason="scan_all_failed")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=(
                "The scan reached the platform but could not analyze any commenters. "
                "Your credit was refunded — please try again."
            ),
        )

    # ---- Phase 5: persist as a saved investigation (SYNCHRONOUS) ----
    # We persist BEFORE returning so the slug we hand back ALWAYS resolves: no
    # read-after-write 404, and never an empty-payload row. The cost is a single
    # indexed insert — the expensive work (scan + serialise) already happened, so
    # this adds negligible latency to a multi-second scan.
    #
    # Runs for BOTH authenticated users and the local-mode user (id=0): a solo
    # install still saves every scan. The persister resolves id=0 to the stable
    # local-user row so the FK holds. (The anonymous demo endpoint never reaches
    # here — it calls scan_comprehensive_endpoint directly — so demos aren't saved.)
    slug = _resolve_investigation_slug(
        requested_slug=payload.get("investigation_slug"), user_id=current.id,
    )
    result.investigation_slug = slug
    try:
        result_payload = _serialize_result(result)
    except Exception:
        log.exception("could not serialise investigation payload for %s", slug)
        # The scan succeeded and is already in the response. We refuse to persist
        # an empty payload, and we don't hand back a slug that points at nothing.
        result.investigation_slug = None
        return result

    saved = _persist_investigation(
        slug=slug,
        user_id=current.id,
        classification=classification,
        url=url,
        payload=result_payload,
    )
    if not saved:
        # Persistence genuinely failed after retries — the user keeps their
        # result, but we don't advertise a saved investigation that isn't there.
        log.error("investigation %s could not be persisted; returning unsaved result", slug)
        result.investigation_slug = None
    return result


def _clean_content_label(title: str | None) -> str | None:
    """Turn a raw video title / tweet text into a clean, single-line investigation label:
    collapse whitespace, take the first meaningful line, truncate long text with an ellipsis."""
    if not title:
        return None
    first_line = next((ln.strip() for ln in str(title).splitlines() if ln.strip()), "")
    t = " ".join(first_line.split()).strip()
    if not t:
        return None
    return (t[:157].rstrip() + "…") if len(t) > 160 else t


def _investigation_label(classification: dict, url: str) -> str:
    """Human label for an investigation. Falls back (when no real title is available) to a clean
    author/id form rather than the raw URL."""
    kind = classification.get("kind")
    if kind == "video" and classification.get("video_id"):
        return f"YouTube video {classification['video_id']}"
    if classification.get("tweet_id"):
        return f"X post {classification['tweet_id']}"
    if kind == "channel" and classification.get("account_input"):
        return f"Channel {classification['account_input']}"
    return f"Scan of {url[:200]}"


def _serialize_result(result) -> dict:
    """ComprehensiveScanResult → JSON-serializable dict via Pydantic v2."""
    return result.model_dump(mode="json")


# Ruling 2 (frozen architecture): scan-time AI inference is RETIRED. No component calls the endpoint
# before the Investigation Package is composed — there is exactly ONE endpoint request per
# investigation, owned by the AI Investigation Runtime and reachable only through the Composer path.
# Comment intelligence is therefore a projection of that ONE investigation (composed later, off the
# scan hot path), never a scan-time stage. The deterministic thread_scan remains the scan-time surface.


def _all_commenters_failed(result) -> bool:
    """True only when a video scan produced commenters and EVERY one carries an
    error (systemic failure). False for partial failures, empty/None videos, and
    non-video scans — so a legitimately partial result is still saved/charged."""
    video = getattr(result, "video", None)
    commenters = getattr(video, "commenters", None) if video is not None else None
    if not commenters:
        return False
    return all(getattr(c, "error", None) for c in commenters)


def _merge_payloads(existing: dict, new: dict) -> dict:
    """Merge a continuation batch into an existing payload.

    Strategy: take the new top-level synthesis fields, but APPEND any new
    commenters to the existing list (deduplicated by external_id). Other
    arrays (cross_links, matrix) take the latest values.
    """
    merged = dict(new)  # start with new top-level
    # Carry forward every top-level key the continuation batch does not have its own value for.
    # Without this, `dict(new)` silently DELETES anything that was grafted onto the payload after
    # the original scan: `analyst_assessment_v1` (the whole written assessment the customer paid
    # for), the shadow-comparison block, and `campaign_detection_v1`. A fresh scan result never
    # carries those keys, so a second batch was wiping the first batch's analysis every time.
    for key, value in existing.items():
        if key not in merged:
            merged[key] = value
    existing_video = (existing.get("video") or {}) if isinstance(existing.get("video"), dict) else {}
    new_video = (new.get("video") or {}) if isinstance(new.get("video"), dict) else {}
    if existing_video and new_video:
        seen_ids = {c.get("external_id") for c in existing_video.get("commenters", [])}
        appended = list(existing_video.get("commenters", []))
        for c in new_video.get("commenters", []):
            if c.get("external_id") not in seen_ids:
                appended.append(c)
                seen_ids.add(c.get("external_id"))
        new_video = dict(new_video)
        new_video["commenters"] = appended
        new_video["commenter_count"] = len(appended)
        merged["video"] = new_video
    return merged


@router.post("/comprehensive", response_model=ComprehensiveScanResult)
def scan_comprehensive_endpoint(
    req: ComprehensiveScanRequest,
    settings: Settings = Depends(get_settings),
    current: CurrentUser = Depends(require_user),
) -> ComprehensiveScanResult:
    """The unified intelligence endpoint (HTTP surface). Charges credits and
    runs on YouTube; the shared implementation scores any platform when a
    ``Source`` is injected internally (see ``scan_link``)."""
    return _run_comprehensive(req, settings, current, _charge_credit=True, source=None)


def _run_comprehensive(
    req: ComprehensiveScanRequest,
    settings: Settings,
    current: CurrentUser,
    *,
    _charge_credit: bool = True,
    source: "Source | None" = None,
) -> ComprehensiveScanResult:
    """Shared comprehensive-scan implementation. Platform-agnostic via the
    injected ``source`` (defaults to a YouTube source). Internal callers
    (scan_link, demo, bulk) pass ``_charge_credit=False`` + the platform Source.

    Provide any combination of:

    * **account_url_or_handle** — focus account to deep-scan
    * **video_url_or_id** — content (video/tweet) to scan every commenter on
    * **comments_text** — pasted comments / posts / threads (one per line)

    Each provided input is scanned, then the orchestrator computes cross-links
    describing how the inputs relate. Costs credits per batch of commenters
    scanned (see compute_scan_credits).
    """
    if not any([
        req.account_url_or_handle and req.account_url_or_handle.strip(),
        req.video_url_or_id and req.video_url_or_id.strip(),
        req.comments_text and req.comments_text.strip(),
    ]):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one of account_url_or_handle, video_url_or_id, or comments_text must be provided.",
        )

    max_comm = req.max_commenters or settings.scan_max_commenters
    cost = compute_scan_credits("youtube", max_comm, settings) if _charge_credit else 0
    if _charge_credit:
        consume_credits(
            current.id, cost,
            platform="youtube",
            scan_type="comprehensive",
            target_input=(req.video_url_or_id or req.account_url_or_handle or "")[:500],
            settings=settings,
        )

    # Default to a YouTube source when none is injected (direct /comprehensive,
    # demo, bulk). scan_link injects a platform-appropriate Source (YouTube or
    # Twitter) so the SAME engine runs for every platform.
    if source is None:
        needs_client = bool(
            (req.account_url_or_handle and req.account_url_or_handle.strip())
            or (req.video_url_or_id and req.video_url_or_id.strip())
        )
        client = None
        if needs_client:
            factory = _client_factory_override or (lambda: _resolve_client(settings))
            client = factory()
        source = YouTubeSource(client)

    try:
        with get_session() as session:
            out = scan_comprehensive(
                session,
                account_url_or_handle=req.account_url_or_handle,
                video_url_or_id=req.video_url_or_id,
                comments_text=req.comments_text,
                max_commenters=max_comm,
                force_refresh=req.force_refresh,
                source=source,
                start_page_token=req.start_page_token,
                injected_commenters=req.injected_commenters,
                injected_comments=req.injected_comments,
            )
    except YouTubeClientError as e:
        # Refund + map here ONLY when this endpoint owns the charge. When called
        # internally with _charge_credit=False (scan_link, scan_demo, bulk), the
        # caller charged the real cost and owns the refund + HTTP mapping, so
        # propagate raw — otherwise the refund is computed against cost==0 and the
        # caller's real charge is never returned.
        if _charge_credit:
            raise _handle_youtube_error(
                e,
                user_id=current.id,
                credits_to_refund=cost,
                target_input=(req.video_url_or_id or req.account_url_or_handle or ""),
            )
        raise
    except Exception:
        # A failed scan never costs a credit. If we charged, refund before the
        # error surfaces; internal callers (cost==0 here) own their own refund.
        if _charge_credit:
            refund_credits(current.id, cost, reason="scan_error")
        raise

    # Convert to the response schemas
    focus_account_out = None
    if out.focus_account is not None:
        focus_account_out = AccountScanOut(**out.focus_account)

    video_result_out = None
    if out.video_output is not None:
        # Build the video result the same way /youtube/full does
        commenter_results: list[CommenterScanResult] = []
        for r in out.video_output.commenter_records:
            activity_samples, activity_total = _activity_payload(
                r.posts, r.scan_result.tier
            )
            commenter_results.append(CommenterScanResult(
                external_id=r.external_id,
                handle=r.handle,
                display_name=r.display_name,
                avatar_url=r.avatar_url,
                overall_probability=r.scan_result.overall_probability,
                confidence=r.scan_result.confidence,
                tier=r.scan_result.tier,
                summary=r.scan_result.summary,
                from_cache=r.from_cache,
                matched_prior_neighbors=r.matched_neighbors,
                error=r.error,
                coordination_adjusted_probability=r.coordination_adjusted_probability,
                coordination_evidence=r.coordination_evidence,
                suspected_intent=r.scan_result.suspected_intent,
                intent_label=r.scan_result.intent_label,
                reasons=list(r.scan_result.reasons or []),
                weak_signals=list(r.scan_result.weak_signals or []),
                score_adjustments=list(r.scan_result.score_adjustments or []),
                signals=list(r.scan_result.signals or []),
                contributions=list(r.scan_result.contributions or []),
                recent_activity=activity_samples,
                activity_total=activity_total,
                history_size=activity_total,
                thread_comments=_thread_comment_payload(r.thread_comments),
                **_profile_fields(r.profile),
            ))
        tier_counts = Counter(c.tier.value for c in commenter_results)
        high_handles = sorted(
            c.handle for c in commenter_results
            if c.tier in (Tier.HIGH, Tier.ELEVATED)
            or (c.coordination_adjusted_probability or 0) >= 0.5
        )

        # Phase 10 — persist content intelligence (the Content DB) for the
        # comprehensive scan path the product actually uses, mirroring the
        # /youtube/full handler. Fire-and-forget background write; only YouTube
        # video scans populate the YouTube content database (X and other sources
        # have no ContentEntity surface).
        if source.platform == "youtube":
            from app.core import background as _bg
            _bg.submit(
                _record_content_intelligence_async,
                "youtube",
                out.video_output.video_id,
                out.all_comments,
                {r.external_id: r.handle for r in out.video_output.commenter_records},
                dict(tier_counts),
                out.video_output.coordination_score,
                out.video_output.coordination_tier.value,
                current.id,
                getattr(source, "_client", None),
                source.stats,
                out.next_page_token,
            )

        arrivals, arrival_total = _thread_arrivals(out.video_output.all_thread_comments)
        video_result_out = FullVideoScanResult(
            video_id=out.video_output.video_id,
            platform=source.platform,
            commenter_count=len(commenter_results),
            fresh_count=out.video_output.fresh_count,
            cached_count=out.video_output.cached_count,
            quota_used=out.video_output.quota_used,
            tier_distribution=dict(tier_counts),
            high_suspicion_handles=high_handles,
            commenters=commenter_results,
            thread_scan=out.video_output.thread_scan,
            coordination_score=out.video_output.coordination_score,
            coordination_tier=out.video_output.coordination_tier,
            clusters=[
                CoordinationClusterOut(
                    method=cl.method, members=cl.members, score=cl.score,
                    evidence=cl.evidence, metadata=cl.metadata,
                )
                for cl in out.video_output.coordination_clusters
            ],
            focus_account=None,
            summary="",  # the comprehensive summary covers it
            thread_arrivals=arrivals,
            thread_arrival_total=arrival_total,
            next_page_token=out.next_page_token,
        )

    result = ComprehensiveScanResult(
        focus_account=focus_account_out,
        video=video_result_out,
        comments_scan=out.comments_scan,
        cross_links=[CrossLink(**l) for l in out.cross_links],
        convergence_score=out.convergence_score,
        matrix=[MatrixRow(**r) for r in out.matrix_rows],
        matrix_methods=out.matrix_methods,
        overall_tier=out.overall_tier,
        overall_probability=out.overall_probability,
        summary=out.summary,
        inputs_provided=out.inputs_provided,
        quota_used=out.quota_used,
        next_page_token=out.next_page_token,
        video_id=out.video_id,
    )
    # Ruling 2 (frozen architecture): NO AI inference at scan time. Comment intelligence now comes
    # from the single AI investigation (composed later, off the scan hot path), not a scan-time call —
    # so exactly one endpoint request occurs per investigation. The deterministic thread_scan stands.
    return result


def _full_summary_text(
    *, video_id: str, total: int, tier_counts: Counter, coord_score: float,
    cached: int, fresh: int, n_clusters: int, thread_prob: float,
) -> str:
    if total == 0:
        return f"No public commenters were retrievable for video {video_id}."
    high = tier_counts.get(Tier.HIGH.value, 0) + tier_counts.get(Tier.ELEVATED.value, 0)
    pct = round(100 * high / max(1, total))
    coord_pct = round(coord_score * 100)
    thread_pct = round(thread_prob * 100)
    parts = [
        f"Scanned {total} commenter{'s' if total != 1 else ''} on video {video_id}. "
        f"{pct}% individually exhibit patterns consistent with synthetic or "
        f"coordinated activity. Comment thread as a whole scores {thread_pct}% "
        f"for AI/coordinated content. Cross-account coordination signal: "
        f"{coord_pct}% over {n_clusters} detected cluster(s).",
        f"{cached} cached scans reused, {fresh} freshly scored and added to "
        f"the behavioral fingerprint store.",
        "All estimates are probabilistic, not definitive judgements.",
    ]
    return " ".join(parts)


def _resolve_investigation_slug(*, requested_slug: str | None, user_id: int) -> str:
    """Pick the slug for this scan, synchronously and collision-safely.

    A client-supplied slug is honoured ONLY when it names an investigation the
    caller already owns (a continuation batch). Otherwise a fresh server-side
    slug is minted. ``Investigation.slug`` is globally unique, so honouring a
    slug owned by a *different* user would collide on the unique constraint and
    silently fail to persist — this closes that hole while preserving the
    continuation workflow. Read-only: never creates the local-user row.
    """
    import logging
    import secrets

    if requested_slug:
        try:
            with get_session() as session:
                from app.storage.repository import AccountRepository
                repo = AccountRepository(session)
                eff = repo.local_user_id() if user_id == 0 else user_id
                if eff is not None and repo.get_investigation(
                    slug=requested_slug, user_id=eff
                ) is not None:
                    return requested_slug
        except Exception:
            logging.getLogger("omi.scan").exception(
                "slug ownership check failed for %s; minting a fresh slug",
                requested_slug,
            )
    return "inv_" + secrets.token_hex(4)


def _persist_investigation(
    *,
    slug: str,
    user_id: int,
    classification: dict,
    url: str,
    payload: dict,
    label_override: str | None = None,
) -> bool:
    """Persist (create or merge) an investigation row. Returns True on success.

    Called SYNCHRONOUSLY on the request thread so the slug handed back to the
    client always resolves — no read-after-write 404, no empty-payload row.
    Race-safe: a concurrent batch that creates the same owned slug first is
    absorbed (IntegrityError → retry, which finds the row and merges into it).
    Transient DB contention is retried with a short back-off. Never raises — the
    caller decides what to do when persistence ultimately fails.

    The payload dict is pre-serialised by the caller (no Pydantic objects here).
    """
    import logging
    import time as _time
    from sqlalchemy.exc import IntegrityError

    log = logging.getLogger("omi.scan")

    label = _clean_content_label(label_override) or _investigation_label(classification, url)
    target_id = classification.get("video_id") or classification.get("account_input")
    overall_probability = float(payload.get("overall_probability") or 0.0)
    overall_tier = str(payload.get("overall_tier") or "low")
    summary = str(payload.get("summary") or "")
    quota_used = int(payload.get("quota_used") or 0)

    for attempt in range(3):
        try:
            t0 = _time.time()
            created = False
            with get_session() as session:
                from app.storage.repository import AccountRepository
                repo = AccountRepository(session)
                # Local mode (id=0) has no real users row; resolve it to the
                # stable local-user id so the investigation FK holds and the
                # history accumulates under one owner.
                effective_user_id = (
                    repo.ensure_local_user_id() if user_id == 0 else user_id
                )
                # Always look up first — handles both new investigations and
                # continuation batches, and races where the first batch's save
                # hasn't committed yet when the second batch arrives.
                inv = repo.get_investigation(slug=slug, user_id=effective_user_id)
                if inv is None:
                    repo.create_investigation(
                        user_id=effective_user_id, slug=slug, label=label,
                        input_url=url[:500], target_id=target_id,
                        kind=classification.get("kind", "comprehensive"),
                        overall_probability=overall_probability,
                        overall_tier=overall_tier,
                        summary=summary,
                        quota_used=quota_used,
                        payload_json=payload,
                    )
                    created = True
                    log.info(
                        "investigation %s created in %.1fs", slug, _time.time() - t0
                    )
                else:
                    merged = _merge_payloads(inv.payload_json or {}, payload)
                    repo.update_investigation_payload(
                        inv,
                        payload_json=merged,
                        quota_used_delta=quota_used,
                        overall_probability=overall_probability,
                        overall_tier=overall_tier,
                        summary=summary,
                    )
                    log.info(
                        "investigation %s updated (batch %d) in %.1fs",
                        slug, inv.batch_count, _time.time() - t0,
                    )
            if created:
                # Wire the AI analyst into every investigation: schedule a background,
                # cached, exactly-once assessment now that the row is committed. This is the
                # missing link that makes a real investigation reach the live model endpoint —
                # a NO-OP unless OMI_ANALYST_ENABLED is set, so the default path is unchanged.
                from app.reasoning import analyst as _analyst
                _analyst.maybe_autogenerate(slug, effective_user_id)
            return True  # success — row is committed before we return
        except IntegrityError:
            # A concurrent batch created this slug between our lookup and insert.
            # Retry — the next pass finds the committed row and merges into it.
            log.warning("investigation %s create race — retrying as update", slug)
            _time.sleep(0.1 * (attempt + 1))
        except Exception as e:  # noqa: BLE001
            if attempt < 2:
                log.warning(
                    "investigation %s persistence attempt %d failed (%s) — retrying",
                    slug, attempt + 1, e,
                )
                _time.sleep(0.1 * (attempt + 1))
            else:
                log.exception(
                    "investigation %s persistence failed after 3 attempts", slug
                )
    return False


def _persist_reply_pods(session, entity, platform: str, content_id: str, log) -> None:
    """Run reply-pod detection on all stored comments for an entity and persist
    high-confidence pod pairs as CoordinationEdge rows.

    Updates ``entity.latest_reply_pod_count`` so the list page can show a
    badge without re-running the detector per request.
    """
    from datetime import datetime, timezone
    from sqlalchemy import select
    from app.storage.models import ContentComment, CoordinationEdge
    from app.detection.coordination.reply_pods import ReplyEvent, detect_reply_pods

    rows = list(session.execute(
        select(
            ContentComment.external_comment_id,
            ContentComment.parent_comment_id,
            ContentComment.author_external_id,
            ContentComment.observed_at,
        ).where(ContentComment.content_entity_id == entity.id)
    ).all())

    events = [
        ReplyEvent(
            comment_id=ext_id,
            parent_comment_id=parent_id,
            author_external_id=author,
            posted_at=ts,
        )
        for (ext_id, parent_id, author, ts) in rows
        if author
    ]
    pods = detect_reply_pods(events)
    entity.latest_reply_pod_count = len(pods)

    now = datetime.now(timezone.utc)
    for pod in pods:
        if pod.score < 0.50:
            continue
        members = sorted(pod.members)
        for i, acct_a in enumerate(members):
            for acct_b in members[i + 1:]:
                try:
                    existing = session.execute(
                        select(CoordinationEdge).where(
                            CoordinationEdge.platform == platform,
                            CoordinationEdge.account_a == acct_a,
                            CoordinationEdge.account_b == acct_b,
                        )
                    ).scalar_one_or_none()
                    if existing is not None:
                        n = existing.observation_count or 1
                        existing.observation_count = n + 1
                        existing.mean_cluster_score = (
                            existing.mean_cluster_score * n + pod.score
                        ) / (n + 1)
                        if "reply_pod" not in (existing.methods_json or []):
                            existing.methods_json = list(existing.methods_json or []) + ["reply_pod"]
                        existing.last_shared_parent = content_id
                        existing.last_observed_at = now
                    else:
                        session.add(CoordinationEdge(
                            platform=platform,
                            account_a=acct_a,
                            account_b=acct_b,
                            observation_count=1,
                            methods_json=["reply_pod"],
                            mean_cluster_score=pod.score,
                            last_shared_parent=content_id,
                            first_observed_at=now,
                            last_observed_at=now,
                        ))
                except Exception as edge_err:  # noqa: BLE001
                    log.warning("failed to upsert CoordinationEdge %s↔%s: %s", acct_a, acct_b, edge_err)


def _record_content_intelligence_async(
    platform: str,
    content_id: str,
    comments: list,
    handle_map: dict,
    tier_counts: dict,
    coordination_score: float,
    coordination_tier_value: str,
    user_id: int,
    client,
    stats,
    next_page_token: str | None = None,
) -> None:
    """Background worker — records a CommentBatch and upserts content intelligence.

    All failures are logged (not silently swallowed) so production scans
    keep a paper trail even when the optional intelligence write fails.
    """
    import logging
    log = logging.getLogger("omi.content")
    try:
        from app.content.service import ContentIntelligenceService
        from app.storage.db import get_session as _gs

        # Map coordination tier value to internal tier storage name.
        tier_map = {"low": "low", "moderate": "moderate", "elevated": "elevated", "high": "high"}
        risk_tier = tier_map.get(coordination_tier_value, "low")

        # Fetch video metadata opportunistically; don't fail if unavailable.
        meta: dict = {}
        if platform == "youtube":
            try:
                meta = fetch_video_metadata(client, content_id, stats=stats) or {}
            except Exception as e:  # noqa: BLE001
                log.warning("video metadata fetch failed for %s/%s: %s", platform, content_id, e)

        with _gs() as session:
            svc = ContentIntelligenceService(session)
            entity = svc.get_or_create_entity(
                platform=platform,
                content_id=content_id,
                kind="video",
                title=meta.get("title"),
                author_external_id=meta.get("author_external_id"),
                author_handle=meta.get("author_handle"),
                canonical_url=meta.get("canonical_url"),
                thumbnail_url=meta.get("thumbnail_url"),
            )
            svc.record_batch(
                entity=entity,
                user_id=user_id,
                comments=comments,
                handle_map=handle_map,
                coordination_score=coordination_score,
                risk_tier=risk_tier,
                tier_distribution=tier_counts,
                next_page_token=next_page_token,
            )

            # Phase C — run reply-pod detection on stored comments and persist
            # coordination edges so pods appear in the cross-video graph view.
            _persist_reply_pods(session, entity, platform, content_id, log)

            session.commit()
            log.info(
                "recorded batch for %s/%s: %d comments, %d new, next_token=%s",
                platform, content_id, len(comments),
                getattr(svc, "_last_new_count", 0),
                "yes" if next_page_token else "no",
            )
    except Exception as e:  # noqa: BLE001 — must not surface to caller
        log.exception("content intelligence recording failed for %s/%s: %s", platform, content_id, e)


def _video_summary_text(
    video_id: str, total: int, tier_counts: Counter, cached: int, fresh: int
) -> str:
    if total == 0:
        return f"No public commenters were retrievable for video {video_id}."
    high = tier_counts.get(Tier.HIGH.value, 0) + tier_counts.get(Tier.ELEVATED.value, 0)
    pct = round(100 * high / max(1, total))
    return (
        f"Scanned {total} commenter{'s' if total != 1 else ''} on video {video_id}. "
        f"{pct}% exhibit patterns consistent with synthetic or coordinated activity "
        f"(elevated or high suspicion). "
        f"{cached} reused cached scans; {fresh} freshly scored and added to the "
        f"behavioral fingerprint store. Probabilistic estimates only — see "
        f"per-commenter evidence for details."
    )
