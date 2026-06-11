"""Founder-learning endpoints (master-plan Phase 4).

Two halves, both scoped to the five questions (value / return / share /
trust / pay):

* User-facing willingness-to-pay capture — ONE free-text question, shown only
  to users who have come back (>=2 investigations), asked once, dismissible
  forever. The single highest-signal qualitative instrument at small N.
* Admin read surface — ``GET /v1/admin/learning`` answers the five questions
  literally, derived from the EventLog plus the ledgers that already exist
  (ScanLog, Investigation, User). No dashboards, no vanity metrics: numbers
  the founder can act on, and the raw WTP answers verbatim.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.analytics.event_log import record
from app.core.auth import CurrentUser, require_user
from app.storage.db import get_session
from app.storage.models import EventLog, Investigation, ScanLog, User

router = APIRouter(prefix="/v1/learning", tags=["learning"])
admin_router = APIRouter(prefix="/v1/admin", tags=["admin-learning"])

_RETURNER_MIN_INVESTIGATIONS = 2


# ---------------------------------------------------------------------------
# Willingness-to-pay (Q5) — one question, returners only, once ever.
# ---------------------------------------------------------------------------


class WtpPromptStatus(BaseModel):
    show_wtp: bool


class WtpAnswer(BaseModel):
    text: str = Field(min_length=1, max_length=2000)


def _has_event(session, user_id: int, kinds: tuple[str, ...]) -> bool:
    return session.execute(
        select(EventLog.id).where(
            EventLog.user_id == user_id, EventLog.kind.in_(kinds)
        ).limit(1)
    ).scalar_one_or_none() is not None


@router.get("/prompt", response_model=WtpPromptStatus)
def wtp_prompt_status(current: CurrentUser = Depends(require_user)) -> WtpPromptStatus:
    """Should the WTP question be shown to this user right now?

    Yes only when they are a returner (>=2 investigations — they have real
    experience to price) and they have neither answered nor dismissed it.
    """
    if not current.id:
        return WtpPromptStatus(show_wtp=False)
    with get_session() as session:
        inv_count = len(session.execute(
            select(Investigation.id)
            .where(Investigation.user_id == current.id).limit(_RETURNER_MIN_INVESTIGATIONS)
        ).all())
        if inv_count < _RETURNER_MIN_INVESTIGATIONS:
            return WtpPromptStatus(show_wtp=False)
        answered = _has_event(session, current.id, ("wtp_answer", "wtp_dismissed"))
        return WtpPromptStatus(show_wtp=not answered)


@router.post("/wtp")
def submit_wtp(body: WtpAnswer, current: CurrentUser = Depends(require_user)) -> dict:
    """Store the user's answer to "what would make Omi worth paying for?"."""
    with get_session() as session:
        record(session, "wtp_answer", user_id=current.id, text=body.text)
    return {"ok": True}


@router.post("/wtp/dismiss")
def dismiss_wtp(current: CurrentUser = Depends(require_user)) -> dict:
    """Permanently dismiss the WTP question for this user."""
    with get_session() as session:
        record(session, "wtp_dismissed", user_id=current.id)
    return {"ok": True}


# ---------------------------------------------------------------------------
# Admin read surface — the five questions, literally.
# ---------------------------------------------------------------------------


def _utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt


