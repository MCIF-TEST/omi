"""Admin API for the cohort coordination detector.

ADMIN ONLY, and gated on every route. Two reasons, and the second is the one that matters:

1. Like ``Campaign``, a detection is deployment-global in effect: it names accounts, and the
   ``investigation_slug`` it hangs off identifies a specific customer's scan. There is no way to
   scope this to "your own data" that would still be useful.
2. The detector's thresholds are reasoned, not fitted against a labelled corpus. Until they have
   been measured on real scans, a finding is an operator's lead to review, not a claim to publish.
   Nothing here is reachable from the customer app, the public report, or the exports.

Mounted at ``/v1/admin/coordination`` rather than under ``/v1/narratives``, which belongs to the
separate narrative-clustering feature.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from app.core.auth import CurrentUser, require_user
from app.storage.db import get_session
from app.storage.models import CampaignDetection, Investigation

logger = logging.getLogger(__name__)

admin_router = APIRouter(prefix="/v1/admin/coordination", tags=["admin-coordination"])


def _require_admin(current: CurrentUser) -> None:
    """Local mode (``OMI_REQUIRE_AUTH=false``) resolves to ``is_admin=True``, which is why a test
    that means to prove this gate must set ``OMI_REQUIRE_AUTH=true`` and sign up a real user.
    Production refuses the local configuration at boot."""
    if not current.is_admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admins only.")


# ---------------------------------------------------------------------------------------------
# Response shapes
# ---------------------------------------------------------------------------------------------
class MemberOut(BaseModel):
    external_id: str
    handle: str = ""
    score: float | None = None


class EvidenceOut(BaseModel):
    method: str
    family: str
    pair: list[str]
    sentence: str
    artifact: str
    statistic: list | None = None


class FindingOut(BaseModel):
    finding_id: str
    label: str
    score: float
    capped: bool
    density: float
    members: list[MemberOut]
    families_fired: list[str]
    families_silent: list[str]
    methods: list[str]
    evidence: list[str]
    notes: list[str]
    artifacts: list[EvidenceOut] = Field(default_factory=list)


class DetectionSummary(BaseModel):
    investigation_slug: str
    investigation_label: str = ""
    platform: str = "unknown"
    computed_at: datetime | None = None
    passes: int = 1
    score_source: str = "engine"
    scanned_total: int = 0
    cohort_size: int = 0
    finding_count: int = 0
    campaign_count: int = 0
    best_score: float = 0.0
    best_label: str = "no_campaign_detected"
    status: str = "open"
    thresholds_version: str = ""


class DetectionDetail(DetectionSummary):
    findings: list[FindingOut] = Field(default_factory=list)
    lone_high_scorers: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    resolution_note: str | None = None


class DetectionsResponse(BaseModel):
    detections: list[DetectionSummary]
    total: int
    #: Counts by status, so the queue can show what is outstanding without a second request.
    open_count: int = 0
    campaign_count: int = 0


class ResolveRequest(BaseModel):
    note: str = Field("", max_length=1000)


# ---------------------------------------------------------------------------------------------
# Reads
# ---------------------------------------------------------------------------------------------
@admin_router.get("", response_model=DetectionsResponse)
def list_detections(
    status_filter: str = Query("open", alias="status", pattern="^(open|dismissed|all)$"),
    only_campaigns: bool = Query(False),
    platform: str | None = Query(None, max_length=32),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current: CurrentUser = Depends(require_user),
) -> DetectionsResponse:
    """The queue.

    Reads ONLY the denormalised ``campaign_detections`` row and the investigation's label. It must
    never touch ``payload_json``: that column holds the whole scan result and these are the heaviest
    payloads in the product, so a list of fifty would deserialise hundreds of megabytes to render a
    table of numbers. Same trap the archive list already paid for.
    """
    _require_admin(current)

    with get_session() as session:
        q = select(CampaignDetection)
        if status_filter != "all":
            q = q.where(CampaignDetection.status == status_filter)
        if only_campaigns:
            q = q.where(CampaignDetection.campaign_count > 0)
        if platform:
            q = q.where(CampaignDetection.platform == platform)

        total = session.execute(
            select(func.count()).select_from(q.subquery())
        ).scalar_one()
        rows = session.execute(
            q.order_by(
                CampaignDetection.campaign_count.desc(),
                CampaignDetection.best_score.desc(),
                CampaignDetection.computed_at.desc(),
            ).limit(limit).offset(offset)
        ).scalars().all()

        labels = _labels_for(session, [r.investigation_slug for r in rows])
        open_count = session.execute(
            select(func.count()).select_from(CampaignDetection)
            .where(CampaignDetection.status == "open")
        ).scalar_one()
        campaign_count = session.execute(
            select(func.count()).select_from(CampaignDetection)
            .where(CampaignDetection.campaign_count > 0)
        ).scalar_one()

        return DetectionsResponse(
            detections=[_summary(r, labels.get(r.investigation_slug, "")) for r in rows],
            total=int(total),
            open_count=int(open_count),
            campaign_count=int(campaign_count),
        )


@admin_router.get("/{slug}", response_model=DetectionDetail)
def get_detection(
    slug: str,
    current: CurrentUser = Depends(require_user),
) -> DetectionDetail:
    """One detection with every evidence artifact.

    This is the only route that loads ``payload_json``, and it loads exactly one row.
    """
    _require_admin(current)

    from app.campaigns.detector import persist

    with get_session() as session:
        row = session.execute(
            select(CampaignDetection).where(CampaignDetection.investigation_slug == slug)
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "No detection for that investigation.")
        inv = session.execute(
            select(Investigation).where(Investigation.slug == slug)
        ).scalar_one_or_none()
        block = persist.stored_run(inv.payload_json or {}) if inv is not None else None
        handles, scores = _account_index(inv)

        detail = DetectionDetail(
            **_summary(row, getattr(inv, "label", "") or "").model_dump(),
            resolution_note=row.resolution_note,
        )
        if block:
            detail.findings = [
                _finding(f, handles, scores) for f in (block.get("findings") or [])
            ]
            detail.lone_high_scorers = list(block.get("lone_high_scorers") or [])
            detail.notes = list(block.get("notes") or [])
        return detail


# ---------------------------------------------------------------------------------------------
# Writes
# ---------------------------------------------------------------------------------------------
@admin_router.post("/{slug}/rerun", response_model=DetectionDetail)
def rerun_detection(
    slug: str,
    current: CurrentUser = Depends(require_user),
) -> DetectionDetail:
    """Re-run the detector on the already-persisted scan.

    Costs nothing: no provider call, no model call, no credit. It reads the payload that is already
    stored, which is what makes re-running safe to offer as a button.
    """
    _require_admin(current)

    from app.campaigns.detector import run as detector

    with get_session() as session:
        inv = session.execute(
            select(Investigation).where(Investigation.slug == slug)
        ).scalar_one_or_none()
        if inv is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "No such investigation.")
        owner = inv.user_id

    detector.detect_for_investigation(slug, owner, "analyst")
    return get_detection(slug, current)


@admin_router.post("/{slug}/dismiss", response_model=DetectionDetail)
def dismiss_detection(
    req: ResolveRequest,
    slug: str,
    current: CurrentUser = Depends(require_user),
) -> DetectionDetail:
    """Record a reviewed negative.

    These are the only ground truth this detector will ever accumulate. Every threshold in it is
    reasoned rather than fitted, so a growing set of admin-labelled false positives is what a future
    calibration gets to work from.
    """
    _require_admin(current)

    with get_session() as session:
        row = session.execute(
            select(CampaignDetection).where(CampaignDetection.investigation_slug == slug)
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "No detection for that investigation.")
        row.status = "dismissed"
        row.resolution_note = (req.note or "").strip()[:1000] or None
        row.resolved_at = datetime.now(timezone.utc)
        session.flush()

    return get_detection(slug, current)


@admin_router.post("/{slug}/reopen", response_model=DetectionDetail)
def reopen_detection(
    slug: str,
    current: CurrentUser = Depends(require_user),
) -> DetectionDetail:
    _require_admin(current)

    with get_session() as session:
        row = session.execute(
            select(CampaignDetection).where(CampaignDetection.investigation_slug == slug)
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "No detection for that investigation.")
        row.status = "open"
        row.resolved_at = None
        session.flush()

    return get_detection(slug, current)


# ---------------------------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------------------------
def _summary(row: CampaignDetection, label: str) -> DetectionSummary:
    return DetectionSummary(
        investigation_slug=row.investigation_slug,
        investigation_label=label,
        platform=row.platform or "unknown",
        computed_at=row.computed_at,
        passes=row.passes or 1,
        score_source=row.score_source or "engine",
        scanned_total=row.scanned_total or 0,
        cohort_size=row.cohort_size or 0,
        finding_count=row.finding_count or 0,
        campaign_count=row.campaign_count or 0,
        best_score=row.best_score or 0.0,
        best_label=row.best_label or "no_campaign_detected",
        status=row.status or "open",
        thresholds_version=row.thresholds_version or "",
    )


def _labels_for(session, slugs: list[str]) -> dict[str, str]:
    """Investigation labels for the queue, without loading their payloads."""
    if not slugs:
        return {}
    rows = session.execute(
        select(Investigation.slug, Investigation.label).where(Investigation.slug.in_(slugs))
    ).all()
    return {s: (lbl or "") for s, lbl in rows}


def _account_index(inv) -> tuple[dict[str, str], dict[str, float]]:
    """``external_id -> handle`` and ``-> score``, so a finding renders names rather than ids.

    An id is not something a reviewer can check. The handle is.
    """
    handles: dict[str, str] = {}
    scores: dict[str, float] = {}
    if inv is None:
        return handles, scores
    payload = inv.payload_json or {}
    video = payload.get("video") if isinstance(payload.get("video"), dict) else {}
    for row in (video or {}).get("commenters") or []:
        if not isinstance(row, dict):
            continue
        ext = str(row.get("external_id") or "")
        if not ext:
            continue
        handles[ext] = str(row.get("handle") or "")
        prob = row.get("coordination_adjusted_probability")
        if prob is None:
            prob = row.get("overall_probability")
        if prob is not None:
            try:
                scores[ext] = round(float(prob) * 100.0, 1)
            except (TypeError, ValueError):
                pass
    # The analyst's OMI score wins when present, because it is the number the cohort was cut on.
    entry = payload.get("analyst_assessment_v1")
    assessment = entry.get("assessment") if isinstance(entry, dict) else None
    if isinstance(assessment, dict):
        for row in assessment.get("commenter_assessments") or []:
            if not isinstance(row, dict):
                continue
            ext, omi = row.get("external_id"), row.get("omi_score")
            if ext and omi is not None:
                try:
                    scores[str(ext)] = float(omi)
                except (TypeError, ValueError):
                    pass
    return handles, scores


def _finding(f: dict, handles: dict[str, str], scores: dict[str, float]) -> FindingOut:
    members = [
        MemberOut(external_id=m, handle=handles.get(m, ""), score=scores.get(m))
        for m in (f.get("members") or [])
    ]
    artifacts = [
        EvidenceOut(
            method=str(e.get("method") or ""),
            family=str(e.get("family") or ""),
            pair=[handles.get(str(e.get("a")), str(e.get("a"))),
                  handles.get(str(e.get("b")), str(e.get("b")))],
            sentence=str(e.get("sentence") or ""),
            artifact=str(e.get("artifact") or ""),
            statistic=e.get("statistic"),
        )
        for e in (f.get("edges") or [])[:40]
    ]
    return FindingOut(
        finding_id=str(f.get("finding_id") or ""),
        label=str(f.get("label") or "lead"),
        score=float(f.get("score") or 0.0),
        capped=bool(f.get("capped")),
        density=float(f.get("density") or 0.0),
        members=members,
        families_fired=list(f.get("families_fired") or []),
        families_silent=list(f.get("families_silent") or []),
        methods=list(f.get("methods") or []),
        evidence=list(f.get("evidence") or []),
        notes=list(f.get("notes") or []),
        artifacts=artifacts,
    )
