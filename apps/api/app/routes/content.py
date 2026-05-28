"""Content intelligence endpoints — Phase 10."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.content.platforms import display_name as platform_display_name, supports_rescan
from app.content.service import ContentIntelligenceService
from app.core.auth import CurrentUser, require_user
from app.core.config import Settings, get_settings
from app.schemas import (
    AuthorCommentRow,
    AuthorCommentsResponse,
    AuthorContentRow,
    AuthorPresenceResponse,
    BatchDiffResponse,
    CommentBatchOut,
    ContentCommentsResponse,
    ContentCommentOut,
    ContentEntityDetail,
    ContentEntityListResponse,
    ContentEntitySummary,
    FullVideoScanRequest,
    FullVideoScanResult,
    ReplyPodMember,
    ReplyPodOut,
    ReplyPodsResponse,
    ReplyTreeNode,
    ReplyTreeResponse,
)
from app.storage.db import get_session

router = APIRouter(prefix="/v1/content", tags=["content"])


def _entity_to_summary(e) -> ContentEntitySummary:
    return ContentEntitySummary(
        id=e.id,
        platform=e.platform,
        content_id=e.content_id,
        kind=e.kind,
        title=e.title,
        author_external_id=e.author_external_id,
        author_handle=e.author_handle,
        canonical_url=e.canonical_url,
        thumbnail_url=e.thumbnail_url,
        total_batches=e.total_batches or 0,
        total_comments_collected=e.total_comments_collected or 0,
        total_distinct_authors=e.total_distinct_authors or 0,
        contributor_count=e.contributor_count or 0,
        latest_coordination_score=e.latest_coordination_score or 0.0,
        latest_risk_tier=e.latest_risk_tier or "low",
        latest_tier_distribution=e.latest_tier_distribution or {},
        first_scanned_at=e.first_scanned_at,
        last_scanned_at=e.last_scanned_at,
    )


def _batch_to_out(b) -> CommentBatchOut:
    return CommentBatchOut(
        id=b.id,
        fetched_at=b.fetched_at,
        comments_fetched=b.comments_fetched or 0,
        new_comments=b.new_comments or 0,
        duplicates=b.duplicates or 0,
        distinct_authors=b.distinct_authors or 0,
        new_authors=b.new_authors or 0,
        coordination_score=b.coordination_score or 0.0,
        risk_tier=b.risk_tier or "low",
        tier_distribution=b.tier_distribution or {},
        summary=b.summary,
        has_more=bool(b.next_page_token),
    )


def _comment_to_out(c) -> ContentCommentOut:
    return ContentCommentOut(
        id=c.id,
        external_comment_id=c.external_comment_id,
        author_external_id=c.author_external_id,
        author_handle=c.author_handle,
        text=c.text,
        like_count=c.like_count,
        reply_count=c.reply_count,
        observed_at=c.observed_at,
        first_batch_id=c.first_batch_id,
    )


@router.get("", response_model=ContentEntityListResponse)
def list_content_entities(
    platform: str | None = Query(None),
    min_risk_tier: str = Query("low", pattern="^(low|moderate|high|extreme)$"),
    q: str | None = Query(None, max_length=200, description="Substring search on title / content_id / author_handle"),
    limit: int = Query(40, ge=1, le=100),
    offset: int = Query(0, ge=0),
    _: CurrentUser = Depends(require_user),
) -> ContentEntityListResponse:
    """List all tracked content entities, sorted by most recently scanned."""
    # Map public tier names to internal storage names
    internal_tier = {"low": "low", "moderate": "moderate", "high": "elevated", "extreme": "high"}.get(
        min_risk_tier, "low"
    )
    with get_session() as session:
        svc = ContentIntelligenceService(session)
        total, entities = svc.list_entities(
            platform=platform,
            min_risk_tier=internal_tier,
            search=q,
            limit=limit,
            offset=offset,
        )
    return ContentEntityListResponse(
        total=total,
        platform=platform,
        entities=[_entity_to_summary(e) for e in entities],
    )


@router.get("/{platform}/{content_id}", response_model=ContentEntityDetail)
def get_content_entity(
    platform: str,
    content_id: str,
    _: CurrentUser = Depends(require_user),
) -> ContentEntityDetail:
    """Full intelligence detail for one piece of content."""
    with get_session() as session:
        svc = ContentIntelligenceService(session)
        entity = svc.get_entity_by_platform_id(platform, content_id)
        if entity is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No content entity found for {platform}/{content_id}.",
            )
        batches = svc.get_batches(entity.id, limit=50)
        total_comments, recent = svc.get_comments(entity.id, limit=20)
        has_continuation = svc.latest_next_page_token(entity.id) is not None
        summary = _entity_to_summary(entity)

    return ContentEntityDetail(
        entity=summary,
        batches=[_batch_to_out(b) for b in batches],
        recent_comments=[_comment_to_out(c) for c in recent],
        total_comments=total_comments,
        has_continuation=has_continuation,
    )


@router.get("/{platform}/{content_id}/batches", response_model=list[CommentBatchOut])
def get_content_batches(
    platform: str,
    content_id: str,
    limit: int = Query(50, ge=1, le=200),
    _: CurrentUser = Depends(require_user),
) -> list[CommentBatchOut]:
    """Batch history for one piece of content."""
    with get_session() as session:
        svc = ContentIntelligenceService(session)
        entity = svc.get_entity_by_platform_id(platform, content_id)
        if entity is None:
            raise HTTPException(status_code=404, detail="Content entity not found.")
        batches = svc.get_batches(entity.id, limit=limit)
    return [_batch_to_out(b) for b in batches]


@router.post("/{platform}/{content_id}/rescan", response_model=FullVideoScanResult)
def rescan_content_entity(
    platform: str,
    content_id: str,
    settings: Settings = Depends(get_settings),
    current: CurrentUser = Depends(require_user),
) -> FullVideoScanResult:
    """Run an incremental scan against this content, resuming pagination
    from the latest server-tracked cursor when possible.

    Falls back to a fresh page-1 scan if the platform's cursor has expired
    or this is the first scan of the content. Charges 1 credit just like a
    direct scan call.
    """
    if not supports_rescan(platform):
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail=(
                f"Rescans for {platform_display_name(platform)} aren't wired up yet — "
                "scan via the Investigate page to ingest this content."
            ),
        )

    # Lookup token before invoking the scan so we can short-circuit gracefully.
    with get_session() as session:
        svc = ContentIntelligenceService(session)
        entity = svc.get_entity_by_platform_id(platform, content_id)
        if entity is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No content entity for {platform}/{content_id}. Run a scan first.",
            )
        token = svc.latest_next_page_token(entity.id)
        video_url = entity.canonical_url or content_id

    # Import the scan handler lazily to avoid circular imports at module load.
    from app.routes.scan import scan_youtube_video_full
    req = FullVideoScanRequest(
        video_url_or_id=video_url,
        force_refresh=False,
        start_page_token=token,
    )
    return scan_youtube_video_full(req, settings=settings, current=current)


@router.get("/{platform}/{content_id}/diff", response_model=BatchDiffResponse)
def diff_content_batches(
    platform: str,
    content_id: str,
    from_batch_id: int | None = Query(None, alias="from"),
    to_batch_id: int | None = Query(None, alias="to"),
    _: CurrentUser = Depends(require_user),
) -> BatchDiffResponse:
    """Compare two batches of the same content. With no params, diffs the
    newest batch against the one before — "what changed since last scan."
    """
    with get_session() as session:
        svc = ContentIntelligenceService(session)
        entity = svc.get_entity_by_platform_id(platform, content_id)
        if entity is None:
            raise HTTPException(status_code=404, detail="Content entity not found.")
        result = svc.diff_batches(
            entity.id,
            from_batch_id=from_batch_id,
            to_batch_id=to_batch_id,
        )
        if result is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Need at least two batches to compute a diff. Re-scan this content to create a second batch.",
            )

    return BatchDiffResponse(
        from_batch=_batch_to_out(result["from_batch"]),
        to_batch=_batch_to_out(result["to_batch"]),
        coordination_score_delta=result["coordination_score_delta"],
        risk_tier_changed=result["risk_tier_changed"],
        tier_distribution_delta=result["tier_distribution_delta"],
        new_comment_count=result["new_comment_count"],
        new_author_count=result["new_author_count"],
        new_authors=result["new_authors"],
        sample_new_comments=[_comment_to_out(c) for c in result["sample_new_comments"]],
    )


@router.get("/authors/{platform}/{author_external_id}", response_model=AuthorPresenceResponse)
def get_author_presence(
    platform: str,
    author_external_id: str,
    limit: int = Query(50, ge=1, le=200),
    _: CurrentUser = Depends(require_user),
) -> AuthorPresenceResponse:
    """Cross-content footprint for one author — every piece of content
    OMISPHERE has seen them comment on, ranked by recency."""
    with get_session() as session:
        svc = ContentIntelligenceService(session)
        data = svc.get_author_presence(platform, author_external_id, limit=limit)

        if data["total_comments"] == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No tracked comments by {author_external_id} on {platform}.",
            )

        entities = [
            AuthorContentRow(
                entity=_entity_to_summary(row["entity"]),
                comment_count=row["comment_count"],
                first_comment=row["first_comment"],
                last_comment=row["last_comment"],
                sample_text=row["sample_text"],
            )
            for row in data["entities"]
        ]

    return AuthorPresenceResponse(
        platform=platform,
        author_external_id=author_external_id,
        author_handle=data["author_handle"],
        total_comments=data["total_comments"],
        content_count=data["content_count"],
        first_seen=data["first_seen"],
        last_seen=data["last_seen"],
        entities=entities,
    )


@router.get("/authors/{platform}/{author_external_id}/comments", response_model=AuthorCommentsResponse)
def get_author_comments(
    platform: str,
    author_external_id: str,
    limit: int = Query(200, ge=1, le=1000),
    _: CurrentUser = Depends(require_user),
) -> AuthorCommentsResponse:
    """Every comment we've recorded from one author on a platform, paired
    with the content entity it was posted on. Newest-first."""
    with get_session() as session:
        svc = ContentIntelligenceService(session)
        total, rows = svc.get_author_comments(platform, author_external_id, limit=limit)

        if total == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No tracked comments by {author_external_id} on {platform}.",
            )

        # Most recently observed handle wins
        handle = next((c.author_handle for c, _e in rows if c.author_handle), None)

        return AuthorCommentsResponse(
            platform=platform,
            author_external_id=author_external_id,
            author_handle=handle,
            total=total,
            comments=[
                AuthorCommentRow(
                    comment=_comment_to_out(c),
                    entity=_entity_to_summary(e),
                )
                for c, e in rows
            ],
        )


@router.get("/{platform}/{content_id}/comments", response_model=ContentCommentsResponse)
def get_content_comments(
    platform: str,
    content_id: str,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    batch_id: int | None = Query(None),
    _: CurrentUser = Depends(require_user),
) -> ContentCommentsResponse:
    """Paginated comment feed for one piece of content, optionally filtered to one batch."""
    with get_session() as session:
        svc = ContentIntelligenceService(session)
        entity = svc.get_entity_by_platform_id(platform, content_id)
        if entity is None:
            raise HTTPException(status_code=404, detail="Content entity not found.")
        total, comments = svc.get_comments(
            entity.id, limit=limit, offset=offset, batch_id=batch_id
        )
    return ContentCommentsResponse(
        total=total,
        comments=[_comment_to_out(c) for c in comments],
    )


# ---------------------------------------------------------------------------
# Phase C — Reply tree + engagement pods
# ---------------------------------------------------------------------------


@router.get("/{platform}/{content_id}/reply-tree", response_model=ReplyTreeResponse)
def get_reply_tree(
    platform: str,
    content_id: str,
    _: CurrentUser = Depends(require_user),
) -> ReplyTreeResponse:
    """Return the threaded comment structure for a single video.

    Returns top-level comments as roots, with their replies nested. Reply-pod
    membership is annotated inline so the UI can colour-code threads
    without making a second request.
    """
    from sqlalchemy import select
    from app.storage.models import Account, ContentComment
    from app.detection.coordination.reply_pods import ReplyEvent, detect_reply_pods

    with get_session() as session:
        svc = ContentIntelligenceService(session)
        entity = svc.get_entity_by_platform_id(platform, content_id)
        if entity is None:
            raise HTTPException(status_code=404, detail="Content entity not found.")

        rows = list(session.execute(
            select(ContentComment)
            .where(ContentComment.content_entity_id == entity.id)
            .order_by(ContentComment.observed_at.asc())
        ).scalars().all())

        # Run reply-pod detection so we can annotate nodes with pod_id.
        events = [
            ReplyEvent(
                comment_id=r.external_comment_id,
                parent_comment_id=r.parent_comment_id,
                author_external_id=r.author_external_id,
                posted_at=r.observed_at,
            )
            for r in rows
            if r.author_external_id
        ]
        pods = detect_reply_pods(events)
        author_to_pod: dict[str, int] = {}
        for idx, pod in enumerate(pods):
            for member in pod.members:
                author_to_pod[member] = idx

        # Resolve author tiers in one query.
        author_ids = {r.author_external_id for r in rows if r.author_external_id}
        tiers: dict[str, str | None] = {}
        if author_ids:
            for acct in session.execute(
                select(Account).where(
                    Account.platform == platform,
                    Account.external_id.in_(author_ids),
                )
            ).scalars().all():
                tiers[acct.external_id] = acct.last_tier

        # Build tree: any comment with parent_comment_id present in our rows
        # becomes a child of that node; orphan replies fall back to root level.
        nodes_by_id: dict[str, ReplyTreeNode] = {}
        for r in rows:
            nodes_by_id[r.external_comment_id] = ReplyTreeNode(
                comment_id=r.external_comment_id,
                parent_comment_id=r.parent_comment_id,
                author_external_id=r.author_external_id,
                author_handle=r.author_handle,
                author_tier=tiers.get(r.author_external_id),
                text=r.text,
                like_count=r.like_count,
                reply_count=r.reply_count,
                posted_at=r.observed_at,
                pod_id=author_to_pod.get(r.author_external_id),
            )

        roots: list[ReplyTreeNode] = []
        reply_count = 0
        for r in rows:
            node = nodes_by_id[r.external_comment_id]
            if r.parent_comment_id and r.parent_comment_id in nodes_by_id:
                nodes_by_id[r.parent_comment_id].replies.append(node)
                reply_count += 1
            else:
                roots.append(node)

        return ReplyTreeResponse(
            platform=platform,
            content_id=content_id,
            total_comments=len(rows),
            top_level_count=len(roots),
            reply_count=reply_count,
            roots=roots,
        )


@router.get("/{platform}/{content_id}/reply-pods", response_model=ReplyPodsResponse)
def get_reply_pods(
    platform: str,
    content_id: str,
    _: CurrentUser = Depends(require_user),
) -> ReplyPodsResponse:
    """Detect engagement pods inside a video's reply structure.

    Pods are clusters of accounts that reply to each other or co-reply to
    the same parent comment in tight windows. Each pod returns a score,
    evidence, and per-member risk tier from the persistent account store.
    """
    from sqlalchemy import select
    from app.storage.models import Account, ContentComment
    from app.detection.coordination.reply_pods import ReplyEvent, detect_reply_pods

    with get_session() as session:
        svc = ContentIntelligenceService(session)
        entity = svc.get_entity_by_platform_id(platform, content_id)
        if entity is None:
            raise HTTPException(status_code=404, detail="Content entity not found.")

        rows = list(session.execute(
            select(ContentComment.external_comment_id,
                   ContentComment.parent_comment_id,
                   ContentComment.author_external_id,
                   ContentComment.author_handle,
                   ContentComment.observed_at)
            .where(ContentComment.content_entity_id == entity.id)
        ).all())

        events = [
            ReplyEvent(
                comment_id=ext_id,
                parent_comment_id=parent_id,
                author_external_id=author,
                posted_at=ts,
            )
            for (ext_id, parent_id, author, _handle, ts) in rows
            if author
        ]
        handle_map = {author: handle for (_eid, _pid, author, handle, _ts) in rows if author}

        pods = detect_reply_pods(events)

        # Look up author tier + probability for every pod member.
        all_members = {m for p in pods for m in p.members}
        accounts: dict[str, Account] = {}
        if all_members:
            for acct in session.execute(
                select(Account).where(
                    Account.platform == platform,
                    Account.external_id.in_(all_members),
                )
            ).scalars().all():
                accounts[acct.external_id] = acct

        pods_out: list[ReplyPodOut] = []
        for idx, pod in enumerate(pods):
            interaction_count = sum(pod.pair_counts.values())
            members_out = []
            for m in pod.members:
                acct = accounts.get(m)
                members_out.append(ReplyPodMember(
                    external_id=m,
                    handle=acct.handle if acct else handle_map.get(m),
                    tier=acct.last_tier if acct else None,
                    overall_probability=acct.last_score if acct else None,
                ))
            pods_out.append(ReplyPodOut(
                pod_id=idx,
                score=pod.score,
                members=members_out,
                evidence=pod.evidence,
                interaction_count=interaction_count,
            ))

        return ReplyPodsResponse(
            platform=platform,
            content_id=content_id,
            pod_count=len(pods_out),
            pods=pods_out,
        )