@admin_router.get("/learning")
def learning_report(current: CurrentUser = Depends(require_user)) -> dict:
    """Answers, from real data: did users experience value / come back /
    share / trust the result / would they pay. Derived from EventLog + the
    existing ledgers; computed in Python (fine at pre-PMF scale)."""
    if not current.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin only.")

    with get_session() as session:
        users = session.execute(select(User)).scalars().all()
        events = session.execute(select(EventLog)).scalars().all()
        scans = session.execute(select(ScanLog)).scalars().all()
        invs = session.execute(select(Investigation)).scalars().all()

    by_user_events: dict[int, list[EventLog]] = {}
    for e in events:
        if e.user_id is not None:
            by_user_events.setdefault(e.user_id, []).append(e)
    scans_by_user: dict[int, list[ScanLog]] = {}
    for s in scans:
        scans_by_user.setdefault(s.user_id, []).append(s)
    invs_by_user: dict[int, list[Investigation]] = {}
    for i in invs:
        if i.user_id is not None:
            invs_by_user.setdefault(i.user_id, []).append(i)

    def value_moments(uid: int) -> list[datetime]:
        """Timestamps of activation-definition actions: export, share minted,
        investigation published, successful scan."""
        out: list[datetime] = []
        for e in by_user_events.get(uid, []):
            if e.kind in ("campaign_export", "campaign_share_minted"):
                out.append(_utc(e.created_at))
        for i in invs_by_user.get(uid, []):
            if i.published_at:
                out.append(_utc(i.published_at))
        for s in scans_by_user.get(uid, []):
            if s.success:
                out.append(_utc(s.created_at))
        return [t for t in out if t]

    # Q1 — did the user experience value?
    activated, first_week = 0, 0
    featured_reached = 0
    for u in users:
        moments = value_moments(u.id)
        if moments:
            activated += 1
            signup = _utc(u.created_at)
            if signup and min(moments) <= signup + timedelta(days=7):
                first_week += 1
        if any(e.kind == "featured_viewed" for e in by_user_events.get(u.id, [])):
            featured_reached += 1

    # Q2 — did the user come back? (distinct active days across all ledgers;
    # blind spot, accepted: a purely passive visit with no action is invisible.)
    returned = 0
    for u in users:
        days: set = set()
        for e in by_user_events.get(u.id, []):
            days.add(_utc(e.created_at).date())
        for s in scans_by_user.get(u.id, []):
            days.add(_utc(s.created_at).date())
        for i in invs_by_user.get(u.id, []):
            if i.updated_at:
                days.add(_utc(i.updated_at).date())
        if len(days) >= 2:
            returned += 1

    # Q3 — did the user share something, and was it read?
    campaign_shares = sum(1 for e in events if e.kind == "campaign_share_minted")
    investigation_shares = sum(1 for i in invs if i.published_at)
    report_views = [e for e in events if e.kind == "public_report_view"]
    views_by_kind: dict[str, int] = {}
    for e in report_views:
        k = str((e.payload_json or {}).get("report_kind", "unknown"))
        views_by_kind[k] = views_by_kind.get(k, 0) + 1
    total_shares = campaign_shares + investigation_shares

    # Q4 — did the user trust the result? (engaged enough to conclude.)
    concluded = sum(1 for i in invs if i.verdict and i.verdict != "pending")
    with_notes = sum(1 for i in invs if (i.notes or "").strip())

    # Q5 — would the user pay?
    subscribed = sum(1 for u in users if u.subscription_status == "active")
    wtp = sorted(
        (e for e in events if e.kind == "wtp_answer"),
        key=lambda e: e.created_at, reverse=True,
    )

    n_users = len(users) or 1
    return {
        "q1_did_users_experience_value": {
            "users_total": len(users),
            "reached_featured_value_surface": featured_reached,
            "activated_users": activated,
            "activation_rate": round(activated / n_users, 3),
            "first_week_activation": first_week,
            "definition": "export OR share-minted OR published investigation OR successful scan",
        },
        "q2_did_users_come_back": {
            "returned_users": returned,
            "return_rate": round(returned / n_users, 3),
            "definition": ">=2 distinct active days across scans/events/investigations",
        },
        "q3_did_users_share": {
            "campaign_shares_minted": campaign_shares,
            "investigation_shares_minted": investigation_shares,
            "public_report_views": len(report_views),
            "views_by_kind": views_by_kind,
            "views_per_share": round(len(report_views) / total_shares, 2) if total_shares else None,
        },
        "q4_did_users_trust_the_result": {
            "investigations_total": len(invs),
            "verdict_concluded": concluded,
            "verdict_rate": round(concluded / len(invs), 3) if invs else None,
            "with_analyst_notes": with_notes,
            "caveat": "silence is not distrust — this measures engaged conclusion only",
        },
        "q5_would_users_pay": {
            "subscribed_users": subscribed,
            "wtp_answers": [
                {"at": _utc(e.created_at).isoformat() if e.created_at else None,
                 "text": str((e.payload_json or {}).get("text", ""))}
                for e in wtp
            ],
        },
    }
