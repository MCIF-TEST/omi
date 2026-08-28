"""Admin surface for the coordinated-network detector: /v1/admin/netdetect/*.

Admin-only, and for the same reason `/campaigns` and `/narratives` are: this reports groups of
NAMED REAL PEOPLE as running together, on evidence that is statistical rather than certain. It is an
operator's lead, not a customer-facing verdict, and it stays that way until the dilution curve and
the adjudication layer say otherwise.

Findings are now RECORDED, and the distinction that makes that acceptable is worth stating: this
persists an internal finding, it does not publish one. No share token is minted, no `Campaign` row
is created, and nothing reaches a customer surface. The original rule, that a claim this system
makes about a person is a decision somebody took rather than a side effect of a page load, is about
PUBLICATION and is untouched.

Recording is what the detector was missing twice over. Its findings evaporated when the page
closed, so the tracking layer that survives account rotation learned only from the older cohort
detector; and there was nothing to dismiss, so the one reservoir of ground truth this system will
ever accumulate stayed empty while the better detector ran.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select

from app.core.auth import CurrentUser, require_user
from app.netdetect import detect_from_commenters
from app.netdetect.persist import persist_finding
from app.netdetect.shuffle import DEFAULT_SHUFFLES
from app.storage.db import get_session
from app.storage.models import Investigation, NetdetectFinding

log = logging.getLogger("omi.netdetect.routes")

admin_router = APIRouter(prefix="/v1/admin/netdetect", tags=["admin-netdetect"])


def _require_admin(current: CurrentUser) -> None:
    if not current.is_admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admins only.")


class EvidenceOut(BaseModel):
    family: str
    kind: str
    shared_by: int
    corpus_count: int
    surprise: float
    sentence: str


class FindingOut(BaseModel):
    members: list[str]
    handles: list[str]
    size: int
    score: float
    by_family: dict[str, float]
    hard_evidence: float
    corrected_p: float | None
    #: Non-null when the evidence cannot settle whether this is an operation or a community, and a
    #: person has to look. The reason is in the string.
    needs_adjudication: str | None
    evidence: list[EvidenceOut]


class RunOut(BaseModel):
    slug: str
    corpus_size: int
    rare_features: int
    null_shuffles: int
    null_threshold: float | None
    findings: list[FindingOut]
    #: How many candidates scored but did not beat the shuffled search. "We looked and refused" is a
    #: more trustworthy statement than "we found nothing", and an operator calibrating needs the
    #: near-misses.
    rejected: int
    #: Set when the run could not be performed at all, as distinct from performing it and finding
    #: nothing. Never read an empty findings list as a clean result without checking this.
    refused: str | None
    #: Findings written to the store, and pairwise edges folded into the accumulating graph.
    recorded: int = 0
    accumulated_pairs: int = 0


@admin_router.post("/{slug}", response_model=RunOut)
def run_on_investigation(
    slug: str,
    shuffles: int = Query(DEFAULT_SHUFFLES, ge=1, le=200),
    record: bool = Query(True, description="Store the findings and accumulate their pairs."),
    current: CurrentUser = Depends(require_user),
) -> RunOut:
    """Run the detector over one stored investigation.

    Costs nothing: no provider call, no model call, no credit. It reads a payload that is already
    stored, which is what makes it safe to offer as a button.

    The scanned post's own ids are excluded from the evidence. Every commenter engaged that post by
    construction, so without the exclusion the whole comment section shares a perfect feature and
    reports as one enormous operation.
    """
    _require_admin(current)

    with get_session() as session:
        inv = session.execute(
            select(Investigation).where(Investigation.slug == slug)
        ).scalar_one_or_none()
        if inv is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "No such investigation.")
        payload = inv.payload_json or {}
        target = str(getattr(inv, "target_id", "") or "")
        investigation_id = inv.id

    rows = [c for c in (payload.get("commenters") or []) if isinstance(c, dict)]
    if not rows:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "That investigation stored no commenters, so there is nothing to compare.",
        )

    exclude = {target} if target else set()
    for key in ("content_id", "video_id", "post_id"):
        v = payload.get(key)
        if v:
            exclude.add(str(v))

    result = detect_from_commenters(rows, exclude_context=exclude, shuffles=shuffles)

    handles = {str(r.get("external_id")): str(r.get("handle") or "") for r in rows}

    recorded = 0
    accumulated = 0
    if record and result.findings and result.corpus is not None:
        # Best-effort. A failure here loses accumulated history, which degrades FUTURE findings, and
        # must never turn a completed run into an error for the operator looking at it now.
        try:
            with get_session() as session:
                before = _edge_count(session)
                for candidate in result.findings:
                    persist_finding(
                        session, candidate, result.corpus,
                        investigation_id=investigation_id,
                        context_id=target or None,
                        platform=candidate.platform,
                        corpus_size=result.corpus_size,
                        null_shuffles=result.null_shuffles,
                        null_threshold=result.null_threshold,
                    )
                    recorded += 1
                session.commit()
                accumulated = max(0, _edge_count(session) - before)
        except Exception:  # noqa: BLE001
            log.warning("netdetect: could not record findings for %s", slug, exc_info=True)
            recorded = 0

    return RunOut(
        slug=slug,
        corpus_size=result.corpus_size,
        rare_features=result.rare_features,
        null_shuffles=result.null_shuffles,
        null_threshold=result.null_threshold,
        rejected=len(result.rejected),
        refused=result.refused,
        recorded=recorded,
        accumulated_pairs=accumulated,
        findings=[
            FindingOut(
                members=c.members,
                handles=[handles.get(m, m) for m in c.members],
                size=c.size,
                score=round(c.score, 3),
                by_family={k: round(v, 3) for k, v in sorted(c.by_family.items())},
                hard_evidence=round(c.hard_evidence, 3),
                corrected_p=c.corrected_p,
                needs_adjudication=c.needs_adjudication,
                evidence=[
                    EvidenceOut(
                        family=e.feature.family, kind=e.feature.kind,
                        shared_by=e.shared_by, corpus_count=e.corpus_count,
                        surprise=round(e.surprise, 3), sentence=e.sentence,
                    )
                    for e in c.evidence[:25]
                ],
            )
            for c in result.findings
        ],
    )


def _edge_count(session) -> int:
    from sqlalchemy import func

    from app.storage.models import CoordinationEdge

    return int(session.execute(select(func.count(CoordinationEdge.id))).scalar_one() or 0)


# ---------------------------------------------------------------------------------------------
# The queue, and the dismissals.
#
# THESE DISMISSALS ARE THE ONLY GROUND TRUTH THIS DETECTOR WILL EVER ACCUMULATE. Every constant in
# `app/netdetect` is reasoned rather than fitted, because no labelled corpus of coordinated accounts
# exists and none can be bought. An operator saying "this is a newsroom" or "this one is real" is
# the only signal a later calibration can be fitted against, which is why the reason is required and
# why a judged row is never deleted.
# ---------------------------------------------------------------------------------------------------


class StoredFindingOut(BaseModel):
    id: int
    investigation_id: int | None
    context_id: str | None
    platform: str
    members: list[str]
    member_count: int
    score: float
    corrected_p: float | None
    by_family: dict[str, float]
    needs_adjudication: str | None
    evidence: list[EvidenceOut]
    corpus_size: int
    null_shuffles: int
    null_threshold: float | None
    status: str
    dismissal_reason: str | None
    confirmed: bool


def _stored_out(row: NetdetectFinding) -> StoredFindingOut:
    return StoredFindingOut(
        id=row.id,
        investigation_id=row.investigation_id,
        context_id=row.context_id,
        platform=row.platform,
        members=list(row.members_json or []),
        member_count=row.member_count,
        score=row.score,
        corrected_p=row.corrected_p,
        by_family=dict(row.by_family_json or {}),
        needs_adjudication=row.needs_adjudication,
        evidence=[EvidenceOut(**e) for e in (row.evidence_json or [])],
        corpus_size=row.corpus_size,
        null_shuffles=row.null_shuffles,
        null_threshold=row.null_threshold,
        status=row.status,
        dismissal_reason=row.dismissal_reason,
        confirmed=row.confirmed_at is not None,
    )


@admin_router.get("/findings/all", response_model=list[StoredFindingOut])
def list_findings(
    status_filter: str = Query("open", pattern="^(open|dismissed|confirmed|all)$", alias="status"),
    limit: int = Query(50, ge=1, le=200),
    current: CurrentUser = Depends(require_user),
) -> list[StoredFindingOut]:
    """Everything the detector has recorded, worst first."""
    _require_admin(current)
    with get_session() as session:
        stmt = select(NetdetectFinding)
        if status_filter != "all":
            stmt = stmt.where(NetdetectFinding.status == status_filter)
        rows = list(session.execute(
            stmt.order_by(NetdetectFinding.score.desc()).limit(limit)
        ).scalars())
        return [_stored_out(r) for r in rows]


class JudgementRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=2000)

    @field_validator("reason")
    @classmethod
    def _not_blank(cls, v: str) -> str:
        """A reason of spaces is an absent reason wearing a length.

        `min_length` alone lets `"   "` through, and it then strips to nothing on the way into the
        column, so the row records that somebody was unconvinced and nothing about why. That is the
        one thing this field exists to prevent.
        """
        stripped = v.strip()
        if not stripped:
            raise ValueError("A judgement needs a stated reason; it is the only ground truth here.")
        return stripped


@admin_router.post("/findings/{finding_id}/dismiss", response_model=StoredFindingOut)
def dismiss_finding(
    finding_id: int,
    body: JudgementRequest,
    current: CurrentUser = Depends(require_user),
) -> StoredFindingOut:
    """Record that this finding is wrong, and why.

    The reason is required and is the entire point. A dismissal with no stated reason records that
    somebody was unconvinced and nothing about what convinced them, which cannot be fitted against.
    """
    _require_admin(current)
    with get_session() as session:
        row = session.get(NetdetectFinding, finding_id)
        if row is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "No such finding.")
        row.status = "dismissed"
        row.dismissed_at = _now()
        row.dismissed_by = current.id
        row.dismissal_reason = body.reason
        row.confirmed_at = None
        session.commit()
        session.refresh(row)
        return _stored_out(row)


@admin_router.post("/findings/{finding_id}/confirm", response_model=StoredFindingOut)
def confirm_finding(
    finding_id: int,
    body: JudgementRequest,
    current: CurrentUser = Depends(require_user),
) -> StoredFindingOut:
    """Record that this finding is right, and why.

    Positives are rarer and worth more than negatives. A reservoir holding only rejections can only
    ever teach the detector to be quieter, which is not the same as teaching it to be correct.
    """
    _require_admin(current)
    with get_session() as session:
        row = session.get(NetdetectFinding, finding_id)
        if row is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "No such finding.")
        row.status = "confirmed"
        row.confirmed_at = _now()
        row.dismissed_at = None
        row.dismissed_by = current.id
        row.dismissal_reason = body.reason
        session.commit()
        session.refresh(row)
        return _stored_out(row)


def _now():
    from datetime import datetime, timezone

    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------------------------------
# The calibration report.
#
# IT REPORTS AND IT NEVER MOVES ANYTHING. Every constant in `app/netdetect` stays in code, with a
# commit, a reviewer and a reason beside it. A gate that retunes itself on operator clicks can be
# steered by whoever clicks, and this one decides whether named real people are reported as running
# an operation together. See the module docstring in `app/netdetect/calibration.py`.
# ---------------------------------------------------------------------------------------------------


class SweepRowOut(BaseModel):
    value: float
    confirmed_kept: int
    dismissed_kept: int
    dismissed_removed: int


class SweepOut(BaseModel):
    constant: str
    #: The file to edit by hand if the recommendation is accepted.
    where: str
    current: float
    #: "raise" or "lower". Stated because a reader cannot infer it from the numbers, and reading it
    #: backwards inverts every recommendation on the page.
    stricter_direction: str
    rows: list[SweepRowOut]
    proposed: float | None
    recommendation: str | None


class FamilySplitOut(BaseModel):
    family: str
    weight: float
    hard: bool
    mean_in_confirmed: float
    mean_in_dismissed: float
    present_in_confirmed: int
    present_in_dismissed: int
    separation: float


class CalibrationOut(BaseModel):
    confirmed: int
    dismissed: int
    open: int
    #: False while the reservoir is too thin to fit anything. The sweeps are still returned, because
    #: watching it fill is useful and an empty response would look like a broken endpoint.
    sufficient: bool
    insufficient_reason: str
    sweeps: list[SweepOut]
    families: list[FamilySplitOut]
    recommendations: list[str]
    caveats: list[str]


@admin_router.get("/findings/calibration", response_model=CalibrationOut)
def calibration_report(current: CurrentUser = Depends(require_user)) -> CalibrationOut:
    """What the accumulated judgements would move, and whether there are yet enough of them.

    Read-only in the strongest sense: it writes nothing and it changes no threshold. The output is a
    recommendation with its arithmetic attached, for a person to read and then edit
    `significance.py` or `detect.py` by hand if they agree.
    """
    _require_admin(current)
    from app.netdetect import calibration as cal

    with get_session() as session:
        report = cal.build_report(session)

    return CalibrationOut(
        confirmed=report.confirmed,
        dismissed=report.dismissed,
        open=report.open,
        sufficient=report.sufficient,
        insufficient_reason=report.insufficient_reason,
        recommendations=report.recommendations,
        caveats=report.caveats,
        sweeps=[
            SweepOut(
                constant=s.constant, where=s.where, current=s.current,
                stricter_direction=s.stricter_direction,
                proposed=s.proposed, recommendation=s.recommendation,
                rows=[
                    SweepRowOut(
                        value=r.value, confirmed_kept=r.confirmed_kept,
                        dismissed_kept=r.dismissed_kept, dismissed_removed=r.dismissed_removed,
                    )
                    for r in s.rows
                ],
            )
            for s in report.sweeps
        ],
        families=[
            FamilySplitOut(
                family=f.family, weight=f.weight, hard=f.hard,
                mean_in_confirmed=f.mean_in_confirmed, mean_in_dismissed=f.mean_in_dismissed,
                present_in_confirmed=f.present_in_confirmed,
                present_in_dismissed=f.present_in_dismissed,
                separation=round(f.separation, 3),
            )
            for f in report.families
        ],
    )
