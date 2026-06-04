"""Dataset governance — manifest quarantine + runtime quality gate.

These pin the Tier-2 "poison can't reach training by accident" guarantee:
the committed poison files are excluded by the manifest, and the quality gate
independently blocks random-label noise / error-string contamination on any
*undeclared* file — while leaving operator-vouched files as advisory.
"""

from __future__ import annotations

import csv
import random

import pytest

from app.ml.datasets.discovery import discover
from app.ml.datasets.ingest import ingest_directory
from app.ml.datasets.manifest import load_manifest
from app.ml.datasets.paths import default_datasets_dir
from app.ml.datasets.quality import assess_accounts, assess_text
from app.ml.datasets.records import TextRecord
from app.ml.public_import import PublicRecord


# --- Manifest quarantine over the real committed datasets --------------------

def test_manifest_quarantines_committed_poison():
    # Manifest-only (the full tree is now multi-GB; the manifest→discover→
    # supported link is covered by test_headerless_bot_adapters + the ingest
    # tests). Paths reflect the post-reorg layout (corpus under Datasets/).
    manifest = load_manifest(default_datasets_dir())
    bot = "Datasets/Fake Social Media Account Detection Dataset/bot_detection_data.csv"
    assert manifest.is_excluded(bot) and manifest.status(bot) == "quarantine"
    # ai_human_detection_v1 was salvaged (the ~6 API-error rows are now dropped
    # at parse), so it is no longer quarantined wholesale — it's a validation set.
    err = "ai vs human text/ai_human_detection_v1.csv"
    assert not manifest.is_excluded(err) and manifest.status(err) == "validation"


def test_manifest_keeps_vouched_training_files_supported():
    manifest = load_manifest(default_datasets_dir())
    assert manifest.status(
        "Datasets/Fake Social Media Account Detection Dataset/real_users.csv"
    ) == "train"


# --- Quality gate: random-label noise (accounts) -----------------------------

def test_gate_flags_random_label_noise():
    random.seed(0)
    recs = [
        PublicRecord(
            external_id=str(i), texts=["hi"], is_bot=bool(i % 2),
            follower_count=random.randint(0, 9999),
            following_count=random.randint(0, 9999),
            account_age_days=random.randint(0, 3000),
        )
        for i in range(2000)
    ]
    rep = assess_accounts(recs)
    assert not rep.passed
    assert any("random-label" in r for r in rep.reasons), rep.reasons


def test_gate_passes_separable_accounts():
    # Bots: few followers, many following, brand-new. Humans: the opposite.
    recs = []
    for i in range(2000):
        bot = i % 2 == 0
        recs.append(PublicRecord(
            external_id=str(i), texts=["hi"], is_bot=bot,
            follower_count=10 if bot else 5000,
            following_count=5000 if bot else 100,
            account_age_days=10 if bot else 1500,
        ))
    rep = assess_accounts(recs)
    assert rep.passed, rep.reasons


def test_gate_flags_degenerate_single_class_two_class_file():
    # 2000 rows, only 5 of the minority class (0.25%) → untrainable.
    recs = [
        PublicRecord(external_id=str(i), texts=["hi"], is_bot=(i >= 5),
                     follower_count=i, following_count=i, account_age_days=i)
        for i in range(2000)
    ]
    rep = assess_accounts(recs)
    assert not rep.passed
    assert any("degenerate" in r for r in rep.reasons), rep.reasons


# --- Quality gate: error-string text poison ----------------------------------

def test_gate_flags_error_string_text():
    recs = []
    for i in range(200):
        if i % 2 == 0:
            recs.append(TextRecord(
                external_id=str(i), is_ai=True,
                text="Error: 400 Client Error: Bad Request for url: "
                     "https://api.groq.com/openai/v1/chat/completions",
            ))
        else:
            recs.append(TextRecord(
                external_id=str(i), is_ai=False,
                text="I really enjoyed the nuanced argument in this essay.",
            ))
    rep = assess_text(recs)
    assert not rep.passed
    assert any("error" in r.lower() for r in rep.reasons), rep.reasons


def test_gate_passes_clean_text():
    recs = []
    for i in range(200):
        ai = i % 2 == 0
        recs.append(TextRecord(
            external_id=str(i), is_ai=ai,
            text=("In summary, the passage articulates several key considerations "
                  "regarding the topic.") if ai else
                 "honestly i think the ref totally blew that call lol",
        ))
    rep = assess_text(recs)
    assert rep.passed, rep.reasons


# --- Ingest-level enforcement on an UNDECLARED file ---------------------------

def _write_noise_accounts(path, n=1500, seed=1):
    random.seed(seed)
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["is_fake", "followers", "following", "account_age_days"])
        for _ in range(n):
            w.writerow([random.randint(0, 1), random.randint(0, 9999),
                        random.randint(0, 9999), random.randint(0, 3000)])


def test_ingest_blocks_undeclared_noise(tmp_path):
    _write_noise_accounts(tmp_path / "noise.csv")
    report = ingest_directory(tmp_path, session=None)
    assert report.files_blocked == 1, report.per_file
    blocked = [f for f in report.per_file if f.get("blocked")]
    assert blocked, report.per_file
    assert any("random-label" in r for r in blocked[0]["quality_reasons"])


def test_manifest_vouch_downgrades_gate_to_advisory(tmp_path):
    _write_noise_accounts(tmp_path / "noise.csv")
    (tmp_path / "manifest.toml").write_text(
        'schema_version = 1\n[[file]]\npath = "noise.csv"\nstatus = "train"\n',
        encoding="utf-8",
    )
    report = ingest_directory(tmp_path, session=None)
    # Vouched → not blocked, but the risk is surfaced as a warning.
    assert report.files_blocked == 0, report.per_file
    entry = next(f for f in report.per_file if f["file"] == "noise.csv")
    assert entry.get("quality_passed") is False
    assert "quality_warning" in entry


# --- Tier-2A: dir-rules + headerless bot adapters + re-quarantine ----------

def test_manifest_dir_rule_and_file_override(tmp_path):
    from app.ml.datasets.manifest import load_manifest
    (tmp_path / "manifest.toml").write_text(
        'schema_version = 2\n'
        '[[dir]]\npath = "campaigns"\nstatus = "validation"\n'
        '[[file]]\npath = "campaigns/bad.csv"\nstatus = "quarantine"\n',
        encoding="utf-8",
    )
    m = load_manifest(tmp_path)
    assert m.status("campaigns/2020/x.csv") == "validation"   # dir prefix rule
    assert m.is_excluded("campaigns/bad.csv")                  # exact file overrides
    assert m.status("elsewhere/y.csv") == ""                   # unmatched → ungoverned


_HAS_BOT_GT = (default_datasets_dir() / "astroturf" / "astroturf.tsv").exists()


@pytest.mark.skipif(not _HAS_BOT_GT, reason="bot ground-truth datasets not present")
def test_headerless_bot_adapters(tmp_path):
    import shutil
    from app.ml.datasets.discovery import discover, read_records
    src = default_datasets_dir()
    for rel in ("astroturf/astroturf.tsv", "cresci-rtbust-2019/cresci-rtbust-2019.tsv"):
        dst = tmp_path / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(src / rel, dst)
    files = {f.rel_path: f for f in discover(tmp_path)}

    a = files["astroturf/astroturf.tsv"]
    assert a.supported and a.adapter.name == "astroturf"
    recs, _ = read_records(a)
    assert recs and all(r.is_bot and r.label == "bot" for r in recs)

    c = files["cresci-rtbust-2019/cresci-rtbust-2019.tsv"]
    assert c.supported and c.adapter.name == "cresci_rtbust"
    recs, _ = read_records(c)
    assert {r.label for r in recs} == {"human", "bot"}


@pytest.mark.skipif(
    not (default_datasets_dir() / "manifest.toml").exists(),
    reason="repaired manifest not present",
)
def test_real_manifest_requarantines_moved_poison_and_governs_io():
    from app.ml.datasets.manifest import load_manifest
    m = load_manifest(default_datasets_dir())
    # poison re-gated at its new Datasets/ path
    assert m.is_excluded(
        "Datasets/Fake Social Media Account Detection Dataset/bot_detection_data.csv"
    )
    # IO archives governed as validation via dir-rules
    assert m.status("2020-09/iran_092020_tweets_csv_hashed.csv") == "validation"
    assert m.status("Datasets/GRU/x.csv") == "validation"
