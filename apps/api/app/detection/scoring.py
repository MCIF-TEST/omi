"""Calibrated aggregation of detector outputs.

Each detector returns ``SignalResult(probability, confidence, evidence)``. We
combine them in **log-odds space**, shifting the posterior away from a
configured prior by an amount proportional to each signal's confidence and
its detector weight. This:

* never collapses to a binary verdict,
* preserves a meaningful "no idea" output when confidence is low,
* makes weights easy to interpret (a weight of 1.0 means "trust this
  detector as much as a calibrated likelihood ratio").

We map the final probability into qualitative tiers for the UI, but the
numeric probability + evidence are always carried alongside.
"""

from __future__ import annotations

import math

from app.core.config import Settings, get_settings
from app.detection.correlation import (
    CORRELATION_GROUPS,
    get_correlation_model,
    static_axis_of,
)
from app.schemas import (
    DetectorContribution,
    ScanResult,
    ScoreBreakdown,
    SignalResult,
    Tier,
)

# Re-exported for backward compatibility: the independence-axis helper under the
# default group model. Internally the aggregator uses the *active* correlation
# model (which may be the learned one), but callers/tests importing ``_axis_of``
# get the stable default semantics.
_axis_of = static_axis_of

# ---------------------------------------------------------------------------
# Supplemental detectors (GAP-03)
#
# A supplemental detector is computed and surfaced for *context*, but is
# structurally excluded from every path that produces or escalates a suspicion
# verdict: the weighted log-odds sum, the convergence bonus, the single-axis
# HIGH cap, intent inference, the "why flagged" reasons, and the weak-signal
# confidence penalty.
#
# ``ai_writing`` is supplemental because AI-assisted phrasing is not evidence
# of inauthenticity. Stylometric "AI tells" (low burstiness, hedging boilerplate,
# em-dashes, templated openings) are produced just as readily by ESL writers,
# formal/professional writers, and the very large population of legitimate users
# who run their text through Grammarly or an LLM. Letting it drive suspicion
# manufactures false positives against exactly those groups. We keep the signal
# visible (it is genuinely useful to know that text reads as AI-assisted) but it
# can never, on its own or in combination, raise an account's risk tier.
SUPPLEMENTAL_DETECTORS: frozenset[str] = frozenset({"ai_writing"})

# Downward-only detectors (GAP-07): they can subtract suspicion but never add it,
# and their *silence* on an unremarkable account is meaningful — not a data
# deficiency. So they are excluded from weak-signal flagging (a quiet community
# detector doesn't mean "low-confidence scan") while still participating fully in
# the log-odds aggregation.
_DOWNWARD_DETECTORS: frozenset[str] = frozenset({"community"})

# Keep the name importable for any external reference.
__all__ = [
    "aggregate",
    "CORRELATION_GROUPS",
    "SUPPLEMENTAL_DETECTORS",
    "_axis_of",
    "_redundancy_factors",
]


def _redundancy_factors(
    signals: list[SignalResult],
    weights: dict[str, float],
    settings: Settings,
    prior_logit: float,
) -> tuple[dict[str, float], list[str]]:
    """Per-detector contribution multiplier in [0, 1], plus plain-language notes.

    Delegates to the active correlation model: the default group model (each
    additional member of a correlated group discounted by a compounding
    redundancy factor) when no learned artifact exists, or the fitted matrix
    model (continuous discount from measured pairwise correlation) when it does.
    """
    model = get_correlation_model(settings)
    return model.compute_factors(signals, weights, prior_logit)


def aggregate(signals: list[SignalResult], settings: Settings | None = None) -> ScanResult:
    settings = settings or get_settings()
    weights = {
        "temporal": settings.weight_temporal,
        "semantic": settings.weight_semantic,
        "ai_writing": settings.weight_ai_writing,
        "profile": settings.weight_profile,
        "memory": settings.weight_memory,
        "voice": settings.weight_voice,
        "engagement": settings.weight_engagement,
        "coordination": settings.weight_coordination,
        "narrative": settings.weight_narrative,
        "community": settings.weight_community,
    }

    prior = settings.prior_probability
    prior_logit = _logit(prior)
    posterior_logit = prior_logit
    effective_weight_sum = 0.0
    adjustments: list[str] = []

    # Stamp supplemental signals so downstream consumers (UI, exports) know they
    # are contextual and were not counted toward suspicion. They still ride along
    # in ``signals`` with their real probability/confidence for display.
    for sig in signals:
        if sig.name in SUPPLEMENTAL_DETECTORS:
            sig.supplemental = True

    # The signals that actually participate in scoring — supplemental detectors
    # are removed up-front so they cannot influence the composite through any
    # path (sum, convergence, cap, confidence). This is the authoritative
    # exclusion; the zero weight in Settings is only a mechanical backstop.
    scored_signals = [s for s in signals if s.name not in SUPPLEMENTAL_DETECTORS]

    # Active correlation model: learned matrix when an artifact exists, else the
    # hand-tuned default groups. Drives both the redundancy discount and the
    # independence-axis assignment used by the convergence bonus / single-axis cap.
    model = get_correlation_model(settings)
    axis_of = model.axis_of

    # Decorrelate: discount redundant members of each correlated detector group
    # before combining, so shared evidence isn't double-counted.
    factors, decorr_notes = model.compute_factors(scored_signals, weights, prior_logit)
    adjustments.extend(decorr_notes)

    # Per-detector deltas, captured for the faithful contribution breakdown
    # (GAP-06). ``deltas[name]`` is the exact signed log-odds this detector added
    # to the posterior — the same number that builds the score, so the breakdown
    # reconstructs the headline rather than narrating it after the fact.
    deltas: dict[str, float] = {}
    for sig in scored_signals:
        if sig.confidence <= 0:
            continue
        w = weights.get(sig.name, 0.0)
        if w <= 0:
            continue
        # Bound the per-signal probability so we don't get infinite logits.
        p = min(0.98, max(0.02, sig.probability))
        factor = factors.get(sig.name, 1.0)
        effective = sig.confidence * w * factor
        delta = (_logit(p) - prior_logit) * effective
        posterior_logit += delta
        effective_weight_sum += effective
        deltas[sig.name] = delta

    detector_logit_sum = posterior_logit - prior_logit

    # ----- Convergence bonus -----
    # When detectors from *distinct independence axes* agree at high
    # probability with meaningful confidence, the joint evidence is much
    # stronger than any single signal. We count axes, not raw detectors, so a
    # cluster of correlated detectors (e.g. temporal+engagement+coordination)
    # can't masquerade as broad independent corroboration.
    strong = [s for s in scored_signals
              if s.probability > 0.60 and s.confidence > 0.30
              and weights.get(s.name, 0.0) > 0]
    strong_axes = {axis_of(s.name) for s in strong}
    convergence_bonus = 0.0
    if len(strong_axes) >= 3:
        convergence_bonus = 0.45 * (len(strong_axes) - 2)
        posterior_logit += convergence_bonus
        adjustments.append(
            f"Convergence bonus: {len(strong_axes)} independent signal axes "
            f"agree, which is stronger evidence than any one detector alone."
        )

    posterior_logit_final = posterior_logit
    overall = _sigmoid(posterior_logit)

    # ----- Single-signal cap -----
    # No single independence axis — no matter how confident — should be able to
    # trigger a HIGH verdict on its own. HIGH requires corroboration from at
    # least one *other independent* axis (two correlated detectors do not
    # count). Cap at the ELEVATED ceiling.
    confident = [s for s in scored_signals
                 if s.confidence > 0.30 and s.probability > 0.40
                 and weights.get(s.name, 0.0) > 0]
    confident_axes = {axis_of(s.name) for s in confident}
    single_axis_capped = False
    if len(confident_axes) <= 1 and overall >= 0.75:
        overall = 0.74
        single_axis_capped = True
        adjustments.append(
            "Capped below HIGH: only one independent signal axis had enough "
            "data, so there is no cross-detector corroboration to justify HIGH."
        )

    # Confidence: how much weighted evidence backed the estimate, normalised so
    # that ~all detectors firing at full confidence with their nominal weights
    # gives ~1.0. Uses the *decorrelated* effective weight, so correlated
    # detectors don't inflate reported confidence either.
    nominal_max = sum(weights.values())
    confidence = min(1.0, effective_weight_sum / nominal_max) if nominal_max > 0 else 0.0

    tier = _tier_for(overall)
    summary = _summarize(overall, tier, confidence, signals)
    intent_code, intent_label = _infer_intent(signals, tier)
    reasons = _extract_reasons(signals, tier)
    weak_signals = _detect_weak_signals(signals, weights)

    contributions = _build_contributions(signals, weights, factors, deltas)
    score_breakdown = ScoreBreakdown(
        prior_probability=prior,
        prior_logit=prior_logit,
        detector_logit_sum=detector_logit_sum,
        convergence_bonus_logit=convergence_bonus,
        posterior_logit=posterior_logit_final,
        single_axis_capped=single_axis_capped,
        final_probability=overall,
    )

    return ScanResult(
        overall_probability=overall,
        confidence=confidence,
        tier=tier,
        signals=signals,
        summary=summary,
        suspected_intent=intent_code,
        intent_label=intent_label,
        reasons=reasons,
        weak_signals=weak_signals,
        score_adjustments=adjustments,
        contributions=contributions,
        score_breakdown=score_breakdown,
    )


# ---------------------------------------------------------------------------
# Weak-signal flagging
#
# A detector is "weak" when it produced a result but with too little data to
# be trustworthy. Surfacing these gives the UI a clean way to say "this scan
# was low-confidence because we didn't have enough posts" instead of just
# burying the issue in the summary.
# ---------------------------------------------------------------------------

# Map detector name -> human-readable reason it would be weak.
_WEAK_REASON: dict[str, str] = {
    "temporal":   "Too few posts to establish a cadence pattern (need ~30+).",
    "semantic":   "Too few posts to detect repetition or templates (need ~20+).",
    "ai_writing": "Not enough text to estimate burstiness or AI tells (need ~600 words).",
    "profile":    "Profile metadata is missing or sparse.",
    "voice":      "Not enough text to estimate first-person rate (need ~800 words).",
    "engagement": "Too few posts to detect engagement-spam patterns (need ~20+).",
    "memory":     "Fingerprint database has no close neighbors yet — scan more accounts to train it.",
    "coordination": "No cross-account signal — this account wasn't scanned with peers.",
    "narrative":  "Too few posts for narrative-injection pattern analysis (need ~3+).",
}


def _detect_weak_signals(
    signals: list[SignalResult], weights: dict[str, float]
) -> list[str]:
    """Return list of plain-language reasons why this scan is low-confidence.

    A detector contributes a weak-signal flag when:
    * Its weight is positive (we'd otherwise use it), AND
    * Its reported confidence is below 0.25.
    """
    flags: list[str] = []
    by_name = {s.name: s for s in signals}
    for name, w in weights.items():
        if w <= 0 or name in SUPPLEMENTAL_DETECTORS or name in _DOWNWARD_DETECTORS:
            continue
        sig = by_name.get(name)
        if sig is None or sig.confidence < 0.25:
            reason = _WEAK_REASON.get(name, f"Not enough data for the {name} detector.")
            flags.append(reason)
    return flags


def _logit(p: float) -> float:
    p = min(0.999, max(0.001, p))
    return math.log(p / (1 - p))


def _sigmoid(x: float) -> float:
    if x >= 0:
        z = math.exp(-x)
        return 1.0 / (1.0 + z)
    z = math.exp(x)
    return z / (1.0 + z)


def _tier_for(p: float) -> Tier:
    if p < 0.25:
        return Tier.LOW
    if p < 0.50:
        return Tier.MODERATE
    if p < 0.75:
        return Tier.ELEVATED
    return Tier.HIGH


_INTENT_LABELS: dict[str, str] = {
    "ai_content": "AI-generated content posting",
    "engagement_farming": "Engagement farming (likes/subs/follow farming)",
    "spam_promotion": "Spam / affiliate / link promotion",
    "coordinated_campaign": "Coordinated inauthentic behavior (likely campaign)",
    "sockpuppet_cohort": "Fresh-account cohort (potential sockpuppets)",
    "copy_paste_template": "Templated / copy-paste activity",
    "broadcast_persona": "Broadcast-style persona (low personal voice)",
    "multi_vector": "Multi-vector bot (combined spam + AI + coordination)",
    "unclear": "Unclear — patterns are mixed",
}


def _infer_intent(signals: list[SignalResult], tier: Tier) -> tuple[str | None, str | None]:
    """Map detector results to a plain-language guess at the account's intent.

    Returns ``(code, label)`` or ``(None, None)`` when the tier is too low to
    warrant a guess. The output is deliberately probabilistic phrasing applied
    to a likely *category*, not an accusation.
    """
    if tier == Tier.LOW:
        return None, None

    # Supplemental detectors (ai_writing) never imply an inauthentic *intent* —
    # exclude them so intent inference reads only the scored evidence.
    by_name = {s.name: s for s in signals if s.name not in SUPPLEMENTAL_DETECTORS}

    def strong(name: str, min_p: float = 0.55, min_c: float = 0.25) -> bool:
        s = by_name.get(name)
        return s is not None and s.probability >= min_p and s.confidence >= min_c

    strong_signals = {n for n in by_name if strong(n)}

    # Multi-vector: 3+ different strong detectors covering distinct angles
    diversity = {
        "content": strong_signals & {"semantic"},
        "engagement": strong_signals & {"engagement"},
        "coord": strong_signals & {"coordination", "memory"},
        "behavioral": strong_signals & {"temporal", "voice", "profile"},
    }
    distinct_axes = sum(1 for v in diversity.values() if v)
    if distinct_axes >= 3:
        return "multi_vector", _INTENT_LABELS["multi_vector"]

    # Coordination or narrative injection evidence → campaign
    if strong("coordination") or strong("narrative"):
        return "coordinated_campaign", _INTENT_LABELS["coordinated_campaign"]

    # Profile cohort + low age signal often indicates sockpuppets
    profile = by_name.get("profile")
    if profile and profile.probability >= 0.6 and profile.confidence >= 0.3:
        evidence_blob = " ".join(profile.evidence).lower()
        if any(k in evidence_blob for k in ("recent", "young account", "age", "cohort", "follower")):
            return "sockpuppet_cohort", _INTENT_LABELS["sockpuppet_cohort"]

    # Engagement detector → farming vs spam-promotion (URL-heavy)
    eng = by_name.get("engagement")
    if eng and eng.probability >= 0.55 and eng.confidence >= 0.25:
        evidence_blob = " ".join(eng.evidence).lower()
        if any(k in evidence_blob for k in ("url", "link", "http", "promo", ".com")):
            return "spam_promotion", _INTENT_LABELS["spam_promotion"]
        return "engagement_farming", _INTENT_LABELS["engagement_farming"]

    # NOTE: ai_writing is supplemental (GAP-03) and is intentionally NOT an
    # intent driver — AI-assisted phrasing is not evidence of inauthentic intent.

    # Semantic detector (repetition/templates) dominates → copy-paste
    if strong("semantic"):
        return "copy_paste_template", _INTENT_LABELS["copy_paste_template"]

    # Voice detector flagged broadcast persona (low first-person)
    if strong("voice"):
        return "broadcast_persona", _INTENT_LABELS["broadcast_persona"]

    return "unclear", _INTENT_LABELS["unclear"]


# Map detector names → human-readable phrases that say WHY a signal contributed.
_DETECTOR_HEADLINES: dict[str, str] = {
    "temporal": "Posting cadence looks mechanical (not human-paced)",
    "semantic": "Comments repeat themselves or share templates",
    "ai_writing": "Writing style matches AI-generation patterns",
    "profile": "Profile metadata is suspicious (handle, age, or follower shape)",
    "voice": "First-person voice is unusually rare for the text volume",
    "engagement": "Comments show spam / engagement-farming patterns",
    "memory": "Behavioral fingerprint matches previously-flagged accounts",
    "coordination": "Account appears in a cross-account coordination cluster",
    "narrative": "Posts contain coordinated-narrative / political-astroturf language",
    "community": "Established audience / community footprint (lowers suspicion)",
}


def _build_contributions(
    signals: list[SignalResult],
    weights: dict[str, float],
    factors: dict[str, float],
    deltas: dict[str, float],
) -> list[DetectorContribution]:
    """Assemble the faithful per-detector attribution (GAP-06).

    ``deltas`` holds the exact signed log-odds each scoring detector added to the
    posterior — we surface those verbatim so the breakdown reconstructs the
    headline number. Supplemental detectors (e.g. ai_writing) are included for
    context but with a zero delta and ``supplemental=True``, making explicit that
    they were shown but never scored. ``impact`` is each detector's share of the
    total absolute movement, a sign-agnostic "how much of the picture" value.
    """
    total_abs = sum(abs(d) for d in deltas.values())
    items: list[DetectorContribution] = []
    for sig in signals:
        is_supp = sig.name in SUPPLEMENTAL_DETECTORS
        delta = 0.0 if is_supp else deltas.get(sig.name, 0.0)
        if abs(delta) < 1e-9:
            direction = "neutral"
        elif delta > 0:
            direction = "raises"
        else:
            direction = "lowers"
        impact = (abs(delta) / total_abs) if total_abs > 0 else 0.0
        items.append(
            DetectorContribution(
                name=sig.name,
                headline=_DETECTOR_HEADLINES.get(sig.name, f"Detector '{sig.name}'"),
                probability=sig.probability,
                confidence=sig.confidence,
                weight=weights.get(sig.name, 0.0),
                decorrelation_factor=factors.get(sig.name, 1.0),
                logit_delta=delta,
                impact=impact,
                direction=direction,
                supplemental=is_supp,
                evidence=sig.evidence[0] if sig.evidence else None,
            )
        )
    # Rank by impact (largest mover first); neutral/zero contributions sink to
    # the bottom but are retained so the explanation is complete.
    items.sort(key=lambda c: abs(c.logit_delta), reverse=True)
    return items


def _extract_reasons(signals: list[SignalResult], tier: Tier) -> list[str]:
    """Build a bulleted list of WHY this account got flagged.

    Each entry is one short sentence: the headline reason + the top piece of
    evidence backing it. Only emitted for non-low tiers.
    """
    if tier == Tier.LOW:
        return []
    reasons: list[str] = []
    # Supplemental detectors (ai_writing) are contextual, not grounds for a
    # flag — exclude them so they never appear in the "why flagged" reasons.
    scored = [s for s in signals if s.name not in SUPPLEMENTAL_DETECTORS]
    # Sort: highest contributing detector first (probability × confidence)
    ranked = sorted(
        scored,
        key=lambda s: s.probability * s.confidence,
        reverse=True,
    )
    for s in ranked:
        if s.probability < 0.5 or s.confidence < 0.2:
            continue
        headline = _DETECTOR_HEADLINES.get(s.name, f"Detector '{s.name}' flagged this account")
        ev = s.evidence[0] if s.evidence else None
        if ev:
            reasons.append(f"{headline} — {ev}")
        else:
            reasons.append(headline + ".")
        if len(reasons) >= 6:
            break
    return reasons


def _summarize(prob: float, tier: Tier, confidence: float, signals: list[SignalResult]) -> str:
    """Human-readable, deliberately probabilistic. Never accuses."""
    pct = round(prob * 100)
    conf_pct = round(confidence * 100)

    # Supplemental detectors (ai_writing) are contextual — never list them as
    # "primary contributing signals" in the suspicion summary.
    scored = [s for s in signals if s.name not in SUPPLEMENTAL_DETECTORS]
    strong = [s.name for s in scored if s.confidence > 0.3 and s.probability > 0.6]
    weak_data = [s.name for s in scored if s.confidence < 0.2]

    tier_phrase = {
        Tier.LOW: "low suspicion of synthetic or coordinated behavior",
        Tier.MODERATE: "moderate signs of patterns that warrant a closer look",
        Tier.ELEVATED: "elevated indicators consistent with synthetic or coordinated activity",
        Tier.HIGH: "strong indicators consistent with synthetic or coordinated activity",
    }[tier]

    parts = [
        f"Overall estimate: {pct}% probability of {tier_phrase} "
        f"(scan confidence ~{conf_pct}%)."
    ]
    if strong:
        parts.append("Primary contributing signals: " + ", ".join(strong) + ".")
    if weak_data:
        parts.append(
            "Limited data for: " + ", ".join(weak_data)
            + ". More posts or profile metadata would sharpen this estimate."
        )
    parts.append(
        "This is a probabilistic estimate based on observable patterns, not a "
        "definitive judgement about the account or person behind it."
    )
    return " ".join(parts)
