"""Combine the per-detector coordination findings into one video-level score.

Tier-2B calibration. The first real-world evaluation (state-IO campaigns vs
real-human controls) showed two things about the original confidence-weighted
mean:

1. **Coordination is disjunctive, not conjunctive.** A real operation that
   coordinates through shared infrastructure (``fingerprint``) need not also
   post in synchronized bursts (``temporal_semantic``). A plain mean demands
   *consensus* across every lens, so a campaign that lights up two strong
   detectors but not the others gets averaged back under threshold. The clearest
   victim in the eval: a GRU/IRA group where ``fingerprint`` (0.82) **and**
   ``style`` (0.77) both fired with real clusters, yet ``cohort`` (0.05) and
   ``temporal_semantic`` (0.23, floored) dragged the mean to 0.42 — a miss.

2. **Detectors are not equally discriminative.** Measured separation between
   IO campaigns and human controls: ``fingerprint`` +0.32, ``style`` +0.32,
   ``cohort`` +0.15, ``temporal_semantic`` **−0.24** *on account-history data*
   (it abstains there because account timelines aren't bursts — but on the
   production shape, comment bursts on a single video, it is the canonical
   signal, so it must not be discarded).

The calibration here keeps the consensus view but makes it reliability-aware,
and lifts it with a corroboration view that only ever *adds* evidence:

* ``weighted_mean`` — reliability-prior × data-confidence weighted average of
  every detector's score. The consensus lens, now down-weighting the weak/
  noisy detectors so they dilute less.
* ``corroboration`` — a noisy-OR over each detector's *positive* evidence only
  (the part of its score above the neutral 0.5, scaled by reliability and
  confidence). A detector sitting at its "no-signal" floor contributes **zero**
  here, so a confidently-negative detector can no longer drag the score down;
  two independent strong signatures combine the way real evidence does.

Final ``score = max(weighted_mean, corroboration)``. Both views are
dilution-resistant; the OR carries the disjunctive cases, the mean carries the
broad-but-moderate cases. Crucially, the positive-evidence gate means this is
*not* overfit to the eval's data shape: ``temporal_semantic`` keeps full
reliability for production video-comment data, but its account-history floor
can no longer pull a real campaign under threshold.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.detection.coordination._types import CoordinationFinding

# Per-detector reliability priors, keyed by the detector's ``method`` string.
# Grounded in the Tier-2B evaluation's measured IO-vs-human separation, tempered
# by domain knowledge (a low eval number caused by a data-shape mismatch is not
# the same as a weak detector). fingerprint/style are the proven discriminators;
# co_engagement is strong when engagement data exists; cohort is suggestive but
# noisy; temporal_semantic is kept moderate — it abstains on account histories
# but is the primary signal on the production comment-burst shape, and the
# positive-evidence gate already prevents its floor from diluting anything.
DETECTOR_RELIABILITY: dict[str, float] = {
    "fingerprint_cluster": 1.0,
    "style_match": 1.0,
    "co_engagement": 0.9,
    "co_tag": 1.0,
    "age_cohort": 0.5,
    "temporal_semantic_clique": 0.4,
}
_DEFAULT_RELIABILITY = 0.5

# --- Corroboration gate (Phase 3) ------------------------------------------
# Phase 2 proved the aggregate score could not separate a state campaign from
# unrelated professionals: legitimate humans scored 1.0 because a SINGLE
# non-discriminative detector (style_match) fired and the noisy-OR carried it to
# maximal. The gate fixes that: a maximal verdict requires CORROBORATION —
# either a discriminative lens (one that actually separated IO from humans on
# real data), or two independent detectors agreeing. A lone supporting detector
# can raise suspicion to MODERATE but never to a maximal coordination verdict.
#
# Discriminative (may stand closer to alone): the network + infrastructure lenses
# that measured a real IO-vs-human gap. Supporting (need corroboration):
# style_match (non-discriminative on real text), temporal_semantic (floored on
# account history), age_cohort (sparse/suggestive).
#
# Exported (no leading underscore) because elevate.py applies the SAME
# corroboration rule at the per-member elevation site — these constants must not
# drift between the video verdict and the member verdict.
DISCRIMINATIVE_DETECTORS: frozenset[str] = frozenset({
    "fingerprint_cluster", "co_engagement", "co_tag",
})
EVIDENCE_EPS = 0.05          # a detector "fired" if its positive evidence exceeds this
SUPPORTING_CEILING = 0.49    # top of MODERATE — a lone supporting detector's max

# A detector's score midpoint: 0.5 means "no signal either way". Only the
# portion of a score *above* this counts as positive coordination evidence.
_NEUTRAL = 0.5


@dataclass
class DetectorContribution:
    """What one detector contributed to the final score — for UI attribution
    and for the evaluation harness to explain a result."""

    method: str
    score: float          # detector's overall_score (0..1)
    confidence: float     # detector's self-reported data sufficiency (0..1)
    reliability: float    # static prior applied to this detector
    mean_weight: float    # reliability × confidence (its weight in the mean)
    evidence: float       # positive evidence contributed to the noisy-OR (0..1)


@dataclass
class CoordinationAggregate:
    """The combined coordination verdict for one batch of findings."""

    score: float
    weighted_mean: float
    corroboration: float
    contributions: list[DetectorContribution] = field(default_factory=list)
    # Phase 3 corroboration gate: ``ungated_score`` is the pre-gate value;
    # ``gated`` is True when the verdict was capped for lack of corroboration.
    ungated_score: float = 0.0
    gated: bool = False


def aggregate_coordination(
    findings: list[CoordinationFinding],
) -> CoordinationAggregate:
    """Reduce per-detector findings to a single 0..1 coordination score.

    Empty / all-zero-confidence input yields a score of 0.0. The result also
    carries the full per-detector breakdown so callers can show *why* a batch
    scored the way it did (signed attribution).
    """
    contributions: list[DetectorContribution] = []
    weight_sum = 0.0
    mean_acc = 0.0
    not_or = 1.0  # running product of (1 - evidence_i) for the noisy-OR

    for f in findings:
        if f is None:
            continue
        rel = DETECTOR_RELIABILITY.get(f.method, _DEFAULT_RELIABILITY)
        mean_w = rel * f.confidence
        weight_sum += mean_w
        mean_acc += mean_w * f.overall_score

        # Positive evidence: only the part of the score above neutral, scaled to
        # 0..1, then discounted by reliability and confidence. A floored / below-
        # neutral detector contributes 0 — it cannot dilute the corroboration.
        above = max(0.0, (f.overall_score - _NEUTRAL) / (1.0 - _NEUTRAL))
        evidence = rel * f.confidence * above
        evidence = min(max(evidence, 0.0), 0.999)  # keep the OR strictly < 1
        not_or *= (1.0 - evidence)

        contributions.append(DetectorContribution(
            method=f.method, score=f.overall_score, confidence=f.confidence,
            reliability=rel, mean_weight=mean_w, evidence=evidence,
        ))

    weighted_mean = mean_acc / weight_sum if weight_sum > 0 else 0.0
    corroboration = 1.0 - not_or
    score = max(weighted_mean, corroboration)

    # Corroboration gate: a maximal verdict needs either a discriminative lens or
    # ≥2 independent detectors with positive evidence. A lone supporting detector
    # (e.g. style_match on a set of professional writers) is capped at MODERATE.
    fired = [c for c in contributions if c.evidence > EVIDENCE_EPS]
    has_discriminative = any(c.method in DISCRIMINATIVE_DETECTORS for c in fired)
    corroborated = has_discriminative or len(fired) >= 2
    ungated_score = score
    gated = False
    if not corroborated and score > SUPPORTING_CEILING:
        score = SUPPORTING_CEILING
        gated = True

    return CoordinationAggregate(
        score=score,
        weighted_mean=weighted_mean,
        corroboration=corroboration,
        contributions=contributions,
        ungated_score=ungated_score,
        gated=gated,
    )
