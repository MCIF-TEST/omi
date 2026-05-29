"""The content-hash ledger that makes ingestion incremental + repeatable."""

from __future__ import annotations

import csv
from pathlib import Path

from app.ml.datasets.ingest import plan_directory
from app.ml.datasets.ledger import Ledger, LedgerEntry, sha256_file


def _write_csv(path: Path, header, rows):
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(header)
        w.writerows(rows)


def test_ledger_roundtrip(tmp_path):
    led = Ledger(tmp_path / ".omi_ingest_ledger.json")
    led.record("a.csv", LedgerEntry("abc", "fake_social_media", "accounts", 10, 9, "t"))
    led.save()
    reloaded = Ledger(tmp_path / ".omi_ingest_ledger.json")
    assert reloaded.is_unchanged("a.csv", "abc")
    assert not reloaded.is_unchanged("a.csv", "different")
    assert reloaded.get("a.csv").n_rows == 10


def test_plan_marks_new_then_unchanged(tmp_path):
    p = tmp_path / "fake_social_media.csv"
    _write_csv(p, ["platform", "followers", "following", "account_age_days", "is_fake"],
               [["Twitter", "1", "2", "3", "1"]])

    plan = plan_directory(tmp_path)
    [f] = [x for x in plan.files if x.supported]
    assert f.is_new is True

    # Simulate a prior ingest by recording the file's current hash.
    led = Ledger(tmp_path / ".omi_ingest_ledger.json")
    led.record(f.rel_path, LedgerEntry(
        sha256_file(p), "fake_social_media", "accounts", 1, 1, "t"))
    led.save()

    plan2 = plan_directory(tmp_path)
    [f2] = [x for x in plan2.files if x.supported]
    assert f2.is_new is False

    # Editing the file changes its hash → new again.
    _write_csv(p, ["platform", "followers", "following", "account_age_days", "is_fake"],
               [["Twitter", "1", "2", "3", "1"], ["Twitter", "9", "9", "9", "0"]])
    plan3 = plan_directory(tmp_path)
    [f3] = [x for x in plan3.files if x.supported]
    assert f3.is_new is True
