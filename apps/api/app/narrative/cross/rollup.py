"""The topic-day rollup: the numbers every score is computed from.

Written rather than derived on read. The anomaly test compares a window against a trailing baseline,
so a read-time computation would walk months of utterances for every question anyone asks, and this
codebase has already paid once for reading the heavy path per row.

**Bucketed on POST time.** A day bucketed on the scan time describes our crawler's working hours,
and every member of one scan would land in a single bucket and look like a spike. Utterances with no
known post time are excluded entirely rather than dated to the day we happened to look.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.narrative.coordination import MIN_INCLUSION_TIER_RANK, TIER_RANK
from app.storage.models import CrossTopicDay, Utterance

#: How far back a rollup pass recomputes. Days already written can still change: an investigation
#: scanned today carries comments posted weeks ago, so a bucket is never final. Recomputing a window
#: rather than appending is what keeps the table correct as history arrives late.
RECOMPUTE_DAYS = 45


def is_elevated(tier: str | None) -> bool:
    """Moderate or above, the same threshold the rest of the product treats as 'worth a look'."""
    if not tier:
        return False
    return TIER_RANK.get(tier, 0) >= MIN_INCLUSION_TIER_RANK


@dataclass(frozen=True)
class DayCounts:
    day: str
    utterances: int
    distinct_accounts: int
    distinct_investigations: int
    distinct_customers: int
    elevated_accounts: int
    scored_accounts: int
    novel_accounts: int


def _day_of(value: datetime) -> str:
    at = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    return at.astimezone(timezone.utc).date().isoformat()


def compute_days(
    session: Session,
    topic_id: int,
    *,
    since: date | None = None,
) -> list[DayCounts]:
    """Recompute this topic's daily counts from the utterances themselves.

    Every count is over DISTINCT things and the tier is taken per ACCOUNT rather than per utterance.
    That distinction is load-bearing for the tier-mix test: one account posting forty times on a
    topic is one account, and counting its comments instead would let a single prolific bot carry
    the binomial tail on its own.
    """
    rows = list(session.execute(
        select(
            Utterance.posted_at,
            Utterance.account_external_id,
            Utterance.investigation_id,
            Utterance.user_id,
            Utterance.tier,
        )
        .where(Utterance.topic_id == topic_id, Utterance.posted_at.is_not(None))
        .order_by(Utterance.posted_at.asc())
    ).all())
    if not rows:
        return []

    per_day: dict[str, dict] = {}
    for posted_at, account, investigation_id, user_id, tier in rows:
        day = _day_of(posted_at)
        bucket = per_day.setdefault(day, {
            "utterances": 0,
            "accounts": {},
            "investigations": set(),
            "customers": set(),
        })
        bucket["utterances"] += 1
        bucket["investigations"].add(investigation_id)
        bucket["customers"].add(user_id)
        # Worst tier seen for this account that day. An account scanned twice with different
        # outcomes is one account, and the harsher reading is the one worth reporting.
        current = bucket["accounts"].get(account)
        if current is None or TIER_RANK.get(tier or "", 0) > TIER_RANK.get(current or "", 0):
            bucket["accounts"][account] = tier

    seen_before: set[str] = set()
    out: list[DayCounts] = []
    for day in sorted(per_day):
        bucket = per_day[day]
        accounts: dict[str, str | None] = bucket["accounts"]
        scored = [t for t in accounts.values() if t]
        novel = sum(1 for account in accounts if account not in seen_before)
        seen_before.update(accounts)
        counts = DayCounts(
            day=day,
            utterances=bucket["utterances"],
            distinct_accounts=len(accounts),
            distinct_investigations=len(bucket["investigations"]),
            distinct_customers=len(bucket["customers"]),
            elevated_accounts=sum(1 for t in scored if is_elevated(t)),
            scored_accounts=len(scored),
            novel_accounts=novel,
        )
        if since is not None and date.fromisoformat(day) < since:
            continue
        out.append(counts)
    return out


def rollup_topic(session: Session, topic_id: int, *, now: datetime | None = None) -> int:
    """Recompute and persist this topic's recent days. Returns days written."""
    at = now or datetime.now(timezone.utc)
    since = (at - timedelta(days=RECOMPUTE_DAYS)).date()
    days = compute_days(session, topic_id, since=since)
    if not days:
        return 0

    existing = {
        row.day: row for row in session.execute(
            select(CrossTopicDay)
            .where(CrossTopicDay.topic_id == topic_id, CrossTopicDay.day >= since.isoformat())
        ).scalars()
    }
    for counts in days:
        row = existing.get(counts.day)
        if row is None:
            row = CrossTopicDay(topic_id=topic_id, day=counts.day)
            session.add(row)
        row.utterances = counts.utterances
        row.distinct_accounts = counts.distinct_accounts
        row.distinct_investigations = counts.distinct_investigations
        row.distinct_customers = counts.distinct_customers
        row.elevated_accounts = counts.elevated_accounts
        row.scored_accounts = counts.scored_accounts
        row.novel_accounts = counts.novel_accounts
        row.updated_at = at
    return len(days)


def corpus_elevated_rate(
    session: Session,
    *,
    exclude_topic_id: int | None = None,
    since: date | None = None,
    until: date | None = None,
) -> tuple[int, int]:
    """The base rate of moderate-and-above accounts across the corpus. Returns (elevated, scored).

    **The topic under test is excluded**, and that is not a refinement. A cluster counted in its own
    background inflates the distribution it is being compared against and hides itself; this
    codebase has now paid for that lesson three separate times, in three different coordinates. The
    window can be narrowed too, so the baseline can be measured OUTSIDE the window under test rather
    than including it.
    """
    stmt = select(
        func.coalesce(func.sum(CrossTopicDay.elevated_accounts), 0),
        func.coalesce(func.sum(CrossTopicDay.scored_accounts), 0),
    )
    if exclude_topic_id is not None:
        stmt = stmt.where(CrossTopicDay.topic_id != exclude_topic_id)
    if since is not None:
        stmt = stmt.where(CrossTopicDay.day >= since.isoformat())
    if until is not None:
        stmt = stmt.where(CrossTopicDay.day < until.isoformat())
    elevated, scored = session.execute(stmt).one()
    return int(elevated or 0), int(scored or 0)
