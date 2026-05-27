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

from sqlalchemy import and_, desc, func, select
from sqlalchemy.orm import Session

from app.narrative.clustering import best_match
from app.narrative.embeddings import Embedder, get_embedder
from app.storage.models import Account, Narrative, NarrativeMembership, Scan


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
    recent_members: int
    spread_ratio: float
    sample_text: str
    inauthenticity_score: float = 0.0
    risk_label: str = "unknown"
    platforms: list = None  # type: ignore[assignment]

    def __post_init__(self):
        if self.platforms is None:
            self.platforms = []


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

        # Platform breakdown per narrative (one query for all)
        plat_rows = list(self.session.execute(
            select(
                NarrativeMembership.narrative_id,
                NarrativeMembership.platform,
                func.count(NarrativeMembership.id),
            )
            .where(NarrativeMembership.narrative_id.in_(narrative_ids))
            .group_by(NarrativeMembership.narrative_id, NarrativeMembership.platform)
        ).all())
        platforms_by_id: dict[int, list[str]] = {}
        for nid, plat, _ in plat_rows:
            platforms_by_id.setdefault(nid, [])
            if plat not in platforms_by_id[nid]:
                platforms_by_id[nid].append(plat)

        # Inauthenticity score per narrative — fraction of *scanned* distinct
        # authors whose latest scan is elevated or high.
        inauth_by_id = _batch_inauthenticity(self.session, narrative_ids)

        results: list[TrendingNarrative] = []
        for n in narrative_rows:
            spread = (n.distinct_authors / n.member_count) if n.member_count else 0.0
            inauth = inauth_by_id.get(n.id, 0.0)
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
                inauthenticity_score=inauth,
                risk_label=_risk_label(inauth, spread),
                platforms=platforms_by_id.get(n.id, []),
            ))

        # Final ranking: recent_members × (0.5 + spread). Mixes volume + spread.
        results.sort(key=lambda t: t.recent_members * (0.5 + t.spread_ratio), reverse=True)
        return results[:limit]

    # ---- Detail ---------------------------------------------------------

    def get_detail(self, narrative_id: int) -> "NarrativeDetailData | None":
        """Full drill-down for one narrative cluster."""
        narrative = self.session.get(Narrative, narrative_id)
        if narrative is None:
            return None

        # Platform breakdown
        plat_rows = list(self.session.execute(
            select(NarrativeMembership.platform, func.count(NarrativeMembership.id))
            .where(NarrativeMembership.narrative_id == narrative_id)
            .group_by(NarrativeMembership.platform)
        ).all())
        platform_breakdown: dict[str, int] = {p: int(c) for p, c in plat_rows}
        platforms = list(platform_breakdown.keys())

        # Daily activity for last 30 days (SQLite strftime)
        cutoff_30 = datetime.now(timezone.utc) - timedelta(days=30)
        activity_rows = list(self.session.execute(
            select(
                func.strftime("%Y-%m-%d", NarrativeMembership.observed_at).label("day"),
                func.count(NarrativeMembership.id).label("cnt"),
            )
            .where(
                NarrativeMembership.narrative_id == narrative_id,
                NarrativeMembership.observed_at >= cutoff_30,
            )
            .group_by("day")
            .order_by("day")
        ).all())
        activity = [{"date": row[0], "count": int(row[1])} for row in activity_rows]

        # Top accounts by comment count (with handle from Account table if available)
        top_acct_rows = list(self.session.execute(
            select(
                NarrativeMembership.account_external_id,
                NarrativeMembership.platform,
                func.count(NarrativeMembership.id).label("cnt"),
            )
            .where(NarrativeMembership.narrative_id == narrative_id)
            .group_by(NarrativeMembership.account_external_id, NarrativeMembership.platform)
            .order_by(desc("cnt"))
            .limit(12)
        ).all())

        top_accounts: list[NarrativeTopAccountData] = []
        for ext_id, plat, cnt in top_acct_rows:
            acc = self.session.execute(
                select(Account).where(Account.external_id == ext_id)
            ).scalar_one_or_none()
            tier: str | None = None
            if acc is not None:
                latest_scan = self.session.execute(
                    select(Scan)
                    .where(Scan.account_id == acc.id)
                    .order_by(Scan.scanned_at.desc())
                    .limit(1)
                ).scalar_one_or_none()
                if latest_scan:
                    tier = latest_scan.tier
            top_accounts.append(NarrativeTopAccountData(
                external_id=ext_id,
                handle=acc.handle if acc else ext_id,
                display_name=acc.display_name if acc else None,
                platform=plat,
                comment_count=int(cnt),
                tier=tier,
            ))

        # Sample comments (15 most recent, de-duped by text)
        sample_rows = list(self.session.execute(
            select(NarrativeMembership)
            .where(NarrativeMembership.narrative_id == narrative_id)
            .order_by(NarrativeMembership.observed_at.desc())
            .limit(40)
        ).scalars())
        seen_texts: set[str] = set()
        samples: list[NarrativeSampleData] = []
        for row in sample_rows:
            text_key = row.comment_text[:80].lower().strip()
            if text_key in seen_texts:
                continue
            seen_texts.add(text_key)
            acc = self.session.execute(
                select(Account).where(Account.external_id == row.account_external_id)
            ).scalar_one_or_none()
            samples.append(NarrativeSampleData(
                text=row.comment_text,
                account_external_id=row.account_external_id,
                handle=acc.handle if acc else None,
                platform=row.platform,
                parent_id=row.parent_id,
                observed_at=_to_utc(row.observed_at),
            ))
            if len(samples) >= 15:
                break

        spread = (narrative.distinct_authors / narrative.member_count) if narrative.member_count else 0.0
        inauth = _batch_inauthenticity(self.session, [narrative_id]).get(narrative_id, 0.0)

        return NarrativeDetailData(
            id=narrative.id,
            label=narrative.label or "(unnamed)",
            member_count=narrative.member_count,
            distinct_authors=narrative.distinct_authors,
            spread_ratio=spread,
            first_seen_at=_to_utc(narrative.first_seen_at),
            last_seen_at=_to_utc(narrative.last_seen_at),
            inauthenticity_score=inauth,
            risk_label=_risk_label(inauth, spread),
            platforms=platforms,
            platform_breakdown=platform_breakdown,
            activity=activity,
            top_accounts=top_accounts,
            samples=samples,
        )


