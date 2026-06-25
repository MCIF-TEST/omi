"""Canonical Evidence Bundle — the normalized, content-addressed evidence object.

Implements the deterministic core of ``OMI_EVIDENCE_BUNDLE_SPEC_V1``: a bundle is a
**normalized graph** — a flat index of atomic ``EvidenceItem``s (addressed by
``ev:NNNN``), typed ``Entity`` records, and typed ``Relationship`` edges that reference
them by id. It is **content-addressed** (``bundle_id``) and **version-bound** for
reproducibility.

Determinism: a bundle is a *pure function of its inputs* — it carries no wall-clock
timestamps in the addressed content, so identical evidence yields an identical
``bundle_id``. Read-only to all consumers.

Standalone + additive: imports nothing from the detection engine; the Binder
(``binder.py``) produces these from engine outputs without changing any existing
behavior.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from typing import Any

BUNDLE_SCHEMA_VERSION = 1

# The corroboration-gate "discriminative" methods (mirrors the frozen engine guardrail):
# a coordinated/manipulation_network verdict requires at least one of these.
DISCRIMINATIVE_METHODS = frozenset({"fingerprint_cluster", "co_engagement", "co_tag"})

FACETS = frozenset({
    "behavioral", "language", "narrative", "coordination", "graph",
    "metadata", "historical", "risk", "detector", "ml", "label",
})


def canonical_json(obj: Any) -> str:
    """Deterministic JSON serialization (sorted keys, no whitespace) — the basis of
    content-addressing. Stable across runs and processes."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def digest(obj: Any, *, prefix: str = "", length: int = 32) -> str:
    """A content hash of ``obj`` (sha256 over its canonical JSON), optionally prefixed."""
    h = hashlib.sha256(canonical_json(obj).encode("utf-8")).hexdigest()[:length]
    return f"{prefix}{h}" if prefix else h


@dataclass
class EvidenceItem:
    """One atomic, fully-traced piece of evidence. The unit a reasoning module cites."""

    id: str                               # ev:NNNN — unique within the bundle
    facet: str                            # one of FACETS
    kind: str                             # detector_signal | contribution | headline | ...
    source: str                           # store/detector origin
    originating_detector: str             # the specific detector/method/model
    value: dict[str, Any] = field(default_factory=dict)
    confidence: float = 0.0               # 0..1, engine-provided
    direction: str = "neutral"            # raises | lowers | neutral
    supplemental: bool = False            # true => context only, zero suspicion weight
    discriminative: bool | None = None    # for coordination methods
    subject_refs: list[str] = field(default_factory=list)
    label: str = ""
    note: str = ""
    traceability_path: list[dict[str, Any]] = field(default_factory=list)
    provenance: dict[str, Any] = field(default_factory=dict)

    def content_digest(self) -> str:
        """Global content address of this item's normalized value (cross-bundle dedup)."""
        return digest(self.value)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["digest"] = self.content_digest()
        return d


@dataclass
class Entity:
    """A subject under investigation — account / content / cluster / campaign / narrative.
    References evidence by id; never embeds copies of it."""

    id: str                               # acct:001 | content:001 | cluster:001 | ...
    kind: str
    ref: str                              # pseudonymous (never raw handle / PII)
    grain_role: str = "subject"           # subject | member | context
    headline: dict[str, Any] = field(default_factory=dict)  # ECHOED engine numbers
    evidence_refs: list[str] = field(default_factory=list)
    platform: str = "unknown"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Relationship:
    """A typed edge in the batch graph (member_of / co_engaged / cross_link / ...).
    ``grain_boundary`` marks an edge that crosses grains (account<->message) — never
    silent."""

    id: str                               # rel:NNNN
    type: str
    from_: str
    to: str
    weight: float = 0.0
    evidence_refs: list[str] = field(default_factory=list)
    grain_boundary: bool = False

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["from"] = d.pop("from_")        # JSON key is "from"
        return d


@dataclass
class EvidenceBundle:
    """The envelope: a normalized graph over a single grain. Content-addressed and
    version-bound. Built only by the Binder; read-only to consumers."""

    grain: str
    subject: dict[str, Any]
    version_binding: dict[str, Any]
    entities: dict[str, Entity] = field(default_factory=dict)
    evidence: dict[str, EvidenceItem] = field(default_factory=dict)
    relationships: list[Relationship] = field(default_factory=list)
    epistemics: dict[str, list] = field(
        default_factory=lambda: {"contradictions": [], "missing_evidence": [], "unknowns": []}
    )
    capabilities: dict[str, bool] = field(default_factory=dict)

    # ---- content addressing ------------------------------------------------- #
    def _content(self) -> dict[str, Any]:
        """The addressed content. Excludes the ``bundle_id`` itself and any wall-clock,
        so the id is a pure function of the evidence (reproducible)."""
        return {
            "schema": BUNDLE_SCHEMA_VERSION,
            "grain": self.grain,
            "subject": self.subject,
            "version_binding": self.version_binding,
            "entities": {k: self.entities[k].to_dict() for k in sorted(self.entities)},
            "evidence": {k: self.evidence[k].to_dict() for k in sorted(self.evidence)},
            "relationships": sorted((r.to_dict() for r in self.relationships), key=canonical_json),
            "epistemics": self.epistemics,
        }

    def bundle_id(self) -> str:
        return digest(self._content(), prefix="b:")

    def citation_index(self) -> dict[str, dict[str, str]]:
        return {eid: {"facet": it.facet, "digest": it.content_digest()} for eid, it in self.evidence.items()}

    def headline(self) -> dict[str, Any]:
        """The single ``kind == 'headline'`` item's value — the echo source for the
        Governor (overall_probability / tier / confidence)."""
        for it in self.evidence.values():
            if it.kind == "headline":
                return it.value
        return {}

    def resolve(self, ref: str) -> bool:
        """Resolve a citation reference against this bundle.

        Accepts (a) native ``ev:NNNN`` ids (optionally with a ``#pointer`` fragment) and
        ``ko:`` / entity ids that are present, and (b) — for transition compatibility with
        the existing analyst — legacy dotted facet paths like ``signals.temporal`` /
        ``contributions.co_engagement`` that map to a present item by originating detector.
        """
        base = ref.split("#", 1)[0].strip()
        if not base:
            return False
        if base in self.evidence or base in self.entities:
            return True
        token = base.rsplit(".", 1)[1] if "." in base else base
        if any(it.originating_detector == token for it in self.evidence.values()):
            return True
        if any(ent.ref == token or ent.id == token for ent in self.entities.values()):
            return True
        return False

    def to_dict(self) -> dict[str, Any]:
        d = self._content()
        d["bundle_id"] = self.bundle_id()
        d["capabilities"] = dict(self.capabilities)
        d["citation_index"] = self.citation_index()
        return d
