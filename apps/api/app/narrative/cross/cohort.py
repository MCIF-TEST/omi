"""Score two: are the accounts on this topic a formation?

Takes every account that appeared on a topic in the window, **across all investigations**, and runs
`app/netdetect` over that cohort. That is the part no single investigation can do: an operation
spread thinly over eight posts scanned by three customers is invisible in each of those eight scans
and obvious in the union.

**THE TWO SCORES ARE NEVER MULTIPLIED.** They answer different questions, and collapsing them would
hide the two most interesting cases: a topic that is anomalous but whose accounts are unrelated
(organic outrage, or a news event), and a tight formation on a topic that is not spiking at all,
which is what a patient operation looks like.

The evidence a cohort is built from is the account's OWN behaviour, gathered from whichever
investigations happened to include it. Nothing here reads a suspicion score: coordination and
botness are orthogonal, and the operation worth catching is the one whose members each score 30.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.netdetect.detect import DEFAULT_SHUFFLES, DetectionResult, detect
from app.netdetect.features import profile_from_commenter
from app.netdetect.significance import Corpus
from app.storage.models import Investigation, Utterance

_log = logging.getLogger("omi.narrative.cross")

#: Accounts below this and there is no corpus to estimate a null from; netdetect refuses anyway, and
#: this avoids assembling the payload to be told so.
MIN_COHORT = 25

#: Accounts above this and one topic's cohort is the whole corpus. A "cohort" that large is not a
#: cohort, it is a subject everybody talks about, and the search space blows up with it.
MAX_COHORT = 600


@dataclass
class CohortResult:
    topic_id: int
    accounts: int = 0
    investigations: int = 0
    detection: DetectionResult | None = None
    refused: str | None = None
    #: The posts every member of the cohort demonstrably engaged, excluded from the evidence.
    excluded_contexts: int = 0

    @property
    def findings(self) -> list:
        return list(self.detection.findings) if self.detection else []

    @property
    def looked(self) -> bool:
        return self.detection is not None and self.detection.looked


def _window_accounts(
    session: Session, topic_id: int, start: date, end: date,
) -> tuple[dict[str, set[int]], set[str]]:
    """Accounts on this topic in the window, and the posts they were seen under.

    Returns ``({account: {investigation_id}}, {parent_id})``.
    """
    rows = list(session.execute(
        select(
            Utterance.account_external_id,
            Utterance.investigation_id,
            Utterance.parent_id,
        )
        .where(
            Utterance.topic_id == topic_id,
            Utterance.posted_at.is_not(None),
            Utterance.posted_at >= datetime.combine(start, time.min, tzinfo=timezone.utc),
            Utterance.posted_at < datetime.combine(end, time.min, tzinfo=timezone.utc),
        )
    ).all())

    accounts: dict[str, set[int]] = {}
    contexts: set[str] = set()
    for account, investigation_id, parent_id in rows:
        accounts.setdefault(account, set()).add(investigation_id)
        if parent_id:
            contexts.add(str(parent_id))
    return accounts, contexts


def _rows_for(session: Session, investigation_ids: set[int], wanted: set[str]) -> list[dict]:
    """Pull the persisted per-account blocks for the cohort, merged across investigations.

    An account seen in three investigations has three blocks, each holding whatever that scan
    collected. The MOST COMPLETE one wins rather than the newest: these blocks differ mainly in how
    much history was fetched, and a detector reading the thinner copy of an account simply finds
    fewer features, which reads as innocence it has not earned.
    """
    best: dict[str, dict] = {}
    for investigation in session.execute(
        select(Investigation).where(Investigation.id.in_(list(investigation_ids)))
    ).scalars():
        payload = investigation.payload_json
        if not isinstance(payload, dict):
            continue
        video = payload.get("video")
        rows = list((video or {}).get("commenters") or []) if isinstance(video, dict) else []
        for row in rows:
            if not isinstance(row, dict):
                continue
            external_id = str(row.get("external_id") or "")
            if external_id not in wanted:
                continue
            current = best.get(external_id)
            if current is None or _evidence_weight(row) > _evidence_weight(current):
                best[external_id] = row
    return list(best.values())


def _evidence_weight(row: dict) -> int:
    """How much this block actually knows about the account. Bigger is more complete."""
    return (
        len(row.get("recent_activity") or [])
        + len(row.get("thread_comments") or [])
        + (1 if row.get("bio") else 0)
        + (1 if row.get("account_created_at") else 0)
    )


def score_topic_cohort(
    session: Session,
    topic_id: int,
    *,
    now: datetime | None = None,
    window_days: int = 7,
    shuffles: int = DEFAULT_SHUFFLES,
) -> CohortResult:
    """Run netdetect over this topic's cross-investigation cohort."""
    at = (now or datetime.now(timezone.utc)).date()
    start = at - timedelta(days=window_days)

    accounts, contexts = _window_accounts(session, topic_id, start, at)
    result = CohortResult(topic_id=topic_id, accounts=len(accounts))

    if len(accounts) < MIN_COHORT:
        result.refused = (
            f"{len(accounts)} accounts on this topic in the window, below the {MIN_COHORT} needed "
            "to estimate a null. Nothing was tested."
        )
        return result
    if len(accounts) > MAX_COHORT:
        result.refused = (
            f"{len(accounts)} accounts is above the {MAX_COHORT} cap: a cohort this large is a "
            "subject everybody talks about rather than a formation."
        )
        return result

    investigation_ids: set[int] = set()
    for ids in accounts.values():
        investigation_ids |= ids
    result.investigations = len(investigation_ids)

    rows = _rows_for(session, investigation_ids, set(accounts))
    if len(rows) < MIN_COHORT:
        result.refused = (
            f"only {len(rows)} of {len(accounts)} accounts still have evidence in a stored payload."
        )
        return result

    # Every account in the cohort engaged the posts the topic was found on, by construction. Without
    # excluding them the whole cohort shares a perfect feature and reports as one enormous
    # operation, which is the same trap `detect_from_commenters` documents for a single scan and is
    # strictly worse here, because the cohort spans several posts and would manufacture a link
    # between every pair of them.
    result.excluded_contexts = len(contexts)
    profiles = [
        profile_from_commenter(row, exclude_context=contexts)
        for row in rows
        if row.get("external_id")
    ]
    result.detection = detect(Corpus(profiles), shuffles=shuffles)
    return result
