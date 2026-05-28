"""Content Intelligence Service — Phase 10.

Every scanned video/post/thread gets a persistent ContentEntity record shared
across all users. Each scan adds an immutable CommentBatch. Individual comments
are deduplicated into ContentComment rows keyed on
(content_entity_id, external_comment_id).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.storage.models import CommentBatch, ContentComment, ContentEntity


class ContentIntelligenceService:
    def __init__(self, session: Session) -> None:
        self._s = session

    # ------------------------------------------------------------------
    # Entity management
    # ------------------------------------------------------------------

    def get_or_create_entity(
        self,
        *,
        platform: str,
        content_id: str,
        kind: str = "video",
        title: str | None = None,
        author_external_id: str | None = None,
        author_handle: str | None = None,
        canonical_url: str | None = None,
        thumbnail_url: str | None = None,
    ) -> ContentEntity:
        entity = self._s.execute(
            select(ContentEntity).where(
                ContentEntity.platform == platform,
                ContentEntity.content_id == content_id,
            )
        ).scalar_one_or_none()

        if entity is None:
            entity = ContentEntity(
                platform=platform,
                content_id=content_id,
                kind=kind,
                title=title,
                author_external_id=author_external_id,
                author_handle=author_handle,
                canonical_url=canonical_url,
                thumbnail_url=thumbnail_url,
            )
            self._s.add(entity)
            self._s.flush()
        else:
            if title and not entity.title:
                entity.title = title
            if author_external_id and not entity.author_external_id:
                entity.author_external_id = author_external_id
            if author_handle and not entity.author_handle:
                entity.author_handle = author_handle
            if canonical_url and not entity.canonical_url:
                entity.canonical_url = canonical_url
            if thumbnail_url and not entity.thumbnail_url:
                entity.thumbnail_url = thumbnail_url

        return entity

    # ------------------------------------------------------------------
    # Batch recording
    # ------------------------------------------------------------------

    def record_batch(
        self,
        *,
        entity: ContentEntity,
        user_id: int | None,
        comments: list[dict[str, Any]],
        handle_map: dict[str, str],
        coordination_score: float = 0.0,
        risk_tier: str = "low",
        tier_distribution: dict[str, int] | None = None,
        next_page_token: str | None = None,
    ) -> CommentBatch:
        tier_distribution = tier_distribution or {}

        # Check new contributor before creating the batch row.
        is_new_contributor = False
        if user_id is not None:
            prior = self._s.execute(
                select(CommentBatch.id).where(
                    CommentBatch.content_entity_id == entity.id,
                    CommentBatch.user_id == user_id,
                ).limit(1)
            ).scalar_one_or_none()
            is_new_contributor = prior is None

        batch = CommentBatch(
            content_entity_id=entity.id,
            user_id=user_id,
            coordination_score=coordination_score,
            risk_tier=risk_tier,
            tier_distribution=tier_distribution,
            next_page_token=next_page_token,
        )
        self._s.add(batch)
        self._s.flush()  # materialise batch.id before comment inserts

        # Pre-load existing comment IDs to avoid per-row SELECT in the loop.
        existing_ids: set[str] = set(
            self._s.execute(
                select(ContentComment.external_comment_id).where(
                    ContentComment.content_entity_id == entity.id,
                )
            ).scalars().all()
        )

        # Pre-load existing author IDs for new-author counting.
        existing_authors: set[str] = set(
            self._s.execute(
                select(ContentComment.author_external_id.distinct()).where(
                    ContentComment.content_entity_id == entity.id,
                )
            ).scalars().all()
        )

        new_count = 0
        dup_count = 0
        batch_authors: set[str] = set()
        new_author_set: set[str] = set()

        for c in comments:
            ext_id = (c.get("comment_id") or "").strip()
            author = (c.get("author_external_id") or "").strip()
            text = (c.get("text") or "").strip()
            created_at: datetime | None = c.get("created_at")

            if not ext_id or not text:
                continue

            batch_authors.add(author)

            if ext_id in existing_ids:
                dup_count += 1
                continue

            if author and author not in existing_authors:
                new_author_set.add(author)

            self._s.add(ContentComment(
                content_entity_id=entity.id,
                first_batch_id=batch.id,
                external_comment_id=ext_id,
                author_external_id=author,
                author_handle=handle_map.get(author),
                text=text,
                observed_at=created_at or datetime.now(tz=timezone.utc),
            ))
            existing_ids.add(ext_id)
            new_count += 1

        batch.comments_fetched = len(comments)
        batch.new_comments = new_count
        batch.duplicates = dup_count
        batch.distinct_authors = len(batch_authors)
        batch.new_authors = len(new_author_set)
        self._last_new_count = new_count   # for callers that want to log it

        # Recompute entity cumulative counters.
        entity.total_batches = (entity.total_batches or 0) + 1
        entity.total_comments_collected = (entity.total_comments_collected or 0) + new_count
        entity.latest_coordination_score = coordination_score
        entity.latest_risk_tier = risk_tier
        entity.latest_tier_distribution = tier_distribution
        entity.last_scanned_at = datetime.now(tz=timezone.utc)
        if is_new_contributor:
            entity.contributor_count = (entity.contributor_count or 0) + 1

        # Recount total distinct authors from the live table.
        distinct_total = self._s.execute(
            select(func.count(ContentComment.author_external_id.distinct())).where(
                ContentComment.content_entity_id == entity.id,
            )
        ).scalar_one() or 0
        entity.total_distinct_authors = distinct_total

        return batch

    # ------------------------------------------------------------------
    # Query helpers
    # ------------------------------------------------------------------

    def list_entities(
        self,
        *,
        platform: str | None = None,
        min_risk_tier: str = "low",
        limit: int = 40,
        offset: int = 0,
    ) -> tuple[int, list[ContentEntity]]:
        """Return (total_count, page) of ContentEntity rows."""
        tier_order = {"low": 0, "moderate": 1, "elevated": 2, "high": 3}
        min_ord = tier_order.get(min_risk_tier, 0)

        q = select(ContentEntity)
        cq = select(func.count()).select_from(ContentEntity)
        if platform:
            q = q.where(ContentEntity.platform == platform)
            cq = cq.where(ContentEntity.platform == platform)
        if min_ord > 0:
            allowed = [t for t, o in tier_order.items() if o >= min_ord]
            q = q.where(ContentEntity.latest_risk_tier.in_(allowed))
            cq = cq.where(ContentEntity.latest_risk_tier.in_(allowed))

        total = self._s.execute(cq).scalar_one() or 0
        rows = list(
            self._s.execute(
                q.order_by(ContentEntity.last_scanned_at.desc())
                .limit(limit)
                .offset(offset)
            ).scalars().all()
        )
        return total, rows

    def get_entity_by_platform_id(
        self, platform: str, content_id: str
    ) -> ContentEntity | None:
        return self._s.execute(
            select(ContentEntity).where(
                ContentEntity.platform == platform,
                ContentEntity.content_id == content_id,
            )
        ).scalar_one_or_none()

    def latest_next_page_token(self, entity_id: int) -> str | None:
        """Return the most recent non-null continuation cursor for resuming
        ingestion, or None if no batch left a cursor (exhausted or first scan).
        """
        return self._s.execute(
            select(CommentBatch.next_page_token)
            .where(
                CommentBatch.content_entity_id == entity_id,
                CommentBatch.next_page_token.is_not(None),
            )
            .order_by(CommentBatch.fetched_at.desc())
            .limit(1)
        ).scalar_one_or_none()

    def get_batches(
        self, entity_id: int, *, limit: int = 50
    ) -> list[CommentBatch]:
        return list(
            self._s.execute(
                select(CommentBatch)
                .where(CommentBatch.content_entity_id == entity_id)
                .order_by(CommentBatch.fetched_at.desc())
                .limit(limit)
            ).scalars().all()
        )

    def get_comments(
        self,
        entity_id: int,
        *,
        limit: int = 100,
        offset: int = 0,
        batch_id: int | None = None,
    ) -> tuple[int, list[ContentComment]]:
        q = select(ContentComment).where(
            ContentComment.content_entity_id == entity_id
        )
        cq = select(func.count()).select_from(ContentComment).where(
            ContentComment.content_entity_id == entity_id
        )
        if batch_id is not None:
            q = q.where(ContentComment.first_batch_id == batch_id)
            cq = cq.where(ContentComment.first_batch_id == batch_id)

        total = self._s.execute(cq).scalar_one() or 0
        rows = list(
            self._s.execute(
                q.order_by(ContentComment.observed_at.desc())
                .limit(limit)
                .offset(offset)
            ).scalars().all()
        )
        return total, rows
