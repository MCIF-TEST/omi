"""Campaign intelligence endpoints — the Campaign Library.

Exposes the durable coordination-cluster records captured during scans. These
are observations, not verdicts: every field is measured evidence the operator
can inspect (members, methods, coordination score, recurrence, hashtags,
mentions, raw observation history).
"""

from __future__ import annotations

import secrets
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Response, status
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
    # Opt-in public sharing (None/false until shared).
    share_token: str | None = None
    is_public: bool = False


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
        share_token=c.share_token, is_public=bool(c.is_public),
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


class FeaturedCampaign(CampaignSummary):
    blurb: str | None = None


class FeaturedCampaignsResponse(BaseModel):
    campaigns: list[FeaturedCampaign]


# NOTE: declared BEFORE the /{campaign_key} route so "featured" isn't captured
# as a campaign key.
@router.get("/featured", response_model=FeaturedCampaignsResponse)
def list_featured_campaigns(
    current: CurrentUser = Depends(require_user),
) -> FeaturedCampaignsResponse:
    """Real, validated example campaigns (seeded from state-actor disclosure
    archives, scored by the engine) so a new user can explore a genuine
    coordinated operation on first visit. Fixture order; each carries a short
    editorial blurb. Empty if the fixture/seed is absent."""
    from app.content.featured import featured_blurbs, featured_keys

    keys = featured_keys()
    if not keys:
        return FeaturedCampaignsResponse(campaigns=[])
    blurbs = featured_blurbs()
    with get_session() as session:
        rows = session.execute(
            select(Campaign).where(Campaign.campaign_key.in_(keys))
        ).scalars().all()
    by_key = {c.campaign_key: c for c in rows}
    out: list[FeaturedCampaign] = []
    for k in keys:  # preserve fixture order
        c = by_key.get(k)
        if c is not None:
            out.append(FeaturedCampaign(**_summary(c).model_dump(), blurb=blurbs.get(k)))
    return FeaturedCampaignsResponse(campaigns=out)


def _campaign_detail(session, campaign_key: str) -> CampaignDetail | None:
    """Assemble the full CampaignDetail for a key, or None if absent. Shared by
    the detail endpoint and the evidence-pack export so both read identically."""
    c = session.execute(
        select(Campaign).where(Campaign.campaign_key == campaign_key)
    ).scalar_one_or_none()
    if c is None:
        return None
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


@router.get("/{campaign_key}", response_model=CampaignDetail)
def get_campaign(
    campaign_key: str,
    ref: str | None = Query(None, description="Navigation source marker (e.g. 'featured')."),
    current: CurrentUser = Depends(require_user),
) -> CampaignDetail:
    """A single campaign with members, evidence, and its full observation history."""
    from app.analytics.event_log import record

    with get_session() as session:
        detail = _campaign_detail(session, campaign_key)
        if detail is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Campaign not found")
        # Q1 diagnostic (founder learning): did the new user reach the featured
        # value surface? Only the seeded examples are logged — deliberately NOT
        # a pageview log of every campaign view.
        if campaign_key.startswith("feat_"):
            record(session, "featured_viewed", user_id=current.id,
                   campaign_key=campaign_key, ref=ref)
        return detail


@router.get("/{campaign_key}/export")
def export_campaign(
    campaign_key: str,
    format: Literal["markdown", "json"] = Query("markdown"),
    current: CurrentUser = Depends(require_user),
) -> Response:
    """Download a portable evidence pack for one campaign.

    The artifact an investigator cites: members, methods, evidence-for and
    evidence-weakening, recurrence, and the corroboration status + methodology
    + "observation, not verdict" disclaimer — so the trust contract travels
    with the file. Markdown for a report/editor; JSON for archival or tooling.
    Reuses the same detail assembly the campaign page renders.
    """
    from app.analytics.event_log import record
    from app.reports.campaign_pack import render_campaign_json, render_campaign_markdown

    with get_session() as session:
        detail = _campaign_detail(session, campaign_key)
        if detail is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Campaign not found")
        d = detail.model_dump()
        # Q1 (founder learning): the artifact left the app — a value moment.
        record(session, "campaign_export", user_id=current.id,
               campaign_key=campaign_key, format=format)

    if format == "json":
        return Response(
            content=render_campaign_json(d),
            media_type="application/json",
            headers={
                "Content-Disposition": f'attachment; filename="campaign-{campaign_key}.json"',
            },
        )
    return Response(
        content=render_campaign_markdown(d),
        media_type="text/markdown; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="campaign-{campaign_key}.md"',
        },
    )


# ---------------------------------------------------------------------------
# Public sharing — mint/revoke a token (auth), then a read-only token-gated
# public report (no auth). Mirrors the investigation sharing system exactly;
# reuses the same campaign data + the evidence-pack renderers.
# ---------------------------------------------------------------------------


