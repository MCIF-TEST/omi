"""Channel-level deep intelligence.

Aggregates all ContentEntity records authored by a channel to produce:
- Audience composition (tier distribution across all videos)
- Risk trend (coordination score over time from CommentBatch records)
- Top repeat commenters (accounts seen most frequently across videos)
- Per-video summaries sorted by coordination score

No credit cost — reads data already in the intelligence store.
"""

from __future__ import annotations

from datetime import timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select

from app.core.auth import CurrentUser, require_user
from app.schemas import (
    ChannelAudienceComposition,
    ChannelIntelligenceResponse,
    ChannelRiskPoint,
    ChannelTopCommenter,
    ChannelVideoSummary,
)
from app.storage.db import get_session
from app.storage.models import CommentBatch, CommenterEngagement, ContentEntity
from app.storage.repository import AccountRepository


router = APIRouter(prefix="/v1/channels", tags=["channels"])


def _utc(dt):
    if dt is None:
        return None
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt


@router.get("/{platform}/{external_id}/intelligence", response_model=ChannelIntelligenceResponse)
def channel_intelligence(
    platform: str,
    external_id: str,
    current: CurrentUser = Depends(require_user),
) -> ChannelIntelligenceResponse:
    """Channel-level deep intelligence: audience composition, risk trend, top commenters.

    Aggregates all video scans attributed to this channel into a single view.
    """
    with get_session() as session:
        repo = AccountRepository(session)
        account = repo.get(platform, external_id)

        videos_q = (
            select(ContentEntity)
            .where(
                ContentEntity.platform == platform,
                ContentEntity.author_external_id == external_id,
            )
            .order_by(ContentEntity.latest_coordination_score.desc())
            .limit(50)
        )
        videos = list(session.execute(videos_q).scalars())

        if not videos and account is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=(
                    f"No channel data found for {platform}:{external_id}. "
                    "Scan one of their videos first."
                ),
            )

        # Aggregate audience tier composition across all videos
        tier_agg: dict[str, int] = {"high": 0, "elevated": 0, "moderate": 0, "low": 0}
        for v in videos:
            dist: dict = v.latest_tier_distribution or {}
            for tier, count in dist.items():
                if tier in tier_agg:
                    tier_agg[tier] += int(count)
        total_commenters = sum(tier_agg.values())

        # Risk trend: coordination score over time from CommentBatch records
        video_entity_ids = [v.id for v in videos]
        risk_trend: list[ChannelRiskPoint] = []
        if video_entity_ids:
            batches_q = (
                select(CommentBatch, ContentEntity.content_id)
                .join(ContentEntity, CommentBatch.content_entity_id == ContentEntity.id)
                .where(CommentBatch.content_entity_id.in_(video_entity_ids))
                .order_by(CommentBatch.fetched_at.asc())
                .limit(200)
            )
            for batch, vid_content_id in session.execute(batches_q).all():
                risk_trend.append(ChannelRiskPoint(
                    content_id=vid_content_id,
                    date=_utc(batch.fetched_at),
                    coordination_score=batch.coordination_score,
                    risk_tier=batch.risk_tier,
                    comment_count=batch.comments_fetched,
                ))

        # Top repeat commenters: accounts appearing across the most videos
        content_ids = [v.content_id for v in videos]
        top_commenters: list[ChannelTopCommenter] = []
        if content_ids:
            top_q = (
                select(
                    CommenterEngagement.account_external_id,
                    func.count(CommenterEngagement.parent_id.distinct()).label("video_count"),
                )
                .where(
                    CommenterEngagement.platform == platform,
                    CommenterEngagement.parent_id.in_(content_ids),
                )
                .group_by(CommenterEngagement.account_external_id)
                .order_by(func.count(CommenterEngagement.parent_id.distinct()).desc())
                .limit(20)
            )
            for commenter_ext_id, vid_count in session.execute(top_q).all():
                acct = repo.get(platform, commenter_ext_id)
                top_commenters.append(ChannelTopCommenter(
                    external_id=commenter_ext_id,
                    platform=platform,
                    handle=acct.handle if acct else commenter_ext_id,
                    video_count=vid_count,
                    tier=acct.last_tier if acct else None,
                    overall_probability=acct.last_score if acct else None,
                ))

        video_summaries = [
            ChannelVideoSummary(
                content_id=v.content_id,
                title=v.title,
                canonical_url=v.canonical_url,
                thumbnail_url=v.thumbnail_url,
                total_batches=v.total_batches,
                total_comments_collected=v.total_comments_collected,
                total_distinct_authors=v.total_distinct_authors,
                latest_coordination_score=v.latest_coordination_score,
                latest_risk_tier=v.latest_risk_tier,
                first_scanned_at=_utc(v.first_scanned_at),
                last_scanned_at=_utc(v.last_scanned_at),
            )
            for v in videos
        ]

        return ChannelIntelligenceResponse(
            platform=platform,
            external_id=external_id,
            handle=account.handle if account else external_id,
            display_name=account.display_name if account else None,
            bio=account.bio if account else None,
            follower_count=account.follower_count if account else None,
            first_seen_at=_utc(account.first_seen_at) if account else None,
            last_scanned_at=_utc(account.last_scanned_at) if account else None,
            video_count=len(videos),
            videos=video_summaries,
            audience_composition=ChannelAudienceComposition(
                high=tier_agg["high"],
                elevated=tier_agg["elevated"],
                moderate=tier_agg["moderate"],
                low=tier_agg["low"],
                total_commenters=total_commenters,
            ),
            risk_trend=risk_trend,
            top_commenters=top_commenters,
        )
