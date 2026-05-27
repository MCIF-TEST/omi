"""Multi-account scan endpoints.

The marquee route is ``POST /v1/scan/youtube/video``: paste a video URL,
get back a probabilistic authenticity assessment for every commenter,
backed by Omi's growing fingerprint store. Commenters seen in any prior
scan within the cache TTL are reused — and every fresh scan adds to the
intelligence base that future scans benefit from.
"""

from __future__ import annotations

from collections import Counter

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.auth import CurrentUser, consume_credits, require_user
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
    parse_video_id,
    resolve_channel_id,
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
    commenters = fetch_video_commenters(
        client, video_id, max_commenters=max_commenters, stats=stats
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
    commenters_meta, all_comments, _next_token = fetch_video_full(
        client, video_id,
        max_commenters=max_commenters,
        max_comments=max_commenters * 3,
        stats=stats,
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
            n_clusters=len(full.coordination_clusters),
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
            clusters=[
                CoordinationClusterOut(
                    method=cl.method,
                    members=cl.members,
                    score=cl.score,
                    evidence=cl.evidence,
                    metadata=cl.metadata,
                )
                for cl in full.coordination_clusters
            ],
            focus_account=focus,
            summary=summary,
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

    channel_id = resolve_channel_id(client, account_input, stats=stats)
    if not channel_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Could not resolve a YouTube channel from '{account_input}'.",
        )
    profile = fetch_channel_profile(client, channel_id, stats=stats)
    if profile is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="YouTube returned no profile for the resolved channel.",
        )
    history = fetch_channel_recent_comments(
        client, channel_id,
        max_comments=settings.scan_max_history_per_commenter,
        stats=stats,
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
    result = scan_comprehensive_endpoint(creq, settings, current=current, _charge_credit=False)

    # ---- Phase 5: persist as a saved investigation ----
    # First scan creates the row; continuation batches (with start_page_token
    # or investigation_slug) append to the same row so the user has one
    # canonical record per piece of work.
    if current.id != 0:  # skip in local mode
        try:
            import secrets
            from app.storage.repository import AccountRepository
            existing_slug = payload.get("investigation_slug")
            label = _investigation_label(classification, url)
            target_id = (
                classification.get("video_id")
                or classification.get("account_input")
            )
            with get_session() as session:
                repo = AccountRepository(session)
                inv = None
                if existing_slug:
                    inv = repo.get_investigation(slug=existing_slug, user_id=current.id)
                if inv is None:
                    slug = "inv_" + secrets.token_hex(4)
                    inv = repo.create_investigation(
                        user_id=current.id, slug=slug, label=label,
                        input_url=url, target_id=target_id,
                        kind=classification.get("kind", "comprehensive"),
                        overall_probability=result.overall_probability,
                        overall_tier=result.overall_tier.value,
                        summary=result.summary,
                        quota_used=result.quota_used,
                        payload_json=_serialize_result(result),
                    )
                    # Stamp the slug onto the response so the UI can store it
                    result_dict = result.model_dump()
                    result_dict["investigation_slug"] = inv.slug
                    # Pydantic v2 trick: rebuild with the new field
                    from app.schemas import ComprehensiveScanResult as CSR
                    return CSR.model_validate({**result_dict})
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
                    result_dict = result.model_dump()
                    result_dict["investigation_slug"] = inv.slug
                    from app.schemas import ComprehensiveScanResult as CSR
                    return CSR.model_validate({**result_dict})
        except Exception:  # noqa: BLE001 — investigation save mustn't break a paid scan
            pass

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
