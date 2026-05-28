"""Reply-pod detection: clusters of accounts that engage each other inside
a single video's reply structure.

A reply pod is an undirected community of accounts where:
  * member A replied to a comment authored by member B, OR
  * members A and B both replied to the same parent comment within a tight
    time window (default 10 minutes).

Pods surface coordinated reply networks — a common bot-ring pattern is to
seed the top comment then pile reply support on it from a stable cohort.

The algorithm is intentionally simple (union-find on weighted edges) and
runs over an in-memory list of comments. No DB access, no external deps.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Iterable


@dataclass
class ReplyEvent:
    comment_id: str
    parent_comment_id: str | None
    author_external_id: str
    posted_at: datetime


@dataclass
class ReplyPod:
    members: list[str]
    score: float
    evidence: list[str] = field(default_factory=list)
    # Pair counts so the UI can show "alice ↔ bob: 4 mutual replies".
    pair_counts: dict[tuple[str, str], int] = field(default_factory=dict)


class _UnionFind:
    def __init__(self, items: Iterable[str]):
        self.parent = {x: x for x in items}

    def find(self, x: str) -> str:
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a: str, b: str) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[ra] = rb

    def components(self) -> dict[str, list[str]]:
        out: dict[str, list[str]] = defaultdict(list)
        for x in self.parent:
            out[self.find(x)].append(x)
        return dict(out)


def detect_reply_pods(
    events: list[ReplyEvent],
    *,
    co_reply_window: timedelta = timedelta(minutes=10),
    min_edge_weight: int = 2,
    min_pod_size: int = 2,
) -> list[ReplyPod]:
    """Detect pods of accounts that reply to each other or co-reply tightly.

    ``min_edge_weight`` is the minimum number of distinct (parent, peer)
    interactions required to count an edge as a coordination signal — set
    to 2 so a single shared reply doesn't trigger a pod.
    """
    if not events:
        return []

    # Index author by comment ID — needed to resolve "I replied to a comment
    # authored by ..." into an author-author edge.
    author_of: dict[str, str] = {e.comment_id: e.author_external_id for e in events}

    # Active participants: authors who replied to anything OR participated in
    # a co-reply window. Used to filter out pure-target accounts (e.g. the
    # video creator whose pinned comment received replies from many bots).
    # Those targets get pulled in via direct-reply edges, but they aren't
    # themselves part of the coordinating cluster.
    active_authors: set[str] = set()

    # Edge weights: how many distinct events connect two authors.
    edge_weight: dict[tuple[str, str], int] = defaultdict(int)
    edge_evidence: dict[tuple[str, str], list[str]] = defaultdict(list)

    def _edge(a: str, b: str, why: str) -> None:
        if not a or not b or a == b:
            return
        key = (a, b) if a < b else (b, a)
        edge_weight[key] += 1
        if len(edge_evidence[key]) < 3:
            edge_evidence[key].append(why)

    # ---- Edge type 1: direct reply (A replied to a comment authored by B) ----
    for ev in events:
        if not ev.parent_comment_id:
            continue
        active_authors.add(ev.author_external_id)
        parent_author = author_of.get(ev.parent_comment_id)
        if not parent_author:
            continue
        _edge(ev.author_external_id, parent_author, "direct reply")

    # ---- Edge type 2: co-reply within window (A and B replied to same parent close in time) ----
    by_parent: dict[str, list[ReplyEvent]] = defaultdict(list)
    for ev in events:
        if ev.parent_comment_id:
            by_parent[ev.parent_comment_id].append(ev)

    for parent_id, group in by_parent.items():
        group.sort(key=lambda e: e.posted_at)
        for i in range(len(group)):
            ei = group[i]
            for j in range(i + 1, len(group)):
                ej = group[j]
                if ej.posted_at - ei.posted_at > co_reply_window:
                    break
                active_authors.add(ei.author_external_id)
                active_authors.add(ej.author_external_id)
                _edge(ei.author_external_id, ej.author_external_id,
                      f"co-replied to one parent within {(ej.posted_at - ei.posted_at).total_seconds():.0f}s")

    # Keep only edges that pass the noise floor.
    strong_edges = [(a, b, w) for (a, b), w in edge_weight.items() if w >= min_edge_weight]
    if not strong_edges:
        return []

    nodes: set[str] = {a for a, _, _ in strong_edges} | {b for _, b, _ in strong_edges}
    uf = _UnionFind(nodes)
    for a, b, _ in strong_edges:
        uf.union(a, b)

    pods: list[ReplyPod] = []
    for root, members in uf.components().items():
        # Pure-target accounts (received replies but never sent any) get
        # dropped here so the video's creator/host doesn't show up as a
        # member of a pod that's actually piling on them.
        members = [m for m in members if m in active_authors]
        if len(members) < min_pod_size:
            continue
        member_set = set(members)
        intra = [(a, b, w) for a, b, w in strong_edges if a in member_set and b in member_set]
        if not intra:
            continue
        total_weight = sum(w for _, _, w in intra)
        max_weight = max(w for _, _, w in intra)
        evidence = []
        for a, b, w in sorted(intra, key=lambda t: -t[2])[:4]:
            for ev_text in edge_evidence[(a, b)][:1]:
                evidence.append(f"{a} ↔ {b}: {w} interactions · {ev_text}")
        # Score: density of interactions normalised by member count.
        density = total_weight / max(len(members), 1)
        score = min(1.0, 0.50 + 0.15 * min(1.0, (len(members) - 2) / 3.0)
                    + 0.25 * min(1.0, density / 4.0)
                    + 0.10 * min(1.0, max_weight / 6.0))
        pair_counts = {(a, b): w for a, b, w in intra}
        pods.append(ReplyPod(
            members=sorted(members),
            score=round(score, 3),
            evidence=evidence,
            pair_counts=pair_counts,
        ))

    pods.sort(key=lambda p: p.score, reverse=True)
    return pods
