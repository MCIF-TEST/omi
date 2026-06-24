"""Append-only store of Analyst outputs for future training-data collection.

Each assessment the Analyst produces is recorded as one JSONL line: the validated
response, the grain/subject, the provider + model revision that produced it, and a
digest of the input evidence bundle. This is the raw material for the future
``Andrewexiga/omi-analyst-sft`` gold set (``future_finetuning_strategy.md``) — these
rows are **observations, not gold**: they become training data only after human review.

Governance: the subject ``ref`` is the pseudonymous reference already used in the
bundle (no raw PII); the store is local R&D data and is never fed back into scoring.
"""
from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_STORE = REPO_ROOT / "ml/analyst/data/analyst_outputs.jsonl"


def bundle_digest(bundle: dict[str, Any]) -> str:
    """Stable short hash of the evidence bundle (for dedup + provenance, not identity)."""
    blob = json.dumps(bundle, sort_keys=True, default=str).encode("utf-8")
    return "ev_" + hashlib.sha256(blob).hexdigest()[:16]


@dataclass
class AnalystOutputStore:
    path: Path = DEFAULT_STORE

    def __post_init__(self) -> None:
        self.path = Path(self.path)

    def record(
        self,
        *,
        response: dict[str, Any],
        provider: str,
        bundle: dict[str, Any] | None = None,
        valid: bool = True,
        validation_errors: list[str] | None = None,
    ) -> dict[str, Any]:
        """Append one record and return it. Never raises on a write hiccup is NOT the
        contract here — storage failures should surface in R&D, so this does raise."""
        subject = response.get("subject", {}) if isinstance(response, dict) else {}
        row = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "grain": subject.get("grain"),
            "subject_ref": subject.get("ref"),
            "platform": subject.get("platform"),
            "analyst_version": response.get("analyst_version"),
            "prompt_version": response.get("prompt_version"),
            "schema_version": response.get("schema_version"),
            "model_revision": response.get("model_revision"),
            "provider": provider,
            "valid": valid,
            "validation_errors": validation_errors or [],
            "bundle_digest": bundle_digest(bundle) if bundle is not None else None,
            "response": response,
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
        return row

    def read_all(self) -> list[dict[str, Any]]:
        if not self.path.is_file():
            return []
        out: list[dict[str, Any]] = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                out.append(json.loads(line))
        return out

    def count(self) -> int:
        return len(self.read_all())
