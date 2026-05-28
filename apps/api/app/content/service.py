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
            parent_id_raw = c.get("parent_comment_id")
            parent_comment_id = (parent_id_raw or "").strip() or None if parent_id_raw is not None else None
            like_count = c.get("like_count")
            reply_count = c.get("reply_count")

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
                parent_comment_id=parent_comment_id,
                author_external_id=author,
                author_handle=handle_map.get(author),
                text=text,
                like_count=like_count if isinstance(like_count, int) else None,
                reply_count=reply_count if isinstance(reply_count, int) else None,
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
        search: str | None = None,
        limit: int = 40,
        offset: int = 0,
    ) -> tuple[int, list[ContentEntity]]:
        """Return (total_count, page) of ContentEntity rows.

        Search matches case-insensitive substrings against title, content_id,
        and author_handle simultaneously. Empty / whitespace-only ``search``
        is ignored.
        """
        from sqlalchemy import or_

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

        if search and search.strip():
            needle = f"%{search.strip().lower()}%"
            pred = or_(
                func.lower(ContentEntity.title).like(needle),
                func.lower(ContentEntity.content_id).like(needle),
                func.lower(ContentEntity.author_handle).like(needle),
            )
            q = q.where(pred)
            cq = cq.where(pred)

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

    def diff_batches(
        self, entity_id: int, *, from_batch_id: int | None = None, to_batch_id: int | None = None,
    ) -> dict[str, Any] | None:
        """Compare two batches of the same content entity. By default compares
        the newest batch against the one before it ("what changed since
        last scan").

        Returns None when there aren't enough batches to compare.
        """
        batches = self.get_batches(entity_id, limit=2 if (from_batch_id is None and to_batch_id is None) else 100)
        if from_batch_id is None and to_batch_id is None:
            if len(batches) < 2:
                return None
            to_batch = batches[0]   # newest
            from_batch = batches[1] # second-newest
        else:
            by_id = {b.id: b for b in batches}
            to_batch = by_id.get(to_batch_id) if to_batch_id else batches[0]
            from_batch = by_id.get(from_batch_id) if from_batch_id else None
            if to_batch is None or from_batch is None:
                # Pull explicit rows that weren't in the limit-2 default
                to_batch = to_batch or self._s.get(CommentBatch, to_batch_id)
                from_batch = from_batch or self._s.get(CommentBatch, from_batch_id)
                if to_batch is None or from_batch is None:
                    return None
        if to_batch.id == from_batch.id:
            return None

        # Tier distribution delta
        from_td = from_batch.tier_distribution or {}
        to_td = to_batch.tier_distribution or {}
        all_tiers = set(from_td) | set(to_td)
        tier_delta = {t: (to_td.get(t, 0) - from_td.get(t, 0)) for t in all_tiers}

        # New comments are anything where first_batch_id matches to_batch.id
        # AND its observed_at is after from_batch.fetched_at (so reanalysis
        # against the same content with new comments shows up correctly).
        new_comments_rows = list(
            self._s.execute(
                select(ContentComment)
                .where(
                    ContentComment.content_entity_id == entity_id,
                    ContentComment.first_batch_id == to_batch.id,
                )
                .order_by(ContentComment.observed_at.desc())
                .limit(20)
            ).scalars().all()
        )

        new_comment_count = self._s.execute(
            select(func.count(ContentComment.id)).where(
                ContentComment.content_entity_id == entity_id,
                ContentComment.first_batch_id == to_batch.id,
            )
        ).scalar_one() or 0

        # New authors = distinct authors among new-comment rows that don't
        # appear in any earlier batch's comments.
        from sqlalchemy import distinct as _distinct
        new_authors_subq = (
            select(_distinct(ContentComment.author_external_id))
            .where(
                ContentComment.content_entity_id == entity_id,
                ContentComment.first_batch_id == to_batch.id,
            )
        )
        candidate_authors = list(self._s.execute(new_authors_subq).scalars().all())

        prior_authors = set(self._s.execute(
            select(_distinct(ContentComment.author_external_id))
            .where(
                ContentComment.content_entity_id == entity_id,
                ContentComment.first_batch_id != to_batch.id,
            )
        ).scalars().all())
        new_author_set = [a for a in candidate_authors if a not in prior_authors]

        return {
            "from_batch": from_batch,
            "to_batch": to_batch,
            "coordination_score_delta": (to_batch.coordination_score or 0) - (from_batch.coordination_score or 0),
            "risk_tier_changed": (from_batch.risk_tier or "low") != (to_batch.risk_tier or "low"),
            "tier_distribution_delta": tier_delta,
            "new_comment_count": new_comment_count,
            "new_author_count": len(new_author_set),
            "new_authors": new_author_set[:30],
            "sample_new_comments": new_comments_rows,
        }

    def get_author_presence(
        self, platform: str, author_external_id: str, *, limit: int = 50,
    ) -> dict[str, Any]:
        """Cross-content footprint for one author.

        Returns a dict with:
          - ``author_handle``: most recently observed handle (may be None)
          - ``total_comments``: total comments by this author across ALL content
          - ``content_count``: number of distinct content entities they've commented on
          - ``first_seen``: timestamp of earliest comment
          - ``last_seen``: timestamp of most recent comment
          - ``entities``: list of dicts with ContentEntity + per-entity comment_count

        Comments are joined to ContentEntity to filter by platform — this is
        important because the same external_id could in theory exist on
        multiple platforms.
        """
        # All comments by this author across all content (limited to platform)
        comments = list(
            self._s.execute(
                select(ContentComment, ContentEntity)
                .join(ContentEntity, ContentComment.content_entity_id == ContentEntity.id)
                .where(
                    ContentEntity.platform == platform,
                    ContentComment.author_external_id == author_external_id,
                )
                .order_by(ContentComment.observed_at.desc())
            ).all()
        )

        if not comments:
            return {
                "author_handle": None,
                "total_comments": 0,
                "content_count": 0,
                "first_seen": None,
                "last_seen": None,
                "entities": [],
            }

        # Group by content entity
        by_entity: dict[int, dict[str, Any]] = {}
        for c, ent in comments:
            row = by_entity.setdefault(ent.id, {
                "entity": ent,
                "comment_count": 0,
                "first_comment": c.observed_at,
                "last_comment": c.observed_at,
                "sample_text": c.text,
            })
            row["comment_count"] += 1
            if c.observed_at < row["first_comment"]:
                row["first_comment"] = c.observed_at
            if c.observed_at > row["last_comment"]:
                row["last_comment"] = c.observed_at

        # Most recent handle observation
        latest_handle = next(
            (c.author_handle for c, _ in comments if c.author_handle), None
        )

        first_seen = min(c.observed_at for c, _ in comments)
        last_seen = max(c.observed_at for c, _ in comments)

        # Sort entities by recency of latest comment, cap to limit
        entity_rows = sorted(
            by_entity.values(),
            key=lambda r: r["last_comment"],
            reverse=True,
        )[:limit]

        return {
            "author_handle": latest_handle,
            "total_comments": len(comments),
            "content_count": len(by_entity),
            "first_seen": first_seen,
            "last_seen": last_seen,
            "entities": entity_rows,
        }

    def get_author_comments(
        self,
        platform: str,
        author_external_id: str,
        *,
        limit: int = 200,
    ) -> tuple[int, list[tuple[ContentComment, ContentEntity]]]:
        """All comments by one author across every content entity on a platform.

        Returns ``(total_count, rows)`` where ``rows`` is newest-first and each
        row is ``(ContentComment, ContentEntity)`` so the UI can show the
        comment alongside what it was posted on. The count reflects the
        unfiltered total even if ``limit`` truncates the page.
        """
        base = (
            select(ContentComment, ContentEntity)
            .join(ContentEntity, ContentComment.content_entity_id == ContentEntity.id)
            .where(
                ContentEntity.platform == platform,
                ContentComment.author_external_id == author_external_id,
            )
        )
        count_q = (
            select(func.count())
            .select_from(ContentComment)
            .join(ContentEntity, ContentComment.content_entity_id == ContentEntity.id)
            .where(
                ContentEntity.platform == platform,
                ContentComment.author_external_id == author_external_id,
            )
        )
        total = self._s.execute(count_q).scalar_one() or 0
        rows = list(
            self._s.execute(
                base.order_by(ContentComment.observed_at.desc()).limit(limit)
            ).all()
        )
        return total, [(c, e) for c, e in rows]

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
