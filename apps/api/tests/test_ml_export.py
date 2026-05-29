"""DB-backed tests for the ML training export + public dataset importer."""

from __future__ import annotations

from app.ml.export import export_summary, iter_training_rows
from app.ml.features import FEATURE_DIM
from app.ml.public_import import PublicRecord, ingest_records
from app.storage.db import get_session


def _bot_texts() -> list[str]:
    # Repetitive, templated, link-heavy — what the engine should flag.
    return [
        "Check out this amazing deal!!! http://spam.example/x click now",
        "Check out this amazing deal!!! http://spam.example/y click now",
        "Check out this amazing deal!!! http://spam.example/z click now",
        "Amazing offer don't miss out http://spam.example/a click now",
    ] * 3


def _human_texts() -> list[str]:
    return [
        "honestly the second half of this video changed how I think about the topic",
        "I disagree with the framing here but the data section was solid",
        "lol the part at 12:30 got me, did not expect that turn",
        "been following this channel for years, this is one of the better ones",
    ]


def test_public_import_then_export_roundtrip():
    records = [
        PublicRecord(external_id="b1", texts=_bot_texts(), is_bot=True,
                     follower_count=3, following_count=4000, account_age_days=5),
        PublicRecord(external_id="b2", texts=_bot_texts(), is_bot=True,
                     follower_count=1, following_count=5000, account_age_days=3),
        PublicRecord(external_id="h1", texts=_human_texts(), is_bot=False,
                     follower_count=800, following_count=300, account_age_days=2000),
        PublicRecord(external_id="h2", texts=_human_texts(), is_bot=False,
                     follower_count=1200, following_count=400, account_age_days=1500),
    ]
    with get_session() as session:
        stats = ingest_records(session, records, dataset_name="unittest")
        session.commit()

    assert stats["ingested"] == 4
    assert stats["bots"] == 2
    assert stats["humans"] == 2

    with get_session() as session:
        rows = list(iter_training_rows(session))
        # Each imported account becomes a training row (all have scans now).
        ids = {r.account_external_id for r in rows}
        assert "unittest:b1" in ids
        assert "unittest:h1" in ids
        for r in rows:
            assert len(r.features) == FEATURE_DIM
            assert r.source == "imported_dataset"
            assert r.sample_weight > 0
            # Bots → inauthentic target 1, humans → 0
            if r.account_external_id.startswith("unittest:b"):
                assert r.inauthentic == 1
            if r.account_external_id.startswith("unittest:h"):
                assert r.inauthentic == 0


def test_export_summary_counts():
    records = [
        PublicRecord(external_id="s1", texts=_bot_texts(), is_bot=True),
        PublicRecord(external_id="s2", texts=_human_texts(), is_bot=False),
    ]
    with get_session() as session:
        ingest_records(session, records, dataset_name="summ")
        session.commit()

    with get_session() as session:
        summary = export_summary(session)
    assert summary["n_features"] == FEATURE_DIM
    assert summary["n_training_rows"] >= 2
    assert "imported_dataset" in summary["by_source"]
    assert summary["by_target"]["inauthentic"] >= 1
    assert summary["by_target"]["authentic"] >= 1
