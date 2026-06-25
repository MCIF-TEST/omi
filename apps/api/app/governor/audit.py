"""Audit substrate for the Constitutional Governor — the immutable ValidationTrace.

Every Governor decision yields a content-addressed ``ValidationTrace``. The trace id is a
pure function of the verdict + violation codes + version binding + input/bundle digests
(it excludes the wall-clock ``decided_at``), so a decision is **reproducible**: the same
inputs always yield the same ``trace_id``. The :class:`AuditLog` is append-only.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

from app.evidence.bundle import digest


@dataclass
class ValidationTrace:
    verdict: str                        # permit | reject
    violation_codes: list[str]
    stage_results: list[dict[str, Any]]
    version_binding: dict[str, Any]
    input_digest: str
    bundle_id: str
    fallback_path: str = "none"         # none | floor | safe_abstention
    decided_at: str = ""                # wall-clock; EXCLUDED from trace_id

    def trace_id(self) -> str:
        return digest(
            {
                "verdict": self.verdict,
                "codes": sorted(self.violation_codes),
                "version_binding": self.version_binding,
                "input_digest": self.input_digest,
                "bundle_id": self.bundle_id,
            },
            prefix="vt:",
        )

    @property
    def permitted(self) -> bool:
        return self.verdict == "permit"

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["trace_id"] = self.trace_id()
        return d


class AuditLog:
    """Append-only, content-addressed audit log. In-memory; a JSONL/object-store sink can
    be layered later without changing the contract."""

    def __init__(self) -> None:
        self._entries: list[ValidationTrace] = []

    def record(self, trace: ValidationTrace) -> ValidationTrace:
        if not trace.decided_at:
            trace.decided_at = datetime.now(timezone.utc).isoformat()
        self._entries.append(trace)
        return trace

    @property
    def entries(self) -> list[ValidationTrace]:
        return list(self._entries)

    def __len__(self) -> int:
        return len(self._entries)
