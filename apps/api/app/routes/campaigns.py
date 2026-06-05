"""Campaign intelligence endpoints — the Campaign Library.

Exposes the durable coordination-cluster records captured during scans. These
are observations, not verdicts: every field is measured evidence the operator
can inspect (members, methods, coordination score, recurrence, hashtags,
mentions, raw observation history).
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import desc, select

from app.core.auth import CurrentUser, require_user
from app.storage.db import get_session
from app.storage.models import Campaign, CampaignMember, CampaignObservation

router = APIRouter(prefix="/v1/campaigns", tags=["campaigns"])


class CampaignSummary(BaseModel):
    campaign_key: str
    name: str
    platform: str
    coordination_score: float
    max_coordination_score: float
    confidence: float
    member_count: int
    observation_count: int
    methods: list[str]
    hashtags: list[str]
    mentions: list[str]
    status: str
    first_detected_at: datetime
    last_seen_at: datetime


class CampaignMemberOut(BaseModel):
    account_external_id: str
    handle: str | None
    times_observed: int
    methods: list[str]


class CampaignObservationOut(BaseModel):
    observed_at: datetime
    context_id: str | None
    coordination_score: float
    member_count: int
    methods: list[str]
    evidence: list[str]


class CampaignDetail(CampaignSummary):
    evidence: list[str]
    theme: str | None
    members: list[CampaignMemberOut]
    observations: list[CampaignObservationOut]


class CampaignsResponse(BaseModel):
    campaigns: list[CampaignSummary]
    total: int


def _summary(c: Campaign) -> CampaignSummary:
    return CampaignSummary(
        campaign_key=c.campaign_key, name=c.name, platform=c.platform,
        coordination_score=c.coordination_score,
        max_coordination_score=c.max_coordination_score, confidence=c.confidence,
        member_count=c.member_count, observation_count=c.observation_count,
        methods=c.methods_json or [], hashtags=c.hashtags_json or [],
        mentions=c.mentions_json or [], status=c.status,
        first_detected_at=c.first_detected_at, last_seen_at=c.last_seen_at,
    )


@router.get("", response_model=CampaignsResponse)
def list_campaigns(
    platform: str | None = Query(None),
    min_score: float = Query(0.0, ge=0.0, le=1.0,
                             description="Filter by max observed coordination score."),
    recurring_only: bool = Query(False, description="Only campaigns seen in >1 detection."),
    sort: str = Query("recent", pattern="^(recent|score|size|recurrence)$"),
    limit: int = Query(50, ge=1, le=200),
    current: CurrentUser = Depends(require_user),
) -> CampaignsResponse:
    """The Campaign Library — durable coordinated-account groups, newest first."""
    with get_session() as session:
        q = select(Campaign).where(Campaign.max_coordination_score >= min_score)
        if platform:
            q = q.where(Campaign.platform == platform)
        if recurring_only:
            q = q.where(Campaign.observation_count > 1)
        order = {
            "recent": desc(Campaign.last_seen_at),
            "score": desc(Campaign.max_coordination_score),
            "size": desc(Campaign.member_count),
            "recurrence": desc(Campaign.observation_count),
        }[sort]
        rows = session.execute(q.order_by(order).limit(limit)).scalars().all()
        total = session.query(Campaign).count()
        return CampaignsResponse(campaigns=[_summary(c) for c in rows], total=total)


@router.get("/{campaign_key}", response_model=CampaignDetail)
def get_campaign(
    campaign_key: str,
    current: CurrentUser = Depends(require_user),
) -> CampaignDetail:
    """A single campaign with members, evidence, and its full observation history."""
    with get_session() as session:
        c = session.execute(
            select(Campaign).where(Campaign.campaign_key == campaign_key)
        ).scalar_one_or_none()
        if c is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Campaign not found")
        members = session.execute(
            select(CampaignMember).where(CampaignMember.campaign_id == c.id)
            .order_by(desc(CampaignMember.times_observed))
        ).scalars().all()
        obs = session.execute(
            select(CampaignObservation).where(CampaignObservation.campaign_id == c.id)
            .order_by(desc(CampaignObservation.observed_at)).limit(50)
        ).scalars().all()
        return CampaignDetail(
            **_summary(c).model_dump(),
            evidence=c.evidence_json or [], theme=c.theme,
            members=[CampaignMemberOut(
                account_external_id=m.account_external_id, handle=m.handle,
                times_observed=m.times_observed, methods=m.methods_json or [],
            ) for m in members],
            observations=[CampaignObservationOut(
                observed_at=o.observed_at, context_id=o.context_id,
                coordination_score=o.coordination_score, member_count=o.member_count,
                methods=o.methods_json or [], evidence=o.evidence_json or [],
            ) for o in obs],
        )