class CampaignShareResponse(BaseModel):
    campaign_key: str
    share_token: str
    is_public: bool
    published_at: datetime | None
    public_url: str


@router.post("/{campaign_key}/share", response_model=CampaignShareResponse)
def share_campaign(
    campaign_key: str,
    current: CurrentUser = Depends(require_user),
) -> CampaignShareResponse:
    """Mint (or reuse) a public share token for this campaign. Idempotent —
    calling twice returns the existing token rather than rotating. The campaign
    becomes readable at /rc/{token} with no login."""
    from app.analytics.event_log import record

    with get_session() as session:
        c = session.execute(
            select(Campaign).where(Campaign.campaign_key == campaign_key)
        ).scalar_one_or_none()
        if c is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Campaign not found")
        if not c.share_token:
            c.share_token = "cmp_" + secrets.token_urlsafe(16)
        c.is_public = 1
        c.published_at = c.published_at or datetime.now(timezone.utc)
        # Q3 (founder learning): Campaign rows are global (no user_id), so this
        # event is the only per-user record of WHO shared.
        record(session, "campaign_share_minted", user_id=current.id,
               campaign_key=campaign_key)
        return CampaignShareResponse(
            campaign_key=c.campaign_key,
            share_token=c.share_token,
            is_public=True,
            published_at=c.published_at,
            public_url=f"/rc/{c.share_token}",
        )


@router.delete("/{campaign_key}/share")
def unshare_campaign(
    campaign_key: str,
    current: CurrentUser = Depends(require_user),
) -> dict:
    """Revoke the share token. The public URL 404s immediately afterward."""
    with get_session() as session:
        c = session.execute(
            select(Campaign).where(Campaign.campaign_key == campaign_key)
        ).scalar_one_or_none()
        if c is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Campaign not found")
        c.share_token = None
        c.is_public = 0
        return {"ok": True}


# --- public (no auth) -------------------------------------------------------

campaign_public_router = APIRouter(prefix="/rc", tags=["public-campaign-reports"])


class CampaignReportResponse(BaseModel):
    view: dict


def _resolve_public_campaign(token: str):
    """Resolve a public campaign by token (+ is_public), returning
    (CampaignDetail, published_at). 404 if missing or unshared."""
    with get_session() as session:
        c = session.execute(
            select(Campaign).where(
                Campaign.share_token == token, Campaign.is_public == 1
            )
        ).scalar_one_or_none()
        if c is None:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND, "Report not found or no longer public."
            )
        detail = _campaign_detail(session, c.campaign_key)
        if detail is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Report not found.")
        return detail, c.published_at


@campaign_public_router.get("/{token}", response_model=CampaignReportResponse)
def public_campaign_report(token: str = Path(min_length=8)) -> CampaignReportResponse:
    """Read-only campaign report view for the Next.js public page."""
    from app.analytics.event_log import record
    from app.content.featured import featured_keys
    from app.reports.campaign_pack import build_campaign_report_view

    detail, published_at = _resolve_public_campaign(token)
    view = build_campaign_report_view(detail.model_dump(), published_at=published_at)

    # Q3 (founder learning): was the shared link actually read? Anonymous —
    # token only; no user, no IP, no user agent.
    with get_session() as session:
        record(session, "public_report_view", token=token, report_kind="campaign")

    # First-run cross-navigation: when an anonymous visitor lands on a featured
    # example, offer the other featured campaign(s) so they can compare without
    # an account. Only public featured campaigns are listed; non-featured
    # reports expose nothing extra.
    if detail.campaign_key in featured_keys():
        with get_session() as session:
            others = session.execute(
                select(Campaign).where(
                    Campaign.campaign_key.in_(
                        [k for k in featured_keys() if k != detail.campaign_key]
                    ),
                    Campaign.is_public == 1,
                    Campaign.share_token.is_not(None),
                )
            ).scalars().all()
        view["other_featured"] = [
            {"name": c.name, "share_token": c.share_token} for c in others
        ]
    return CampaignReportResponse(view=view)


@campaign_public_router.get("/{token}/markdown")
def public_campaign_markdown(token: str = Path(min_length=8)) -> Response:
    """Download the public campaign report as Markdown."""
    from app.reports.campaign_pack import render_campaign_markdown

    detail, _ = _resolve_public_campaign(token)
    return Response(
        content=render_campaign_markdown(detail.model_dump()),
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="campaign-{token}.md"'},
    )


@campaign_public_router.get("/{token}/json")
def public_campaign_json(token: str = Path(min_length=8)) -> Response:
    """Download the public campaign report as JSON."""
    from app.reports.campaign_pack import render_campaign_json

    detail, _ = _resolve_public_campaign(token)
    return Response(
        content=render_campaign_json(detail.model_dump()),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="campaign-{token}.json"'},
    )
