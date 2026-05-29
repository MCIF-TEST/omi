"""Content-hash ledger for incremental, repeatable ingestion.

The operator's workflow is "keep dropping files into ``datasets/`` and re-run
ingestion". To make that cheap and idempotent we record, per file, the SHA-256
of its bytes the last time we ingested it. A re-run skips files whose hash is
unchanged and processes only what is new or edited.

The ledger is a single JSON document. It is keyed by the file path *relative to
the datasets root* so it stays stable across machines/checkouts.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

LEDGER_FILENAME = ".omi_ingest_ledger.json"


@dataclass
class LedgerEntry:
    sha256: str
    adapter: str
    kind: str
    n_rows: int
    n_ingested: int
    ingested_at: str


def sha256_file(path: Path, *, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(chunk), b""):
            h.update(block)
    return h.hexdigest()


class Ledger:
    """Load/save/query the ingestion ledger. Safe to construct against a path
    that does not exist yet (treated as empty)."""

    def __init__(self, path: Path):
        self.path = path
        self._entries: dict[str, LedgerEntry] = {}
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return
        for key, val in (raw.get("files") or {}).items():
            try:
                self._entries[key] = LedgerEntry(**val)
            except TypeError:
                continue  # tolerate schema drift in an old ledger

    def is_unchanged(self, rel_path: str, sha256: str) -> bool:
        entry = self._entries.get(rel_path)
        return entry is not None and entry.sha256 == sha256

    def record(self, rel_path: str, entry: LedgerEntry) -> None:
        self._entries[rel_path] = entry

    def get(self, rel_path: str) -> LedgerEntry | None:
        return self._entries.get(rel_path)

    def entries(self) -> dict[str, LedgerEntry]:
        return dict(self._entries)

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        doc = {
            "version": 1,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "files": {k: asdict(v) for k, v in sorted(self._entries.items())},
        }
        self.path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
