"""Shared types for the coordination detectors.

Defined here (and re-exported from ``app.schemas``) so the detector modules
stay decoupled from the schemas package and remain independently testable.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class CoordinationCluster:
    """A group of accounts that look like they're acting together.

    ``method`` identifies which detector produced this cluster — useful for
    the UI ("these 4 share a writing style", "these 12 commented in a
    coordinated burst"). ``score`` is the per-cluster suspicion: 0..1.
    ``members`` are platform-external ids (e.g. YouTube channel IDs).
    """

    method: str
    members: list[str]
    score: float
    evidence: list[str] = field(default_factory=list)
    metadata: dict[str, float] = field(default_factory=dict)


@dataclass
class CoordinationFinding:
    """Output of a single coordination detector run on a batch."""

    method: str
    overall_score: float          # 0..1 — how coordinated the batch looks via this lens
    confidence: float             # 0..1 — how much data backed the estimate
    clusters: list[CoordinationCluster]
    evidence: list[str] = field(default_factory=list)


# Small union-find helper. Used by several detectors to convert a list of
# "these two go together" edges into connected components.
class _UnionFind:
    def __init__(self, items):
        self.parent = {x: x for x in items}

    def find(self, x):
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[ra] = rb

    def components(self) -> dict:
        comps: dict = {}
        for x in self.parent:
            r = self.find(x)
            comps.setdefault(r, []).append(x)
        return comps
