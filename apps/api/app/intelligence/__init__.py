"""Omi Intelligence layer — the OmiScore engine.

Composes the rule engine's detector outputs (and any ML re-ranking already
applied) into a unified, explainable intelligence envelope: a single
``omi_score`` plus per-threat dimension probabilities, each traceable to the
detectors and evidence that produced it.

Public surface:

    from app.intelligence import compute_omiscore, OmiScore
"""

from __future__ import annotations

from app.intelligence.omiscore import compute_omiscore
from app.intelligence.schemas import (
    DimensionContribution,
    IntelligenceDimension,
    OmiScore,
)
from app.intelligence.signals import (
    INTELLIGENCE_DIMENSIONS,
    OMISCORE_SCHEMA_VERSION,
)

__all__ = [
    "compute_omiscore",
    "OmiScore",
    "IntelligenceDimension",
    "DimensionContribution",
    "INTELLIGENCE_DIMENSIONS",
    "OMISCORE_SCHEMA_VERSION",
]
