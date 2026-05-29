"""AI-writing detector benchmark over a labeled text corpus.

Two layers:
* a deterministic synthetic check of the report shape + abstention behavior, and
* a soft ratchet against the *real* uploaded corpus when it's present, pinning
  the honest baseline (the detector is high-precision / low-coverage on short
  social text) so a regression that floods false positives trips the gate.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.evaluation import evaluate_ai_writing, evaluate_ai_writing_default
from app.ml.datasets.paths import default_datasets_dir
from app.ml.datasets.records import TextRecord

# Long, low-burstiness, hedge-heavy passage — the detector should fire here.
# Kept well over the 120-word / 6-sentence floor with uniform sentence lengths.
_AI_LONG = (
    "It is worth noting that the system is a multifaceted and ever-evolving framework. "
    "It is worth noting that the data is a multifaceted and ever-evolving framework. "
    "Moreover the results underscore the broader pattern that we observe here. "
    "Moreover the findings underscore the broader pattern that we observe here. "
    "Furthermore the analysis delves into the intricate details of this domain. "
    "Furthermore the review delves into the intricate details of this domain. "
    "Additionally the approach speaks to the broader implications of the work. "
    "Additionally the method speaks to the broader implications of the work. "
    "In conclusion the framework fundamentally captures the essence of the matter. "
    "In conclusion the structure fundamentally captures the essence of the matter. "
    "In essence this stands as a testament to a nuanced and thoughtful design. "
    "In essence this stands as a testament to a careful and thoughtful design."
)
# Bursty, idiosyncratic human writing of comparable length: full sentences of
# varied length, no AI hedges or em-dashes.
_HUMAN_LONG = (
    "I tried this last night and it was a complete disaster. "
    "The machine refused to boot at first. "
    "Then it started, ran for barely a minute, and crashed really hard. "
    "I spent three hours chasing the problem around in circles getting nowhere. "
    "Eventually I discovered that the real culprit was a cheap cable. "
    "A five dollar cable had been the issue the entire time. "
    "I felt pretty silly after taking the whole thing apart for nothing. "
    "If your setup acts strange, check the cables before anything else. "
    "That one small step would have saved my entire evening of frustration. "
    "Honestly the relief of finally finding it was enormous. "
    "I grabbed a coffee afterwards and called it a night. "
    "Tomorrow I will write the part number down somewhere safe."
)


def test_report_shape_and_abstention():
    records = [
        TextRecord("a", _AI_LONG, is_ai=True),
        TextRecord("b", _HUMAN_LONG, is_ai=False),
        TextRecord("c", "too short to score", is_ai=True),
    ]
    rep = evaluate_ai_writing(records)
    assert rep["n_total"] == 3
    assert rep["n_ai"] == 2 and rep["n_human"] == 1
    # The short sample must abstain; the two long ones get scored.
    assert rep["n_covered"] == 2
    assert 0.0 < rep["coverage"] <= 1.0
    for block in ("overall", "covered"):
        for key in ("accuracy", "ai_precision", "ai_recall", "ai_f1", "brier"):
            assert key in rep[block]


def test_ai_long_text_scores_higher_than_human():
    rep = evaluate_ai_writing([
        TextRecord("a", _AI_LONG, is_ai=True),
        TextRecord("b", _HUMAN_LONG, is_ai=False),
    ])
    # On the covered set the detector should not be calling the human text AI.
    assert rep["covered"]["confusion"]["fp"] == 0


def test_empty_corpus_message():
    rep = evaluate_ai_writing_default(root=Path("/nonexistent/datasets/dir"))
    assert rep["n_total"] == 0 and "message" in rep


# --- ratchet on the real corpus (skipped if not checked out) -------------

_HAS_REAL_CORPUS = (default_datasets_dir() / "ai vs human text").is_dir()

# Current measured baseline (see docs/dataset-training.md). Tighten as the
# detector / text head improve. The point of the gate is to catch a regression
# that starts mislabeling human text as AI.
GATE_MIN_COVERAGE = 0.02              # currently ~0.054
GATE_MIN_COVERED_AI_PRECISION = 0.80  # currently 1.000
GATE_MIN_OVERALL_ACCURACY = 0.50      # currently 0.549; must beat a coin flip


@pytest.mark.skipif(not _HAS_REAL_CORPUS, reason="datasets/ not present")
def test_real_corpus_baseline_holds():
    rep = evaluate_ai_writing_default()
    assert rep["n_total"] >= 3000
    assert rep["coverage"] >= GATE_MIN_COVERAGE
    assert rep["covered"]["ai_precision"] >= GATE_MIN_COVERED_AI_PRECISION
    assert rep["overall"]["accuracy"] >= GATE_MIN_OVERALL_ACCURACY
