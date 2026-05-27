"""Narrative service — ingest + retrieve + coordination intelligence.

The orchestrator calls ``ingest_batch()`` after each scan to feed
comments into the narrative store. The narratives route calls
``list_trending()`` to surface what's spreading, and ``get_detail()`` to
drill into one cluster.

Both retrieval methods now run the multi-signal coordination layer
(``app.narrative.coordination``) on top of the raw semantic clustering.
The output: probabilistic scores, propagation timelines, and a graph of
the cluster's MODERATE-or-above accounts. Low-tier accounts never appear
in the displayed cluster — see ``coordination.is_qualifying_tier``.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Iterable

from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.narrative.clustering import best_match
from app.narrative.coordination import (
    CoordinationScores,
    MembershipRecord,
    PropagationPoint,
    amplification_bursts,
    display_tier,
    is_qualifying_tier,
    origin_window,
    propagation_timeline,
    score_narrative,
    text_fingerprint,
)
from app.narrative.embeddings import Embedder, get_embedder
from app.storage.models import (
    Account,
    CoordinationEdge,
    Narrative,
    NarrativeMembership,
    Scan,
)


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
    # Legacy fields
    inauthenticity_score: float = 0.0
    risk_label: str = "unknown"
    platforms: list = None  # type: ignore[assignment]
    # New coordination panel
    risk_tier: str = "low"                       # low | moderate | high | extreme
    coordination_score: float = 0.0
    manipulation_probability: float = 0.0
    synchronization_intensity: float = 0.0
    semantic_cohesion: float = 0.0
    cluster_confidence: int = 0
    coordination_label: str = "unscored"
    qualifying_member_count: int = 0
    qualifying_author_count: int = 0

    def __post_init__(self):
        if self.platforms is None:
            self.platforms = []


@dataclass
class NarrativeTopAccountData:
    external_id: str
    handle: str
    display_name: str | None
    platform: str
    comment_count: int
    tier: str | None
    display_tier: str | None = None
    distinct_parents: int = 0
    influence_score: float = 0.0


@dataclass
class NarrativeSampleData:
    text: str
    account_external_id: str
    handle: str | None
    platform: str
    parent_id: str | None
    observed_at: datetime


@dataclass
class NarrativeGraphNodeData:
    external_id: str
    handle: str
    platform: str
    tier: str | None
    display_tier: str | None
    comment_count: int
    distinct_parents: int
    influence_score: float


@dataclass
class NarrativeGraphEdgeData:
    a: str
    b: str
    strength: float
    methods: list[str]


@dataclass
class NarrativeGraphData:
    nodes: list[NarrativeGraphNodeData] = field(default_factory=list)
    edges: list[NarrativeGraphEdgeData] = field(default_factory=list)


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
    # New coordination panel
    risk_tier: str = "low"
    coordination_score: float = 0.0
    manipulation_probability: float = 0.0
    synchronization_intensity: float = 0.0
    semantic_cohesion: float = 0.0
    cluster_confidence: int = 0
    coordination_label: str = "unscored"
    qualifying_member_count: int = 0
    qualifying_author_count: int = 0
    signal_breakdown: list[dict] = field(default_factory=list)
    propagation: list[dict] = field(default_factory=list)
    bursts: list[dict] = field(default_factory=list)
    origin: dict | None = None
    graph: NarrativeGraphData = field(default_factory=NarrativeGraphData)


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

        stmt = select(Narrative.id, Narrative.centroid_json, Narrative.member_count)
        existing = list(self.session.execute(stmt).all())
        candidates: list[tuple[int, list[float], int]] = [
            (nid, list(centroid or []), mc) for (nid, centroid, mc) in existing
        ]

        assigned = 0
        now = datetime.now(timezone.utc)
        batch_author_pairs: set[tuple[int, str]] = set()

        for item, vec in zip(items, vecs):
            decision = best_match(vec, candidates, match_threshold=self.match_threshold)
            if decision.narrative_id is None:
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
                self.session.add(NarrativeMembership(
                    narrative_id=narrative.id,
                    platform=item.platform,
                    account_external_id=item.account_external_id,
                    parent_id=item.parent_id,
                    comment_text=item.text[:600],
                    observed_at=now,
                ))
                batch_author_pairs.add((narrative.id, item.account_external_id))
                candidates.append((narrative.id, decision.new_centroid, 1))
                assigned += 1
            else:
                narrative = self.session.get(Narrative, decision.narrative_id)
                if narrative is None:
                    continue
                narrative.centroid_json = decision.new_centroid
                narrative.member_count += 1
                narrative.last_seen_at = now
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
                self.session.add(NarrativeMembership(
                    narrative_id=narrative.id,
                    platform=item.platform,
                    account_external_id=item.account_external_id,
                    parent_id=item.parent_id,
                    comment_text=item.text[:600],
                    observed_at=now,
                ))
                for idx, (nid, _c, mc) in enumerate(candidates):
                    if nid == narrative.id:
                        candidates[idx] = (nid, decision.new_centroid, mc + 1)
                        break
                assigned += 1

        return assigned

    # ---- Trending list (with coordination scoring) ----------------------

    def list_trending(
        self,
        *,
        window_days: int = 7,
        limit: int = 20,
        min_risk_tier: str = "low",
    ) -> list[TrendingNarrative]:
        """Return narratives ordered by trending score, enriched with the
        full coordination panel. Clusters with all-low membership and no
        coordination signal naturally rank below high-coordination clusters.

        ``min_risk_tier`` filters output: pass "moderate" to hide organic
        clusters entirely from the list.
        """
        cutoff = datetime.now(timezone.utc) - timedelta(days=window_days)

        # Over-fetch — coordination scoring may re-order significantly.
        recent_stmt = (
            select(
                NarrativeMembership.narrative_id,
                func.count(NarrativeMembership.id).label("recent_n"),
            )
            .where(NarrativeMembership.observed_at >= cutoff)
            .group_by(NarrativeMembership.narrative_id)
            .order_by(desc("recent_n"))
            .limit(limit * 4)
        )
        recent_rows = list(self.session.execute(recent_stmt).all())
        if not recent_rows:
            return []

        narrative_ids = [r[0] for r in recent_rows]
        recent_by_id = {r[0]: int(r[1]) for r in recent_rows}

        narrative_rows = list(self.session.execute(
            select(Narrative).where(Narrative.id.in_(narrative_ids))
        ).scalars())

        # Platform breakdown
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

        # Compute the full coordination panel per narrative. This is the
        # heavyweight part; we batch the tier lookup once.
        worst_tier = _batch_worst_tier(self.session, narrative_ids)
        panels_by_id = _score_panels(self.session, narrative_ids, worst_tier)
        inauth_by_id = {
            nid: panels_by_id[nid].inauthenticity_fraction
            for nid in panels_by_id
        }

        min_rank = _RISK_TIER_RANK.get(min_risk_tier, 0)

        results: list[TrendingNarrative] = []
        for n in narrative_rows:
            spread = (n.distinct_authors / n.member_count) if n.member_count else 0.0
            panel = panels_by_id.get(n.id) or CoordinationScores()
            inauth = inauth_by_id.get(n.id, 0.0)
            if _RISK_TIER_RANK.get(panel.risk_tier, 0) < min_rank:
                continue
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
                risk_label=_legacy_risk_label(inauth, spread),
                platforms=platforms_by_id.get(n.id, []),
                risk_tier=panel.risk_tier,
                coordination_score=panel.coordination_score,
                manipulation_probability=panel.manipulation_probability,
                synchronization_intensity=panel.synchronization_intensity,
                semantic_cohesion=panel.semantic_cohesion,
                cluster_confidence=panel.cluster_confidence,
                coordination_label=panel.coordination_label,
                qualifying_member_count=panel.qualifying_member_count,
                qualifying_author_count=panel.qualifying_author_count,
            ))

        # Final ranking: coordination_score dominates, with recent volume
        # and spread as tiebreakers. Pure semantic recency is no longer
        # enough to chart — the system favours coordination intelligence.
        def _rank_key(t: TrendingNarrative) -> float:
            return (
                t.coordination_score * 100.0
                + (1.0 if t.cluster_confidence >= 2 else 0.0) * 25.0
                + min(1.0, t.recent_members / 50.0) * 10.0
                + t.spread_ratio * 5.0
            )

        results.sort(key=_rank_key, reverse=True)
        return results[:limit]

    # ---- Detail (full drill-down) ---------------------------------------

    def get_detail(self, narrative_id: int) -> NarrativeDetailData | None:
        narrative = self.session.get(Narrative, narrative_id)
        if narrative is None:
            return None

        # Load ALL memberships for this narrative — coordination scoring
        # needs the full set. Capped to a reasonable maximum to keep
        # memory bounded for very large clusters.
        memberships = list(self.session.execute(
            select(NarrativeMembership)
            .where(NarrativeMembership.narrative_id == narrative_id)
            .order_by(NarrativeMembership.observed_at.asc())
            .limit(5000)
        ).scalars())

        # Platform breakdown
        platform_breakdown: dict[str, int] = {}
        for m in memberships:
            platform_breakdown[m.platform] = platform_breakdown.get(m.platform, 0) + 1
        platforms = list(platform_breakdown.keys())

        # Daily activity for last 30 days — bucket in-Python so we don't need
        # cross-dialect date functions.
        cutoff_30 = datetime.now(timezone.utc) - timedelta(days=30)
        day_counts: Counter = Counter()
        for m in memberships:
            obs = _to_utc(m.observed_at)
            if obs < cutoff_30:
                continue
            day_counts[obs.date().isoformat()] += 1
        activity = [{"date": d, "count": c} for d, c in sorted(day_counts.items())]

        # Lookup tier + handle info per (platform, external_id) pair —
        # one query for everyone in this cluster.
        ext_ids = list({m.account_external_id for m in memberships})
        accounts_by_key: dict[tuple[str, str], Account] = {}
        if ext_ids:
            for acc in self.session.execute(
                select(Account).where(Account.external_id.in_(ext_ids))
            ).scalars():
                accounts_by_key[(acc.platform, acc.external_id)] = acc

        # Latest tier per account (across all their scans, keep worst).
        worst_tier_by_ext: dict[str, str] = {}
        if accounts_by_key:
            account_ids = [a.id for a in accounts_by_key.values()]
            tier_rows = list(self.session.execute(
                select(Account.external_id, Scan.tier)
                .join(Scan, Scan.account_id == Account.id)
                .where(Account.id.in_(account_ids))
            ).all())
            for ext_id, tier in tier_rows:
                cur = worst_tier_by_ext.get(ext_id)
                if cur is None or _TIER_RANK.get(tier, 0) > _TIER_RANK.get(cur, 0):
                    worst_tier_by_ext[ext_id] = tier

        # Build the MembershipRecord set for coordination scoring.
        records: list[MembershipRecord] = [
            MembershipRecord(
                account_external_id=m.account_external_id,
                platform=m.platform,
                parent_id=m.parent_id,
                observed_at=_to_utc(m.observed_at),
                text_hash=text_fingerprint(m.comment_text),
                tier=worst_tier_by_ext.get(m.account_external_id),
            )
            for m in memberships
        ]

        panel = score_narrative(
            members=records,
            first_seen_at=_to_utc(narrative.first_seen_at),
            last_seen_at=_to_utc(narrative.last_seen_at),
        )

        # Top accounts — MODERATE+ only. This is the "MOST IMPORTANT RULE":
        # never expose low-tier or unscanned accounts in the cluster surface.
        top_accounts = _build_top_accounts(
            records=records,
            accounts_by_key=accounts_by_key,
        )

        # Sample comments — restricted to suspicious authors when any exist
        # (so the UI shows what the coordinated cell is actually saying);
        # falls back to all members when the cluster is organic.
        samples = _build_samples(
            memberships=memberships,
            accounts_by_key=accounts_by_key,
            qualifying_only=bool(panel.qualifying_member_count),
            worst_tier_by_ext=worst_tier_by_ext,
        )

        # Propagation timeline + bursts
        prop_points = propagation_timeline(records)
        prop_dicts = [
            {
                "bucket_start": p.bucket_start.isoformat(),
                "count": p.count,
                "velocity": round(p.velocity, 3),
                "suspicious_count": p.suspicious_count,
            }
            for p in prop_points
        ]
        bursts = amplification_bursts(prop_points)
        origin = origin_window(records)

        # Coordination subgraph — moderate+ accounts + their persisted
        # coordination_edges from the global graph (Phase 4 store).
        graph = _build_subgraph(
            session=self.session,
            top_accounts=top_accounts,
        )

        spread = (narrative.distinct_authors / narrative.member_count) if narrative.member_count else 0.0

        return NarrativeDetailData(
            id=narrative.id,
            label=narrative.label or "(unnamed)",
            member_count=narrative.member_count,
            distinct_authors=narrative.distinct_authors,
            spread_ratio=spread,
            first_seen_at=_to_utc(narrative.first_seen_at),
            last_seen_at=_to_utc(narrative.last_seen_at),
            inauthenticity_score=panel.inauthenticity_fraction,
            risk_label=_legacy_risk_label(panel.inauthenticity_fraction, spread),
            platforms=platforms,
            platform_breakdown=platform_breakdown,
            activity=activity,
            top_accounts=top_accounts,
            samples=samples,
            risk_tier=panel.risk_tier,
            coordination_score=panel.coordination_score,
            manipulation_probability=panel.manipulation_probability,
            synchronization_intensity=panel.synchronization_intensity,
            semantic_cohesion=panel.semantic_cohesion,
            cluster_confidence=panel.cluster_confidence,
            coordination_label=panel.coordination_label,
            qualifying_member_count=panel.qualifying_member_count,
            qualifying_author_count=panel.qualifying_author_count,
            signal_breakdown=panel.signal_breakdown,
            propagation=prop_dicts,
            bursts=bursts,
            origin=origin,
            graph=graph,
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


_TIER_RANK = {"low": 0, "moderate": 1, "elevated": 2, "high": 3}
_RISK_TIER_RANK = {"low": 0, "moderate": 1, "high": 2, "extreme": 3}


def _clip_label(text: str, max_len: int = 200) -> str:
    s = text.strip().replace("\n", " ")
    if len(s) <= max_len:
        return s
    return s[: max_len - 1].rstrip() + "…"


def _to_utc(dt: datetime) -> datetime:
    if dt is None:
        return dt
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _legacy_risk_label(inauthenticity_score: float, spread_ratio: float) -> str:
    """Map numeric inauthentic fraction → legacy plain-language label.

    Kept so the old `risk_label` field in the API payload remains stable
    for clients that haven't migrated to `risk_tier` yet.
    """
    if inauthenticity_score >= 0.60:
        return "likely_coordinated"
    if inauthenticity_score >= 0.35:
        return "suspicious"
    if inauthenticity_score >= 0.15 or spread_ratio < 0.10:
        return "mixed"
    return "organic"


def _batch_worst_tier(session: Session, narrative_ids: list[int]) -> dict[str, str]:
    """For all accounts touching any of these narratives, return ext_id → worst tier."""
    if not narrative_ids:
        return {}
    ext_ids = list({
        row[0]
        for row in session.execute(
            select(NarrativeMembership.account_external_id)
            .where(NarrativeMembership.narrative_id.in_(narrative_ids))
            .distinct()
        ).all()
    })
    if not ext_ids:
        return {}
    rows = list(session.execute(
        select(Account.external_id, Scan.tier)
        .join(Scan, Scan.account_id == Account.id)
        .where(Account.external_id.in_(ext_ids))
    ).all())
    worst: dict[str, str] = {}
    for ext_id, tier in rows:
        cur = worst.get(ext_id)
        if cur is None or _TIER_RANK.get(tier, 0) > _TIER_RANK.get(cur, 0):
            worst[ext_id] = tier
    return worst


def _score_panels(
    session: Session,
    narrative_ids: list[int],
    worst_tier_by_ext: dict[str, str],
) -> dict[int, CoordinationScores]:
    """Run the coordination scorer over a batch of narratives.

    Loads light membership records (no Account joins) and dispatches to
    ``score_narrative`` per cluster. Memberships per cluster are capped to
    keep the list endpoint bounded.
    """
    if not narrative_ids:
        return {}

    rows = list(session.execute(
        select(
            NarrativeMembership.narrative_id,
            NarrativeMembership.account_external_id,
            NarrativeMembership.platform,
            NarrativeMembership.parent_id,
            NarrativeMembership.observed_at,
            NarrativeMembership.comment_text,
        )
        .where(NarrativeMembership.narrative_id.in_(narrative_ids))
        .order_by(NarrativeMembership.observed_at.desc())
    ).all())

    # Bucket rows per narrative, capping each to MAX_PER_CLUSTER.
    MAX_PER_CLUSTER = 800
    bucketed: dict[int, list] = defaultdict(list)
    for row in rows:
        nid = row[0]
        if len(bucketed[nid]) >= MAX_PER_CLUSTER:
            continue
        bucketed[nid].append(row)

    # Need first/last_seen — query narratives in one shot.
    narratives = {
        n.id: n for n in session.execute(
            select(Narrative).where(Narrative.id.in_(narrative_ids))
        ).scalars()
    }

    out: dict[int, CoordinationScores] = {}
    for nid, rs in bucketed.items():
        narrative = narratives.get(nid)
        if narrative is None:
            continue
        records = [
            MembershipRecord(
                account_external_id=r[1],
                platform=r[2],
                parent_id=r[3],
                observed_at=_to_utc(r[4]),
                text_hash=text_fingerprint(r[5]),
                tier=worst_tier_by_ext.get(r[1]),
            )
            for r in rs
        ]
        out[nid] = score_narrative(
            members=records,
            first_seen_at=_to_utc(narrative.first_seen_at),
            last_seen_at=_to_utc(narrative.last_seen_at),
        )
    # Narratives with no members still need a default entry.
    for nid in narrative_ids:
        out.setdefault(nid, CoordinationScores())
    return out


def _build_top_accounts(
    *,
    records: list[MembershipRecord],
    accounts_by_key: dict[tuple[str, str], Account],
) -> list[NarrativeTopAccountData]:
    """Build the top-accounts list — MODERATE+ accounts ONLY.

    This is the user's "MOST IMPORTANT RULE" enforced in code: low-tier
    or unscanned authors never appear in cluster surfaces.
    """
    by_author: dict[tuple[str, str], dict] = {}
    for r in records:
        if not is_qualifying_tier(r.tier):
            continue
        key = (r.platform, r.account_external_id)
        if key not in by_author:
            by_author[key] = {
                "count": 0,
                "parents": set(),
                "tier": r.tier,
            }
        by_author[key]["count"] += 1
        if r.parent_id:
            by_author[key]["parents"].add(r.parent_id)

    items: list[NarrativeTopAccountData] = []
    max_count = max((d["count"] for d in by_author.values()), default=1)
    max_parents = max((len(d["parents"]) for d in by_author.values()), default=1)
    for (plat, ext_id), data in by_author.items():
        acc = accounts_by_key.get((plat, ext_id))
        tier = data["tier"]
        # Influence score = blend of volume + cross-target spread + tier rank.
        volume_term = data["count"] / max_count if max_count else 0.0
        spread_term = len(data["parents"]) / max_parents if max_parents else 0.0
        tier_term = _TIER_RANK.get(tier, 0) / 3.0
        influence = round(volume_term * 0.45 + spread_term * 0.30 + tier_term * 0.25, 4)
        items.append(NarrativeTopAccountData(
            external_id=ext_id,
            handle=acc.handle if acc else ext_id,
            display_name=acc.display_name if acc else None,
            platform=plat,
            comment_count=data["count"],
            tier=tier,
            display_tier=display_tier(tier),
            distinct_parents=len(data["parents"]),
            influence_score=influence,
        ))
    items.sort(key=lambda x: (x.influence_score, x.comment_count), reverse=True)
    return items[:20]


def _build_samples(
    *,
    memberships: list[NarrativeMembership],
    accounts_by_key: dict[tuple[str, str], Account],
    qualifying_only: bool,
    worst_tier_by_ext: dict[str, str],
) -> list[NarrativeSampleData]:
    """Most recent (deduplicated) comments. When the cluster contains
    suspicious authors, only their comments are sampled — that's what
    the analyst needs to see.
    """
    if not memberships:
        return []
    pool = sorted(memberships, key=lambda m: m.observed_at, reverse=True)
    seen: set[str] = set()
    out: list[NarrativeSampleData] = []
    for m in pool:
        if qualifying_only and not is_qualifying_tier(
            worst_tier_by_ext.get(m.account_external_id)
        ):
            continue
        text_key = m.comment_text[:80].lower().strip()
        if text_key in seen:
            continue
        seen.add(text_key)
        acc = accounts_by_key.get((m.platform, m.account_external_id))
        out.append(NarrativeSampleData(
            text=m.comment_text,
            account_external_id=m.account_external_id,
            handle=acc.handle if acc else None,
            platform=m.platform,
            parent_id=m.parent_id,
            observed_at=_to_utc(m.observed_at),
        ))
        if len(out) >= 15:
            break
    # Fallback: if filter wiped everything, fall back to unfiltered list.
    if qualifying_only and not out:
        return _build_samples(
            memberships=memberships,
            accounts_by_key=accounts_by_key,
            qualifying_only=False,
            worst_tier_by_ext=worst_tier_by_ext,
        )
    return out


def _build_subgraph(
    *,
    session: Session,
    top_accounts: list[NarrativeTopAccountData],
) -> NarrativeGraphData:
    """Build a coordination subgraph from the top moderate+ accounts.

    Pulls persisted edges from the CoordinationEdge store (Phase 4) and
    keeps only edges where BOTH endpoints are in the moderate+ subset —
    the user rule applies to graphs too.
    """
    if not top_accounts:
        return NarrativeGraphData()
    ids = {a.external_id for a in top_accounts}
    if not ids:
        return NarrativeGraphData()

    nodes = [
        NarrativeGraphNodeData(
            external_id=a.external_id,
            handle=a.handle,
            platform=a.platform,
            tier=a.tier,
            display_tier=a.display_tier,
            comment_count=a.comment_count,
            distinct_parents=a.distinct_parents,
            influence_score=a.influence_score,
        )
        for a in top_accounts
    ]

    # Pull edges where either endpoint is in our cluster, keep only ones
    # where BOTH endpoints are.
    id_list = list(ids)
    edge_rows = list(session.execute(
        select(CoordinationEdge)
        .where(
            (CoordinationEdge.account_a.in_(id_list))
            | (CoordinationEdge.account_b.in_(id_list))
        )
    ).scalars())

    max_obs = max((e.observation_count for e in edge_rows), default=1) or 1
    edges: list[NarrativeGraphEdgeData] = []
    for e in edge_rows:
        if e.account_a not in ids or e.account_b not in ids:
            continue
        # Strength blend: observation count + mean cluster score.
        strength = min(1.0, 0.5 * (e.observation_count / max_obs) + 0.5 * float(e.mean_cluster_score or 0.0))
        edges.append(NarrativeGraphEdgeData(
            a=e.account_a,
            b=e.account_b,
            strength=round(strength, 4),
            methods=list(e.methods_json or []),
        ))

    return NarrativeGraphData(nodes=nodes, edges=edges)
