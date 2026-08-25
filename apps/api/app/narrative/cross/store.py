"""The utterance store: every comment from every investigation, in one queryable table.

WHY A COPY. Everything here already exists inside some investigation's ``payload_json``. A blob
cannot be queried, and `payload_json` is the heaviest column in the product, so the alternative to
this table is deserialising megabytes per investigation for every question anyone asks. The archive
list already paid for that lesson once.

WHAT IS DERIVED AND WHAT IS FROZEN. `text`, `posted_at` and `parent_id` are copies. `tier` is a
SNAPSHOT: the tier-mix test asks what the population on a topic looked like at the time, and reading
a later score would quietly rewrite history every time an account is rescanned. `topic_id` is
assigned by a later pass and is NULL until then, which is a resumable state and not an error.
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.storage.models import CrossNarrativeWatermark, Investigation, Utterance

_log = logging.getLogger("omi.narrative.cross")

#: Text is kept this long, then dropped while the row and every aggregate survive. Long enough for a
#: seasonal baseline, short enough that "how much of other people's content do you hold" has an
#: answer. Decision taken with the owner, 2026-08-20.
TEXT_RETENTION_DAYS = 90

#: Comments shorter than this are not evidence of a topic. "nice", "lol", "first" cluster into one
#: enormous meaningless blob and drown every real topic in it.
MIN_TEXT_LEN = 24

#: Per comment. The topic signal is in the opening of a post, and an unbounded copy of every comment
#: in the product is a storage bill with no matching gain in clustering quality.
MAX_TEXT_LEN = 1000

#: Investigations per backfill pass. Bounded because this runs inside the API process alongside real
#: requests, and an unbounded catch-up pass after a long outage would hold the loop for minutes.
BACKFILL_BATCH = 25

STAGE_EXTRACT = "extract_utterances"


@dataclass(frozen=True)
class ExtractedUtterance:
    """One comment, before it becomes a row."""

    account_external_id: str
    handle: str | None
    platform: str
    parent_id: str | None
    text: str
    posted_at: datetime | None
    tier: str | None


def _coerce_dt(value: object) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str) and value:
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    return None


def dedupe_key(
    *,
    platform: str,
    account_external_id: str,
    parent_id: str | None,
    text: str,
    posted_at: datetime | None,
) -> str:
    """A stable identity for one comment.

    Deliberately NOT keyed on the investigation: the same comment reached through two customers'
    scans of the same post is ONE comment, and counting it twice would inflate every volume and
    tier-mix number with our own duplication. It is also not keyed on the platform's comment id,
    because that id is missing often enough that a key depending on it would silently stop
    deduplicating exactly where duplicates are most likely.
    """
    raw = "\x1f".join([
        platform or "",
        account_external_id or "",
        parent_id or "",
        (posted_at.isoformat() if posted_at else ""),
        (text or "").strip()[:MAX_TEXT_LEN],
    ])
    return hashlib.blake2b(raw.encode("utf-8"), digest_size=32).hexdigest()


def extract(payload: dict) -> list[ExtractedUtterance]:
    """Pull every comment out of one investigation payload.

    Reads the per-account ``thread_comments`` blocks, which are the account's comments UNDER THE
    SCANNED POST with their real timestamps. `recent_activity` is deliberately NOT read: that is the
    account's own timeline, which says what an account talks about generally and not what it said
    here, and mixing the two would let one prolific account's unrelated history dominate a topic.
    """
    if not isinstance(payload, dict):
        return []
    video = payload.get("video")
    rows = list((video or {}).get("commenters") or []) if isinstance(video, dict) else []

    out: list[ExtractedUtterance] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        external_id = str(row.get("external_id") or "").strip()
        if not external_id:
            continue
        platform = str(row.get("platform") or "unknown")
        handle = row.get("handle")
        tier = row.get("tier")
        for comment in row.get("thread_comments") or []:
            if not isinstance(comment, dict):
                continue
            text = str(comment.get("text") or "").strip()
            if len(text) < MIN_TEXT_LEN:
                continue
            out.append(ExtractedUtterance(
                account_external_id=external_id,
                handle=str(handle) if handle else None,
                platform=platform,
                parent_id=(str(comment.get("parent_id")) if comment.get("parent_id")
                           else str(row.get("parent_id") or "") or None),
                text=text[:MAX_TEXT_LEN],
                posted_at=_coerce_dt(comment.get("created_at")),
                tier=str(tier) if tier else None,
            ))
    return out


def ingest_investigation(session: Session, investigation: Investigation) -> int:
    """Copy one investigation's comments into the store. Returns rows written.

    Idempotent by construction: the unique index on ``dedupe_key`` is what makes re-running safe,
    and re-running is the normal case for a scheduler that dies on every deploy.
    """
    payload = investigation.payload_json
    if not isinstance(payload, dict):
        return 0

    extracted = extract(payload)
    if not extracted:
        return 0

    keys = [
        dedupe_key(
            platform=u.platform,
            account_external_id=u.account_external_id,
            parent_id=u.parent_id,
            text=u.text,
            posted_at=u.posted_at,
        )
        for u in extracted
    ]
    known = set(session.execute(
        select(Utterance.dedupe_key).where(Utterance.dedupe_key.in_(keys))
    ).scalars())

    written = 0
    seen_in_batch: set[str] = set()
    for utterance, key in zip(extracted, keys):
        if key in known or key in seen_in_batch:
            continue
        seen_in_batch.add(key)
        session.add(Utterance(
            dedupe_key=key,
            investigation_id=investigation.id,
            user_id=investigation.user_id,
            platform=utterance.platform,
            account_external_id=utterance.account_external_id,
            handle=utterance.handle,
            parent_id=utterance.parent_id,
            text=utterance.text,
            posted_at=utterance.posted_at,
            tier=utterance.tier,
        ))
        written += 1
    return written


# ---------------------------------------------------------------------------
# Watermarks. Every stage is resumable, never restartable.
# ---------------------------------------------------------------------------


def get_watermark(session: Session, stage: str) -> CrossNarrativeWatermark:
    row = session.execute(
        select(CrossNarrativeWatermark).where(CrossNarrativeWatermark.stage == stage)
    ).scalar_one_or_none()
    if row is None:
        row = CrossNarrativeWatermark(stage=stage, last_id=0)
        session.add(row)
        session.flush()
    return row


def backfill(session: Session, *, limit: int = BACKFILL_BATCH) -> tuple[int, int]:
    """Extract the next batch of investigations. Returns (investigations, utterances).

    Walks in ``id`` order from the watermark, which is the one ordering that cannot skip a row: an
    investigation is inserted with a monotonically increasing id, so "everything above N" is
    complete in a way that "everything since timestamp T" is not (a transaction committing late
    would fall behind the watermark and be missed forever).
    """
    mark = get_watermark(session, STAGE_EXTRACT)
    rows = list(session.execute(
        select(Investigation)
        .where(Investigation.id > mark.last_id)
        .order_by(Investigation.id.asc())
        .limit(max(1, limit))
    ).scalars())
    if not rows:
        return 0, 0

    total = 0
    for investigation in rows:
        try:
            total += ingest_investigation(session, investigation)
        except Exception:  # noqa: BLE001
            # One malformed payload must not stop the pipeline for every investigation behind it.
            _log.exception("utterance extraction failed for investigation %s", investigation.id)
        mark.last_id = investigation.id
    mark.updated_at = datetime.now(timezone.utc)
    return len(rows), total


def purge_expired_text(session: Session, *, now: datetime | None = None) -> int:
    """Drop the text of utterances past the retention window. Returns rows affected.

    The ROW survives, and so does every count computed from it. Only the text goes, which is what
    bounds how much of other people's content is held while leaving the rolling aggregates that
    drive detection intact.
    """
    cutoff = (now or datetime.now(timezone.utc)) - timedelta(days=TEXT_RETENTION_DAYS)
    result = session.execute(
        update(Utterance)
        .where(Utterance.created_at < cutoff, Utterance.text.is_not(None))
        .values(text=None)
    )
    return int(result.rowcount or 0)


def store_stats(session: Session) -> dict:
    """What the store currently holds. For the admin surface, and for watching it fill up."""
    total, with_topic, with_text = session.execute(
        select(
            func.count(Utterance.id),
            func.count(Utterance.topic_id),
            func.count(Utterance.text),
        )
    ).one()
    accounts = session.execute(
        select(func.count(func.distinct(Utterance.account_external_id)))
    ).scalar_one()
    customers = session.execute(
        select(func.count(func.distinct(Utterance.user_id)))
    ).scalar_one()
    investigations = session.execute(
        select(func.count(func.distinct(Utterance.investigation_id)))
    ).scalar_one()
    return {
        "utterances": int(total or 0),
        "assigned_to_topic": int(with_topic or 0),
        "text_retained": int(with_text or 0),
        "distinct_accounts": int(accounts or 0),
        "distinct_customers": int(customers or 0),
        "distinct_investigations": int(investigations or 0),
    }
