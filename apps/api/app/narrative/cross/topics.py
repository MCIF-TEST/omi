"""Emergent topic assignment over the utterance store.

NO TAXONOMY, NO KEYWORD FILE. A topic is a centroid; its label is derived from its own contents
after the fact. Nobody ever writes "water" anywhere, which is the whole point: a curated list can
only ever find what somebody already thought to look for, and an operation on a subject nobody
anticipated is exactly the case worth catching.

Incremental online clustering, reusing `app.narrative.clustering`. O(topics) per utterance, which is
fine while topics number in the hundreds and is the same trade the per-scan path already makes.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.narrative.clustering import best_match
from app.narrative.embeddings import EmbeddingUnavailable, get_embedder
from app.narrative.cross.store import get_watermark
from app.storage.models import CrossTopic, Utterance

_log = logging.getLogger("omi.narrative.cross")

STAGE_ASSIGN = "assign_topics"

#: Cosine above which an utterance joins an existing topic rather than starting one.
#:
#: Higher than the per-scan path's 0.78, deliberately. That path clusters one thread, where being
#: slightly too eager merges two conversations about one video. This path clusters everything every
#: customer has ever scanned, so an over-eager threshold collapses unrelated subjects into a single
#: enormous topic that is then "anomalous" forever because it contains the whole corpus.
MATCH_THRESHOLD = 0.82

#: Utterances per pass. This runs inside the API process next to real requests, and with a hosted
#: embedder each pass is also a network call and a bill.
ASSIGN_BATCH = 200

#: Longest label kept from a representative utterance.
LABEL_CHARS = 160


@dataclass(frozen=True)
class AssignmentResult:
    assigned: int
    topics_created: int
    skipped: bool = False
    reason: str | None = None


def _label_for(text: str) -> str:
    collapsed = " ".join((text or "").split())
    return collapsed[:LABEL_CHARS]


def assign_pending(session: Session, *, limit: int = ASSIGN_BATCH) -> AssignmentResult:
    """Assign the next batch of unassigned utterances to topics.

    Resumable rather than restartable: `topic_id IS NULL` is the queue, so an interrupted pass
    leaves the remainder exactly where it was. The watermark records progress for reporting; the
    NULL check is what actually makes it correct, because a row whose assignment was rolled back
    must be picked up again rather than skipped for being below a watermark.
    """
    embedder = get_embedder()
    space = getattr(embedder, "space", None)

    rows = list(session.execute(
        select(Utterance)
        .where(Utterance.topic_id.is_(None), Utterance.text.is_not(None))
        .order_by(Utterance.id.asc())
        .limit(max(1, limit))
    ).scalars())
    if not rows:
        return AssignmentResult(assigned=0, topics_created=0)

    try:
        vectors = embedder.embed([r.text or "" for r in rows])
    except EmbeddingUnavailable as exc:
        # Skip, never substitute. A batch embedded by a different embedder lands in a space the
        # stored centroids do not share, so every utterance in it would miss every topic and spawn
        # a duplicate. The text is still here, so this is recoverable; a forked topic space is not.
        _log.warning("topic assignment skipped: %s", exc)
        return AssignmentResult(assigned=0, topics_created=0, skipped=True, reason=str(exc))

    if len(vectors) != len(rows):
        return AssignmentResult(
            assigned=0, topics_created=0, skipped=True, reason="embedder returned a short batch",
        )

    width = len(vectors[0])
    space = getattr(embedder, "space", space)

    candidates: list[tuple[int, list[float], int]] = [
        (tid, list(centroid or []), count)
        for (tid, centroid, count) in session.execute(
            select(CrossTopic.id, CrossTopic.centroid_json, CrossTopic.utterance_count)
            .where(or_(CrossTopic.embedding_space == space, CrossTopic.embedding_space.is_(None)))
        ).all()
        if len(centroid or []) == width
    ]

    now = datetime.now(timezone.utc)
    assigned = 0
    created = 0
    touched: set[int] = set()

    for utterance, vector in zip(rows, vectors):
        decision = best_match(vector, candidates, match_threshold=MATCH_THRESHOLD)
        if decision.narrative_id is None:
            topic = CrossTopic(
                label=_label_for(utterance.text or ""),
                centroid_json=decision.new_centroid,
                dimensions=width,
                embedding_space=space,
                utterance_count=1,
                account_count=1,
                first_seen_at=now,
                last_seen_at=now,
            )
            session.add(topic)
            session.flush()
            candidates.append((topic.id, decision.new_centroid, 1))
            utterance.topic_id = topic.id
            created += 1
        else:
            topic = session.get(CrossTopic, decision.narrative_id)
            if topic is None:
                continue
            topic.centroid_json = decision.new_centroid
            topic.utterance_count += 1
            topic.last_seen_at = now
            utterance.topic_id = topic.id
            for index, (tid, _c, count) in enumerate(candidates):
                if tid == topic.id:
                    candidates[index] = (tid, decision.new_centroid, count + 1)
                    break
        utterance.embedding_space = space
        touched.add(utterance.topic_id or 0)
        assigned += 1

    # Distinct accounts, recomputed for the topics this pass touched. Counting incrementally would
    # need a per-topic set of every account ever seen, and the query is cheap next to the embedding
    # call that just ran.
    for topic_id in touched:
        if not topic_id:
            continue
        topic = session.get(CrossTopic, topic_id)
        if topic is None:
            continue
        topic.account_count = int(session.execute(
            select(func.count(func.distinct(Utterance.account_external_id)))
            .where(Utterance.topic_id == topic_id)
        ).scalar_one() or 0)

    mark = get_watermark(session, STAGE_ASSIGN)
    mark.last_id = max(r.id for r in rows)
    mark.updated_at = now

    return AssignmentResult(assigned=assigned, topics_created=created)


def pending_count(session: Session) -> int:
    return int(session.execute(
        select(func.count(Utterance.id))
        .where(Utterance.topic_id.is_(None), Utterance.text.is_not(None))
    ).scalar_one() or 0)
