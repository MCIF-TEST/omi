"""Adapter registry + auto-detection.

An adapter knows how to recognize one family of dataset (by the normalized set
of column names, with the filename as a tie-breaker / label source) and how to
turn each row into a canonical record.

Detection is specificity-ranked: a purpose-built adapter that names the exact
columns of a known file wins over a generic sniffer that only requires "some
text column + some label column". That way the known uploads parse precisely,
while genuinely new files still get a best-effort ingestion path.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from app.ml.datasets.records import PublicRecord, TextRecord

# A parser turns (row, filename, row_id) into a record, or None to skip the
# row. ``row`` arrives with normalized (lowercased, underscored) keys. ``row_id``
# is a stable per-row identifier the reader assigns (``<stem>:<index>``) that
# the parser uses unless the row carries its own id column.
RowParser = Callable[[dict, str, str], "PublicRecord | TextRecord | None"]
# A matcher scores how well an adapter fits (header_set, filename). 0 = no
# match. Higher = more specific. Sniffers return 1; named adapters return >=10.
Matcher = Callable[[set, str], int]


@dataclass
class DatasetAdapter:
    name: str
    kind: str  # "accounts" | "text"
    match: Matcher
    parse_row: RowParser
    # When True, the adapter cannot label rows without a filename hint and
    # should be skipped if the filename carries no fake/real/bot/human/ai
    # signal. Used by per-class split datasets (fake_users.csv / real_users.csv).
    needs_filename_label: bool = False
    description: str = ""


_REGISTRY: list[DatasetAdapter] = []


def register_adapter(adapter: DatasetAdapter) -> DatasetAdapter:
    """Register (or replace, by name) an adapter. Returns it for decorator-ish
    use."""
    global _REGISTRY
    _REGISTRY = [a for a in _REGISTRY if a.name != adapter.name]
    _REGISTRY.append(adapter)
    return adapter


def iter_adapters() -> list[DatasetAdapter]:
    return list(_REGISTRY)


def detect_adapter(header: set, filename: str = "") -> DatasetAdapter | None:
    """Return the highest-specificity adapter that matches this header, or
    ``None`` if nothing claims it."""
    best: tuple[int, DatasetAdapter] | None = None
    for adapter in _REGISTRY:
        score = adapter.match(header, filename)
        if score <= 0:
            continue
        if best is None or score > best[0]:
            best = (score, adapter)
    return best[1] if best else None


def _ensure_loaded() -> None:
    """Import the concrete adapters so registration side effects run. Kept lazy
    to avoid an import cycle (adapters import this module)."""
    from app.ml.datasets import adapters  # noqa: F401


_ensure_loaded()
