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
    entries: dict[str, ManifestEntry] = field(default_factory=dict)  # exact rel path → entry
    dir_rules: list[ManifestEntry] = field(default_factory=list)     # path-prefix rules

    def get(self, rel_path: str) -> ManifestEntry | None:
        """Exact file rule wins; otherwise the longest matching directory-prefix
        rule. Lets a whole archive (many per-year IO files) be governed by one
        ``[[dir]]`` entry while still allowing per-file overrides."""
        norm = _norm(rel_path)
        exact = self.entries.get(norm)
        if exact is not None:
            return exact
        best: ManifestEntry | None = None
        for rule in self.dir_rules:
            prefix = _norm(rule.path).rstrip("/")
            if norm == prefix or norm.startswith(prefix + "/"):
                if best is None or len(prefix) > len(_norm(best.path).rstrip("/")):
                    best = rule
        return best

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

    def _parse(raw: dict) -> ManifestEntry | None:
        rel = raw.get("path")
        status = str(raw.get("status", "")).strip().lower()
        if not rel or status not in KNOWN_STATUSES:
            return None
        return ManifestEntry(
            path=str(rel), status=status,
            kind=str(raw.get("kind", "")),
            reason=str(raw.get("reason", "")),
            provenance=str(raw.get("provenance", "")),
        )

    entries: dict[str, ManifestEntry] = {}
    for raw in data.get("file", []) or []:
        if isinstance(raw, dict) and (e := _parse(raw)) is not None:
            entries[_norm(e.path)] = e

    dir_rules: list[ManifestEntry] = []
    for raw in data.get("dir", []) or []:
        if isinstance(raw, dict) and (e := _parse(raw)) is not None:
            dir_rules.append(e)

    return Manifest(entries=entries, dir_rules=dir_rules)
