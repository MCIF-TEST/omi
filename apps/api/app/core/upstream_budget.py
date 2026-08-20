"""A daily, database-backed ceiling on paid upstream API spend.

The problem this closes: ``POST /v1/scan/link/commenters`` (the compile step) requires auth, charges
**no credits**, and calls the real X / YouTube API. twitterapi.io bills per call, so credits cannot
guard this route: there is nothing to spend. Its only ceiling was ``_compile_limiter()`` at 30 per
minute, which has three properties that make it an abuse guard rather than a cost control:

* it is **per minute**, so it bounds a burst and not a day. Thirty a minute sustained is roughly
  43,000 upstream calls per user per day.
* it is **in-process**, so the budget is per instance and resets on every deploy. Two instances give
  two budgets.
* it records **nothing**, so no query anywhere could answer "how much did today cost".

The first signal that any of that had gone wrong would have been the invoice.

Design notes, each of which is a decision rather than an accident:

* **Counts upstream calls, not requests.** One compile can page the provider many times. The number
  that bills is the call count, which the sources already track (``Source.quota_used``).
* **Checked BEFORE the fetch, recorded after.** A refusal must cost nothing, the same property
  ``test_compile_is_capped_per_user_and_stops_upstream_calls`` already pins for the rate limiter.
* **Recording never raises.** A ledger failure must not break a scan the customer is watching. The
  budget failing open is the correct trade: an over-spend is recoverable, and a book-keeping table
  taking the product down is not.
* **The paid scan path records but is not gated.** Credits are a real billing control and a scan has
  already been paid for; refusing one mid-flight would take the customer's credits and give nothing
  back. The ledger still counts those calls, because the deployment-wide total is only useful if it
  is the actual total.
* **Admins are exempt**, matching how they skip credit consumption and the rate limiters.

Both budgets are env-tunable (``OMI_UPSTREAM_DAILY_CALLS_PER_USER`` /
``OMI_UPSTREAM_DAILY_CALLS_GLOBAL``) so a launch-day spike is absorbed without a deploy, and ``0``
disables a budget entirely.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.storage.models import UpstreamUsage

log = logging.getLogger("omi.upstream_budget")

GLOBAL_SCOPE = "global"
USER_SCOPE = "user"


def today_utc() -> str:
    """The ledger's day key. A UTC date string, so the boundary is unambiguous across drivers."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _scope_id_for(user_id: int | None) -> str:
    """Local mode's id=0 is not a real identity, mirroring ``rate_limit.user_key``."""
    return str(user_id) if user_id else "anon"


# --------------------------------------------------------------------------- #
# Reading
# --------------------------------------------------------------------------- #
def calls_today(session, *, scope: str, scope_id: str = "", day: str | None = None) -> int:
    """Upstream calls charged to this scope today, across every platform."""
    from sqlalchemy import func as _func

    total = session.execute(
        select(_func.coalesce(_func.sum(UpstreamUsage.api_calls), 0)).where(
            UpstreamUsage.scope == scope,
            UpstreamUsage.scope_id == scope_id,
            UpstreamUsage.usage_date == (day or today_utc()),
        )
    ).scalar()
    return int(total or 0)


