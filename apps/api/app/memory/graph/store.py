"""Institutional Memory store — the append-only knowledge graph + write path.

In-memory for V1 (deterministic, testable); the schema is the contract a graph-DB / vector
backend will later implement without changing callers. The **write path** (``ingest``) is
evidence-gated: it accepts only structural candidates extracted from settled Evidence
Bundles + human/platform anchors — **never an LLM opinion**. Observations are appended;
aggregates are recomputed from the ledger, never overwritten.
"""
from __future__ import annotations

from typing import Any, Iterable

from .objects import KnowledgeObject, ObservationLedgerEntry


def jaccard(a: Iterable[str], b: Iterable[str]) -> float:
    sa, sb = set(a), set(b)
    if not sa and not sb:
        return 0.0
    inter = len(sa & sb)
    union = len(sa | sb)
    return inter / union if union else 0.0


class MemoryStore:
    """The institutional knowledge graph. Append-only; nothing is hard-deleted (retirement
    is a status, kept for audit)."""

    def __init__(self) -> None:
        self._objs: dict[str, KnowledgeObject] = {}
        self._seq = 0
        self._tiers: dict[str, str] = {}          # cached distillation tiers (Sprint 013)

    # -- read ----------------------------------------------------------------- #
    def get(self, ko_id: str) -> KnowledgeObject | None:
        return self._objs.get(ko_id)

    def all(self, *, include_superseded: bool = False) -> list[KnowledgeObject]:
        return [o for o in self._objs.values() if include_superseded or not o.superseded_by]

    def __len__(self) -> int:
        return len(self._objs)

    def candidates_for(self, bundle: Any) -> list[KnowledgeObject]:
        """Narrow to non-superseded objects sharing a signature token with the bundle — the
        in-memory analogue of the Postgres index path (parity for the retrieval engine)."""
        from .retrieval import bundle_signature
        tokens = bundle_signature(bundle)
        if not tokens:
            return []
        return [o for o in self.all() if tokens & set(o.signature)]

    # -- tier cache (Sprint 013 distillation) -------------------------------- #
    def tiers(self) -> dict[str, str]:
        return dict(self._tiers)

    def set_tier(self, ko_id: str, tier: str) -> None:
        prev = self._tiers.get(ko_id)
        self._tiers[ko_id] = tier
        ko = self._objs.get(ko_id)
        if ko is not None:
            ko.version_history.append({"rev": len(ko.version_history) + 1, "change": f"tier:{prev}->{tier}"})

    # -- write (evidence-gated) ---------------------------------------------- #
    def _new_id(self, type_: str) -> str:
        self._seq += 1
        return f"ko:{type_.lower()}:{self._seq:04d}"

    def add(self, obj: KnowledgeObject) -> KnowledgeObject:
        self._objs[obj.id] = obj
        return obj

    def create(
        self, *, type: str, family: str, label: str, signature: Iterable[str],
        is_control: bool = False, influence_class: str = "context",
        attributes: dict[str, Any] | None = None, platform_scope: Iterable[str] | None = None,
    ) -> KnowledgeObject:
        ko = KnowledgeObject(
            id=self._new_id(type), type=type, family=family, label=label,
            signature=list(signature), is_control=is_control,
            influence_class=("exculpatory" if is_control else influence_class),
            attributes=attributes or {}, platform_scope=list(platform_scope or []),
        )
        ko.version_history.append({"rev": 1, "change": "created"})
        return self.add(ko)

    def observe(self, ko_id: str, entry: ObservationLedgerEntry) -> KnowledgeObject:
        """Append one observation (append-only) and version it. Aggregates recompute lazily."""
        ko = self._objs[ko_id]
        ko.ledger.append(entry)
        ko.version_history.append({
            "rev": len(ko.version_history) + 1, "at": entry.at,
            "change": f"observed:{entry.stance}", "investigation": entry.investigation,
        })
        return ko

    def _best_match(self, type_: str, signature: Iterable[str], threshold: float) -> KnowledgeObject | None:
        best: KnowledgeObject | None = None
        best_j = threshold
        for ko in self._objs.values():
            if ko.type != type_ or ko.superseded_by:
                continue
            j = jaccard(ko.signature, signature)
            if j >= best_j:
                best_j, best = j, ko
        return best

    def ingest(
        self, *, candidate: dict[str, Any], investigation: str, stance: str,
        evidence_refs: list[str], independence_key: str, at: str,
        human_anchor: dict[str, Any] | None = None, memory_influence: str = "none",
        match_threshold: float = 0.5,
    ) -> KnowledgeObject:
        """The evidence-gated write path. ``candidate`` is a structural pattern extracted
        from a settled Evidence Bundle ({type, family, label, signature, is_control}); it is
        matched to an existing object (by type + signature) or created, then the observation
        is appended. The LLM is never a write source — only evidence + human anchors."""
        match = self._best_match(candidate["type"], candidate.get("signature", []), match_threshold)
        entry = ObservationLedgerEntry(
            investigation=investigation, stance=stance, evidence_refs=list(evidence_refs),
            independence_key=independence_key, at=at, human_anchor=human_anchor,
            memory_influence=memory_influence,
        )
        if match is None:
            ko = self.create(
                type=candidate["type"], family=candidate.get("family", "patterns_signatures"),
                label=candidate.get("label", candidate["type"]),
                signature=candidate.get("signature", []),
                is_control=bool(candidate.get("is_control", False)),
                influence_class=candidate.get("influence_class", "context"),
                attributes=candidate.get("attributes"),
            )
            return self.observe(ko.id, entry)
        return self.observe(match.id, entry)

    def supersede(self, old_id: str, new_id: str) -> None:
        ko = self._objs.get(old_id)
        if ko is not None:
            ko.superseded_by = new_id
            ko.version_history.append({"rev": len(ko.version_history) + 1, "change": f"superseded_by:{new_id}"})
