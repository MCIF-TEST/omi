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

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select

from app.core.auth import CurrentUser, consume_credits, refund_credits, require_user
from app.core.config import Settings, get_settings
from app.integrations import youtube as yt
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


def _activity_payload(posts: list, tier: Tier) -> tuple[list[dict], int]:
    """Build the recent_activity samples for a non-low-tier account.

    Returns (samples, total). Low-tier accounts get empty samples to keep
    the response payload small — the UI doesn't render activity for them.
    """
    if tier == Tier.LOW or not posts:
        return [], len(posts) if posts else 0
    samples: list[dict] = []
    for p in posts[:10]:
        text = (getattr(p, "text", "") or "").strip()
        if len(text) > 280:
            text = text[:280] + "…"
        ts = getattr(p, "created_at", None)
        samples.append({
            "text": text,
            "created_at": ts.isoformat() if ts is not None else None,
            "parent_id": getattr(p, "parent_id", None),
            "like_count": getattr(p, "like_count", None),
        })
    return samples, len(posts)


# Tests inject a fake client through this hook; production builds the real one.
def _resolve_client(settings: Settings) -> YouTubeClient:
    key = (settings.youtube_api_key or "").strip()
    if not key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "YouTube API key is not configured. Set OMI_YOUTUBE_API_KEY "
                "or use POST /v1/analyze/account with pre-fetched data."
            ),
        )
    try:
        return build_default_client(key)
    except RuntimeError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(e),
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
    consume_credits(current.id, 1,
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

    max_commenters = req.max_commenters or settings.scan_max_commenters
    stats = FetchStats()
    try:
        commenters = fetch_video_commenters(
            client, video_id, max_commenters=max_commenters, stats=stats
        )
    except YouTubeClientError as e:
        raise _handle_youtube_error(
            e, user_id=current.id, credits_to_refund=1,
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
    consume_credits(current.id, 1,
        platform="youtube", scan_type="youtube_full",
        target_input=req.video_url_or_id[:500], settings=settings)
    """Unified scan: every commenter (account-level), the whole comment thread
    (content-level), and cross-account coordination analysis, all in one
    call. The three perspectives cross-pollinate — commenters flagged in
    coordination clusters get adjusted scores, the video gets its own
    coordination verdict, and high-suspicion handles surface to the top.
    """
    video_id = parse_video_id(req.video_url_or_id)
    if not video_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Could not parse a YouTube video ID from the input.",
        )

    factory = _client_factory_override or (lambda: _resolve_client(settings))
    client = factory()

    max_commenters = req.max_commenters or settings.scan_max_commenters
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
            e, user_id=current.id, credits_to_refund=1,
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
                signals=list(r.scan_result.signals or []),
                recent_activity=activity_samples,
                activity_total=activity_total,
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

    activity_samples, activity_total = _activity_payload(history, orch.result.tier)
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


@router.get("/classify")
def classify_link_endpoint(url: str = "") -> dict:
    """Live URL classification for the UI: tells the operator what OMI will
    do with a pasted URL before they commit to scanning. No quota cost."""
    return classify_url(url)


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


@router.post("/demo", response_model=ComprehensiveScanResult)
def scan_demo(
    payload: dict,
    request: Request,
    settings: Settings = Depends(get_settings),
) -> ComprehensiveScanResult:
    """Anonymous demo scan — no auth required, no credits charged.

    Rate-limited to one scan per IP per 24h to keep YouTube quota under
    control. Capped at 10 commenters so the result lands in 5-10 seconds
    and the visitor sees real coordination output without any signup
    friction. After this they need an account to scan again, save the
    result, or unlock the rest of the platform.
    """
    from datetime import timedelta
    from app.storage.models import DemoScanLog

    url = (payload.get("url") or "").strip() if isinstance(payload, dict) else ""
    if not url:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="url is required.")

    classification = classify_url(url)
    if classification["kind"] != "video":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Demo scans only support YouTube video URLs right now. Paste a watch?v= or youtu.be link.",
        )

    ip = _client_ip(request)
    ip_hash = _hash_ip(ip)
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)

    # Rate limit: 1 successful demo per IP per 24h
    with get_session() as session:
        existing = session.execute(
            select(DemoScanLog).where(
                DemoScanLog.ip_hash == ip_hash,
                DemoScanLog.created_at >= cutoff,
                DemoScanLog.success == 1,
            ).limit(1)
        ).scalar_one_or_none()
        if existing is not None:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=(
                    "You've used your free demo for today. "
                    "Sign up to run more scans, save results, and unlock the full platform."
                ),
            )

    # Synthetic anonymous user just for the request — id=0 skips credit logic + persistence.
    from app.core.auth import CurrentUser
    anon = CurrentUser(
        id=0, email="demo@omi.local",
        credits_remaining=999, subscription_status="demo",
        subscription_renews_at=None, is_admin=False,
    )

    # Run the comprehensive scan with a smaller batch — demo only.
    creq = ComprehensiveScanRequest(
        video_url_or_id=classification.get("video_id"),
        account_url_or_handle=None,
        comments_text=None,
        max_commenters=10,
        force_refresh=False,
        start_page_token=None,
    )

    success_flag = 1
    try:
        result = scan_comprehensive_endpoint(creq, settings, current=anon, _charge_credit=False)
    except HTTPException:
        success_flag = 0
        raise
    finally:
        # Log the attempt either way so a failed demo doesn't grant an extra free one,
        # but only successful scans count toward the rate limit (success=1 above).
        with get_session() as session:
            session.add(DemoScanLog(
                ip_hash=ip_hash,
                video_id=classification.get("video_id") or url[:60],
                user_agent_snippet=(request.headers.get("user-agent") or "")[:200],
                success=success_flag,
            ))
            session.commit()

    return result


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

    Costs 1 credit per call (including continuation batches).
    """
    url = (payload.get("url") or "").strip() if isinstance(payload, dict) else ""
    if not url:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="url is required.",
        )
    classification = classify_url(url)
    if classification["kind"] == "unknown":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Unrecognized link. Paste a YouTube video or channel URL. "
                "(More platforms coming as Omi grows.)"
            ),
        )

    # Deduct one credit before running the scan. 402 if user is out.
    consume_credits(
        current.id, 1,
        platform="youtube",
        scan_type="link",
        target_input=url[:500],
        settings=settings,
    )

    creq = ComprehensiveScanRequest(
        video_url_or_id=classification.get("video_id"),
        account_url_or_handle=classification.get("account_input"),
        comments_text=None,
        max_commenters=int(payload.get("max_commenters", 25)),
        force_refresh=bool(payload.get("force_refresh", False)),
        start_page_token=payload.get("start_page_token") or None,
    )

    import logging
    import time as _time
    log = logging.getLogger("omi.scan")
    t_scan = _time.time()
    result = scan_comprehensive_endpoint(creq, settings, current=current, _charge_credit=False)
    log.info(
        "comprehensive scan finished in %.1fs (commenters=%s, tier=%s)",
        _time.time() - t_scan,
        (result.video.commenter_count if result.video else 0),
        result.overall_tier.value if hasattr(result.overall_tier, "value") else result.overall_tier,
    )

    # ---- Phase 5: persist as a saved investigation ----
    # Pre-generate the slug so we can stamp it on the response WITHOUT waiting
    # for the database write. Persistence is offloaded to a background worker
    # — if the DB is slow or the 200KB+ payload serialization stalls, the
    # user still gets their scan result immediately. The slug is reserved
    # client-side; on first follow-up scan the bg worker has long since
    # committed the row.
    if current.id != 0:  # skip in local mode
        import secrets
        existing_slug = payload.get("investigation_slug")
        slug = existing_slug or ("inv_" + secrets.token_hex(4))

        result_dict = result.model_dump()
        result_dict["investigation_slug"] = slug
        from app.schemas import ComprehensiveScanResult as CSR
        stamped = CSR.model_validate({**result_dict})

        # Offload persistence to the background pool.
        from app.core import background as _bg
        _bg.submit(
            _persist_investigation_async,
            slug=slug,
            existing=bool(existing_slug),
            user_id=current.id,
            classification=classification,
            url=url,
            result=result,
        )
        return stamped

    return result


def _investigation_label(classification: dict, url: str) -> str:
    """Generate a human label like 'Video mBuhgvJzAN0' or 'Channel @handle'."""
    kind = classification.get("kind")
    if kind == "video" and classification.get("video_id"):
        return f"Video {classification['video_id']}"
    if kind == "channel" and classification.get("account_input"):
        return f"Channel {classification['account_input']}"
    return f"Scan of {url[:200]}"


def _serialize_result(result) -> dict:
    """ComprehensiveScanResult → JSON-serializable dict via Pydantic v2."""
    return result.model_dump(mode="json")


def _merge_payloads(existing: dict, new: dict) -> dict:
    """Merge a continuation batch into an existing payload.

    Strategy: take the new top-level synthesis fields, but APPEND any new
    commenters to the existing list (deduplicated by external_id). Other
    arrays (cross_links, matrix) take the latest values.
    """
    merged = dict(new)  # start with new top-level
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
    _charge_credit: bool = True,
) -> ComprehensiveScanResult:
    """The unified intelligence endpoint — provide any combination of:

    * **account_url_or_handle** — focus account to deep-scan
    * **video_url_or_id** — video to scan every commenter on
    * **comments_text** — pasted comments / posts / threads (one per line)

    Each provided input is scanned, then the orchestrator computes
    cross-links describing how the inputs relate (focus account in
    cluster, fellow-traveler overlap, style match, etc.). Multiple
    independent cross-links converging on the same entity strengthen the
    verdict — this is the interconnection that single-source detection
    can't see.

    Costs 1 credit per call.
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

    if _charge_credit:
        consume_credits(
            current.id, 1,
            platform="youtube",
            scan_type="comprehensive",
            target_input=(req.video_url_or_id or req.account_url_or_handle or "")[:500],
            settings=settings,
        )

    # Pasted-comments-only flow doesn't need YouTube; everything else does.
    needs_youtube = bool(
        (req.account_url_or_handle and req.account_url_or_handle.strip())
        or (req.video_url_or_id and req.video_url_or_id.strip())
    )
    client = None
    if needs_youtube:
        factory = _client_factory_override or (lambda: _resolve_client(settings))
        client = factory()

    try:
        with get_session() as session:
            out = scan_comprehensive(
                session,
                account_url_or_handle=req.account_url_or_handle,
                video_url_or_id=req.video_url_or_id,
                comments_text=req.comments_text,
                max_commenters=req.max_commenters,
                force_refresh=req.force_refresh,
                client=client,
                youtube=yt,
                start_page_token=req.start_page_token,
            )
    except YouTubeClientError as e:
        # If this was a continuation (we only charged on the first call),
        # there's nothing to refund; the helper handles credits_to_refund=0.
        raise _handle_youtube_error(
            e,
            user_id=current.id,
            credits_to_refund=1 if _charge_credit else 0,
            target_input=(req.video_url_or_id or req.account_url_or_handle or ""),
        )

    # Convert to the response schemas
    focus_account_out = None
    if out.focus_account is not None:
        focus_account_out = AccountScanOut(**out.focus_account)

    video_result_out = None
    if out.video_output is not None:
        # Build the video result the same way /youtube/full does
        commenter_results: list[CommenterScanResult] = []
        for r in out.video_output.commenter_records:
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
                signals=list(r.scan_result.signals or []),
            ))
        tier_counts = Counter(c.tier.value for c in commenter_results)
        high_handles = sorted(
            c.handle for c in commenter_results
            if c.tier in (Tier.HIGH, Tier.ELEVATED)
            or (c.coordination_adjusted_probability or 0) >= 0.5
        )
        video_result_out = FullVideoScanResult(
            video_id=out.video_output.video_id,
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
            next_page_token=out.next_page_token,
        )

    return ComprehensiveScanResult(
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


def _persist_investigation_async(
    *,
    slug: str,
    existing: bool,
    user_id: int,
    classification: dict,
    url: str,
    result,
) -> None:
    """Background worker — saves an investigation row WITHOUT blocking the
    request response. Heavy operations (model_dump on a 200KB+ payload,
    JSON DB write) happen here instead of on the request thread, so the
    user always sees their scan finish promptly even when the DB is slow.
    """
    import logging
    import time as _time
    log = logging.getLogger("omi.scan")
    try:
        from app.storage.repository import AccountRepository
        label = _investigation_label(classification, url)
        target_id = (
            classification.get("video_id")
            or classification.get("account_input")
        )
        t0 = _time.time()
        with get_session() as session:
            repo = AccountRepository(session)
            inv = repo.get_investigation(slug=slug, user_id=user_id) if existing else None
            if inv is None:
                repo.create_investigation(
                    user_id=user_id, slug=slug, label=label,
                    input_url=url, target_id=target_id,
                    kind=classification.get("kind", "comprehensive"),
                    overall_probability=result.overall_probability,
                    overall_tier=result.overall_tier.value,
                    summary=result.summary,
                    quota_used=result.quota_used,
                    payload_json=_serialize_result(result),
                )
            else:
                merged_payload = _merge_payloads(inv.payload_json or {}, _serialize_result(result))
                repo.update_investigation_payload(
                    inv,
                    payload_json=merged_payload,
                    quota_used_delta=result.quota_used,
                    overall_probability=result.overall_probability,
                    overall_tier=result.overall_tier.value,
                    summary=result.summary,
                )
            session.commit()
        log.info("investigation %s persisted in %.1fs", slug, _time.time() - t0)
    except Exception as e:  # noqa: BLE001
        log.exception("investigation %s persistence failed: %s", slug, e)


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