def usage_snapshot(session, *, days: int = 7, top_users: int = 20) -> dict:
    """What today and the recent past cost, for the admin view.

    A ledger nobody reads is the same as no ledger: the point of recording spend is that an operator
    can watch it accrue instead of meeting it on a statement.
    """
    from sqlalchemy import func as _func

    from app.core.config import get_settings

    settings = get_settings()
    day = today_utc()

    by_day = [
        {"date": d, "api_calls": int(c or 0), "requests": int(r or 0)}
        for d, c, r in session.execute(
            select(
                UpstreamUsage.usage_date,
                _func.sum(UpstreamUsage.api_calls),
                _func.sum(UpstreamUsage.requests),
            )
            .where(UpstreamUsage.scope == GLOBAL_SCOPE)
            .group_by(UpstreamUsage.usage_date)
            .order_by(UpstreamUsage.usage_date.desc())
            .limit(max(1, days))
        ).all()
    ]

    by_platform = [
        {"platform": p, "api_calls": int(c or 0)}
        for p, c in session.execute(
            select(UpstreamUsage.platform, _func.sum(UpstreamUsage.api_calls))
            .where(UpstreamUsage.scope == GLOBAL_SCOPE, UpstreamUsage.usage_date == day)
            .group_by(UpstreamUsage.platform)
            .order_by(_func.sum(UpstreamUsage.api_calls).desc())
        ).all()
    ]

    heaviest = [
        {"user_id": u, "api_calls": int(c or 0), "requests": int(r or 0)}
        for u, c, r in session.execute(
            select(
                UpstreamUsage.scope_id,
                _func.sum(UpstreamUsage.api_calls),
                _func.sum(UpstreamUsage.requests),
            )
            .where(UpstreamUsage.scope == USER_SCOPE, UpstreamUsage.usage_date == day)
            .group_by(UpstreamUsage.scope_id)
            .order_by(_func.sum(UpstreamUsage.api_calls).desc())
            .limit(max(1, top_users))
        ).all()
    ]

    global_budget = int(settings.upstream_daily_calls_global or 0)
    spent = calls_today(session, scope=GLOBAL_SCOPE, day=day)
    return {
        "date": day,
        "today_api_calls": spent,
        "per_user_budget": int(settings.upstream_daily_calls_per_user or 0),
        "global_budget": global_budget,
        "global_remaining": max(0, global_budget - spent) if global_budget > 0 else None,
        "by_day": by_day,
        "by_platform": by_platform,
        "heaviest_users_today": heaviest,
    }


# --------------------------------------------------------------------------- #
# Enforcing
# --------------------------------------------------------------------------- #
def enforce_daily_budget(session, *, user_id: int | None, is_admin: bool, what: str) -> None:
    """Refuse the request if today's upstream budget is spent. Call BEFORE any upstream fetch.

    Deliberately checks the budget rather than reserving against it. Sizing a reservation would mean
    predicting how many provider calls a compile will make, which is not knowable before it runs, and
    a wrong prediction is worse than a small overshoot: the budgets exist to stop a runaway, and one
    compile past the line is not a runaway.
    """
    from app.core.config import get_settings

    if is_admin:
        return
    settings = get_settings()

    per_user = int(getattr(settings, "upstream_daily_calls_per_user", 0) or 0)
    if per_user > 0:
        spent = calls_today(session, scope=USER_SCOPE, scope_id=_scope_id_for(user_id))
        if spent >= per_user:
            log.warning(
                "upstream daily budget spent: user=%s calls=%s budget=%s (%s)",
                user_id, spent, per_user, what,
            )
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=(
                    "You have reached today's limit for loading new comment sections. "
                    "It resets at midnight UTC. Scanning accounts you have already loaded is "
                    "unaffected."
                ),
                headers={"Retry-After": str(_seconds_to_utc_midnight())},
            )

    total = int(getattr(settings, "upstream_daily_calls_global", 0) or 0)
    if total > 0:
        spent = calls_today(session, scope=GLOBAL_SCOPE)
        if spent >= total:
            # Loud, because this one is not a user problem. It means the deployment has hit its own
            # ceiling and every customer is about to see the same refusal.
            log.error(
                "DEPLOYMENT upstream daily budget spent: calls=%s budget=%s (%s). "
                "Raise OMI_UPSTREAM_DAILY_CALLS_GLOBAL or wait for the UTC rollover.",
                spent, total, what,
            )
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=(
                    "We have hit today's limit for reading new comment sections. This is on us, not "
                    "you. It resets at midnight UTC, and nothing you have already loaded is affected."
                ),
                headers={"Retry-After": str(_seconds_to_utc_midnight())},
            )


def _seconds_to_utc_midnight() -> int:
    now = datetime.now(timezone.utc)
    end = now.replace(hour=23, minute=59, second=59, microsecond=0)
    return max(1, int((end - now).total_seconds()) + 1)


