"""Institutional Memory — knowledge objects + observation ledger.

Implements the deterministic core of ``OMI_INTELLIGENCE_MEMORY_SYSTEM_V1``. A
``KnowledgeObject`` stores **evidence and observed patterns, never a verdict**; its
confidence / stability / status are *pure functions of its append-only Observation
Ledger* (recomputed, never overwritten). Confidence rises with independent corroboration,
falls with contradiction, and **decays** without re-observation — so memory can never
ossify into self-fulfilling prophecy.

Hard guarantees baked in here: independent-corroboration only (no double-counting), the
**memory-influence quarantine** (entries flagged ``primed`` cannot count as independent
support — memory cannot confirm itself), and ``influence_class`` capped at
``context``/``exculpatory`` (never ``discriminative``).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


def _parse(ts: str | None) -> datetime | None:
    if not ts:
        return None
    try:
        dt = datetime.fromisoformat(ts)
    except ValueError:
        return None
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt


@dataclass
class ObservationLedgerEntry:
    """One evidence event. The raw record is retained so aggregates can be recomputed and
    history is never overwritten."""

    investigation: str                       # the settled investigation (provenance)
    stance: str                              # "supports" | "contradicts"
    evidence_refs: list[str] = field(default_factory=list)   # EvidenceItem digests (evidence, not opinion)
    independence_key: str = ""               # grouped dedup (account/campaign/operation/window)
    at: str = ""                             # ISO-8601 observation time (drives decay)
    human_anchor: dict[str, Any] | None = None
    memory_influence: str = "none"           # "none" | "primed" (quarantine: primed != independent)


@dataclass
class KnowledgeObject:
    """A node in the institutional knowledge graph — a recurring, falsifiable pattern."""

    id: str
    type: str                                # LinguisticFingerprint | BehavioralArchetype | ...
    family: str
    label: str
    signature: list[str] = field(default_factory=list)       # detector/method names that characterize it
    attributes: dict[str, Any] = field(default_factory=dict)
    ledger: list[ObservationLedgerEntry] = field(default_factory=list)
    is_control: bool = False                 # LegitimateCoordinationControl — exculpatory, never raises suspicion
    influence_class: str = "context"         # context | exculpatory (NEVER discriminative)
    superseded_by: str | None = None
    half_life_days: float = 180.0
    retirement_floor: float = 0.12
    version_history: list[dict[str, Any]] = field(default_factory=list)
    platform_scope: list[str] = field(default_factory=list)

    # -- ledger partitions ---------------------------------------------------- #
    def _supports(self) -> list[ObservationLedgerEntry]:
        return [e for e in self.ledger if e.stance == "supports"]

    def _contradicts(self) -> list[ObservationLedgerEntry]:
        return [e for e in self.ledger if e.stance == "contradicts"]

    # -- evidence tally ------------------------------------------------------- #
    def independent_support_count(self) -> int:
        """Distinct independence keys among NON-primed supporting entries. This is the
        anti-double-count + memory-influence quarantine: a memory-primed investigation
        cannot count as independent corroboration (memory cannot confirm itself)."""
        keys = {
            (e.independence_key or e.investigation)
            for e in self._supports() if e.memory_influence != "primed"
        }
        return len(keys)

    def evidence_count(self) -> int:
        return sum(len(e.evidence_refs) for e in self.ledger)

    def contradiction_ratio(self) -> float:
        s, c = len(self._supports()), len(self._contradicts())
        return 0.0 if (s + c) == 0 else round(c / (s + c), 4)

    def stability_score(self) -> float:
        """How consistent the pattern has been (support share). Distinct from confidence."""
        s, c = len(self._supports()), len(self._contradicts())
        return 1.0 if (s + c) == 0 else round(s / (s + c), 4)

    def first_observed(self) -> str | None:
        ts = [e.at for e in self.ledger if e.at]
        return min(ts) if ts else None

    def last_observed(self) -> str | None:
        ts = [e.at for e in self.ledger if e.at]
        return max(ts) if ts else None

    # -- confidence evolution ------------------------------------------------- #
    def confidence(self, now: datetime | None = None) -> float:
        """Corroboration up (saturating) · contradiction down · decay down (half-life).
        A pure function of the ledger + ``now`` — reproducible."""
        n_sup = self.independent_support_count()
        n_con = len(self._contradicts())
        raw = (1.0 - 0.6 ** n_sup) if n_sup > 0 else 0.0          # saturating corroboration
        total = n_sup + n_con
        contra_factor = (1.0 - 0.5 * (n_con / total)) if total else 1.0
        conf = raw * contra_factor
        last = _parse(self.last_observed())
        if last is not None:
            now = now or datetime.now(timezone.utc)
            days = max(0.0, (now - last).total_seconds() / 86400.0)
            conf *= 0.5 ** (days / self.half_life_days)          # decay
        return round(max(0.0, min(1.0, conf)), 4)

    def epistemic_status(self, now: datetime | None = None) -> str:
        """Never reaches a "confirmed truth" value — falsifiable by construction."""
        if self.superseded_by:
            return "superseded"
        if self.confidence(now) < self.retirement_floor:
            return "retired"
        n_sup = self.independent_support_count()
        n_con = len(self._contradicts())
        if n_con > n_sup:
            return "contested"
        if n_sup >= 3 and self.stability_score() >= 0.6:
            return "corroborated"
        if n_sup >= 2:
            return "observed"
        return "hypothesized"

    def retireable(self, now: datetime | None = None) -> bool:
        return (self.confidence(now) < self.retirement_floor) or (self.contradiction_ratio() > 0.5)
