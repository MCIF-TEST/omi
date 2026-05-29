"""Pydantic schemas for the Omi Intelligence layer (OmiScore).

These wrap the rule engine's :class:`~app.schemas.ScanResult` in a richer,
explainable intelligence envelope. The shape matches the Phase 4 contract:

    {
      "omi_score": 0-100,
      "authenticity_score": 0-100,
      "coordination_probability": 0-100,
      "amplification_probability": 0-100,
      "spam_probability": 0-100,
      "ai_generation_probability": 0-100,
      "risk_level": "low|medium|high"
    }

…plus full traceability (`dimensions`, `evidence`, `contributions`) so every
number is explainable back to the detectors that produced it.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

RiskLevel = Literal["low", "medium", "high"]


class DimensionContribution(BaseModel):
    """One detector's traced contribution to a dimension's score."""

    detector: str
    label: str
    # The detector's probability AFTER any inversion this dimension applies
    # (so it reads in the dimension's own direction).
    contribution_probability: float = Field(ge=0.0, le=1.0)
    confidence: float = Field(ge=0.0, le=1.0)
    # Share of the dimension this detector accounted for, 0–1, after
    # confidence weighting. Sums to ~1.0 across a dimension's contributors.
    weight_share: float = Field(ge=0.0, le=1.0)
    evidence: list[str] = Field(default_factory=list)


class IntelligenceDimension(BaseModel):
    """A single scored intelligence dimension with its evidence trail."""

    key: str
    label: str
    description: str
    score: float = Field(ge=0.0, le=100.0, description="0–100 in the dimension's own direction")
    confidence: float = Field(ge=0.0, le=1.0)
    is_risk: bool
    contributions: list[DimensionContribution] = Field(default_factory=list)


class OmiScore(BaseModel):
    """The unified intelligence verdict for one subject.

    The flat 0–100 fields at the top are the stable public contract; the
    ``dimensions`` list underneath is the explainability layer.
    """

    schema_version: int

    # ---- The Phase 4 public contract (flat, 0–100) ----
    omi_score: float = Field(ge=0.0, le=100.0, description="Composite risk, 0–100")
    authenticity_score: float = Field(ge=0.0, le=100.0)
    coordination_probability: float = Field(ge=0.0, le=100.0)
    amplification_probability: float = Field(ge=0.0, le=100.0)
    spam_probability: float = Field(ge=0.0, le=100.0)
    ai_generation_probability: float = Field(ge=0.0, le=100.0)
    risk_level: RiskLevel

    # ---- Explainability / traceability ----
    confidence: float = Field(ge=0.0, le=1.0, description="Overall evidence confidence")
    subject: str | None = None
    headline: str = Field(description="One-line plain-language verdict")
    primary_threat: str | None = Field(
        default=None,
        description="Key of the highest-scoring threat dimension, if any concerning.",
    )
    dimensions: list[IntelligenceDimension] = Field(default_factory=list)
    # The single most important reasons, deduped across dimensions, ranked by
    # contribution — for compact UI rendering without expanding every dimension.
    top_evidence: list[str] = Field(default_factory=list)
