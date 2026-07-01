"""Gold Corpus expansion — the collection framework (AI Readiness — Phase 5).

The permanent design for growing the Gold Corpus with REAL, human-reviewed investigations. This
module invents NO cases; it defines the taxonomy the corpus should span, and, per category, the
required sample size, the ground-truth (provenance) requirements, the evaluation metrics that
matter, a difficulty rating, and the promotion criteria a category must satisfy before its cases
join the standing benchmark (``default_gold_corpus``).

It complements — never duplicates — the evaluation framework: a collected real investigation becomes
a :class:`GoldCase`, is scored by ``evaluate_corpus``, and is admitted only when it clears its
category's promotion gate. Controls (legitimate coordination) are the precision frontier: their gate
is a zero false-positive rate. Content-addressed for drift detection.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.evidence.bundle import digest

CORPUS_DESIGN_VERSION = "v1"

# Provenance standards a case must carry to be admissible ground truth.
GROUND_TRUTH_STANDARDS = {
    "platform_enforcement": "The platform took action (removal, ban, state-actor label) on the subject.",
    "public_attribution": "A published attribution/threat-intel report names the operation.",
    "reviewer_consensus": ">=2 independent human reviewers agree on the label.",
    "account_provenance": "Verified identity/history establishes the group as legitimate.",
    "external_corroboration": "Independent external reporting confirms the read.",
    "temporal_confirmation": "The behavior is confirmed over time or on re-scan.",
}

# Metrics that gate quality. Controls are scored on FPR; hostile on recall; all on agreement.
_M_RECALL = "hostile_recall"                 # coordinated/hostile cases must be flagged
_M_FPR = "control_false_positive_rate"       # legitimate cases must NOT be flagged
_M_AGREE = "label_agreement"                 # verdict/coordination-label match to the reviewed label
_M_NUMBER = "number_preserved"               # the engine number is echoed, never moved
_M_COORD = "coordination_label_accuracy"     # correct point on organic->manipulation_network
_M_CALIB = "calibration_appropriateness"     # confidence tracks evidence strength/quantity


@dataclass(frozen=True)
class CorpusCategory:
    """One collection target. ``is_control`` marks legitimate categories (the precision frontier);
    their promotion gate is a zero false-positive rate. Immutable + content-addressed."""

    id: str
    name: str
    description: str
    required_samples: int
    ground_truth: tuple[str, ...]
    metrics: tuple[str, ...]
    difficulty: str                            # easy | moderate | hard | frontier
    is_control: bool
    promotion_criteria: tuple[str, ...]


def _hostile(id, name, desc, n, gt, difficulty, extra_metrics=()):
    return CorpusCategory(
        id=id, name=name, description=desc, required_samples=n, ground_truth=gt,
        metrics=(_M_RECALL, _M_COORD, _M_AGREE, _M_NUMBER) + extra_metrics,
        difficulty=difficulty, is_control=False,
        promotion_criteria=(
            f"collect >={n} cases, each with ground truth from {', '.join(gt)}",
            "measured hostile_recall >= 0.90 on the category",
            "coordination_label_accuracy >= 0.80",
            "number_preserved == 1.0 (engine number never moved)",
            "no case promoted without >=2-reviewer consensus",
        ),
    )


def _control(id, name, desc, n, gt, difficulty, extra_metrics=()):
    return CorpusCategory(
        id=id, name=name, description=desc, required_samples=n, ground_truth=gt,
        metrics=(_M_FPR, _M_AGREE, _M_NUMBER) + extra_metrics,
        difficulty=difficulty, is_control=True,
        promotion_criteria=(
            f"collect >={n} legitimate cases, each with ground truth from {', '.join(gt)}",
            "measured control_false_positive_rate == 0.0 (precision frontier is absolute)",
            "number_preserved == 1.0",
            "no case promoted without account_provenance + >=2-reviewer consensus",
        ),
    )


CORPUS_CATEGORIES: tuple[CorpusCategory, ...] = (
    # --- legitimate / organic (CONTROLS — must never be flagged hostile) --------------------- #
    _control("organic_viral", "Organic viral events",
             "Genuinely viral content with broad, varied, independent participation.",
             20, ("account_provenance", "reviewer_consensus", "external_corroboration"), "moderate",
             extra_metrics=(_M_COORD,)),
    _control("gaming_community", "Gaming communities",
             "Tight-knit gaming audiences that co-engage heavily but authentically.",
             15, ("account_provenance", "reviewer_consensus"), "hard", extra_metrics=(_M_COORD,)),
    _control("brand_community", "Brand communities",
             "Official/fan brand communities that post on-message but legitimately.",
             15, ("account_provenance", "reviewer_consensus"), "hard", extra_metrics=(_M_COORD,)),
    _control("breaking_news", "Breaking news",
             "Synchronized reaction to a real event — organic bursts, broad authorship.",
             15, ("external_corroboration", "reviewer_consensus"), "moderate",
             extra_metrics=(_M_CALIB,)),
    _control("legitimate_activism", "Legitimate activism",
             "Grassroots or organized-but-authentic activism and newsroom on-message posting.",
             20, ("account_provenance", "public_attribution", "reviewer_consensus"), "frontier",
             extra_metrics=(_M_COORD,)),
    _control("false_positive", "Known false positives",
             "Cases the engine or a prior model flagged that human review cleared.",
             20, ("reviewer_consensus", "temporal_confirmation"), "frontier",
             extra_metrics=(_M_COORD, _M_CALIB)),
    # --- hostile / inauthentic (must be flagged — recall) ------------------------------------ #
    _hostile("bot_farm", "Bot farms",
             "Automated account clusters amplifying content with fingerprint/co-engagement links.",
             20, ("platform_enforcement", "public_attribution", "reviewer_consensus"), "easy"),
    _hostile("spam_ring", "Spam rings",
             "Commercial spam clusters posting templated links across many targets.",
             20, ("platform_enforcement", "reviewer_consensus"), "easy"),
    _hostile("crypto_scam", "Crypto scams",
             "Coordinated crypto/financial scam promotion (co-tag, templated shilling).",
             15, ("platform_enforcement", "external_corroboration", "reviewer_consensus"), "moderate"),
    _hostile("sockpuppet", "Sockpuppets",
             "One operator running many personas (fingerprint/style-matched, staggered timing).",
             15, ("public_attribution", "reviewer_consensus", "temporal_confirmation"), "hard"),
    _hostile("astroturf", "Astroturfing",
             "Manufactured 'grassroots' coordination masquerading as organic support.",
             20, ("public_attribution", "reviewer_consensus"), "frontier",
             extra_metrics=(_M_CALIB,)),
    _hostile("influence_operation", "Influence operations",
             "State/organized influence ops with multi-method, cross-narrative coordination.",
             20, ("platform_enforcement", "public_attribution", "external_corroboration"), "frontier",
             extra_metrics=(_M_CALIB,)),
    # --- politically-sensitive + ambiguous --------------------------------------------------- #
    CorpusCategory(
        id="political_campaign", name="Political campaigns",
        description="Political coordination that may be legitimate (official on-message) OR a hostile "
                    "operation — the label must be earned case by case.",
        required_samples=20,
        ground_truth=("public_attribution", "account_provenance", "reviewer_consensus"),
        metrics=(_M_RECALL, _M_FPR, _M_COORD, _M_AGREE, _M_NUMBER, _M_CALIB),
        difficulty="frontier", is_control=False,
        promotion_criteria=(
            "collect >=20 cases balanced between legitimate and hostile political coordination",
            "legitimate members scored as controls: control_false_positive_rate == 0.0",
            "hostile members: hostile_recall >= 0.90",
            "coordination_label_accuracy >= 0.80; number_preserved == 1.0",
            "every case dual-reviewed; provenance recorded for the legitimate/hostile call",
        ),
    ),
    CorpusCategory(
        id="edge_case", name="Edge cases",
        description="Thin-data, single-axis, or genuinely ambiguous investigations where the correct "
                    "output is calibrated uncertainty, not a confident label.",
        required_samples=15,
        ground_truth=("reviewer_consensus", "temporal_confirmation"),
        metrics=(_M_CALIB, _M_AGREE, _M_NUMBER),
        difficulty="frontier", is_control=False,
        promotion_criteria=(
            "collect >=15 ambiguous/thin-data cases",
            "expected read is 'inconclusive'/'mixed' with explicit uncertainty",
            "calibration_appropriateness >= 0.80 (no over-confident labels on thin data)",
            "number_preserved == 1.0; >=2-reviewer consensus on ambiguity",
        ),
    ),
)

CATEGORIES_BY_ID: dict[str, CorpusCategory] = {c.id: c for c in CORPUS_CATEGORIES}


def control_categories() -> list[CorpusCategory]:
    return [c for c in CORPUS_CATEGORIES if c.is_control]


def hostile_categories() -> list[CorpusCategory]:
    return [c for c in CORPUS_CATEGORIES if not c.is_control]


def total_required_samples() -> int:
    return sum(c.required_samples for c in CORPUS_CATEGORIES)


@dataclass(frozen=True)
class CategoryReadiness:
    """The promotion verdict for one category given what has actually been collected + measured."""

    category_id: str
    collected: int
    required: int
    metrics_met: dict
    ready: bool
    blocking: tuple[str, ...]


def evaluate_category_readiness(
    category: CorpusCategory, *, collected: int, measured: dict[str, float] | None = None,
    all_have_ground_truth: bool = False,
) -> CategoryReadiness:
    """Decide whether a category is ready to promote its collected cases into the benchmark.

    Pure + deterministic: given how many real cases were collected, whether each carries admissible
    ground truth, and the measured metrics, it applies the category's gate. Controls require FPR
    == 0; hostile require recall >= 0.90; all require number_preserved == 1.0. Never mutates the
    corpus — promotion stays a human-gated, evidence-backed decision."""
    measured = measured or {}
    blocking: list[str] = []
    if collected < category.required_samples:
        blocking.append(f"insufficient samples: {collected}/{category.required_samples}")
    if not all_have_ground_truth:
        blocking.append(f"missing ground truth (need one of: {', '.join(category.ground_truth)})")

    metrics_met: dict[str, bool] = {}
    if _M_NUMBER in category.metrics:
        ok = measured.get(_M_NUMBER, 0.0) >= 1.0
        metrics_met[_M_NUMBER] = ok
        if not ok:
            blocking.append("number_preserved must be 1.0")
    if category.is_control and _M_FPR in category.metrics:
        ok = measured.get(_M_FPR, 1.0) <= 0.0
        metrics_met[_M_FPR] = ok
        if not ok:
            blocking.append("control_false_positive_rate must be 0.0 (precision frontier)")
    if (not category.is_control) and _M_RECALL in category.metrics:
        ok = measured.get(_M_RECALL, 0.0) >= 0.90
        metrics_met[_M_RECALL] = ok
        if not ok:
            blocking.append("hostile_recall must be >= 0.90")
    if _M_COORD in category.metrics:
        ok = measured.get(_M_COORD, 0.0) >= 0.80
        metrics_met[_M_COORD] = ok
        if not ok:
            blocking.append("coordination_label_accuracy must be >= 0.80")
    if _M_CALIB in category.metrics:
        ok = measured.get(_M_CALIB, 0.0) >= 0.80
        metrics_met[_M_CALIB] = ok
        if not ok:
            blocking.append("calibration_appropriateness must be >= 0.80")

    return CategoryReadiness(
        category_id=category.id, collected=collected, required=category.required_samples,
        metrics_met=metrics_met, ready=not blocking, blocking=tuple(blocking),
    )


def collection_plan() -> dict:
    """A serializable snapshot of the collection target: per-category requirements + totals."""
    return {
        "version": CORPUS_DESIGN_VERSION,
        "total_categories": len(CORPUS_CATEGORIES),
        "control_categories": [c.id for c in control_categories()],
        "hostile_categories": [c.id for c in hostile_categories()],
        "total_required_samples": total_required_samples(),
        "ground_truth_standards": GROUND_TRUTH_STANDARDS,
        "categories": [
            {"id": c.id, "name": c.name, "required_samples": c.required_samples,
             "difficulty": c.difficulty, "is_control": c.is_control,
             "ground_truth": list(c.ground_truth), "metrics": list(c.metrics),
             "promotion_criteria": list(c.promotion_criteria)}
            for c in CORPUS_CATEGORIES
        ],
    }


def corpus_design_hash() -> str:
    """Content address of the whole collection framework — drift-detectable + versionable."""
    return digest(collection_plan(), prefix="cd:")


__all__ = [
    "CORPUS_DESIGN_VERSION", "GROUND_TRUTH_STANDARDS", "CorpusCategory", "CORPUS_CATEGORIES",
    "CATEGORIES_BY_ID", "control_categories", "hostile_categories", "total_required_samples",
    "CategoryReadiness", "evaluate_category_readiness", "collection_plan", "corpus_design_hash",
]
