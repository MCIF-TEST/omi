"""Walk the datasets folder, detect an adapter per file, and read records.

Everything here is pure I/O over the filesystem + stdlib ``csv`` — no database,
no heavy deps — so it is fully exercisable in a test or a dry run. The DB-bound
work (running accounts through the engine) lives in :mod:`app.ml.datasets.ingest`.
"""

from __future__ import annotations

import csv
import sys
from dataclasses import dataclass, field
from pathlib import Path

from app.ml.datasets.ledger import LEDGER_FILENAME, sha256_file
from app.ml.datasets.normalize import norm_key
from app.ml.datasets.records import PublicRecord, TextRecord
from app.ml.datasets.registry import DatasetAdapter, detect_adapter

# csv fields can be large (a full essay in one cell). Raise the limit once.
try:
    csv.field_size_limit(sys.maxsize)
except (OverflowError, ValueError):  # pragma: no cover - platform-specific cap
    csv.field_size_limit(2**31 - 1)

_CSV_SUFFIXES = {".csv", ".tsv"}
_KNOWN_UNSUPPORTED = {".xlsx", ".xls", ".parquet"}


@dataclass
class DiscoveredFile:
    path: Path
    rel_path: str
    sha256: str
    header: list[str] = field(default_factory=list)
    adapter: DatasetAdapter | None = None
    supported: bool = False
    reason: str = ""

    @property
    def kind(self) -> str:
        return self.adapter.kind if self.adapter else "unknown"


def _read_header(path: Path) -> list[str]:
    delim = "\t" if path.suffix.lower() == ".tsv" else ","
    with path.open("r", encoding="utf-8", errors="replace", newline="") as fh:
        reader = csv.reader(fh, delimiter=delim)
        for row in reader:
            return row
    return []


def discover(root: Path) -> list[DiscoveredFile]:
    """Scan ``root`` recursively and classify every data file. The ledger file
    and anything under a ``_generated`` directory are skipped."""
    root = Path(root)
    found: list[DiscoveredFile] = []
    if not root.exists():
        return found
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if path.name == LEDGER_FILENAME or "_generated" in path.parts:
            continue
        suffix = path.suffix.lower()
        rel = str(path.relative_to(root))
        if suffix in _KNOWN_UNSUPPORTED:
            found.append(DiscoveredFile(
                path=path, rel_path=rel, sha256="",
                supported=False,
                reason=f"{suffix} not readable without an extra dependency; "
                       "export to CSV to ingest.",
            ))
            continue
        if suffix not in _CSV_SUFFIXES:
            continue  # silently ignore non-tabular files (READMEs, blobs, ...)

        header = _read_header(path)
        norm = {norm_key(h) for h in header if h}
        adapter = detect_adapter(norm, path.name)
        df = DiscoveredFile(
            path=path, rel_path=rel, sha256=sha256_file(path), header=header,
            adapter=adapter, supported=adapter is not None,
        )
        if adapter is None:
            df.reason = "No adapter matched this column signature."
        elif adapter.needs_filename_label:
            from app.ml.datasets.normalize import label_hint_from_filename
            if label_hint_from_filename(path.name) is None:
                df.supported = False
                df.reason = (
                    f"Adapter '{adapter.name}' needs a fake/real label in the "
                    "filename, but the name carries none."
                )
        found.append(df)
    return found


def read_records(
    df: DiscoveredFile,
    *,
    limit: int | None = None,
) -> tuple[list[PublicRecord | TextRecord], int]:
    """Parse a discovered file into canonical records. Returns
    ``(records, n_rows_seen)``. Rows the adapter rejects are counted but not
    returned."""
    if df.adapter is None:
        return [], 0
    delim = "\t" if df.path.suffix.lower() == ".tsv" else ","
    records: list[PublicRecord | TextRecord] = []
    n_rows = 0
    stem = df.path.stem
    with df.path.open("r", encoding="utf-8", errors="replace", newline="") as fh:
        reader = csv.DictReader(fh, delimiter=delim)
        for i, raw in enumerate(reader):
            n_rows += 1
            row = {norm_key(k): v for k, v in raw.items() if k is not None}
            rec = df.adapter.parse_row(row, df.path.name, f"{stem}:{i}")
            if rec is not None:
                records.append(rec)
            if limit is not None and len(records) >= limit:
                break
    return records, n_rows
