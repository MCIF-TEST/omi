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
    # When True the dimension is *contextual* — reported and explainable, but
    # deliberately excluded from the composite omi_score, the primary-threat
    # selection, and the top-evidence roll-up. Used for signals that are
    # informative but must not raise suspicion on their own (GAP-03:
    # ai_generation_probability, which is driven by the supplemental ai_writing
    # detector — AI-assisted phrasing is not evidence of inauthenticity).
    is_contextual: bool = False
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
    # AI generation: synthetic text. CONTEXTUAL (GAP-03) — reported and fully
    # explainable, but excluded from the composite omi_score and primary-threat
    # selection. The ai_writing detector that drives it false-positives on ESL
    # writers, formal writers, and legitimate Grammarly/LLM-assisted humans, so
    # "this reads as AI-assisted" is shown as information, never as suspicion.
    "ai_generation_probability": DimensionSpec(
        key="ai_generation_probability",
        label="AI-generated content",
        description=(
            "Likelihood the content is AI-generated or AI-assisted — burstiness, "
            "templated phrasing, and an unusually impersonal voice. Contextual "
            "only: this is informational and does not contribute to the risk score, "
            "because AI-assisted writing is not by itself a sign of inauthenticity."
        ),
        is_contextual=True,
        contributions=(
            _c("ai_writing", 0.70),
            _c("semantic", 0.20),
            _c("voice", 0.10),
        ),
    ),
    # Authenticity: the trust-framed dimension. Built from the *inverse* of the
    # behavioral detectors that most directly distinguish organic humans from
    # synthetic/automated accounts. ai_writing is intentionally NOT a member
    # (GAP-03): penalising AI-assisted phrasing as "inauthentic" is precisely
    # the false-positive harm we are removing.
    "authenticity_score": DimensionSpec(
        key="authenticity_score",
        label="Authenticity",
        description=(
            "How organic the account looks — high means human-paced behavior, "
            "natural language, and a credible profile shape."
        ),
        is_risk=False,
        contributions=(
            _c("temporal", 0.30, invert=True),
            _c("semantic", 0.30, invert=True),
            _c("voice", 0.20, invert=True),
            _c("profile", 0.20, invert=True),
        ),
    ),
}


# Threat dimensions: the risk-framed dimensions that actually feed the
# composite omi_score, primary-threat selection, and top-evidence roll-up.
# Derived from the registry so it stays in sync: a risk dimension is a threat
# dimension unless it is explicitly marked contextual (GAP-03 demoted
# ai_generation_probability to contextual — reported, but not scored).
THREAT_DIMENSIONS: tuple[str, ...] = tuple(
    spec.key
    for spec in INTELLIGENCE_DIMENSIONS.values()
    if spec.is_risk and not spec.is_contextual
)

# Contextual dimensions: reported and explainable, but excluded from the
# composite. Surfaced separately so the UI can render them as information.
CONTEXTUAL_DIMENSIONS: tuple[str, ...] = tuple(
    spec.key for spec in INTELLIGENCE_DIMENSIONS.values() if spec.is_contextual
)


def all_referenced_detectors() -> set[str]:
    """Every detector name referenced by any dimension — used by tests to
    guard against typos that would silently zero out a dimension."""
    names: set[str] = set()
    for spec in INTELLIGENCE_DIMENSIONS.values():
        for contrib in spec.contributions:
            names.add(contrib.detector)
    return names