@dataclass
class NarrativeTopAccountData:
    external_id: str
    handle: str
    display_name: str | None
    platform: str
    comment_count: int
    tier: str | None


@dataclass
class NarrativeSampleData:
    text: str
    account_external_id: str
    handle: str | None
    platform: str
    parent_id: str | None
    observed_at: datetime


@dataclass
class NarrativeDetailData:
    id: int
    label: str
    member_count: int
    distinct_authors: int
    spread_ratio: float
    first_seen_at: datetime
    last_seen_at: datetime
    inauthenticity_score: float
    risk_label: str
    platforms: list[str]
    platform_breakdown: dict[str, int]
    activity: list[dict]
    top_accounts: list[NarrativeTopAccountData]
    samples: list[NarrativeSampleData]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _clip_label(text: str, max_len: int = 200) -> str:
    s = text.strip().replace("\n", " ")
    if len(s) <= max_len:
        return s
    return s[: max_len - 1].rstrip() + "…"


def _to_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _risk_label(inauthenticity_score: float, spread_ratio: float) -> str:
    """Map numeric inauthentic fraction → plain-language risk label."""
    if inauthenticity_score >= 0.60:
        return "likely_coordinated"
    if inauthenticity_score >= 0.35:
        return "suspicious"
    if inauthenticity_score >= 0.15 or spread_ratio < 0.10:
        return "mixed"
    return "organic"


def _batch_inauthenticity(session: Session, narrative_ids: list[int]) -> dict[int, float]:
    """Compute inauthenticity score for a batch of narratives in two queries.

    Returns a dict mapping narrative_id → fraction of scanned distinct
    authors whose latest scan tier is elevated or high.
    """
    if not narrative_ids:
        return {}

    # Step 1: Get all (narrative_id, account_external_id) distinct pairs
    pairs = list(session.execute(
        select(
            NarrativeMembership.narrative_id,
            NarrativeMembership.account_external_id,
        )
        .where(NarrativeMembership.narrative_id.in_(narrative_ids))
        .distinct()
    ).all())

    if not pairs:
        return {}

    all_ext_ids = list({p[1] for p in pairs})

    # Step 2: Get latest scan tier per account (correlated subquery approach)
    tier_rows = list(session.execute(
        select(Account.external_id, Scan.tier)
        .join(Scan, Scan.account_id == Account.id)
        .where(Account.external_id.in_(all_ext_ids))
    ).all())

    # Keep only the "worst" (highest-risk) tier per account since multiple
    # scans may exist. worst = most informative for inauthentic scoring.
    _tier_rank = {"low": 0, "moderate": 1, "elevated": 2, "high": 3}
    worst_tier: dict[str, str] = {}
    for ext_id, tier in tier_rows:
        current = worst_tier.get(ext_id)
        if current is None or _tier_rank.get(tier, 0) > _tier_rank.get(current, 0):
            worst_tier[ext_id] = tier

    # Step 3: Aggregate per narrative
    from collections import defaultdict
    scanned: dict[int, list[str]] = defaultdict(list)
    for nid, ext_id in pairs:
        if ext_id in worst_tier:
            scanned[nid].append(worst_tier[ext_id])

    result: dict[int, float] = {}
    for nid in narrative_ids:
        tiers = scanned.get(nid, [])
        if not tiers:
            result[nid] = 0.0
            continue
        flagged = sum(1 for t in tiers if t in ("elevated", "high"))
        result[nid] = flagged / len(tiers)

    return result
