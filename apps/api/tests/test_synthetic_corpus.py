"""Synthetic ground-truth corpus + label-aware ingestion.

These pin the contract GAP-01 relies on:

* the generator is deterministic (same seed → identical corpus), so it doubles
  as a CI regression fixture;
* the false-positive personas (ESL, AI-assisted) are labeled human/low — the
  whole point is that the engine must NOT learn to flag them;
* ``ingest_records`` honors an explicit label/tier and persists it as an
  ``imported_dataset`` AccountLabel, validating bad labels loudly;
* the IO-disclosure adapter recognizes the Twitter/X transparency format and
  labels those accounts political_coord/high.
"""

from __future__ import annotations

import csv
from pathlib import Path

import pytest

from app.ml.datasets.discovery import discover, read_records
from app.ml.datasets.registry import detect_adapter
from app.ml.datasets.normalize import norm_key
from app.ml.datasets.synthetic import (
    PERSONAS,
    PERSONAS_BY_NAME,
    corpus_label_distribution,
    generate_corpus,
)
from app.ml.public_import import PublicRecord, ingest_records, _resolve_ground_truth
from app.storage.db import get_session
from app.storage.models import Account, AccountLabel


def _norm(header):
    return {norm_key(h) for h in header}


# --- generator: determinism + labeling -----------------------------------

def test_generation_is_deterministic():
    a = generate_corpus(n_per_persona=10, seed=42)
    b = generate_corpus(n_per_persona=10, seed=42)
    assert [(r.external_id, r.texts, r.label) for r in a] == \
           [(r.external_id, r.texts, r.label) for r in b]


def test_different_seeds_diverge():
    a = generate_corpus(n_per_persona=10, seed=1)
    b = generate_corpus(n_per_persona=10, seed=2)
    assert [r.texts for r in a] != [r.texts for r in b]


def test_corpus_covers_every_persona_evenly():
    n = 7
    recs = generate_corpus(n_per_persona=n)
    assert len(recs) == n * len(PERSONAS)
    by_persona: dict[str, int] = {}
    for r in recs:
        by_persona[r.external_id.rsplit("_", 1)[0]] = by_persona.get(r.external_id.rsplit("_", 1)[0], 0) + 1
    assert set(by_persona) == set(PERSONAS_BY_NAME)
    assert all(v == n for v in by_persona.values())


def test_every_record_carries_explicit_ground_truth():
    for r in generate_corpus(n_per_persona=3):
        assert r.label is not None
        assert r.expected_tier in ("low", "moderate", "elevated", "high")
        assert r.texts, f"{r.external_id} must have at least one post"


def test_false_positive_personas_are_human_low():
    """The crux of GAP-01: genuine-but-suspicious-looking accounts are labeled
    authentic. If this regresses, the engine will be calibrated to flag real
    non-native speakers and grammar-tool users."""
    recs = generate_corpus(n_per_persona=5)
    for name in ("esl_human", "ai_assisted_human", "organic_human"):
        sub = [r for r in recs if r.external_id.startswith(name)]
        assert sub, f"no records for {name}"
        assert all(r.label == "human" for r in sub)
        assert all(r.expected_tier == "low" for r in sub)
        assert all(r.is_bot is False for r in sub)


def test_inauthentic_personas_are_high_tier():
    recs = generate_corpus(n_per_persona=5)
    expected = {
        "coordinated_io": "political_coord",
        "engagement_farm": "engagement_farm",
        "commercial_spam": "commercial_spam",
    }
    for name, label in expected.items():
        sub = [r for r in recs if r.external_id.startswith(name)]
        assert sub
        assert all(r.label == label for r in sub)
        assert all(r.expected_tier == "high" for r in sub)


def test_coordinated_io_carries_campaign_id():
    recs = [r for r in generate_corpus(n_per_persona=5) if r.external_id.startswith("coordinated_io")]
    assert all(r.campaign_id for r in recs)


def test_label_distribution_summary():
    dist = corpus_label_distribution(generate_corpus(n_per_persona=10))
    assert dist["human"] == 30          # 3 human personas x 10
    assert dist["political_coord"] == 10
    assert dist["engagement_farm"] == 10
    assert dist["commercial_spam"] == 10


