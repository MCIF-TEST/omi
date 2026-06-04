"""Phase 1 free wins — AI-set salvage, FSM xlsx->csv unlock, botscore reference."""

from __future__ import annotations

from app.ml.datasets.adapters import _parse_text_detection_v1
from app.ml.datasets.botscore_reference import botscore_distribution, score_to_tier
from app.ml.datasets.discovery import discover
from app.ml.datasets.manifest import load_manifest
from app.ml.datasets.paths import default_datasets_dir

_FSM_CSV = "Datasets/Fake Social Media Account Detection Dataset/fake_social_media_global_2.0.csv"
_FSM_XLSX = "Datasets/Fake Social Media Account Detection Dataset/fake_social_media_global_2.0_with_missing.xlsx"
_AI_V1 = "ai vs human text/ai_human_detection_v1.csv"


# --- AI-set salvage ---------------------------------------------------------

def test_ai_detection_skips_api_error_rows_keeps_clean():
    err = _parse_text_detection_v1(
        {"text": "Error: 400 Client Error: Bad Request for url: https://api.groq",
         "human_or_ai": "ai", "source_model": "x"}, "ai_human_detection_v1.csv", "r0")
    assert err is None  # contamination dropped at parse
    ok = _parse_text_detection_v1(
        {"text": "Aprender a programar en Python es accesible para todos.",
         "human_or_ai": "human", "source_model": "human"}, "ai_human_detection_v1.csv", "r1")
    assert ok is not None and ok.is_ai is False


def test_ai_detection_v1_unquarantined():
    man = load_manifest(default_datasets_dir())
    assert man.status(_AI_V1) == "validation"
    df = next((d for d in discover(default_datasets_dir()) if d.rel_path == _AI_V1), None)
    assert df is not None and df.supported and df.adapter.name == "ai_human_detection_v1"


# --- FSM xlsx -> csv unlock --------------------------------------------------

def test_fsm_csv_unlocked_balanced_and_routed():
    root = default_datasets_dir()
    man = load_manifest(root)
    assert man.status(_FSM_CSV) == "train"
    assert man.status(_FSM_XLSX) == "archive"  # superseded
    df = next((d for d in discover(root) if d.rel_path == _FSM_CSV), None)
    assert df is not None and df.supported and df.adapter.name == "fake_social_media"


# --- botscore reference ------------------------------------------------------

def test_botscore_reference_distribution():
    d = botscore_distribution(default_datasets_dir() / "Datasets" / "activity_botscore.csv")
    assert d["n"] > 10_000
    assert set(d["tiers"]) == {"low", "moderate", "elevated", "high"}
    assert abs(sum(d["tier_fractions"].values()) - 1.0) < 0.01
    assert 0.0 <= d["flagged_fraction"] <= 1.0
    assert score_to_tier(0.1) == "low" and score_to_tier(0.4) == "moderate"
    assert score_to_tier(0.6) == "elevated" and score_to_tier(0.9) == "high"
