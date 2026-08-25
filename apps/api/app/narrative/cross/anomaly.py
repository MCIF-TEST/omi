"""Score one: is this topic behaving oddly?

THREE COMPONENTS, EACH REQUIRED, AND THE MIDDLE ONE CARRIES THE ARGUMENT.

    volume spike        Is this topic busier than its OWN trailing baseline?
    tier-mix anomaly    Is the share of moderate-and-above accounts above the corpus base rate?
    independence        How many UNRELATED customers landed here?

Volume alone flags every news story: topics genuinely trend. Independence alone flags every news
story too, and worse, because customers scan what they suspect, so a story that makes a subject
topical pulls several customers to it without anything being manufactured. That confound is real and
does not improve with scale.

**The tier-mix test is what separates the two**, and it is why it is not optional. A story that makes
everyone talk about a subject recruits a REPRESENTATIVE sample of accounts. A subject being pushed
recruits a BIASED one. One is a topic being discussed; the other is a topic being worked.

The claim this can support is "anomalous relative to our own corpus", never "anomalous on the
platform", and every report has to say so: the corpus is what customers chose to scan, which is not
a sample of anything.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.narrative.coordination import TIER_RANK
from app.narrative.cross.rollup import corpus_elevated_rate, is_elevated
from app.storage.models import CrossTopic, CrossTopicDay, Utterance

#: The window under test, in days.
WINDOW_DAYS = 7

#: Trailing baseline compared against, in days, ending where the window begins. Long enough that a
#: single quiet week does not make the next one a spike.
BASELINE_DAYS = 28

#: Minimum accounts in the window before the tier mix is tested at all. Below this the binomial tail
#: is dominated by sampling noise, and a topic with four accounts in it can hit any ratio by luck.
MIN_ACCOUNTS = 12

#: Minimum distinct customers before independence counts for anything. Two is where "somebody else
#: also looked" begins; one is a single person's curiosity by definition.
MIN_CUSTOMERS = 2

#: Baseline days required before a volume comparison is honest. A topic first seen three days ago
#: has no trailing baseline, and comparing it against zero makes every new topic infinitely spiky.
MIN_BASELINE_DAYS = 7


@dataclass
class TopicAnomaly:
    topic_id: int
    label: str
    window_start: str
    window_end: str

    # --- the three components, kept separate and reported separately ---------------------------
    volume: float = 0.0
    tier_mix: float = 0.0
    independence: float = 0.0
    score: float = 0.0

    # --- the numbers behind them, so a reader can check the arithmetic --------------------------
    window_utterances: int = 0
    window_accounts: int = 0
    baseline_daily_mean: float = 0.0
    window_daily_mean: float = 0.0
    elevated_accounts: int = 0
    scored_accounts: int = 0
    corpus_elevated: int = 0
    corpus_scored: int = 0
    tier_mix_p: float | None = None
    distinct_customers: int = 0
    distinct_investigations: int = 0
    novel_accounts: int = 0

    refusals: list[str] = field(default_factory=list)

    @property
    def testable(self) -> bool:
        return not self.refusals


def _log_binom(n: int, k: int) -> float:
    if k < 0 or k > n:
        return -math.inf
    return math.lgamma(n + 1) - math.lgamma(k + 1) - math.lgamma(n - k + 1)


def binomial_tail(n: int, k: int, p: float) -> float:
    """``P(X >= k)`` for ``X ~ Binomial(n, p)``. Exact, summed from the smaller side.

    n is the accounts on a topic in a window, which is tens to low hundreds, so an exact sum is
    cheap and there is no reason to approximate something the reader might want to check by hand.
    """
    if k <= 0:
        return 1.0
    if n <= 0 or k > n:
        return 0.0
    p = min(max(p, 0.0), 1.0)
    if p <= 0.0:
        return 0.0
    if p >= 1.0:
        return 1.0
    total = 0.0
    for i in range(k, n + 1):
        total += math.exp(_log_binom(n, i) + i * math.log(p) + (n - i) * math.log1p(-p))
    return min(1.0, max(0.0, total))


def tier_mix_strength(p: float) -> float:
    """Turn a binomial tail into a 0-1 component.

    Nothing above p = 0.05 counts at all, 0.05 maps to 0.5, and 0.0025 (twenty times less likely)
    maps to 1.0. The scale is logarithmic because the interesting range spans orders of magnitude: a
    linear mapping would treat p = 0.04 and p = 0.0001 as nearly the same reading when one is
    unremarkable and the other is the finding.
    """
    if p > 0.05:
        return 0.0
    if p <= 0.0:
        return 1.0
    # log10(0.05 / 0.0025) = 1.301, so dividing by that puts 0.0025 at the top of the range.
    return max(0.0, min(1.0, 0.5 + 0.5 * (math.log10(0.05 / p) / 1.301)))


def _window_distincts(session: Session, topic_id: int, start: date, end: date) -> dict:
    """Distinct accounts, customers and investigations across the whole window.

    Per ACCOUNT for the tier, taking the worst tier that account was seen at. One account posting
    forty times is one account; counting utterances would let a single prolific bot carry the
    binomial tail on its own.
    """
    rows = list(session.execute(
        select(
            Utterance.account_external_id,
            Utterance.user_id,
            Utterance.investigation_id,
            Utterance.tier,
        )
        .where(
            Utterance.topic_id == topic_id,
            Utterance.posted_at.is_not(None),
            Utterance.posted_at >= datetime.combine(start, time.min, tzinfo=timezone.utc),
            Utterance.posted_at < datetime.combine(end, time.min, tzinfo=timezone.utc),
        )
    ).all())

    worst: dict[str, str | None] = {}
    customers: set[int] = set()
    investigations: set[int] = set()
    for account, user_id, investigation_id, tier in rows:
        customers.add(user_id)
        investigations.add(investigation_id)
        current = worst.get(account)
        if account not in worst or TIER_RANK.get(tier or "", 0) > TIER_RANK.get(current or "", 0):
            worst[account] = tier

    scored = [t for t in worst.values() if t]
    return {
        "utterances": len(rows),
        "accounts": len(worst),
        "customers": len(customers),
        "investigations": len(investigations),
        "scored_accounts": len(scored),
        "elevated_accounts": sum(1 for t in scored if is_elevated(t)),
    }


def _days_between(rows: list[CrossTopicDay], start: date, end: date) -> list[CrossTopicDay]:
    return [r for r in rows if start.isoformat() <= r.day < end.isoformat()]


def score_topic(
    session: Session,
    topic_id: int,
    *,
    now: datetime | None = None,
    window_days: int = WINDOW_DAYS,
    baseline_days: int = BASELINE_DAYS,
) -> TopicAnomaly | None:
    """Score one topic over the window ending now. None when the topic does not exist."""
    topic = session.get(CrossTopic, topic_id)
    if topic is None:
        return None

    at = (now or datetime.now(timezone.utc)).date()
    window_start = at - timedelta(days=window_days)
    baseline_start = window_start - timedelta(days=baseline_days)

    rows = list(session.execute(
        select(CrossTopicDay)
        .where(
            CrossTopicDay.topic_id == topic_id,
            CrossTopicDay.day >= baseline_start.isoformat(),
            CrossTopicDay.day < at.isoformat(),
        )
        .order_by(CrossTopicDay.day.asc())
    ).scalars())

    window = _days_between(rows, window_start, at)
    baseline = _days_between(rows, baseline_start, window_start)

    result = TopicAnomaly(
        topic_id=topic_id,
        label=topic.label,
        window_start=window_start.isoformat(),
        window_end=at.isoformat(),
    )

    # DISTINCT counts are computed over the WHOLE WINDOW, not summed from the daily rows.
    #
    # Summing per-day distinct counts is a bug that reads as a feature: an account active on three
    # days counts three times, and two customers who scanned on different days would report as
    # `max(1, 1) = 1` rather than 2, so the one component nothing else can compute would be
    # systematically understated. The daily rows are additive for VOLUME and nothing else.
    window_stats = _window_distincts(session, topic_id, window_start, at)
    result.window_utterances = window_stats["utterances"]
    result.window_accounts = window_stats["accounts"]
    result.elevated_accounts = window_stats["elevated_accounts"]
    result.scored_accounts = window_stats["scored_accounts"]
    result.distinct_customers = window_stats["customers"]
    result.distinct_investigations = window_stats["investigations"]
    result.novel_accounts = sum(d.novel_accounts for d in window)

    if not window or result.window_utterances == 0:
        result.refusals.append("no activity in the window")
        return result

    # --- 1. Volume against the topic's own trailing baseline -------------------------------------
    #
    # Its OWN baseline, never the corpus. Topics differ in size by orders of magnitude, and a busy
    # topic being busy is not news.
    if len(baseline) < MIN_BASELINE_DAYS:
        result.refusals.append(
            f"only {len(baseline)} baseline days, needs {MIN_BASELINE_DAYS}; a topic with no history "
            "cannot be compared against it"
        )
    else:
        result.baseline_daily_mean = sum(d.utterances for d in baseline) / float(baseline_days)
        result.window_daily_mean = result.window_utterances / float(window_days)
        if result.baseline_daily_mean <= 0:
            # Genuinely new activity on a topic that was silent. Real, but it is a first sighting
            # rather than a spike, and calling it an infinite one would rank it above everything.
            result.volume = 0.5 if result.window_utterances > 0 else 0.0
        else:
            ratio = result.window_daily_mean / result.baseline_daily_mean
            # A ratio saturating at 4x. Beyond that the difference between 10x and 40x says more
            # about how quiet the baseline was than about how loud the window is.
            result.volume = max(0.0, min(1.0, (ratio - 1.0) / 3.0))

    # --- 2. Tier mix against the corpus, excluding this topic ------------------------------------
    if result.scored_accounts < MIN_ACCOUNTS:
        result.refusals.append(
            f"{result.scored_accounts} scored accounts in the window, needs {MIN_ACCOUNTS}; "
            "below that the ratio is noise"
        )
    else:
        # The baseline EXCLUDES this topic, and is measured OUTSIDE the window under test. A cluster
        # counted in its own background inflates the distribution it is compared against and hides
        # itself.
        corpus_elevated, corpus_scored = corpus_elevated_rate(
            session,
            exclude_topic_id=topic_id,
            since=baseline_start,
            until=window_start,
        )
        result.corpus_elevated = corpus_elevated
        result.corpus_scored = corpus_scored
        if corpus_scored < MIN_ACCOUNTS:
            result.refusals.append(
                "the corpus has too little history outside this topic to give a base rate"
            )
        else:
            rate = corpus_elevated / float(corpus_scored)
            p = binomial_tail(result.scored_accounts, result.elevated_accounts, rate)
            result.tier_mix_p = p
            result.tier_mix = tier_mix_strength(p)

    # --- 3. Cross-customer independence ----------------------------------------------------------
    #
    # The component no customer and no competitor can compute. It saturates at five, because the
    # difference between five unrelated customers and fifty is not five times the evidence.
    if result.distinct_customers < MIN_CUSTOMERS:
        result.refusals.append(
            f"{result.distinct_customers} customer(s) in the window, needs {MIN_CUSTOMERS}; "
            "one customer's interest is not evidence about the world"
        )
    else:
        result.independence = min(1.0, (result.distinct_customers - 1) / 4.0)

    # Multiplied, not averaged. Each component is REQUIRED: a zero anywhere means the topic has not
    # cleared one of the three questions, and averaging would let a huge volume spike carry a topic
    # whose accounts look completely ordinary, which is every viral news story.
    if result.testable:
        result.score = result.volume * result.tier_mix * result.independence
    return result


def score_all(
    session: Session,
    *,
    now: datetime | None = None,
    limit: int = 200,
) -> list[TopicAnomaly]:
    """Score every topic with recent activity, worst first.

    Untestable topics are RETURNED, carrying their refusals, rather than filtered out. An operator
    watching this fill up needs to see that a topic was looked at and could not be judged; silently
    dropping it is indistinguishable from finding nothing, which is the failure mode the netdetect
    shuffle budget already taught this codebase once.
    """
    at = (now or datetime.now(timezone.utc)).date()
    window_start = at - timedelta(days=WINDOW_DAYS)
    active = list(session.execute(
        select(CrossTopicDay.topic_id)
        .where(CrossTopicDay.day >= window_start.isoformat())
        .group_by(CrossTopicDay.topic_id)
    ).scalars())

    out: list[TopicAnomaly] = []
    for topic_id in active[:max(1, limit)]:
        scored = score_topic(session, topic_id, now=now)
        if scored is not None:
            out.append(scored)
    out.sort(key=lambda a: (a.score, a.window_utterances), reverse=True)
    return out
