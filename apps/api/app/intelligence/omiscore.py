"""Phase 4 — The OmiScore Engine.

Turns a rule-engine :class:`~app.schemas.ScanResult` (8 detector signals +
aggregate) into the unified, explainable intelligence envelope defined in
:mod:`app.intelligence.schemas`.

Design principles
-----------------
* **Additive over the existing engine.** This does NOT replace
  ``app.detection.scoring.aggregate`` — it reads its output. The rule engine
  remains the source of the per-detector probabilities; OmiScore *composes*
  them into intelligence dimensions. If the ML scorer has already re-ranked
  the scan, OmiScore consumes the re-ranked signals transparently.
* **Every number is traceable.** Each dimension records which detectors fed
  it, their confidence-weighted share, and the evidence strings behind them.
* **Graceful degradation.** A detector that didn't run contributes nothing;
  a dimension with no contributing detectors reports score 0 at confidence 0
  rather than a misleading neutral 50.
* **Extensible.** All threat types come from the registry in
  :mod:`app.intelligence.signals`. Adding a dimension or re-pointing a
  detector needs no change here.

The math, per dimension
-----------------------
For each contribution ``(detector d, weight w, invert?)``:

    p_d   = signal.probability  (1 - probability if inverted)
    c_d   = signal.confidence
    eff_d = w * c_d                      # confidence-weighted weight

    dimension_score = Σ(p_d * eff_d) / Σ(eff_d)        # 0..1
    dimension_conf  = Σ(eff_d) / Σ(w)                  # 0..1, "how much of
                                                       #  the intended evidence
                                                       #  actually showed up"

The composite ``omi_score`` is a confidence-weighted blend of the threat
dimensions, nudged by the rule engine's own aggregate so the two never
diverge wildly (the aggregate already encodes the convergence bonus and the
single-signal cap, which are valuable cross-checks).
"""

from __future__ import annotations

from app.intelligence.schemas import (
    DimensionContribution,
    IntelligenceDimension,
    OmiScore,
)
from app.intelligence.signals import (
    INTELLIGENCE_DIMENSIONS,
    OMISCORE_SCHEMA_VERSION,
    THREAT_DIMENSIONS,
    DimensionSpec,
)
from app.schemas import ScanResult, SignalResult

# Risk-level cutoffs on the composite omi_score (0–100). Aligned with the
# rule engine's tier cutoffs (LOW <25, MODERATE <50, ELEVATED <75, HIGH) but
# collapsed to the 3-level public contract: moderate+elevated → "medium".
_RISK_MEDIUM_CUTOFF = 35.0
_RISK_HIGH_CUTOFF = 65.0

# How much the rule engine's own aggregate probability nudges the composite.
# The dimension blend leads; the aggregate is a corroborating cross-check that
# carries the convergence bonus / single-signal cap the registry doesn't see.
_AGGREGATE_NUDGE = 0.25


def _score_dimension(spec: DimensionSpec, by_name: dict[str, SignalResult]) -> IntelligenceDimension:
    """Compute one dimension's 0–100 score + its evidence trail."""
    eff_sum = 0.0
    weighted_p = 0.0
    weight_sum = 0.0
    raw_contribs: list[tuple[SignalResult, float, float, bool]] = []  # (sig, eff, p_dir, invert)

    for contrib in spec.contributions:
        weight_sum += contrib.weight
        sig = by_name.get(contrib.detector)
        if sig is None or sig.confidence <= 0.0:
            continue
        p_dir = (1.0 - sig.probability) if contrib.invert else sig.probability
        eff = contrib.weight * sig.confidence
        eff_sum += eff
        weighted_p += p_dir * eff
        raw_contribs.append((sig, eff, p_dir, contrib.invert))

    score01 = (weighted_p / eff_sum) if eff_sum > 0 else 0.0
    # Confidence: of the evidence we *wanted* (sum of weights), how much
    # actually arrived with confidence behind it.
    dim_conf = (eff_sum / weight_sum) if weight_sum > 0 else 0.0

    contributions: list[DimensionContribution] = []
    for sig, eff, p_dir, _invert in raw_contribs:
        label = _detector_label(sig.name)
        contributions.append(DimensionContribution(
            detector=sig.name,
            label=label,
            contribution_probability=_clip01(p_dir),
            confidence=_clip01(sig.confidence),
            weight_share=_clip01(eff / eff_sum) if eff_sum > 0 else 0.0,
            evidence=list(sig.evidence[:3]),
        ))
    # Strongest contributor first.
    contributions.sort(key=lambda c: c.weight_share, reverse=True)

    return IntelligenceDimension(
        key=spec.key,
        label=spec.label,
        description=spec.description,
        score=round(score01 * 100.0, 1),
        confidence=round(dim_conf, 4),
        is_risk=spec.is_risk,
        is_contextual=spec.is_contextual,
        contributions=contributions,
    )


def compute_omiscore(scan: ScanResult) -> OmiScore:
    """Compose a :class:`ScanResult` into the unified OmiScore envelope."""
    by_name: dict[str, SignalResult] = {s.name: s for s in scan.signals}

    dimensions: list[IntelligenceDimension] = [
        _score_dimension(spec, by_name) for spec in INTELLIGENCE_DIMENSIONS.values()
    ]
    dim_by_key = {d.key: d for d in dimensions}

    # ---- Composite omi_score ----
    # Confidence-weighted blend of the threat dimensions (so a high but
    # low-confidence dimension doesn't dominate), nudged toward the rule
    # engine's own aggregate.
    threat_dims = [dim_by_key[k] for k in THREAT_DIMENSIONS if k in dim_by_key]
    num = sum(d.score * d.confidence for d in threat_dims)
    den = sum(d.confidence for d in threat_dims)
    dim_blend = (num / den) if den > 0 else 0.0  # 0..100

    aggregate_component = _clip01(scan.overall_probability) * 100.0
    omi_score = (1 - _AGGREGATE_NUDGE) * dim_blend + _AGGREGATE_NUDGE * aggregate_component
    omi_score = round(_clip(omi_score, 0.0, 100.0), 1)

    risk_level = _risk_level_for(omi_score)

    # Primary threat = highest-scoring threat dimension that's actually
    # concerning (score above the medium cutoff) and has some confidence.
    primary = max(
        (d for d in threat_dims if d.score >= _RISK_MEDIUM_CUTOFF and d.confidence > 0.05),
        key=lambda d: d.score * d.confidence,
        default=None,
    )

    # Authenticity (trust-framed): reported 0–100 where high = organic.
    auth_dim = dim_by_key.get("authenticity_score")
    authenticity = auth_dim.score if auth_dim else round((1.0 - _clip01(scan.overall_probability)) * 100.0, 1)

    overall_conf = round(_clip01(scan.confidence), 4)
    headline = _headline(omi_score, risk_level, primary, authenticity)
    top_evidence = _top_evidence(threat_dims)

    return OmiScore(
        schema_version=OMISCORE_SCHEMA_VERSION,
        omi_score=omi_score,
        authenticity_score=authenticity,
        coordination_probability=dim_by_key["coordination_probability"].score,
        amplification_probability=dim_by_key["amplification_probability"].score,
        spam_probability=dim_by_key["spam_probability"].score,
        ai_generation_probability=dim_by_key["ai_generation_probability"].score,
        risk_level=risk_level,
        confidence=overall_conf,
        subject=scan.subject,
        headline=headline,
        primary_threat=primary.key if primary else None,
        dimensions=dimensions,
        top_evidence=top_evidence,
    )


# ---------------------------------------------------------------------------
# Presentation helpers
# ---------------------------------------------------------------------------

_DETECTOR_LABELS: dict[str, str] = {
    "temporal": "Posting cadence",
    "semantic": "Content repetition",
    "ai_writing": "AI-writing patterns",
    "voice": "Personal voice",
    "engagement": "Engagement patterns",
    "profile": "Profile shape",
    "memory": "Fingerprint match",
    "coordination": "Cross-account coordination",
}


def _detector_label(name: str) -> str:
    return _DETECTOR_LABELS.get(name, name.replace("_", " ").title())


_RISK_PHRASE = {
    "low": "low risk",
    "medium": "medium risk",
    "high": "high risk",
}


def _headline(omi_score: float, risk: str, primary, authenticity: float) -> str:
    if risk == "low":
        return (
            f"OmiScore {omi_score:.0f}/100 — {authenticity:.0f}/100 authenticity. "
            "Behavior looks largely organic."
        )
    primary_label = primary.label.lower() if primary is not None else "mixed signals"
    return (
        f"OmiScore {omi_score:.0f}/100 ({_RISK_PHRASE[risk]}). "
        f"Primary concern: {primary_label}."
    )


def _top_evidence(threat_dims: list[IntelligenceDimension]) -> list[str]:
    """Flatten + dedupe the strongest evidence across threat dimensions."""
    ranked: list[tuple[float, str]] = []
    seen: set[str] = set()
    for dim in threat_dims:
        for contrib in dim.contributions:
            for ev in contrib.evidence:
                if ev in seen:
                    continue
                seen.add(ev)
                # Rank by the dimension score × contributor share it came with.
                ranked.append((dim.score * contrib.weight_share, ev))
    ranked.sort(key=lambda t: t[0], reverse=True)
    return [ev for _score, ev in ranked[:6]]


def _risk_level_for(omi_score: float) -> str:
    if omi_score >= _RISK_HIGH_CUTOFF:
        return "high"
    if omi_score >= _RISK_MEDIUM_CUTOFF:
        return "medium"
    return "low"


def _clip01(x: float) -> float:
    return max(0.0, min(1.0, float(x)))


def _clip(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, float(x)))
