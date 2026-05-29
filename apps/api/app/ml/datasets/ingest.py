"""Orchestrate ingestion of a datasets folder.

``plan_directory`` is pure (filesystem only) and answers "what's here, what
would be ingested, what's new since last run". ``ingest_directory`` performs
the DB-bound work for account datasets (running each row through the real
detector engine via :mod:`app.ml.public_import`) and collects text datasets for
the AI-writing track, updating the content-hash ledger so the next run only
touches new or changed files.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from app.ml.datasets.discovery import DiscoveredFile, discover, read_records
from app.ml.datasets.ledger import LEDGER_FILENAME, Ledger, LedgerEntry
from app.ml.datasets.records import PublicRecord, TextRecord


@dataclass
class FilePlan:
    rel_path: str
    adapter: str | None
    kind: str
    supported: bool
    sha256: str
    is_new: bool
    reason: str = ""


@dataclass
class DirectoryPlan:
    root: str
    files: list[FilePlan] = field(default_factory=list)

    @property
    def ingestable(self) -> list[FilePlan]:
        return [f for f in self.files if f.supported]

    @property
    def new_files(self) -> list[FilePlan]:
        return [f for f in self.files if f.supported and f.is_new]


def plan_directory(root: Path) -> DirectoryPlan:
    """Classify every file under ``root`` and flag which are new/changed
    against the ledger. No DB, no parsing of full rows."""
    root = Path(root)
    ledger = Ledger(root / LEDGER_FILENAME)
    plan = DirectoryPlan(root=str(root))
    for df in discover(root):
        is_new = not (df.sha256 and ledger.is_unchanged(df.rel_path, df.sha256))
        plan.files.append(FilePlan(
            rel_path=df.rel_path,
            adapter=df.adapter.name if df.adapter else None,
            kind=df.kind,
            supported=df.supported,
            sha256=df.sha256,
            is_new=is_new,
            reason=df.reason,
        ))
    return plan


@dataclass
class IngestReport:
    root: str
    files_processed: int = 0
    files_skipped_unchanged: int = 0
    accounts_ingested: int = 0
    accounts_bots: int = 0
    accounts_humans: int = 0
    text_samples: int = 0
    text_ai: int = 0
    text_human: int = 0
    per_file: list[dict] = field(default_factory=list)
    text_records: list[TextRecord] = field(default_factory=list)


def ingest_directory(
    root: Path,
    *,
    session=None,
    only_new: bool = True,
    user_id: int | None = None,
    label_confidence: str = "medium",
    limit_per_file: int | None = None,
    collect_text: bool = True,
) -> IngestReport:
    """Ingest every supported file under ``root``.

    Account datasets are persisted (requires ``session``); text datasets are
    parsed and returned in the report (and, when ``collect_text``, accumulated
    for the caller to benchmark or export). The ledger is updated and saved.
    """
    from app.ml.public_import import ingest_records

    root = Path(root)
    ledger = Ledger(root / LEDGER_FILENAME)
    report = IngestReport(root=str(root))

    for df in discover(root):
        if not df.supported:
            continue
        if only_new and df.sha256 and ledger.is_unchanged(df.rel_path, df.sha256):
            report.files_skipped_unchanged += 1
            continue

        records, n_rows = read_records(df, limit=limit_per_file)
        n_ingested = 0

        if df.kind == "accounts":
            accounts = [r for r in records if isinstance(r, PublicRecord)]
            if session is None:
                report.per_file.append({
                    "file": df.rel_path, "kind": "accounts",
                    "adapter": df.adapter.name if df.adapter else None,
                    "rows": n_rows, "parsed": len(accounts),
                    "ingested": 0, "note": "no DB session — not persisted",
                })
                continue
            res = ingest_records(
                session, accounts,
                dataset_name=df.adapter.name if df.adapter else df.path.stem,
                label_confidence=label_confidence,
                user_id=user_id,
                allow_textless=True,
            )
            session.commit()
            n_ingested = res["ingested"]
            report.accounts_ingested += res["ingested"]
            report.accounts_bots += res["bots"]
            report.accounts_humans += res["humans"]
            report.per_file.append({
                "file": df.rel_path, "kind": "accounts",
                "adapter": df.adapter.name if df.adapter else None,
                "rows": n_rows, "parsed": len(accounts), **res,
            })

        elif df.kind == "text":
            texts = [r for r in records if isinstance(r, TextRecord)]
            n_ai = sum(1 for r in texts if r.is_ai)
            report.text_samples += len(texts)
            report.text_ai += n_ai
            report.text_human += len(texts) - n_ai
            n_ingested = len(texts)
            if collect_text:
                report.text_records.extend(texts)
            report.per_file.append({
                "file": df.rel_path, "kind": "text",
                "adapter": df.adapter.name if df.adapter else None,
                "rows": n_rows, "parsed": len(texts),
                "ai": n_ai, "human": len(texts) - n_ai,
            })

        ledger.record(df.rel_path, LedgerEntry(
            sha256=df.sha256,
            adapter=df.adapter.name if df.adapter else "",
            kind=df.kind,
            n_rows=n_rows,
            n_ingested=n_ingested,
            ingested_at=datetime.now(timezone.utc).isoformat(),
        ))
        report.files_processed += 1

    ledger.save()
    return report