# --------------------------------------------------------------------------- #
# Recording
# --------------------------------------------------------------------------- #
def record_calls(session, *, user_id: int | None, platform: str, api_calls: int) -> None:
    """Add ``api_calls`` to today's user and deployment counters. Never raises.

    Best-effort on purpose: this is book-keeping running beside work a customer is waiting on, and a
    ledger that can fail a scan is worse than a ledger with a gap in it. Failures are logged and
    reported to the error tracker so a persistent gap is visible rather than silent.
    """
    if api_calls <= 0:
        return
    day = today_utc()
    plat = (platform or "unknown")[:16]
    try:
        for scope, scope_id in (
            (USER_SCOPE, _scope_id_for(user_id)),
            (GLOBAL_SCOPE, ""),
        ):
            _bump(session, scope=scope, scope_id=scope_id, day=day, platform=plat, calls=api_calls)
    except Exception as exc:  # noqa: BLE001 — accounting must never break the request
        log.warning("upstream usage not recorded (user=%s platform=%s): %s", user_id, plat, exc)
        from app.core.observability import capture_exception

        capture_exception(exc)


def _bump(session, *, scope: str, scope_id: str, day: str, platform: str, calls: int) -> None:
    """Increment one counter row, creating it if this is the day's first call.

    Update-then-insert rather than insert-then-catch, because the row exists for all but the first
    call of a day and the common path should not be an exception. The insert is wrapped in a
    SAVEPOINT so that losing the race with a concurrent first call rolls back only that statement:
    without it the IntegrityError would poison the whole session, and this runs inside the caller's
    transaction, which is a compile the customer is waiting on.
    """
    row = session.execute(
        select(UpstreamUsage).where(
            UpstreamUsage.scope == scope,
            UpstreamUsage.scope_id == scope_id,
            UpstreamUsage.usage_date == day,
            UpstreamUsage.platform == platform,
        )
    ).scalar_one_or_none()
    if row is not None:
        row.api_calls = int(row.api_calls or 0) + calls
        row.requests = int(row.requests or 0) + 1
        row.updated_at = datetime.now(timezone.utc)
        session.flush()
        return

    try:
        with session.begin_nested():
            session.add(UpstreamUsage(
                scope=scope, scope_id=scope_id, usage_date=day, platform=platform,
                api_calls=calls, requests=1,
            ))
    except IntegrityError:
        # Someone else created it between the select and the insert. Re-read and add to theirs, so a
        # concurrent first-call-of-the-day never loses a count.
        row = session.execute(
            select(UpstreamUsage).where(
                UpstreamUsage.scope == scope,
                UpstreamUsage.scope_id == scope_id,
                UpstreamUsage.usage_date == day,
                UpstreamUsage.platform == platform,
            )
        ).scalar_one_or_none()
        if row is None:
            raise
        row.api_calls = int(row.api_calls or 0) + calls
        row.requests = int(row.requests or 0) + 1
        row.updated_at = datetime.now(timezone.utc)
    session.flush()


# --------------------------------------------------------------------------- #
# The monthly, plan-derived ceiling
# --------------------------------------------------------------------------- #
#
# WHY A SECOND CEILING EXISTS ALONGSIDE THE DAILY ONE.
#
# The daily budget above is a runaway guard: it answers "is something looping right now". It is not
# a business control, and it was never sized as one. At ~$0.006 per upstream call, its 1,500/user/day
# default is $9 a day, i.e. **$270 a month from one $14.99 subscriber**, and reaching it requires no
# abuse at all — just somebody browsing a lot of comment sections and scanning a few of them.
#
# Credits already bound how many accounts get SCORED. They do not bound compile, which charges no
# credits and still calls the provider. So the plan's economics rested on customers not using the
# free half of the product very much, which is not a control.
#
# This ceiling closes that. It is:
#   * MONTHLY and aligned to the customer's billing period, so it resets when their credits do.
#     A meter that reset on a different day from the thing it meters would be its own support load.
#   * DERIVED FROM THE PLAN (``PlanTier.monthly_call_ceiling``) rather than configured separately,
#     so it cannot drift from what the tier was priced to afford.
#   * SIZED ABOVE what the tier's credits can spend on scans, by a compile allowance. Browsing has
#     to feel free even though it is not, or the product loses the moment that sells it.
#
# It is a METER, NOT A WALL. Hitting it offers a top-up rather than ending the month, because a hard
# stop turns the most engaged customers into churn. The whole design is: bound what a subscription
# includes so it can be priced, then sell more to anyone who wants more.

