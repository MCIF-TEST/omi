"""Tier-2C intake — the labeled_tweets adapter (Known-Good / Known-Mixed).

Pins the contract documented in datasets/INTAKE.md: per-tweet timeline files
with a user-id + text column get the human/bot label from their FILENAME,
collapse to one account WITH its text corpus, and don't collide with the
io_disclosure / cresci_rtbust / twitter_user_features adapters.
"""

from __future__ import annotations

import csv

from app.ml.datasets.discovery import discover, read_records
from app.ml.datasets.registry import detect_adapter
from app.ml.datasets.normalize import norm_key
from app.ml.public_import import coalesce_records


def _hdr(*cols):
    return {norm_key(c) for c in cols}


def _write_tweets(path, rows, header=("user_id", "text")):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(header)
        w.writerows(rows)


# --- adapter selection (no collisions) --------------------------------------

def test_adapter_selection_routes_correctly():
    assert detect_adapter(_hdr("user_id", "text", "created_at"),
                          "cresci2017_genuine_tweets.csv").name == "labeled_tweets"
    assert detect_adapter(_hdr("user_id", "tweet_text"),
                          "known_mixed_journalists_tweets.csv").name == "labeled_tweets"
    # IO files (with follower columns, no filename label) stay io_disclosure.
    assert detect_adapter(_hdr("userid", "tweet_text", "follower_count", "account_creation_date"),
                          "iran_092020_tweets_csv_hashed.csv").name == "io_disclosure"
    # Headerless RTbust id+label stays cresci_rtbust.
    assert detect_adapter({"3039154799", "human"},
                          "cresci-rtbust-2019.tsv").name == "cresci_rtbust"
    # A user-id+text file with NO filename label is not claimed (avoids
    # mislabeling unlabeled timelines).
    assert detect_adapter(_hdr("user_id", "text"), "timeline_2021.csv") is None
    # Regression: an IO-disclosure file whose name spuriously contains a label
    # token ("ai" inside "campaign") must still route to io_disclosure, not get
    # stolen by labeled_tweets — they're disjoint on the IO column triad.
    assert detect_adapter(
        _hdr("userid", "tweet_text", "follower_count", "account_creation_date"),
        "ira_campaign.csv").name == "io_disclosure"


# --- genuine / bot / mixed parsing ------------------------------------------

def test_genuine_tweets_collapse_to_human_account_with_text(tmp_path):
    f = tmp_path / "known-good" / "cresci2017_genuine_tweets.csv"
    _write_tweets(f, [
        ("u1", "had a great coffee this morning"),
        ("u1", "watching the match tonight"),
        ("u2", "new blog post is up"),
    ])
    df = next(d for d in discover(tmp_path) if d.rel_path.endswith("cresci2017_genuine_tweets.csv"))
    assert df.supported and df.adapter.name == "labeled_tweets"
    recs, _ = read_records(df)
    merged = {r.external_id: r for r in coalesce_records(recs)}
    assert set(merged) == {"u1", "u2"}
    assert all(r.label == "human" and not r.is_bot and r.expected_tier == "low"
               for r in merged.values())
    assert len(merged["u1"].texts) == 2          # whole corpus, not one tweet
    assert "coffee" in merged["u1"].texts[0]


def test_spambot_tweets_label_bot(tmp_path):
    f = tmp_path / "known-good" / "cresci2017_spambots_tweets.csv"
    _write_tweets(f, [("b1", "BUY followers cheap http://x"), ("b1", "click here now")])
    df = next(d for d in discover(tmp_path) if d.rel_path.endswith("spambots_tweets.csv"))
    recs, _ = read_records(df)
    merged = coalesce_records(recs)
    assert len(merged) == 1
    assert merged[0].is_bot and merged[0].label == "bot" and merged[0].expected_tier == "high"


def test_known_mixed_is_human_with_category_campaign(tmp_path):
    f = tmp_path / "known-mixed" / "known_mixed_journalists_tweets.csv"
    _write_tweets(f, [("j1", "breaking: city council votes tonight"),
                      ("j1", "follow our live coverage")],
                  header=("author_id", "full_text"))
    df = next(d for d in discover(tmp_path) if "known_mixed_journalists" in d.rel_path)
    assert df.adapter.name == "labeled_tweets"
    recs, _ = read_records(df)
    merged = coalesce_records(recs)
    assert len(merged) == 1
    r = merged[0]
    # legitimate -> human, but the category is tracked for cohort evaluation.
    assert r.label == "human" and not r.is_bot
    assert "known_mixed_journalists" in (r.campaign_id or "")
