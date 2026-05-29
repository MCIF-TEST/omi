"""Adapter detection + parsing contract for the dataset ingestion subsystem.

These pin the behavior the operator relies on: each known upload is claimed by
its purpose-built adapter, the generic sniffers catch novel-but-recognizable
files, and the tolerant label/count parsing absorbs the mess in public data.
All pure — no DB, no filesystem beyond a tmp CSV.
"""

from __future__ import annotations

import csv
from pathlib import Path

from app.ml.datasets.discovery import discover, read_records
from app.ml.datasets.normalize import (
    label_hint_from_filename,
    norm_key,
    parse_bool_label,
    to_count,
)
from app.ml.datasets.records import PublicRecord, TextRecord
from app.ml.datasets.registry import detect_adapter


def _norm(header):
    return {norm_key(h) for h in header}


# --- normalization -------------------------------------------------------

def test_parse_bool_label_variants():
    assert parse_bool_label("AI-generated") is True
    assert parse_bool_label("Human-written") is False
    assert parse_bool_label("1") is True
    assert parse_bool_label("0") is False
    assert parse_bool_label("True") is True
    assert parse_bool_label("fake") is True
    assert parse_bool_label("real") is False
    assert parse_bool_label("None (Human)") is False
    assert parse_bool_label("") is None
    assert parse_bool_label(None) is None


def test_to_count_drops_negatives_and_rounds():
    assert to_count("431") == 431
    assert to_count("12.7") == 13
    assert to_count("-5.0") is None          # z-scored junk → None, not garbage
    assert to_count("-5.0", allow_negative=True) == -5
    assert to_count("") is None


def test_label_hint_from_filename():
    assert label_hint_from_filename("fake_users.csv") is True
    assert label_hint_from_filename("real_users.csv") is False
    assert label_hint_from_filename("dataset.csv") is None


# --- adapter detection ---------------------------------------------------

def test_detects_known_account_and_text_adapters():
    assert detect_adapter(_norm(
        ["platform", "has_profile_pic", "followers", "following",
         "account_age_days", "is_fake"]), "fake_social_media.csv").name == "fake_social_media"
    assert detect_adapter(_norm(
        ["id", "name", "screen_name", "statuses_count", "followers_count",
         "friends_count", "created_at"]), "fake_users.csv").name == "twitter_user_features"
    assert detect_adapter(_norm(
        ["comment_id", "subreddit", "account_age_days", "user_karma",
         "is_bot_flag", "bot_probability"]), "x.csv").name == "reddit_dead_internet"
    assert detect_adapter(_norm(
        ["text_id", "label", "source_model", "domain", "text_content",
         "generation_method"]), "x.csv").name == "ai_vs_human_text_2026"
    assert detect_adapter(_norm(
        ["id", "text", "human_or_ai", "source_model", "domain",
         "language"]), "x.csv").name == "ai_human_detection_v1"
    assert detect_adapter(_norm(
        ["id", "text", "label", "prompt", "model", "date"]),
        "x.csv").name == "ai_vs_human_text_v1"


def test_generic_sniffers_catch_novel_files():
    # A brand-new text file with recognizable columns but no named adapter.
    a = detect_adapter(_norm(["body", "class"]), "newdrop.csv")
    assert a is not None and a.name == "text_generic" and a.kind == "text"
    # A brand-new account file: a label + a behavioral column.
    a = detect_adapter(_norm(["username", "followers", "is_bot"]), "x.csv")
    assert a is not None and a.name == "accounts_generic" and a.kind == "accounts"


def test_specific_adapter_beats_generic():
    # fake_social_media has the generic-account columns too, but the specific
    # adapter (higher score) must win.
    a = detect_adapter(_norm(
        ["followers", "following", "account_age_days", "is_fake"]),
        "fake_social_media.csv")
    assert a.name == "fake_social_media"


def test_unrecognized_header_returns_none():
    assert detect_adapter(_norm(["colA", "colB", "colC"]), "mystery.csv") is None


# --- end-to-end parse of representative CSVs -----------------------------

def _write_csv(path: Path, header, rows):
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(header)
        w.writerows(rows)


def test_text_csv_parses_to_textrecords(tmp_path):
    p = tmp_path / "ai_vs_human_text.csv"
    _write_csv(p, ["id", "text", "label", "prompt", "model", "date"], [
        ["1", "An AI essay about deep learning.", "AI-generated", "p", "ChatGPT", "2024"],
        ["2", "yo this is just me typing lol", "Human-written", "", "", "2024"],
        ["3", "", "AI-generated", "", "", "2024"],  # empty text → dropped
    ])
    [df] = [d for d in discover(tmp_path) if d.supported]
    recs, n_rows = read_records(df)
    assert n_rows == 3 and len(recs) == 2
    assert all(isinstance(r, TextRecord) for r in recs)
    assert recs[0].is_ai is True and recs[1].is_ai is False


def test_fake_social_media_parses_to_publicrecords(tmp_path):
    p = tmp_path / "fake_social_media.csv"
    _write_csv(p, ["platform", "followers", "following", "account_age_days", "is_fake"], [
        ["Twitter", "431", "679", "941", "1"],
        ["Twitter", "5000", "300", "2000", "0"],
    ])
    [df] = [d for d in discover(tmp_path) if d.supported]
    recs, _ = read_records(df)
    assert len(recs) == 2 and all(isinstance(r, PublicRecord) for r in recs)
    assert recs[0].is_bot is True and recs[0].follower_count == 431
    assert recs[1].is_bot is False and recs[0].texts == []  # behavioral-only


def test_twitter_label_comes_from_filename(tmp_path):
    header = ["id", "name", "screen_name", "statuses_count", "followers_count",
              "friends_count", "created_at"]
    fake = tmp_path / "fake_users.csv"
    real = tmp_path / "real_users.csv"
    _write_csv(fake, header, [["1", "A", "a", "10", "5", "5", "2012"]])
    _write_csv(real, header, [["2", "B", "b", "10", "5", "5", "2012"]])
    by_name = {d.path.name: d for d in discover(tmp_path) if d.supported}
    fake_recs, _ = read_records(by_name["fake_users.csv"])
    real_recs, _ = read_records(by_name["real_users.csv"])
    assert fake_recs[0].is_bot is True
    assert real_recs[0].is_bot is False


def test_xlsx_flagged_unsupported(tmp_path):
    (tmp_path / "data.xlsx").write_bytes(b"PK\x03\x04 not a real xlsx")
    [df] = discover(tmp_path)
    assert df.supported is False and "xlsx" in df.reason
