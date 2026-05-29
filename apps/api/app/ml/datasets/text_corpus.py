"""Load + export the labeled AI-vs-human text corpus.

Text datasets don't map onto accounts; they feed the AI-writing track. This
module gathers every text record across the datasets folder (pure filesystem,
no DB) for two consumers:

* :mod:`app.evaluation.ai_writing_benchmark` — measure the rule-based
  ``ai_writing`` detector against real labels.
* an optional learned text head — :func:`export_text_jsonl` writes one
  ``{"text", "label", "is_ai", ...}`` record per line.
"""

from __future__ import annotations

import json
from pathlib import Path

from app.ml.datasets.discovery import discover, read_records
from app.ml.datasets.records import TextRecord


def load_text_records(root: Path, *, limit_per_file: int | None = None) -> list[TextRecord]:
    """Return every parseable text record under ``root``."""
    out: list[TextRecord] = []
    for df in discover(Path(root)):
        if not df.supported or df.kind != "text":
            continue
        records, _ = read_records(df, limit=limit_per_file)
        out.extend(r for r in records if isinstance(r, TextRecord))
    return out


def export_text_jsonl(records: list[TextRecord], path: Path) -> int:
    """Write labeled text rows as JSONL. Returns the count written."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with path.open("w", encoding="utf-8") as fh:
        fh.write(json.dumps({
            "_meta": True,
            "task": "ai_vs_human_text",
            "label_convention": "is_ai: 1 = AI-generated, 0 = human-written",
        }) + "\n")
        for r in records:
            fh.write(json.dumps({
                "external_id": r.external_id,
                "text": r.text,
                "is_ai": 1 if r.is_ai else 0,
                "source_model": r.source_model,
                "domain": r.domain,
                "language": r.language,
            }) + "\n")
            n += 1
    return n
