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
from app.ml.export import export_summary, iter_training_rows
from app.ml.public_import import (
    PublicRecord,
    coalesce_records,
    ingest_records,
    _resolve_ground_truth,
)
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


# --- Fix 1: synthetic provenance is separable -----------------------------

def test_synthetic_ingest_tags_synthetic_source():
    recs = generate_corpus(n_per_persona=3)
    with get_session() as session:
        ingest_records(session, recs, dataset_name="synthetic", source="synthetic")
        sources = {row.source for row in session.query(AccountLabel).all()}
        assert sources == {"synthetic"}


def test_synthetic_excluded_from_training_by_default():
    recs = generate_corpus(n_per_persona=3)
    with get_session() as session:
        ingest_records(session, recs, dataset_name="synthetic", source="synthetic")
        # Default training export must not see synthetic rows...
        default_rows = list(iter_training_rows(session, include_unclear=True))
        assert default_rows == []
        # ...but an explicit opt-in surfaces them.
        opted_in = list(iter_training_rows(session, include_unclear=True, include_synthetic=True))
        assert len(opted_in) == len(recs)
        assert all(r.source == "synthetic" for r in opted_in)


def test_synthetic_and_real_imports_stay_separable():
    synth = generate_corpus(n_per_persona=2)
    real = [PublicRecord(external_id="real1", texts=["totally normal comment"], is_bot=False)]
    with get_session() as session:
        ingest_records(session, synth, dataset_name="synthetic", source="synthetic")
        ingest_records(session, real, dataset_name="public")  # default imported_dataset
        summary = export_summary(session)  # excludes synthetic
        assert "synthetic" not in summary["by_source"]
        assert summary["by_source"].get("imported_dataset") == 1


# --- Fix 2: per-tweet archives coalesce into one account ------------------

def test_coalesce_merges_texts_by_external_id():
    recs = [
        PublicRecord(external_id="u1", texts=["first"], is_bot=True,
                     label="political_coord", expected_tier="high", follower_count=5),
        PublicRecord(external_id="u1", texts=["second"], is_bot=True,
                     label="political_coord", expected_tier="high", following_count=900),
        PublicRecord(external_id="u2", texts=["only"], is_bot=True),
    ]
    merged = coalesce_records(recs)
    assert [m.external_id for m in merged] == ["u1", "u2"]
    u1 = merged[0]
    assert u1.texts == ["first", "second"]      # both posts retained, in order
    assert u1.follower_count == 5               # first-row scalar kept
    assert u1.following_count == 900            # blank backfilled from later row


def test_coalesce_dedupes_and_is_noop_for_unique_ids():
    recs = [
        PublicRecord(external_id="u1", texts=["dup", "dup", "x"], is_bot=False),
        PublicRecord(external_id="u1", texts=["x", "y"], is_bot=False),
    ]
    [u1] = coalesce_records(recs)
    assert u1.texts == ["dup", "x", "y"]
    # Unique-id records pass through untouched.
    uniq = [PublicRecord(external_id=f"u{i}", texts=["t"], is_bot=False) for i in range(3)]
    assert len(coalesce_records(uniq)) == 3


def test_io_multi_tweet_user_scored_on_full_history(tmp_path: Path):
    """End-to-end: a 3-tweet IO user becomes ONE account whose scan saw all
    three posts, not just the last one."""
    p = tmp_path / "io_camp.csv"
    with p.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["tweetid", "userid", "user_screen_name", "follower_count",
                    "following_count", "account_creation_date", "tweet_text"])
        for j in range(3):
            w.writerow([str(j), "uX", "agent", "8", "2200", "2016-01-01",
                        f"coordinated message number {j}"])
    [df] = [d for d in discover(tmp_path) if d.supported]
    recs, _ = read_records(df)
    assert len(recs) == 3  # one per row before coalescing
    merged = coalesce_records(recs)
    assert len(merged) == 1
    assert len(merged[0].texts) == 3
    with get_session() as session:
        res = ingest_records(session, recs, dataset_name="io", source="imported_dataset")
        assert res["ingested"] == 1
        assert session.query(Account).count() == 1


# --- Fix 3: text variety scales with volume ------------------------------

@pytest.mark.parametrize("persona", ["organic_human", "esl_human", "engagement_farm",
                                     "commercial_spam", "ai_assisted_human"])
def test_post_sets_stay_distinct_at_volume(persona):
    """Decoration must keep accounts distinct as --n grows, otherwise the
    corpus collapses into duplicates and stops being useful ground truth."""
    only = (PERSONAS_BY_NAME[persona],)
    recs = generate_corpus(n_per_persona=150, personas=only)
    unique = {tuple(r.texts) for r in recs}
    # Allow a small number of collisions but require the corpus to remain
    # overwhelmingly varied at 150 accounts.
    assert len(unique) / len(recs) >= 0.95, f"{persona}: only {len(unique)}/{len(recs)} unique"


def test_decoration_preserves_determinism():
    a = generate_corpus(n_per_persona=20, seed=7)
    b = generate_corpus(n_per_persona=20, seed=7)
    assert [r.texts for r in a] == [r.texts for r in b]
