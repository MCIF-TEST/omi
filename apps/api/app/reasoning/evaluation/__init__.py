"""Gold evaluation corpus (Sprint 008).

Curated, human-reviewed investigations with benchmark labels for measuring reasoning quality —
agreement with the human read and false-positive rate on legitimate-coordination controls.
Evaluation only; never used for training. Deterministic, so it doubles as a regression and
prompt-comparison harness over the Shadow Mode pipeline.
"""
from __future__ import annotations

from .corpus import GoldCase, GoldCorpus, default_gold_corpus, evaluate_corpus

__all__ = ["GoldCase", "GoldCorpus", "evaluate_corpus", "default_gold_corpus"]
