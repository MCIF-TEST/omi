"""Continuous Improvement Engine (Sprint 011).

Turns Omi's measurement stack (Shadow Mode, replay, benchmarks, prompt registry, gold corpus,
context + evidence metrics, Governor stats) into **deterministic, evidence-backed engineering
recommendations** — and a human-controlled promotion workflow. The engine recommends; humans
approve; nothing here ever changes production behavior automatically. Recommendations are
content-addressed and reproducible.
"""
from __future__ import annotations

from .promotion import STATES, PromotionLedger
from .recommend import DEFAULT_THRESHOLDS, Recommendation, Thresholds, recommend
from .report import engineering_report
from .snapshot import build_snapshot

__all__ = [
    "recommend", "Recommendation", "Thresholds", "DEFAULT_THRESHOLDS",
    "PromotionLedger", "STATES",
    "engineering_report",
    "build_snapshot",
]