def _month_floor(dt: datetime) -> datetime:
    return dt.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def _minus_one_month(dt: datetime) -> datetime:
    """One calendar month earlier, clamping the day so the 31st never overflows a short month."""
    year, month = (dt.year, dt.month - 1) if dt.month > 1 else (dt.year - 1, 12)
    # 28 is safe in every month; the period start only needs to be stable, not exact to the day.
    day = min(dt.day, 28)
    return dt.replace(year=year, month=month, day=day)


def billing_period_start(user) -> str:
    """First day (UTC date string) of the user's current billing period.

    Anchored to ``subscription_renews_at`` when there is one, so the call meter and the credit grant
    reset together. A customer whose credits refill on the 17th but whose call allowance refills on
    the 1st would reasonably conclude one of the two numbers is broken.

    Falls back to the calendar month for accounts with no subscription, which is the only sensible
    period when there is no billing cycle to borrow.
    """
    now = datetime.now(timezone.utc)
    renews = getattr(user, "subscription_renews_at", None)
    if isinstance(renews, datetime):
        if renews.tzinfo is None:
            renews = renews.replace(tzinfo=timezone.utc)
        # ONLY a renewal still in the future describes a live period. A date in the past means the
        # subscription lapsed, or our copy is stale, and anchoring to it would open a window running
        # from whenever that was: a 400-day-old renewal would sum fourteen months of usage into one
        # allowance. The calendar month is the honest answer for an account with no live cycle.
        if renews > now:
            return _minus_one_month(renews).strftime("%Y-%m-%d")
    return _month_floor(now).strftime("%Y-%m-%d")


def calls_this_period(session, *, user_id: int | None, since: str) -> int:
    """Upstream calls charged to this user since ``since`` (inclusive), across every platform."""
    from sqlalchemy import func as _func

    total = session.execute(
        select(_func.coalesce(_func.sum(UpstreamUsage.api_calls), 0)).where(
            UpstreamUsage.scope == USER_SCOPE,
            UpstreamUsage.scope_id == _scope_id_for(user_id),
            UpstreamUsage.usage_date >= since,
        )
    ).scalar()
    return int(total or 0)


def period_usage(session, user) -> tuple[int, int]:
    """``(calls_used, calls_included)`` for this user's current billing period.

    ``calls_included`` of 0 means unmetered (an admin, or a deployment that has switched the ceiling
    off), never "no allowance". Callers must treat 0 as "do not enforce" — reading it as an
    exhausted budget would lock out precisely the accounts meant to be exempt.
    """
    from app.core import plans

    if getattr(user, "is_admin", False):
        return (0, 0)
    tier = plans.get_tier(getattr(user, "plan_tier", None))
    since = billing_period_start(user)
    return (calls_this_period(session, user_id=getattr(user, "id", None), since=since),
            int(tier.monthly_call_ceiling))


def enforce_period_budget(session, user, *, what: str, projected: int = 0) -> None:
    """Refuse when this billing period's plan call ceiling is spent. Call BEFORE any upstream fetch.

    ``projected`` is how many calls the caller is about to make, and is what lets a SCAN be refused
    up front instead of half way through. That distinction is the whole reason this takes a
    projection at all: a compile can simply be declined (it costs the customer nothing), but a scan
    consumes credits, so it must be refused BEFORE the charge or the customer pays for a scan that
    gets cut off. Pass 0 for the compile path, where the call count is not knowable in advance.
    """
    used, included = period_usage(session, user)
    if included <= 0:
        return                                   # unmetered: admin, or the ceiling is switched off
    if used + max(0, projected) < included:
        return

    from app.core import plans

    tier = plans.get_tier(getattr(user, "plan_tier", None))
    log.warning(
        "plan call ceiling reached: user=%s used=%s projected=%s ceiling=%s tier=%s (%s)",
        getattr(user, "id", None), used, projected, included, tier.slug, what,
    )
    raise HTTPException(
        status_code=status.HTTP_402_PAYMENT_REQUIRED,
        detail=(
            f"This month's {tier.display_name} allowance is used up "
            f"({used:,} of {included:,} lookups). Buy a credit pack or move up a plan to keep "
            "going. Everything you have already scanned stays available."
        ),
    )
