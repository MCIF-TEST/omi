"""The Evidence-Anchored Blackboard — the shared reasoning workspace.

Holds the read-only Evidence Bundle (immutable evidence references), a shared citation
registry, and an append-only list of typed artifacts. Modules never see the raw bundle
write side or each other directly — they receive a phase-gated :class:`BlackboardView`
(information hiding: a Tier-N module sees only artifacts produced by tiers < N), which is
how the council prevents anchoring/leakage while staying deterministic.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.evidence.bundle import EvidenceBundle, EvidenceItem

from app.reasoning.contracts import Artifact, ReasoningContract


@dataclass
class BlackboardView:
    """What a single module is allowed to see: the read-only bundle, the citation
    registry, and the upstream artifacts permitted by its tier."""

    bundle: EvidenceBundle
    citations: dict[str, dict[str, str]]
    _visible: list[Artifact] = field(default_factory=list)

    def evidence(self, facet: str | None = None) -> list[EvidenceItem]:
        items = self.bundle.evidence.values()
        return [it for it in items if facet is None or it.facet == facet]

    def findings(self) -> list[Artifact]:
        return [a for a in self._visible if a.kind == "finding"]

    def critiques(self) -> list[Artifact]:
        return [a for a in self._visible if a.kind == "critique"]

    def artifacts(self) -> list[Artifact]:
        return list(self._visible)

    def resolve(self, ref: str) -> bool:
        return self.bundle.resolve(ref)


class Blackboard:
    """Shared, append-only workspace over one Evidence Bundle."""

    def __init__(self, bundle: EvidenceBundle) -> None:
        self._bundle = bundle
        self._posts: list[tuple[int, Artifact]] = []      # (producing tier, artifact)
        self.citations: dict[str, dict[str, str]] = bundle.citation_index()

    @property
    def bundle(self) -> EvidenceBundle:
        return self._bundle

    def post(self, artifact: Artifact, tier: int) -> None:
        """Append an artifact (immutable once posted — append-only, never edited)."""
        self._posts.append((int(tier), artifact))

    def artifacts(self) -> list[Artifact]:
        return [a for _, a in self._posts]

    def artifacts_of(self, kind: str) -> list[Artifact]:
        return [a for _, a in self._posts if a.kind == kind]

    def resolve(self, ref: str) -> bool:
        return self._bundle.resolve(ref)

    def view_for(self, contract: ReasoningContract) -> BlackboardView:
        """Build the phase-gated, lens-respecting view for ``contract``: only artifacts
        produced by strictly-lower tiers are visible (Tier-1 sees none; Tier-3 sees all)."""
        visible = [a for tier, a in self._posts if tier < contract.tier]
        return BlackboardView(bundle=self._bundle, citations=self.citations, _visible=visible)
