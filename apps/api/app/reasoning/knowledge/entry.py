"""Intelligence Library — the knowledge entry (Institutional Intelligence, Sprint 025).

A :class:`KnowledgeEntry` is one unit of curated investigative EXPERTISE — what the AI specialists
reason *from* once the endpoint is live. It is deliberately distinct from the three things it is
often confused with:

* Institutional **Memory** stores *observations* (an append-only, decaying ledger of what was seen).
* The Prompt Registry / Specialist Library stores *instructions* (how a specialist should reason).
* The Intelligence Library stores *expertise* (durable, human-curated investigative knowledge).

Every entry carries the mandated metadata (definition, purpose, evidence requirements, limitations,
false-positive risks, constitutional constraints, relationships, confidence, revision history) plus
the operational core investigators actually use (indicators / counter-indicators) and the lookup
dimensions (category, tags, platforms, investigation types, consuming specialists). Content-addressed
(``ie:``) so knowledge evolution is measurable; GitHub is canonical.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.evidence.bundle import digest

VALID_CONFIDENCE = ("established", "emerging", "hypothesis")
VALID_STATUS = ("draft", "candidate", "validated", "retired", "superseded")


@dataclass(frozen=True)
class Revision:
    """One revision-history record for an entry (audit trail; GitHub PR is the full history)."""

    version: str
    date: str
    note: str


@dataclass(frozen=True)
class KnowledgeEntry:
    """One versioned, content-addressed article of investigative expertise."""

    id: str                                    # stable slug, e.g. "engagement_pods"
    title: str
    category: str                              # KnowledgeCategory id
    definition: str
    purpose: str
    indicators: tuple[str, ...] = ()           # what to look for (operational core)
    counter_indicators: tuple[str, ...] = ()   # what argues against it (precision core)
    evidence_requirements: tuple[str, ...] = ()   # what evidence must be present to assert it
    limitations: tuple[str, ...] = ()
    false_positive_risks: tuple[str, ...] = ()
    constitutional_constraints: tuple[str, ...] = ()   # which constitution rules bound its use
    relationships: tuple[str, ...] = ()        # other entry ids — the knowledge-graph edges
    platforms: tuple[str, ...] = ()            # platform-lookup dimension ("youtube", "x", ...)
    investigation_types: tuple[str, ...] = ()  # investigation-type-lookup dimension
    tags: tuple[str, ...] = ()                 # keyword-lookup dimension
    specialists: tuple[str, ...] = ()          # consuming specialist keys (Phase-3 dependency source)
    confidence: str = "emerging"               # established | emerging | hypothesis
    version: str = "v1"
    status: str = "validated"
    revision_history: tuple[Revision, ...] = ()

    def __post_init__(self) -> None:
        if self.confidence not in VALID_CONFIDENCE:
            raise ValueError(f"unknown confidence {self.confidence!r}")
        if self.status not in VALID_STATUS:
            raise ValueError(f"unknown status {self.status!r}")

    @property
    def content_hash(self) -> str:
        """Content address of the entry's substantive knowledge — stable across processes."""
        return digest(
            {
                "id": self.id, "category": self.category, "version": self.version,
                "definition": self.definition, "purpose": self.purpose,
                "indicators": list(self.indicators), "counter_indicators": list(self.counter_indicators),
                "evidence_requirements": list(self.evidence_requirements),
                "limitations": list(self.limitations),
                "false_positive_risks": list(self.false_positive_risks),
                "constitutional_constraints": list(self.constitutional_constraints),
                "relationships": list(self.relationships),
            },
            prefix="ie:",
        )

    @property
    def active(self) -> bool:
        return self.status == "validated"

    def lookup_terms(self) -> set[str]:
        """The normalized keyword set this entry answers to (id + title words + tags)."""
        terms = {self.id, *self.tags}
        terms.update(w for w in self.title.lower().replace("-", " ").split() if len(w) > 2)
        return {t.lower() for t in terms}

    def to_record(self) -> dict:
        return {
            "id": self.id, "title": self.title, "category": self.category, "version": self.version,
            "status": self.status, "confidence": self.confidence, "content_hash": self.content_hash,
            "relationships": list(self.relationships), "specialists": list(self.specialists),
            "platforms": list(self.platforms), "investigation_types": list(self.investigation_types),
            "tags": list(self.tags), "sections_present": self.sections_present(),
        }

    def sections_present(self) -> int:
        fields = (self.definition, self.purpose, self.indicators, self.counter_indicators,
                  self.evidence_requirements, self.limitations, self.false_positive_risks,
                  self.constitutional_constraints, self.relationships, self.revision_history)
        return sum(1 for f in fields if f)

    def render(self) -> str:
        def _b(items: tuple[str, ...]) -> str:
            return "\n".join(f"- {it}" for it in items) if items else "- (none recorded)"
        revs = "\n".join(f"- {r.version} ({r.date}): {r.note}" for r in self.revision_history) or "- v1: initial"
        return (
            f"# {self.title}  [{self.category} · {self.version} · {self.confidence} · {self.content_hash}]\n\n"
            f"## Definition\n{self.definition}\n\n"
            f"## Purpose\n{self.purpose}\n\n"
            f"## Indicators\n{_b(self.indicators)}\n\n"
            f"## Counter-indicators\n{_b(self.counter_indicators)}\n\n"
            f"## Evidence requirements\n{_b(self.evidence_requirements)}\n\n"
            f"## Limitations\n{_b(self.limitations)}\n\n"
            f"## False-positive risks\n{_b(self.false_positive_risks)}\n\n"
            f"## Constitutional constraints\n{_b(self.constitutional_constraints)}\n\n"
            f"## Relationships\n{_b(self.relationships)}\n\n"
            f"## Revision history\n{revs}"
        )


__all__ = ["KnowledgeEntry", "Revision", "VALID_CONFIDENCE", "VALID_STATUS"]
