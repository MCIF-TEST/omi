"""Persistence layer for coordination edges.

The store guarantees:
* Edges are symmetric (account_a < account_b at write time).
* Upserts are idempotent on (platform, account_a, account_b).
* methods_json is a deduplicated list of detector names.
* mean_cluster_score is a running average across observations.

This is the only module that knows about the underlying DB schema. The
service layer talks to it via this interface; swapping the backend to
Neo4j later just replaces this file.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.storage.models import CoordinationEdge


@dataclass
class EdgeRecord:
    platform: str
    account_a: str
    account_b: str
    observation_count: int
    methods: list[str]
    mean_cluster_score: float
    last_shared_parent: str | None
    first_observed_at: datetime
    last_observed_at: datetime

    @classmethod
    def from_row(cls, row: CoordinationEdge) -> "EdgeRecord":
        return cls(
            platform=row.platform,
            account_a=row.account_a,
            account_b=row.account_b,
            observation_count=row.observation_count,
            methods=list(row.methods_json or []),
            mean_cluster_score=row.mean_cluster_score,
            last_shared_parent=row.last_shared_parent,
            first_observed_at=_to_utc(row.first_observed_at),
            last_observed_at=_to_utc(row.last_observed_at),
        )


def _ordered_pair(a: str, b: str) -> tuple[str, str] | None:
    if not a or not b or a == b:
        return None
    return (a, b) if a < b else (b, a)


def _to_utc(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


class GraphStore:
    def __init__(self, session: Session):
        self.session = session

    # ---- Writes -------------------------------------------------------

    def upsert_observation(
        self,
        *,
        platform: str,
        a: str,
        b: str,
        method: str,
        cluster_score: float,
        parent_id: str | None = None,
    ) -> EdgeRecord | None:
        """Record one pair-level observation (a + b were in the same cluster).

        Idempotent on (platform, a, b). Running-average score, dedup methods.
        Returns the updated edge or None if the pair was invalid (same id).
        """
        pair = _ordered_pair(a, b)
        if pair is None:
            return None
        a_o, b_o = pair
        now = datetime.now(timezone.utc)

        stmt = select(CoordinationEdge).where(
            CoordinationEdge.platform == platform,
            CoordinationEdge.account_a == a_o,
            CoordinationEdge.account_b == b_o,
        )
        edge = self.session.execute(stmt).scalar_one_or_none()
        if edge is None:
            edge = CoordinationEdge(
                platform=platform,
                account_a=a_o,
                account_b=b_o,
                observation_count=1,
                methods_json=[method],
                mean_cluster_score=cluster_score,
                last_shared_parent=parent_id,
                first_observed_at=now,
                last_observed_at=now,
            )
            self.session.add(edge)
            self.session.flush()
        else:
            n = edge.observation_count or 0
            edge.observation_count = n + 1
            edge.mean_cluster_score = (
                (edge.mean_cluster_score * n + cluster_score) / (n + 1)
                if n > 0 else cluster_score
            )
            methods = list(edge.methods_json or [])
            if method not in methods:
                methods.append(method)
            edge.methods_json = methods
            edge.last_shared_parent = parent_id or edge.last_shared_parent
            edge.last_observed_at = now
        return EdgeRecord.from_row(edge)

    def upsert_cluster(
        self,
        *,
        platform: str,
        members: Iterable[str],
        method: str,
        cluster_score: float,
        parent_id: str | None = None,
    ) -> int:
        """Persist every pair within a cluster. Returns count of upserts."""
        unique = sorted(set(m for m in members if m))
        count = 0
        for i in range(len(unique)):
            for j in range(i + 1, len(unique)):
                if self.upsert_observation(
                    platform=platform, a=unique[i], b=unique[j],
                    method=method, cluster_score=cluster_score,
                    parent_id=parent_id,
                ) is not None:
                    count += 1
        return count

    # ---- Reads --------------------------------------------------------

    def get_edge(self, platform: str, a: str, b: str) -> EdgeRecord | None:
        pair = _ordered_pair(a, b)
        if pair is None:
            return None
        stmt = select(CoordinationEdge).where(
            CoordinationEdge.platform == platform,
            CoordinationEdge.account_a == pair[0],
            CoordinationEdge.account_b == pair[1],
        )
        row = self.session.execute(stmt).scalar_one_or_none()
        return EdgeRecord.from_row(row) if row else None

    def neighbors(self, platform: str, account: str) -> list[EdgeRecord]:
        """All direct edges incident on this account."""
        stmt = select(CoordinationEdge).where(
            CoordinationEdge.platform == platform,
            or_(
                CoordinationEdge.account_a == account,
                CoordinationEdge.account_b == account,
            ),
        )
        return [EdgeRecord.from_row(r) for r in self.session.execute(stmt).scalars()]

    def all_edges(self, platform: str, *, limit: int = 5000) -> list[EdgeRecord]:
        """Whole graph (capped). Used for community detection runs."""
        stmt = (
            select(CoordinationEdge)
            .where(CoordinationEdge.platform == platform)
            .order_by(CoordinationEdge.last_observed_at.desc())
            .limit(limit)
        )
        return [EdgeRecord.from_row(r) for r in self.session.execute(stmt).scalars()]
