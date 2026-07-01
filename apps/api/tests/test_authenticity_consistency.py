"""Authenticity-consistent coordination reasoning — the Sprint 020 intelligence improvement.

Evidence (the expanded Gold Corpus) showed the weakest investigative capability was distinguishing
ORGANIC / legitimate coordination from HOSTILE coordination: the ``coordination_label`` was computed
purely from method presence, decoupled from the engine's authenticity read — so a likely-authentic
organic viral event (genuine community co-engagement) was labeled ``suspicious``, a false positive.

The fix keeps the coordination read CONSISTENT with the verdict: a discriminative method is
``suspicious`` only when the final verdict is hostile (``likely_inauthentic``); otherwise ``mixed``.
Deterministic, lowers-never-raises (constitutional), no OmiScore / Governor / schema / API change.

These tests lock the expanded corpus, the precision win (control FPR 0.6 → 0.0), recall preservation
(hostile coordination still suspicious), and verdict/label consistency.
"""
from __future__ import annotations

from app.evidence import Binder
from app.governor import Governor
from app.reasoning.evaluation import default_gold_corpus, evaluate_corpus
from app.reasoning.evaluation.corpus import _is_false_positive
from app.reasoning.orchestrator.modules import build_ruling_assessment

_HOSTILE = {"suspicious", "coordinated", "manipulation_network"}


def _read(payload: dict) -> dict:
    return build_ruling_assessment(Binder().bind(payload, grain="comment_section", subject_ref="x", platform="youtube"))


def _coord(method: str, *, prob: float, tier: str, conf: float = 0.6, extra=None) -> dict:
    return {"overall_probability": prob, "overall_tier": tier, "confidence": conf,
            "contributions": extra or [{"name": "community", "impact": 0.3, "direction": "lowers"}],
            "video": {"clusters": [{"method": method, "members": ["@a", "@b", "@c", "@d"]}]}}


# --------------------------------------------------------------------------- #
# The expanded Gold Corpus
# --------------------------------------------------------------------------- #
def test_gold_corpus_spans_the_stress_categories():
    corpus = default_gold_corpus()
    assert len(corpus) >= 10 and len(corpus.controls()) >= 4          # statistically meaningful
    ids = {c.id for c in corpus.all()}
    for needed in ("hostile_fingerprint_ring", "organic_viral_coengage", "ai_assisted_authentic",
                   "misinfo_campaign_cotag", "ambiguous_thin_data", "legit_community_rally"):
        assert needed in ids


# --------------------------------------------------------------------------- #
# The capability — coordination read is consistent with the authenticity read
# --------------------------------------------------------------------------- #
def test_organic_viral_coordination_is_not_suspicious():
    """A likely-authentic organic viral event (genuine co-engagement) must NOT be labeled hostile."""
    a = _read(_coord("co_engagement", prob=0.12, tier="low"))
    assert a["verdict"] == "likely_authentic"
    assert a["coordination_label"] == "mixed"                         # was 'suspicious' (a false positive)
    assert not _is_false_positive(a)


def test_mixed_subject_coordination_is_not_suspicious():
    a = _read(_coord("co_engagement", prob=0.46, tier="moderate",
                     extra=[{"name": "temporal", "impact": 0.3, "direction": "raises"},
                            {"name": "community", "impact": 0.3, "direction": "lowers"}]))
    assert a["verdict"] == "mixed" and a["coordination_label"] == "mixed"
    assert not _is_false_positive(a)


def test_hostile_coordination_still_suspicious_recall_preserved():
    a = _read(_coord("fingerprint_cluster", prob=0.86, tier="high",
                     extra=[{"name": "temporal", "impact": 0.5, "direction": "raises"}]))
    assert a["verdict"] == "likely_inauthentic" and a["coordination_label"] == "suspicious"


def test_coordination_label_never_contradicts_the_verdict():
    """Invariant across the whole corpus: 'suspicious' only ever co-occurs with a hostile verdict."""
    for case in default_gold_corpus().all():
        a = _read(case.payload)
        if a["coordination_label"] in _HOSTILE:
            assert a["verdict"] == "likely_inauthentic", case.id


# --------------------------------------------------------------------------- #
# Benchmark — before/after on the expanded corpus
# --------------------------------------------------------------------------- #
def test_benchmark_control_fpr_drops_to_zero_recall_preserved():
    out = evaluate_corpus(default_gold_corpus())
    s = out["summary"]
    assert s["controls"] >= 4
    assert s["production_control_fpr"] == 0.0          # was 0.6 before the fix (3/5 controls flagged)
    assert s["number_preserved_rate"] == 1.0           # OmiScore untouched
    # recall: every hostile-coordination case is still labeled suspicious.
    hostile = [r for r in out["cases"] if r["production_label_agreement"].get("coordination_match") is not None]
    assert hostile and all(r["production_label_agreement"]["coordination_match"] for r in hostile)


# --------------------------------------------------------------------------- #
# Constitutional safety — number echoed, Governor permits
# --------------------------------------------------------------------------- #
def test_number_echoed_and_governor_permits():
    payload = _coord("co_engagement", prob=0.12, tier="low")
    bundle = Binder().bind(payload, grain="comment_section", subject_ref="x", platform="youtube")
    a = build_ruling_assessment(bundle)
    assert a["suspicion_probability"] == 0.12 and a["suspicion_tier"] == "low"   # OmiScore intact
    assert Governor().validate(a, bundle, corroboration=a["corroboration"]).permitted is True
