"""The ReasoningContract — a module's stable, versioned interface.

A contract declares what a module IS (tier, lens) and what it produces (output kind +
constraints), independent of *how* it reasons. The orchestrator validates a module's
output against its contract before posting it to the blackboard, so a deterministic
analyst and a future Qwen-backed analyst are interchangeable behind the same contract.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .artifacts import Artifact

# Output-kind names map to the artifact ``kind`` values.
_VALID_OUTPUT_KINDS = frozenset({"finding", "critique", "ruling"})


@dataclass(frozen=True)
class ReasoningContract:
    """A module's interface. Frozen + versioned: the stable seam models plug into."""

    module: str
    tier: int                                  # 1 specialist · 2 synthesis · 3 adjudication
    output_kind: str                           # "finding" | "critique" | "ruling"
    contract_version: str = "v1"
    inputs: tuple[str, ...] = ()               # bundle facets / artifact kinds it may read ("*"=all)
    constraints: tuple[str, ...] = ()          # human-readable invariants the output must honor

    def __post_init__(self) -> None:
        if self.output_kind not in _VALID_OUTPUT_KINDS:
            raise ValueError(f"unknown output_kind {self.output_kind!r}")
        if self.tier not in (1, 2, 3):
            raise ValueError(f"tier must be 1, 2 or 3 (got {self.tier})")


def validate_artifact(contract: ReasoningContract, artifact: Artifact, blackboard: Any) -> tuple[bool, list[str]]:
    """Validate one artifact against its contract + the blackboard.

    Checks (a) the artifact kind matches the contract's declared output, and (b) every
    evidence reference resolves against the bundle (immutable, citable). Returns
    ``(ok, errors)``; the orchestrator drops artifacts that fail (never posts them)."""
    errors: list[str] = []
    if artifact.kind != contract.output_kind:
        errors.append(f"kind {artifact.kind!r} != contract output_kind {contract.output_kind!r}")
    for ref in (artifact.evidence_refs or []):
        if not blackboard.resolve(ref):
            errors.append(f"unresolved evidence_ref: {ref!r}")
    return (not errors, errors)
