"""Activity log — auditable per-user scan history.

Every scan (comprehensive, account, or video) writes a ScanLog row. This
endpoint surfaces that log to the user so they can see what they scanned,
what it cost, and whether any credits were refunded.
"""

from __future__ import annotations

from datetime import timezone

from fastapi import APIRouter, Depends, Query

from app.core.auth import CurrentUser, require_user
from app.schemas import ActivityEntry, ActivityLogResponse
from app.storage.db import get_session
from app.storage.repository import AccountRepository


router = APIRouter(prefix="/v1/activity", tags=["activity"])


@router.get("", response_model=ActivityLogResponse)
def get_activity(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current: CurrentUser = Depends(require_user),
) -> ActivityLogResponse:
    """Paginated scan history for the logged-in user, newest first."""
    with get_session() as session:
        repo = AccountRepository(session)
        rows, total = repo.list_activity(current.id, limit=limit, offset=offset)
        spent, refunded = repo.activity_credit_totals(current.id)

    entries = [
        ActivityEntry(
            id=r.id,
            created_at=_utc(r.created_at),
            platform=r.platform,
            scan_type=r.scan_type,
            credits_cost=r.credits_cost,
            target_input=r.target_input,
            success=bool(r.success),
            refunded=not bool(r.success),
        )
        for r in rows
    ]
    return ActivityLogResponse(
        entries=entries,
        total=total,
        limit=limit,
        offset=offset,
        credits_spent_total=spent,
        credits_refunded_total=refunded,
    )


def _utc(dt):
    if dt is None:
        return dt
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt
