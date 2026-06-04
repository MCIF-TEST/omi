"""Phase 0 — real timestamps through PublicRecord + TwitterData rehabilitation.

Pins the foundational correctness fix: per-tweet adapters now carry real
``post_times`` (index-aligned with ``texts``) so the temporal detector reads
genuine cadence instead of the synthetic 1-hour spacing, and the TwitterData
corpus ingests with correct (inverted) label polarity and cleaned text.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.detection.temporal import analyze_temporal
from app.ml.datasets.adapters import _parse_io_disclosure, _parse_twitterdata
from app.ml.datasets.normalize import days_since, parse_datetime
from app.ml.datasets.registry import detect_adapter
from app.ml.datasets.normalize import norm_key
from app.ml.public_import import PublicRecord, _to_posts, coalesce_records


def _hdr(*c):
    return {norm_key(x) for x in c}


# --- timestamp parsing ------------------------------------------------------

def test_parse_datetime_handles_corpus_formats():
    # IO "YYYY-MM-DD HH:MM", IO creation "YYYY-MM-DD", TwitterData day-first,
    # Twitter_Data ISO-with-seconds, Twitter-API long form.
    assert parse_datetime("2019-10-23 06:05").isoformat() == "2019-10-23T06:05:00+00:00"
    assert parse_datetime("2019-10-21").date().isoformat() == "2019-10-21"
    assert parse_datetime("27-11-2016 06:15").isoformat() == "2016-11-27T06:15:00+00:00"
    assert parse_datetime("2016-11-27 06:15:03").isoformat() == "2016-11-27T06:15:03+00:00"
    assert parse_datetime("Wed May 15 16:00:19 +0000 2019").year == 2019
    assert parse_datetime("") is None and parse_datetime("not a date") is None


def test_days_since_real_creation_date():
    d = days_since("2019-10-21")
    assert d is not None and d > 2000  # several years old, not None


# --- _to_posts: real vs synthetic ------------------------------------------

def test_to_posts_uses_real_timestamps_when_present():
    t0 = datetime(2018, 1, 1, 12, 0, tzinfo=timezone.utc)
    rec = PublicRecord(
        external_id="a", texts=["one", "two", "three"], is_bot=False,
        post_times=[t0, t0 + timedelta(hours=5), t0 + timedelta(hours=40)],
    )
    posts = _to_posts(rec)
    assert [p.created_at for p in posts] == rec.post_times  # genuine, irregular


def test_to_posts_falls_back_to_synthetic_without_times():
    rec = PublicRecord(external_id="a", texts=["one", "two"], is_bot=False)
    posts = _to_posts(rec)
    assert (posts[1].created_at - posts[0].created_at) == timedelta(hours=1)


# --- coalesce keeps texts/post_times aligned --------------------------------

def test_coalesce_preserves_aligned_timestamps():
    t = datetime(2020, 6, 1, tzinfo=timezone.utc)
    rows = [
        PublicRecord(external_id="u", texts=["p1"], is_bot=True, post_times=[t]),
        PublicRecord(external_id="u", texts=["p2"], is_bot=True, post_times=[t + timedelta(hours=2)]),
        PublicRecord(external_id="u", texts=["p1"], is_bot=True, post_times=[t + timedelta(hours=9)]),  # dup text dropped
    ]
    merged = coalesce_records(rows)
    assert len(merged) == 1
    m = merged[0]
    assert m.texts == ["p1", "p2"]
    assert len(m.texts) == len(m.post_times)
    assert m.post_times == [t, t + timedelta(hours=2)]


# --- the reality check: temporal operates on real, not synthetic, cadence ---

def test_temporal_reads_real_cadence_not_synthetic_uniformity():
    # Synthetic uniform spacing (the OLD behavior) is perfectly periodic →
    # interval_cov collapses to ~0 (a spurious "regular = bot" signal that hits
    # every imported account identically).
    legacy = PublicRecord(external_id="s", texts=[f"post {i}" for i in range(12)], is_bot=False)
    syn = analyze_temporal(_to_posts(legacy))
    assert syn.sub_signals["interval_cov"] < 0.05

    # Real human-ish irregular cadence → non-zero coefficient of variation, and
    # the detector actually fires (confidence > 0) instead of seeing a fiction.
    base = datetime(2019, 3, 1, 9, 0, tzinfo=timezone.utc)
    gaps_h = [1, 6, 2, 27, 3, 19, 1, 33, 5, 11, 2]  # irregular, human
    times, acc = [], base
    for g in gaps_h:
        acc = acc + timedelta(hours=g)
        times.append(acc)
    real = PublicRecord(external_id="h", texts=[f"t{i}" for i in range(len(times))],
                        is_bot=False, post_times=times)
    res = analyze_temporal(_to_posts(real))
    assert res.confidence > 0.0
    assert res.sub_signals["interval_cov"] > 0.3  # genuinely irregular


# --- TwitterData adapter ----------------------------------------------------

def test_twitterdata_routing_and_no_io_collision():
    assert detect_adapter(_hdr("Twitter_Account", "Tweet_text", "Label", "Verified", "Followers"),
                          "TwitterData_Joined.csv").name == "twitterdata"
    assert detect_adapter(_hdr("Twitter_Account", "Tweet_text", "Label", "Word_Count"),
                          "TwitterData_FE.csv").name == "twitterdata"
    # IO files keep io_disclosure (userid + follower triad).
    assert detect_adapter(_hdr("userid", "tweet_text", "follower_count", "tweet_time"),
                          "russia_052020_tweets.csv").name == "io_disclosure"


def test_twitterdata_inverted_polarity_and_text_cleanup():
    human = _parse_twitterdata(
        {"twitter_account": "SadiqKhan", "tweet_text": "you are Londoners",
         "label": "1", "verified": "1", "tweet_created_at": "27-11-2016 06:15"},
        "TwitterData_Joined.csv", "r0")
    bot = _parse_twitterdata(
        {"twitter_account": "MuseumBot", "tweet_text": "b'Imperial Coat'",
         "label": "0", "tweet_created_at": "13-06-2017 18:15"},
        "TwitterData_Joined.csv", "r1")
    # Label 1 = human, 0 = bot (the inversion the audit caught).
    assert human.label == "human" and not human.is_bot and human.expected_tier == "low"
    assert bot.label == "bot" and bot.is_bot and bot.expected_tier == "high"
    # b'...' bytes-repr wrapper stripped.
    assert bot.texts[0] == "Imperial Coat"
    # verified human → Known-Mixed cohort tag; real timestamp preserved.
    assert human.campaign_id == "twitterdata_verified_mixed"
    assert human.post_times[0] == datetime(2016, 11, 27, 6, 15, tzinfo=timezone.utc)


def test_twitterdata_rejects_unlabeled_rows():
    assert _parse_twitterdata({"twitter_account": "x", "tweet_text": "hi", "label": ""},
                              "f.csv", "r") is None
