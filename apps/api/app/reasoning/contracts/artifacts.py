"""Typed artifacts exchanged on the Evidence-Anchored Blackboard.

Every artifact carries ``evidence_refs`` into the Evidence Bundle (immutable references).
Modules emit these; they never talk to each other directly. New artifact kinds (Hypothesis,
Calibration) are added here without touching the orchestrator — the registry is open.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Artifact:
    """Base for every blackboard artifact. ``kind`` identifies the type; ``evidence_refs``
    are citations into the Evidence Bundle that the Governor/contract can resolve."""

    module: str
    kind: str = ""
    evidence_refs: list[str] = field(default_factory=list)


@dataclass
class Finding(Artifact):
    """A Tier-1 specialist's qualitative, cited observation about one facet of the evidence."""

    signal: str = ""                      # the detector/method this is about
    claim: str = ""                       # plain-language, probabilistic
    direction: str = "neutral"            # raises | lowers | neutral
    strength: str = "moderate"            # weak | moderate | strong

    def __post_init__(self) -> None:
        self.kind = "finding"


@dataclass
class Critique(Artifact):
    """The Counter-Evidence / Red Team artifact — the strongest exculpatory case + what
    would flip the read."""

    targets: str = "leading_suspicion"
    exculpatory: list[dict[str, Any]] = field(default_factory=list)   # [{signal, claim, evidence_refs}]
    would_flip_if: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.kind = "critique"


@dataclass
class Ruling(Artifact):
    """The Judge's output — the candidate assessment (analyst_response_schema-shaped),
    which the Governor validates before anything reaches the user."""

    assessment: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.kind = "ruling"
