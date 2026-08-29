"""The pass that keeps the cross-investigation view current, and the findings it writes.

FOUR STAGES, EVERY ONE RESUMABLE. This loop lives inside the API process and dies on every deploy,
so a stage that could only be restarted would either redo work (expensive, because assignment
embeds) or skip whatever was in flight (a silent gap in the corpus that no score would report).

    extract  ->  assign  ->  roll up  ->  score

Bounded on purpose. Each stage does a fixed amount of work per pass and returns, because this runs
next to real requests and a catch-up after a long outage must not hold the loop for minutes.
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone

from sqlalchemy import select, true
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.narrative.cross import anomaly, cohort, rollup, store, topics
from app.storage.models import CrossFinding, CrossTopic, CrossTopicDay

_log = logging.getLogger("omi.narrative.cross")

#: Topics rolled up per pass, oldest rollup first.
ROLLUP_PER_PASS = 20

#: Topics scored per pass.
SCORE_PER_PASS = 40

#: A topic must clear this on score one before its cohort is assembled. Not a publication
#: threshold: it is a work threshold, because running netdetect over every topic every pass would
#: burn the loop on subjects nothing has flagged. A cohort finding on a topic below it is still
#: reachable by asking for the topic directly.
COHORT_TRIGGER = 0.15


@dataclass
class PassReport:
    investigations_extracted: int = 0
    utterances_written: int = 0
    utterances_assigned: int = 0
    topics_created: int = 0
    topics_rolled_up: int = 0
    topics_scored: int = 0
    findings_written: int = 0
    cohorts_run: int = 0
    text_purged: int = 0
    skipped: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return asdict(self)


def run_one_pass(session: Session, *, now: datetime | None = None) -> PassReport:
    """One bounded pass through every stage. Safe to call as often as you like."""
    at = now or datetime.now(timezone.utc)
    report = PassReport()

    seen, written = store.backfill(session)
    report.investigations_extracted = seen
    report.utterances_written = written

    assignment = topics.assign_pending(session)
    report.utterances_assigned = assignment.assigned
    report.topics_created = assignment.topics_created
    if assignment.skipped and assignment.reason:
        report.skipped.append(f"assignment: {assignment.reason}")

    for topic_id in _topics_to_roll_up(session):
        rollup.rollup_topic(session, topic_id, now=at)
        report.topics_rolled_up += 1

    scored = anomaly.score_all(session, now=at, limit=SCORE_PER_PASS)
    report.topics_scored = len(scored)

    for result in scored:
        cohort_result = None
        if result.score >= COHORT_TRIGGER:
            cohort_result = cohort.score_topic_cohort(session, result.topic_id, now=at)
            report.cohorts_run += 1
        _write_finding(session, result, cohort_result, now=at)
        report.findings_written += 1

    report.text_purged = store.purge_expired_text(session, now=at)
    return report


def _topics_to_roll_up(session: Session, *, limit: int = ROLLUP_PER_PASS) -> list[int]:
    """Topics whose rollup is most out of date, plus any that have never been rolled up.

    Never-rolled-up first: a topic with no daily rows is invisible to every score, so leaving it
    behind an already-current topic would keep it invisible indefinitely.
    """
    rolled = set(session.execute(select(CrossTopicDay.topic_id).distinct()).scalars())
    # `true()` / `false()` rather than the Python literals: a bare bool in a `where()` is coerced by
    # SQLAlchemy today and is exactly the kind of thing that changes between versions.
    fresh = list(session.execute(
        select(CrossTopic.id)
        .where(CrossTopic.id.notin_(rolled) if rolled else true())
        .order_by(CrossTopic.last_seen_at.desc())
        .limit(limit)
    ).scalars())
    if len(fresh) >= limit or not rolled:
        return fresh

    stale = list(session.execute(
        select(CrossTopic.id)
        .where(CrossTopic.id.in_(rolled))
        .order_by(CrossTopic.last_seen_at.desc())
        .limit(limit - len(fresh))
    ).scalars())
    return fresh + stale


def _write_finding(
    session: Session,
    result: anomaly.TopicAnomaly,
    cohort_result: cohort.CohortResult | None,
    *,
    now: datetime,
) -> CrossFinding:
    """Upsert one finding for (topic, window).

    A dismissed row is UPDATED with the new numbers but keeps its dismissal. An operator who has
    already said "this is a news story" should not be asked again every fifteen minutes, and
    silently reopening it would make the dismissal record worthless as the training signal it is
    the only source of.
    """
    row = session.execute(
        select(CrossFinding).where(
            CrossFinding.topic_id == result.topic_id,
            CrossFinding.window_end == result.window_end,
        )
    ).scalar_one_or_none()
    if row is None:
        row = CrossFinding(topic_id=result.topic_id, window_end=result.window_end)
        session.add(row)

    row.label = result.label
    row.window_start = result.window_start
    row.anomaly_score = result.score
    row.volume = result.volume
    row.tier_mix = result.tier_mix
    row.independence = result.independence
    row.anomaly_detail_json = {
        "window_utterances": result.window_utterances,
        "window_accounts": result.window_accounts,
        "baseline_daily_mean": round(result.baseline_daily_mean, 4),
        "window_daily_mean": round(result.window_daily_mean, 4),
        "elevated_accounts": result.elevated_accounts,
        "scored_accounts": result.scored_accounts,
        "corpus_elevated": result.corpus_elevated,
        "corpus_scored": result.corpus_scored,
        "tier_mix_p": result.tier_mix_p,
        "distinct_customers": result.distinct_customers,
        "distinct_investigations": result.distinct_investigations,
        "novel_accounts": result.novel_accounts,
        # Carried so an operator can see that a topic was LOOKED AT and could not be judged.
        # Dropping this makes "untestable" indistinguishable from "clean".
        "refusals": list(result.refusals),
    }

    if cohort_result is not None:
        row.cohort_accounts = cohort_result.accounts
        row.cohort_refused = cohort_result.refused
        findings = cohort_result.findings
        row.cohort_findings = len(findings)
        ps = [f.corrected_p for f in findings if f.corrected_p is not None]
        row.cohort_best_p = min(ps) if ps else None
        row.needs_adjudication = next(
            (f.needs_adjudication for f in findings if f.needs_adjudication), None,
        )
        row.cohort_detail_json = {
            "investigations": cohort_result.investigations,
            "excluded_contexts": cohort_result.excluded_contexts,
            "findings": [
                {
                    "members": list(f.members),
                    "platform": f.platform,
                    "score": round(f.score, 4),
                    "corrected_p": f.corrected_p,
                    "by_family": {k: round(v, 4) for k, v in (f.by_family or {}).items()},
                    "needs_adjudication": f.needs_adjudication,
                    # The evidence sentences are written HERE, at detection time, because the text
                    # they quote is dropped at the retention window and the finding has to remain
                    # readable after that.
                    "evidence": [
                        {
                            "family": e.feature.family,
                            "kind": e.feature.kind,
                            "shared_by": e.shared_by,
                            # The DENOMINATOR travels with the claim. A rarity assertion with no
                            # corpus count behind it asks to be trusted rather than read.
                            "corpus_count": e.corpus_count,
                            "surprise": round(e.surprise, 4),
                            "sentence": e.sentence,
                        }
                        for e in (f.evidence or [])[:12]
                    ],
                }
                for f in findings[:10]
            ],
        }

    row.updated_at = now
    return row


# ---------------------------------------------------------------------------
# The loop
# ---------------------------------------------------------------------------


def run_one_pass_in_session(*, now: datetime | None = None) -> dict:
    """Open a session, run a pass, commit. The entry point the scheduler and the admin route share."""
    from app.storage.db import get_session

    with get_session() as session:
        report = run_one_pass(session, now=now)
        session.commit()
    return report.as_dict()


# Fixed key in Postgres' advisory-lock namespace, distinct from the monitoring loop's. Must not
# change between deploys or two versions would each think they hold it.
_CROSS_LOCK_KEY = 918_273_646


def _leader_lock():
    """Yield True only to the ONE instance that should run this pass.

    Every instance runs this loop in its own lifespan, so without mutual exclusion N instances mean
    N passes per interval. That is worse here than for monitoring: the assignment stage EMBEDS, so a
    duplicated pass is duplicated spend with a real provider behind it, and two instances assigning
    the same utterances would race on the same centroids.

    Borrowed wholesale from `app.monitoring.scheduler`, including its two judgement calls: a
    Postgres advisory lock because it needs no table and frees itself if the holder crashes, and
    yielding True on any failure because skipping the pass silently is worse than occasionally
    duplicating one.
    """
    from contextlib import contextmanager

    from sqlalchemy import text

    from app.storage.db import get_session

    @contextmanager
    def _inner():
        with get_session() as session:
            bind = session.get_bind()
            if bind.dialect.name != "postgresql":
                yield True
                return
            acquired = False
            try:
                acquired = bool(session.execute(
                    text("SELECT pg_try_advisory_lock(:k)"), {"k": _CROSS_LOCK_KEY},
                ).scalar())
            except Exception:  # noqa: BLE001
                _log.warning("could not acquire the cross-narrative leader lock; running anyway",
                             exc_info=True)
                yield True
                return
            try:
                yield acquired
            finally:
                if acquired:
                    try:
                        session.execute(text("SELECT pg_advisory_unlock(:k)"),
                                        {"k": _CROSS_LOCK_KEY})
                    except Exception:  # noqa: BLE001
                        pass

    return _inner()


@asynccontextmanager
async def lifespan_cross_narratives(app):  # pragma: no cover - exercised by the app lifecycle
    """Start and stop the cross-investigation loop with the FastAPI lifecycle.

    Same shape as `app.monitoring.scheduler.lifespan_monitoring`: no new service, no new bill, one
    asyncio task inside the API process doing bounded work on an interval.
    """
    settings = get_settings()
    task: asyncio.Task | None = None
    if settings.enable_cross_narratives:
        task = asyncio.create_task(_loop())
        _log.info(
            "cross-narrative loop started (interval=%ss)",
            settings.cross_narrative_interval_seconds,
        )
    try:
        yield
    finally:
        if task is not None:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass


async def _loop() -> None:  # pragma: no cover - a timing loop
    settings = get_settings()
    # Offset from the monitoring loop's stagger so the two do not always tick together.
    await asyncio.sleep(11)
    while True:
        try:
            await asyncio.to_thread(_run_if_leader)
        except Exception:  # noqa: BLE001
            _log.exception("cross-narrative pass failed")
        await asyncio.sleep(settings.cross_narrative_interval_seconds)


def _run_if_leader() -> dict | None:  # pragma: no cover - exercised through the loop
    with _leader_lock() as is_leader:
        if not is_leader:
            return None
        return run_one_pass_in_session()