def test_restrict_to_subset_of_personas():
    only = (PERSONAS_BY_NAME["esl_human"],)
    recs = generate_corpus(n_per_persona=4, personas=only)
    assert len(recs) == 4
    assert all(r.external_id.startswith("esl_human") for r in recs)


# --- ground-truth resolution + validation --------------------------------

def test_resolve_ground_truth_uses_explicit_over_binary():
    rec = PublicRecord(external_id="x", texts=["hi"], is_bot=True,
                        label="human", expected_tier="low")
    assert _resolve_ground_truth(rec) == ("human", "low")


def test_resolve_ground_truth_falls_back_to_is_bot():
    assert _resolve_ground_truth(
        PublicRecord(external_id="x", texts=["hi"], is_bot=True)) == ("bot", "high")
    assert _resolve_ground_truth(
        PublicRecord(external_id="x", texts=["hi"], is_bot=False)) == ("human", "low")


def test_resolve_ground_truth_rejects_bad_label():
    with pytest.raises(ValueError):
        _resolve_ground_truth(
            PublicRecord(external_id="x", texts=["hi"], is_bot=True, label="nonsense"))


def test_resolve_ground_truth_rejects_bad_tier():
    with pytest.raises(ValueError):
        _resolve_ground_truth(
            PublicRecord(external_id="x", texts=["hi"], is_bot=True, expected_tier="critical"))


# --- ingestion into AccountLabel (DB-bound) ------------------------------

def test_ingest_synthetic_persists_correct_labels():
    recs = generate_corpus(n_per_persona=4)
    with get_session() as session:
        res = ingest_records(session, recs, dataset_name="synthetic", label_confidence="high")
        assert res["ingested"] == len(recs)
        # Each persona maps to one label kind.
        labels = {row.label for row in session.query(AccountLabel).all()}
        assert {"human", "political_coord", "engagement_farm", "commercial_spam"} <= labels
        # The ESL/AI personas landed as human/low, not flagged.
        humans = session.query(AccountLabel).filter(AccountLabel.label == "human").all()
        assert all(lab.expected_tier == "low" for lab in humans)
        assert all(lab.source == "imported_dataset" for lab in humans)


def test_ingest_is_idempotent_on_rerun():
    recs = generate_corpus(n_per_persona=3)
    with get_session() as session:
        ingest_records(session, recs, dataset_name="synthetic")
        first = session.query(AccountLabel).count()
        first_accounts = session.query(Account).count()
    with get_session() as session:
        ingest_records(session, recs, dataset_name="synthetic")
        assert session.query(AccountLabel).count() == first
        assert session.query(Account).count() == first_accounts


def test_campaign_id_recorded_in_rationale():
    recs = [r for r in generate_corpus(n_per_persona=3) if r.external_id.startswith("coordinated_io")]
    with get_session() as session:
        ingest_records(session, recs, dataset_name="synthetic")
        coord = session.query(AccountLabel).filter(
            AccountLabel.label == "political_coord").all()
        assert coord
        assert all("Campaign:" in (lab.rationale or "") for lab in coord)


# --- IO-disclosure adapter (Stream A archive ingestion) ------------------

def test_io_disclosure_adapter_detected():
    header = _norm(["tweetid", "userid", "user_screen_name", "follower_count",
                    "following_count", "account_creation_date", "tweet_text"])
    adapter = detect_adapter(header, "ira_062020.csv")
    assert adapter is not None
    assert adapter.name == "io_disclosure"


def test_io_disclosure_parses_to_political_coord(tmp_path: Path):
    p = tmp_path / "ira_campaign.csv"
    with p.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["tweetid", "userid", "user_screen_name", "follower_count",
                    "following_count", "account_creation_date", "tweet_text"])
        w.writerow(["1", "u100", "patriot_voice", "12", "3000", "2016-01-01",
                    "Wake up about the election!"])
        w.writerow(["2", "u100", "patriot_voice", "12", "3000", "2016-01-01",
                    "They are hiding the truth."])
    [df] = [d for d in discover(tmp_path) if d.supported]
    recs, _ = read_records(df)
    assert all(isinstance(r, PublicRecord) for r in recs)
    assert all(r.label == "political_coord" and r.expected_tier == "high" for r in recs)
    assert all(r.campaign_id == "ira_campaign" for r in recs)
    assert recs[0].external_id == "u100"
