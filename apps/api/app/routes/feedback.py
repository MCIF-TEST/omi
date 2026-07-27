"""User feedback — submit (any signed-in user) + an admin-only searchable queue.

Every signed-in user can send product feedback from the persistent header button. Admins read the
queue with keyword / user / date filters. Storage is a single ``feedback`` table (auto-created on boot).
"""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from app.core.auth import CurrentUser, require_user
from app.storage.db import get_session
from app.storage.models import Feedback

router = APIRouter(prefix="/v1/feedback", tags=["feedback"])

_CATEGORIES = {"general", "bug", "idea", "praise", "other"}


class FeedbackIn(BaseModel):
    message: str = Field(min_length=1, max_length=5000)
    category: str = Field(default="general", max_length=40)
    page: str | None = Field(default=None, max_length=300)


class FeedbackOut(BaseModel):
    id: int
    user_id: int | None
    email: str | None
    category: str
    message: str
    page: str | None
    created_at: datetime


class FeedbackListOut(BaseModel):
    feedback: list[FeedbackOut]
    total: int


@router.post("", response_model=dict, status_code=status.HTTP_201_CREATED)
def submit_feedback(
    payload: FeedbackIn,
    current: CurrentUser = Depends(require_user),
) -> dict:
    """Record a piece of feedback from the current user. Cheap + always available."""
    category = payload.category.strip().lower()
    if category not in _CATEGORIES:
        category = "other"
    with get_session() as session:
        fb = Feedback(
            user_id=current.id if current.id else None,
            email=current.email or None,
            category=category,
            message=payload.message.strip(),
            page=(payload.page or None),
        )
        session.add(fb)
        session.flush()
        return {"ok": True, "id": fb.id}


@router.get("", response_model=FeedbackListOut)
def list_feedback(
    current: CurrentUser = Depends(require_user),
    q: str | None = Query(default=None, description="keyword search over message + email"),
    user: str | None = Query(default=None, description="filter by submitter email (substring)"),
    since: datetime | None = Query(default=None, description="only entries created at/after this time"),
    until: datetime | None = Query(default=None, description="only entries created at/before this time"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> FeedbackListOut:
    """The admin feedback queue: newest-first, with keyword / user / date filters."""
    if not current.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admins only.")
    with get_session() as session:
        stmt = select(Feedback)
        if q:
            like = f"%{q.strip()}%"
            stmt = stmt.where(Feedback.message.ilike(like) | Feedback.email.ilike(like))
        if user:
            stmt = stmt.where(Feedback.email.ilike(f"%{user.strip()}%"))
        if since:
            stmt = stmt.where(Feedback.created_at >= since)
        if until:
            stmt = stmt.where(Feedback.created_at <= until)

        rows = list(session.execute(
            stmt.order_by(Feedback.created_at.desc()).limit(limit).offset(offset)
        ).scalars().all())
        # Total for the same filter (without paging) so the UI can show counts / paginate.
        count_stmt = select(Feedback.id)
        if q:
            like = f"%{q.strip()}%"
            count_stmt = count_stmt.where(Feedback.message.ilike(like) | Feedback.email.ilike(like))
        if user:
            count_stmt = count_stmt.where(Feedback.email.ilike(f"%{user.strip()}%"))
        if since:
            count_stmt = count_stmt.where(Feedback.created_at >= since)
        if until:
            count_stmt = count_stmt.where(Feedback.created_at <= until)
        # COUNT in the database. This used to load every matching row into Python and take len() of
        # the list, so the cost of counting grew with the table instead of staying flat.
        total = session.execute(
            select(func.count()).select_from(count_stmt.subquery())
        ).scalar_one()

        return FeedbackListOut(
            feedback=[
                FeedbackOut(
                    id=r.id, user_id=r.user_id, email=r.email, category=r.category,
                    message=r.message, page=r.page, created_at=r.created_at,
                )
                for r in rows
            ],
            total=total,
        )
