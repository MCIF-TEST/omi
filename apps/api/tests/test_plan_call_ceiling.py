"""The monthly, plan-derived ceiling on upstream calls.

THE HOLE THIS CLOSES. Credits bound how many accounts get SCORED. They never bounded compile, which
charges no credits and still calls a provider that bills per call. Its only ceiling was a per-minute
limiter and a flat daily budget sized when a call was a free YouTube quota unit. At ~$0.006 a call,
the old 1,500/day default is **$270 a month from one $14.99 subscriber**, reachable with no abuse at
all: somebody who browses a lot of comment sections and scans a few of them.

So the plan's economics rested on customers not using the free half of the product very much, which
is not a control. These tests are the control.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException

from app.core import plans
from app.core.upstream_budget import (
    USER_SCOPE,
    billing_period_start,
    enforce_period_budget,
    period_usage,
    record_calls,
)
from app.storage.db import get_session, reset_db_for_tests
from app.storage.models import User


@pytest.fixture(autouse=True)
def _db():
    reset_db_for_tests("sqlite:///:memory:")
    yield
    reset_db_for_tests("sqlite:///:memory:")


def _user(tier: str | None = "starter", *, renews_in_days: int | None = 20, admin=False) -> User:
    with get_session() as s:
        u = User(email=f"{tier or 'free'}@t.com", password_hash="x", credits_remaining=0)
        u.plan_tier = tier
        u.is_admin = 1 if admin else 0
        if renews_in_days is not None:
            u.subscription_renews_at = datetime.now(timezone.utc) + timedelta(days=renews_in_days)
        s.add(u)
        s.flush()
        s.refresh(u)
        s.expunge(u)
        return u


def _spend(user: User, calls: int) -> None:
    with get_session() as s:
        record_calls(s, user_id=user.id, platform="x", api_calls=calls)


# --------------------------------------------------------------------------------------------- #
# The meter
# --------------------------------------------------------------------------------------------- #
def test_the_ceiling_comes_from_the_plan_not_from_a_separate_setting():
    """Configured separately, the ceiling would drift from what the tier was priced to afford."""
    for tier in plans.paid_tiers():
        u = _user(tier.slug)
        with get_session() as s:
            _used, included = period_usage(s, s.get(User, u.id))
        assert included == tier.monthly_call_ceiling


def test_calls_accumulate_against_the_period_and_the_ceiling_refuses_at_the_line():
    u = _user("starter")
    ceiling = plans.STARTER.monthly_call_ceiling

    _spend(u, ceiling - 1)
    with get_session() as s:
        enforce_period_budget(s, s.get(User, u.id), what="compile")   # one call left: allowed

    _spend(u, 1)
    with get_session() as s:
        with pytest.raises(HTTPException) as e:
            enforce_period_budget(s, s.get(User, u.id), what="compile")
    # 402, not 429. "Too many requests" says wait; this does not clear by waiting, it clears by
    # buying, and telling somebody to retry a request that can never succeed is a support ticket.
    assert e.value.status_code == 402
    assert "credit pack" in e.value.detail


def test_a_scan_is_refused_UP_FRONT_using_its_projected_cost():
    """The distinction that stops a customer paying for work that gets cut off.

    A compile can simply be declined: it costs them nothing. A scan consumes credits, so it has to
    be refused BEFORE the charge. That is why enforcement takes a projection at all.
    """
    u = _user("starter")
    ceiling = plans.STARTER.monthly_call_ceiling
    _spend(u, ceiling - 50)

    with get_session() as s:
        # A compile is still fine: there is headroom, and its cost is not knowable in advance.
        enforce_period_budget(s, s.get(User, u.id), what="compile")
        # A 100-account scan needs 200 calls and there are 50. Refused before a credit moves.
        with pytest.raises(HTTPException) as e:
            enforce_period_budget(s, s.get(User, u.id), what="scan",
                                  projected=100 * plans.CALLS_PER_ACCOUNT)
    assert e.value.status_code == 402


def test_a_bigger_plan_really_does_buy_more_headroom():
    research = _user("research")
    _spend(research, plans.STARTER.monthly_call_ceiling + 100)
    with get_session() as s:
        enforce_period_budget(s, s.get(User, research.id), what="compile")


# --------------------------------------------------------------------------------------------- #
# Who is exempt, and why 0 must never read as "no allowance"
# --------------------------------------------------------------------------------------------- #
def test_admins_are_unmetered_and_report_zero_included():
    """0 included means UNMETERED, never "exhausted".

    Reading it the other way would lock out exactly the accounts meant to be exempt, which is the
    same shape of bug as treating a null signal score as a zero.
    """
    admin = _user("free", admin=True)
    _spend(admin, 50_000)
    with get_session() as s:
        used, included = period_usage(s, s.get(User, admin.id))
        assert (used, included) == (0, 0)
        enforce_period_budget(s, s.get(User, admin.id), what="compile")


def test_a_free_account_is_metered_too():
    """An unpaid account making unbounded compile calls is the same hole as a paid one."""
    u = _user(None, renews_in_days=None)
    _spend(u, plans.FREE.monthly_call_ceiling)
    with get_session() as s:
        with pytest.raises(HTTPException):
            enforce_period_budget(s, s.get(User, u.id), what="compile")


# --------------------------------------------------------------------------------------------- #
# The period boundary
# --------------------------------------------------------------------------------------------- #
def test_the_meter_resets_with_the_customers_billing_period_not_the_calendar():
    """The call allowance and the credit grant must refill on the same day.

    A customer whose credits refill on the 17th but whose lookups refill on the 1st would
    reasonably conclude one of the two numbers is broken.
    """
    renews = datetime.now(timezone.utc) + timedelta(days=8)
    u = _user("starter", renews_in_days=8)
    start = billing_period_start(u)
    # The period began about a month before the renewal, not on the 1st of this month.
    assert start <= (renews - timedelta(days=27)).strftime("%Y-%m-%d")


def test_an_account_with_no_subscription_falls_back_to_the_calendar_month():
    u = _user(None, renews_in_days=None)
    assert billing_period_start(u) == datetime.now(timezone.utc).strftime("%Y-%m-01")


def test_a_stale_renewal_date_does_not_grant_an_unbounded_window():
    """A lapsed subscription's ancient renewal date would otherwise sum months of usage forever."""
    u = _user("starter", renews_in_days=-400)
    assert billing_period_start(u) == datetime.now(timezone.utc).strftime("%Y-%m-01")


def test_spend_before_the_period_started_does_not_count_against_it():
    u = _user("starter", renews_in_days=None)
    with get_session() as s:
        # A row dated last month, i.e. a previous period.
        last_month = (datetime.now(timezone.utc).replace(day=1) - timedelta(days=5))
        from app.core.upstream_budget import _bump

        _bump(s, scope=USER_SCOPE, scope_id=str(u.id),
              day=last_month.strftime("%Y-%m-%d"), platform="x", calls=10_000)
    with get_session() as s:
        used, _ = period_usage(s, s.get(User, u.id))
    assert used == 0, "last period's spend must not eat this period's allowance"
