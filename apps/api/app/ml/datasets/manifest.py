"""Dataset governance manifest — which committed datasets may be ingested, and why.

``datasets/manifest.toml`` declares a status per file. Files marked ``archive``
or ``quarantine`` are EXCLUDED from ingestion (discovery marks them unsupported),
so a known-bad corpus can never reach training by accident — closing the
"one rename away from poisoning the model" hole the Tier-2 audit flagged.

A missing or malformed manifest is a **no-op**: every file is then governed only
by adapter detection + the runtime quality gate, so existing setups keep working
unchanged. Pure stdlib (``tomllib``) — no new dependency, fully testable.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path

MANIFEST_FILENAME = "manifest.toml"

# Statuses whose files must never be ingested as training data.
EXCLUDED_STATUSES = frozenset({"archive", "quarantine"})
# Operator-vouched statuses: the quality gate still runs, but a failure is
# advisory (logged), not a hard block — the operator has accepted the file.
VOUCHED_STATUSES = frozenset({"train", "validation", "reference", "heuristic"})
KNOWN_STATUSES = EXCLUDED_STATUSES | VOUCHED_STATUSES


@dataclass(frozen=True)
class ManifestEntry:
    path: str
    status: str
    kind: str = ""
    reason: str = ""
    provenance: str = ""

    @property
    def excluded(self) -> bool:
        return self.status in EXCLUDED_STATUSES

    @property
    def vouched(self) -> bool:
        return self.status in VOUCHED_STATUSES


@dataclass
class Manifest:
    entries: dict[str, ManifestEntry] = field(default_factory=dict)  # keyed by normalised rel path

    def get(self, rel_path: str) -> ManifestEntry | None:
        return self.entries.get(_norm(rel_path))

    def status(self, rel_path: str) -> str:
        entry = self.get(rel_path)
        return entry.status if entry else ""

    def is_excluded(self, rel_path: str) -> bool:
        entry = self.get(rel_path)
        return bool(entry and entry.excluded)

    def is_vouched(self, rel_path: str) -> bool:
        entry = self.get(rel_path)
        return bool(entry and entry.vouched)


def _norm(rel_path: str) -> str:
    """Match on a case-insensitive POSIX-style path so manifest entries line up
    with ``DiscoveredFile.rel_path`` regardless of OS separator or casing."""
    return str(rel_path).replace("\\", "/").strip().lower()


def load_manifest(root: Path) -> Manifest:
    """Load ``<root>/manifest.toml``. Missing/malformed → empty manifest."""
    path = Path(root) / MANIFEST_FILENAME
    if not path.exists():
        return Manifest()
    try:
        with path.open("rb") as fh:
            data = tomllib.load(fh)
    except (OSError, tomllib.TOMLDecodeError):
        return Manifest()

    entries: dict[str, ManifestEntry] = {}
    for raw in data.get("file", []) or []:
        if not isinstance(raw, dict):
            continue
        rel = raw.get("path")
        status = str(raw.get("status", "")).strip().lower()
        if not rel or status not in KNOWN_STATUSES:
            continue
        entries[_norm(rel)] = ManifestEntry(
            path=str(rel),
            status=status,
            kind=str(raw.get("kind", "")),
            reason=str(raw.get("reason", "")),
            provenance=str(raw.get("provenance", "")),
        )
    return Manifest(entries=entries)
