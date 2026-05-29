"""Phase 3 — Omi Intelligence Signal Registry.

This is the *declarative* layer that turns the rule engine's raw detector
outputs into named intelligence **dimensions** (authenticity, coordination,
amplification, spam, AI-generation). It deliberately contains **no scoring
logic** — only the mapping of which detectors feed which dimension and with
what relative weight. The engine in :mod:`app.intelligence.omiscore` reads
this registry and does the math.

Why a registry?
---------------
The mission requires that "additional signals can be added without major
refactoring". Here that's literally true:

* To make an existing detector feed a dimension → add a
  :class:`SignalContribution` to that dimension's tuple.
* To add a brand-new intelligence dimension → add one
  :class:`DimensionSpec` entry to :data:`INTELLIGENCE_DIMENSIONS` and one
  field to the output schema.
* To onboard a brand-new detector → it starts contributing the moment its
  name appears in any dimension's contributions; no engine code changes.

The detector names below MUST match ``SignalResult.name`` emitted by the
detectors in :mod:`app.detection` (temporal, semantic, ai_writing, voice,
engagement, profile, memory, coordination). A contribution naming a detector
that didn't run is simply skipped at scoring time, so partial scans degrade
gracefully.
"""

from __future__ import annotations

from dataclasses import dataclass, field


# Bump when the dimension layout or weighting semantics change in a way that
# would make two OmiScore payloads incomparable. Surfaced in the output so
# downstream consumers (dashboards, stored investigations) can detect drift.
OMISCORE_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class SignalContribution:
    """One detector's contribution to a single intelligence dimension.

    ``weight`` is *relative within the dimension* — the engine normalizes by
    the sum of weights, so weights are interpretable as "share of this
    dimension this detector is responsible for" before confidence weighting.

    ``invert`` flips the detector's probability (``1 - p``). Used by the
    authenticity dimension, where a *low* inauthenticity probability is the
    signal of organic behavior.
    """

    detector: str
    weight: float
    invert: bool = False


@dataclass(frozen=True)
class DimensionSpec:
    """A named intelligence dimension assembled from detector contributions."""

    key: str            # output field name, e.g. "coordination_probability"
    label: str          # human-readable label for UI / explanations
    description: str
    contributions: tuple[SignalContribution, ...]
    # When True the dimension measures *risk* (higher = more concerning);
    # when False it measures *trust* (higher = more organic). Drives summary
    # phrasing and the authenticity inversion.
    is_risk: bool = True
    aliases: tuple[str, ...] = field(default_factory=tuple)


def _c(detector: str, weight: float, *, invert: bool = False) -> SignalContribution:
    return SignalContribution(detector=detector, weight=weight, invert=invert)


# ---------------------------------------------------------------------------
# The registry.
#
# Weights are defensible defaults, not magic constants — they encode which
# detectors are the *primary* evidence for each threat type and which are
# corroborating. They live here (data, not code) precisely so they can be
# tuned against labeled outcomes later without touching the engine.
# ---------------------------------------------------------------------------

INTELLIGENCE_DIMENSIONS: dict[str, DimensionSpec] = {
    # Coordination: multiple accounts acting in concert. The cross-account
    # coordination detector is the primary witness; the memory detector
    # corroborates when an account's fingerprint matches a known cluster.
    "coordination_probability": DimensionSpec(
        key="coordination_probability",
        label="Coordinated activity",
        description=(
            "Likelihood the account is acting in concert with others — shared "
            "narratives, synchronized timing, or matching behavioral fingerprints."
        ),
        contributions=(
            _c("coordination", 0.70),
            _c("memory", 0.30),
        ),
    ),
    # Amplification: artificial boosting of reach/engagement. Coordination
    # clusters do the amplifying; engagement-farming patterns and mechanical
    # posting bursts are the mechanism.
    "amplification_probability": DimensionSpec(
        key="amplification_probability",
        label="Artificial amplification",
        description=(
            "Likelihood of artificial reach inflation — cluster amplification, "
            "engagement farming, or burst-timed posting designed to boost reach."
        ),
        contributions=(
            _c("coordination", 0.45),
            _c("engagement", 0.35),
            _c("temporal", 0.20),
        ),
    ),
    # Spam: promotional / repetitive behavior. Engagement detector catches the
    # URL/promo patterns; semantic catches the templated repetition.
    "spam_probability": DimensionSpec(
        key="spam_probability",
        label="Spam behavior",
        description=(
            "Likelihood of spam or promotional behavior — repetitive content, "
            "link-pushing, or copy-paste templates."
        ),
        contributions=(
            _c("engagement", 0.60),
            _c("semantic", 0.40),
        ),
    ),
    # AI generation: synthetic text. The ai_writing detector is the primary
    # witness; semantic (templated phrasing) and voice (unusually low
    # first-person rate) corroborate.
    "ai_generation_probability": DimensionSpec(
        key="ai_generation_probability",
        label="AI-generated content",
        description=(
            "Likelihood the content is AI-generated or AI-assisted — burstiness, "
            "templated phrasing, and an unusually impersonal voice."
        ),
        contributions=(
            _c("ai_writing", 0.70),
            _c("semantic", 0.20),
            _c("voice", 0.10),
        ),
    ),
    # Authenticity: the trust-framed dimension. Built from the *inverse* of the
    # behavioral detectors that most directly distinguish organic humans from
    # synthetic/automated accounts.
    "authenticity_score": DimensionSpec(
        key="authenticity_score",
        label="Authenticity",
        description=(
            "How organic the account looks — high means human-paced behavior, "
            "natural language, and a credible profile shape."
        ),
        is_risk=False,
        contributions=(
            _c("temporal", 0.25, invert=True),
            _c("ai_writing", 0.25, invert=True),
            _c("semantic", 0.20, invert=True),
            _c("voice", 0.15, invert=True),
            _c("profile", 0.15, invert=True),
        ),
    ),
}


# Dimensions whose value the engine reports as a 0–100 *probability* number.
# (authenticity_score is reported but framed as trust, handled separately.)
THREAT_DIMENSIONS: tuple[str, ...] = (
    "coordination_probability",
    "amplification_probability",
    "spam_probability",
    "ai_generation_probability",
)


def all_referenced_detectors() -> set[str]:
    """Every detector name referenced by any dimension — used by tests to
    guard against typos that would silently zero out a dimension."""
    names: set[str] = set()
    for spec in INTELLIGENCE_DIMENSIONS.values():
        for contrib in spec.contributions:
            names.add(contrib.detector)
    return names
