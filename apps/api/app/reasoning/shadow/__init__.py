"""Shadow Mode evaluation pipeline (Sprint 007).

Runs the AI-backed Analyst Council in parallel with the deterministic production council, for
**evaluation only** — users keep receiving the deterministic result. The pipeline answers one
question with evidence: *does the AI-backed council outperform the deterministic baseline?* —
via a deterministic comparison engine, deterministic replay, durable per-investigation
storage, and aggregate engineering statistics. Fully operational with or without a live model
(the AI council falls back to deterministic when no endpoint is configured).
"""
from __future__ import annotations

from .benchmark import ab_evaluate, compare_context_modes
from .compare import blackboard_digest, compare, council_view
from .ledger import ShadowLedger, aggregate_stats
from .persist import SHADOW_KEY, all_reports, cached_report, persist_report
from .replay import replay
from .runner import ShadowReport, memory_revision, run_shadow

__all__ = [
    "run_shadow", "ShadowReport", "memory_revision",
    "compare", "council_view", "blackboard_digest",
    "replay",
    "ab_evaluate", "compare_context_modes",
    "aggregate_stats", "ShadowLedger",
    "persist_report", "cached_report", "all_reports", "SHADOW_KEY",
]
