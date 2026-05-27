"""Narrative service — ingest + retrieve.

The orchestrator calls ``ingest_batch()`` after each scan to feed
comments into the narrative store. The narratives route calls
``list_trending()`` to surface what's spreading.

Both methods sit on top of a single SQLAlchemy session passed in by
the caller — no implicit DB state here so it's easy to test.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Iterable

from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.narrative.clustering import best_match
from app.narrative.embeddings import Embedder, get_embedder
from app.storage.models import Narrative, NarrativeMembership


@dataclass
class IngestItem:
    text: str
    platform: str
    account_external_id: str
    parent_id: str | None = None


@dataclass
class TrendingNarrative:
    id: int
    label: str
    member_count: int
    distinct_authors: int
    first_seen_at: datetime
    last_seen_at: datetime
    recent_members: int     # members in the trailing window
    spread_ratio: float     # distinct_authors / member_count
    sample_text: str


class NarrativeService:
    def __init__(self, session: Session, embedder: Embedder | None = None,
                 match_threshold: float = 0.78,
                 min_text_len: int = 18):
        self.session = session
        self.embedder = embedder or get_embedder()
        self.match_threshold = match_threshold
        self.min_text_len = min_text_len

    # ---- Ingest ---------------------------------------------------------

    def ingest_batch(self, items: Iterable[IngestItem]) -> int:
        """Embed + cluster a batch of comments. Returns count assigned.

        Short comments (< min_text_len chars) are skipped — they're too
        noisy to cluster meaningfully ("nice video", "lol").
        """
        items = [i for i in items if i.text and len(i.text.strip()) >= self.min_text_len]
        if not items:
            return 0

        vecs = self.embedder.embed([i.text for i in items])
        if not vecs:
            return 0

        # Load existing narratives once. Brute-force for now; ANN index
        # later. Centroid stored as JSON list[float].
        stmt = select(Narrative.id, Narrative.centroid_json, Narrative.member_count)
        existing = list(self.session.execute(stmt).all())
        candidates: list[tuple[int, list[float], int]] = [
            (nid, list(centroid or []), mc) for (nid, centroid, mc) in existing
        ]

        assigned = 0
        now = datetime.now(timezone.utc)

        # Track (narrative_id, account_external_id) pairs seen so far in
        # this batch so we can update distinct_authors without a mid-loop
        # SELECT (which would trigger autoflush and risk StaleDataError on
        # SQLite StaticPool when the session has unflushed dirty objects).
        batch_author_pairs: set[tuple[int, str]] = set()

        for item, vec in zip(items, vecs):
            decision = best_match(vec, candidates, match_threshold=self.match_threshold)
            if decision.narrative_id is None:
                # Spawn a new narrative with this comment as its seed
                narrative = Narrative(
                    label=_clip_label(item.text),
                    centroid_json=decision.new_centroid,
                    dimensions=len(vec),
                    member_count=1,
                    distinct_authors=1,
                    first_seen_at=now,
                    last_seen_at=now,
                )
                self.session.add(narrative)
                self.session.flush()
                membership = NarrativeMembership(
                    narrative_id=narrative.id,
                    platform=item.platform,
                    account_external_id=item.account_external_id,
                    parent_id=item.parent_id,
                    comment_text=item.text[:600],
                    observed_at=now,
                )
                self.session.add(membership)
                batch_author_pairs.add((narrative.id, item.account_external_id))
                candidates.append((narrative.id, decision.new_centroid, 1))
                assigned += 1
            else:
                # Existing narrative — update centroid, append membership
                narrative = self.session.get(Narrative, decision.narrative_id)
                if narrative is None:
                    continue
                narrative.centroid_json = decision.new_centroid
                narrative.member_count += 1
                narrative.last_seen_at = now
                # Distinct-authors: bump if this account hasn't contributed
                # to this narrative yet (check batch first to avoid a
                # SELECT that triggers autoflush on dirty objects).
                pair = (narrative.id, item.account_external_id)
                if pair not in batch_author_pairs:
                    existing_author = self.session.execute(
                        select(func.count(NarrativeMembership.id)).where(
                            NarrativeMembership.narrative_id == narrative.id,
                            NarrativeMembership.account_external_id == item.account_external_id,
                        )
                    ).scalar_one()
                    if existing_author == 0:
                        narrative.distinct_authors += 1
                batch_author_pairs.add(pair)
                membership = NarrativeMembership(
                    narrative_id=narrative.id,
                    platform=item.platform,
                    account_external_id=item.account_external_id,
                    parent_id=item.parent_id,
                    comment_text=item.text[:600],
                    observed_at=now,
                )
                self.session.add(membership)
                # Update local candidates so the next item sees the new centroid
                for idx, (nid, _c, mc) in enumerate(candidates):
                    if nid == narrative.id:
                        candidates[idx] = (nid, decision.new_centroid, mc + 1)
                        break
                assigned += 1

        return assigned

    # ---- Retrieval ------------------------------------------------------

    def list_trending(
        self, *, window_days: int = 7, limit: int = 20
    ) -> list[TrendingNarrative]:
        """Return narratives ordered by recent activity.

        Trending = number of memberships in the trailing window, with a
        spread bonus (more distinct authors > more comments from one).
        """
        cutoff = datetime.now(timezone.utc) - timedelta(days=window_days)

        # Count recent memberships per narrative
        recent_stmt = (
            select(
                NarrativeMembership.narrative_id,
                func.count(NarrativeMembership.id).label("recent_n"),
            )
            .where(NarrativeMembership.observed_at >= cutoff)
            .group_by(NarrativeMembership.narrative_id)
            .order_by(desc("recent_n"))
            .limit(limit * 3)  # over-fetch; we'll re-rank with spread
        )
        recent_rows = list(self.session.execute(recent_stmt).all())
        if not recent_rows:
            return []

        narrative_ids = [r[0] for r in recent_rows]
        recent_by_id = {r[0]: int(r[1]) for r in recent_rows}

        narrative_rows = list(self.session.execute(
            select(Narrative).where(Narrative.id.in_(narrative_ids))
        ).scalars())

        results: list[TrendingNarrative] = []
        for n in narrative_rows:
            spread = (n.distinct_authors / n.member_count) if n.member_count else 0.0
            results.append(TrendingNarrative(
                id=n.id,
                label=n.label or "(unnamed)",
                member_count=n.member_count,
                distinct_authors=n.distinct_authors,
                first_seen_at=_to_utc(n.first_seen_at),
                last_seen_at=_to_utc(n.last_seen_at),
                recent_members=recent_by_id.get(n.id, 0),
                spread_ratio=spread,
                sample_text=n.label or "",
            ))

        # Final ranking: recent_members × (0.5 + spread). Mixes volume + spread.
        results.sort(key=lambda t: t.recent_members * (0.5 + t.spread_ratio), reverse=True)
        return results[:limit]


def _clip_label(text: str, max_len: int = 200) -> str:
    s = text.strip().replace("\n", " ")
    if len(s) <= max_len:
        return s
    return s[: max_len - 1].rstrip() + "…"


def _to_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt
