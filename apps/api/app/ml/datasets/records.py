"""Canonical record types produced by dataset adapters.

Two record kinds flow out of the adapters:

* :class:`~app.ml.public_import.PublicRecord` — a behavioral *account* row,
  reused verbatim from the public-import path so account datasets land in the
  same feature space as live scans. Re-exported here for convenience.

* :class:`TextRecord` — a single *text* sample (one comment / post / passage)
  with a binary human-vs-AI label. These feed the AI-writing track: the
  rule-detector benchmark (:mod:`app.evaluation.ai_writing_benchmark`) and the
  optional learned text head.

Keeping both behind one import point means the adapter layer never reaches
into :mod:`app.ml.public_import` directly.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.ml.public_import import PublicRecord

__all__ = ["PublicRecord", "TextRecord"]


@dataclass
class TextRecord:
    """One labeled text sample from an AI-vs-human dataset."""

    external_id: str
    text: str
    is_ai: bool
    # Provenance — optional, used for stratified reporting and never required.
    source_model: str | None = None
    domain: str | None = None
    language: str | None = None
