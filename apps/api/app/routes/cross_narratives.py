"""The cross-investigation queue. ADMIN ONLY, for the same reason as every other surface here.

A finding is assembled from many customers' scans and belongs to none of them, so it cannot be
"scoped to your own data" because there is no such thing. It is gated instead, matching
``/v1/narratives``, ``/v1/campaigns`` and the dispute queue.

**No route here reports WHO scanned what.** ``distinct_customers`` is the number the whole system
exists to measure, and the value is in the independence rather than the identity: an admin surface
that named the customers would turn a statistical discriminator into a log of other people's
activity, for no gain in what the finding says.

Note the trap that hid the last authorisation hole in this area: routes like these are usually
tested in local mode, where ``require_user`` returns ``is_admin=True``. A test meaning to prove an
authorisation rule has to set ``OMI_REQUIRE_AUTH=true`` and sign up a real user.
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Body, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import desc, select

from app.core.auth import CurrentUser, require_user
from app.narrative.cross import run as cross_run
from app.narrative.cross import store as cross_store
from app.narrative.cross import topics as cross_topics
from app.narrative.embeddings import get_embedder
from app.storage.db import get_session
from app.storage.models import CrossFinding, CrossTopic

router = APIRouter(prefix="/v1/admin/cross-narratives", tags=["cross-narratives"])


def _require_admin(current: CurrentUser) -> None:
    if not current.is_admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admins only.")


class CrossFindingOut(BaseModel):
    id: int
    topic_id: int
    label: str
    window_start: str
    window_end: str

    #: Score one and its parts. Reported separately, never as one number: which component carried a
    #: finding is most of what tells a reader whether to believe it.
    anomaly_score: float
    volume: float
    tier_mix: float
    independence: float
    anomaly_detail: dict = Field(default_factory=dict)

    #: Score two. Deliberately NOT combined with score one.
    cohort_accounts: int
    cohort_findings: int
    cohort_best_p: float | None
    cohort_refused: str | None
    needs_adjudication: str | None
    cohort_detail: dict = Field(default_factory=dict)

    status: str
    dismissal_reason: str | None
    created_at: datetime
    updated_at: datetime


class CrossQueueResponse(BaseModel):
    findings: list[CrossFindingOut]
    total: int
    #: What the store currently holds, so an operator can watch it fill up before trusting a score.
    store: dict
    #: How many utterances are waiting for a topic. A number that only grows means the embedder is
    #: down or unconfigured, which is otherwise invisible.
    pending_assignment: int
    embedder: str
    #: The honest scope of every claim on this page.
    scope_note: str


_SCOPE_NOTE = (
    "Anomalous relative to the OmiSphere corpus, never relative to the platform. The corpus is what "
    "customers chose to scan, which is not a sample of anything. A topic is flagged when it is "
    "busier than its own history, its accounts score higher than the corpus base rate, and several "
    "unrelated customers arrived at it independently. The two scores are never combined."
)


def _to_out(row: CrossFinding) -> CrossFindingOut:
    return CrossFindingOut(
        id=row.id,
        topic_id=row.topic_id,
        label=row.label,
        window_start=row.window_start,
        window_end=row.window_end,
        anomaly_score=row.anomaly_score,
        volume=row.volume,
        tier_mix=row.tier_mix,
        independence=row.independence,
        anomaly_detail=row.anomaly_detail_json or {},
        cohort_accounts=row.cohort_accounts,
        cohort_findings=row.cohort_findings,
        cohort_best_p=row.cohort_best_p,
        cohort_refused=row.cohort_refused,
        needs_adjudication=row.needs_adjudication,
        cohort_detail=row.cohort_detail_json or {},
        status=row.status,
        dismissal_reason=row.dismissal_reason,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


@router.get("", response_model=CrossQueueResponse)
def list_findings(
    status_filter: str = Query("open", pattern="^(open|dismissed|all)$", alias="status"),
    limit: int = Query(50, ge=1, le=200),
    current: CurrentUser = Depends(require_user),
) -> CrossQueueResponse:
    _require_admin(current)

    with get_session() as session:
        stmt = select(CrossFinding)
        if status_filter != "all":
            stmt = stmt.where(CrossFinding.status == status_filter)
        rows = list(session.execute(
            stmt.order_by(desc(CrossFinding.anomaly_score), desc(CrossFinding.updated_at))
            .limit(limit)
        ).scalars())
        total = len(rows)
        out = [_to_out(r) for r in rows]
        store_stats = cross_store.store_stats(session)
        pending = cross_topics.pending_count(session)

    return CrossQueueResponse(
        findings=out,
        total=total,
        store=store_stats,
        pending_assignment=pending,
        embedder=type(get_embedder()).__name__,
        scope_note=_SCOPE_NOTE,
    )


class DismissRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=2000)


@router.post("/{finding_id}/dismiss", response_model=CrossFindingOut)
def dismiss(
    finding_id: int,
    body: DismissRequest = Body(...),
    current: CurrentUser = Depends(require_user),
) -> CrossFindingOut:
    """Mark a finding as not worth acting on, with a reason.

    **The reason is required, and it is the point of the endpoint.** Every threshold in this
    pipeline is reasoned rather than fitted, because no labelled corpus of worked topics exists.
    These dismissals are the only ground truth that will ever accumulate, so a dismissal with no
    stated reason records that somebody was unconvinced and nothing about why, which cannot be
    fitted against.
    """
    _require_admin(current)
    with get_session() as session:
        row = session.get(CrossFinding, finding_id)
        if row is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "No such finding.")
        row.status = "dismissed"
        row.dismissed_at = datetime.now(timezone.utc)
        row.dismissed_by = current.id
        row.dismissal_reason = body.reason.strip()
        session.commit()
        session.refresh(row)
        return _to_out(row)


@router.post("/{finding_id}/reopen", response_model=CrossFindingOut)
def reopen(
    finding_id: int,
    current: CurrentUser = Depends(require_user),
) -> CrossFindingOut:
    """Undo a dismissal. The reason is KEPT, because it is training data either way."""
    _require_admin(current)
    with get_session() as session:
        row = session.get(CrossFinding, finding_id)
        if row is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "No such finding.")
        row.status = "open"
        row.dismissed_at = None
        session.commit()
        session.refresh(row)
        return _to_out(row)


class TopicOut(BaseModel):
    id: int
    label: str
    utterance_count: int
    account_count: int
    embedding_space: str | None
    first_seen_at: datetime
    last_seen_at: datetime


@router.get("/topics", response_model=list[TopicOut])
def list_topics(
    limit: int = Query(50, ge=1, le=200),
    current: CurrentUser = Depends(require_user),
) -> list[TopicOut]:
    """The topics themselves, busiest first. For watching the corpus take shape."""
    _require_admin(current)
    with get_session() as session:
        rows = list(session.execute(
            select(CrossTopic)
            .order_by(desc(CrossTopic.utterance_count))
            .limit(limit)
        ).scalars())
        return [
            TopicOut(
                id=t.id, label=t.label, utterance_count=t.utterance_count,
                account_count=t.account_count, embedding_space=t.embedding_space,
                first_seen_at=t.first_seen_at, last_seen_at=t.last_seen_at,
            )
            for t in rows
        ]


@router.post("/run")
def run_pass(current: CurrentUser = Depends(require_user)) -> dict:
    """Run one pass now, rather than waiting for the scheduler.

    Bounded exactly like the scheduled pass, so this cannot be used to hold a worker: call it
    repeatedly to catch up rather than expecting one call to do everything.
    """
    _require_admin(current)
    return cross_run.run_one_pass_in_session()
