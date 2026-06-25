"""Reasoning Orchestrator — the deterministic council control plane (Sprint 004).

Builds Omi's permanent intelligence-execution framework: a Blackboard, the council modules
(deterministic today, model-backed later via the same contracts), and the Orchestrator that
runs them tier-by-tier, validates artifacts against their contracts, adjudicates, and puts
every decision through the mandatory Governor with the deterministic Floor as fallback.
"""
from __future__ import annotations

from .blackboard import Blackboard, BlackboardView
from .modules import (
    AnalystModule,
    BehaviorAnalyst,
    CounterEvidenceAnalyst,
    FloorJudge,
    Judge,
    build_ruling_assessment,
    default_council,
)
from .orchestrator import BudgetController, CouncilResult, Orchestrator

__all__ = [
    "Blackboard", "BlackboardView",
    "AnalystModule", "BehaviorAnalyst", "CounterEvidenceAnalyst", "Judge", "FloorJudge",
    "build_ruling_assessment", "default_council",
    "Orchestrator", "BudgetController", "CouncilResult",
]
