"""CI gate for the member-level elevation measurement (PHASE4_REPORT.md).

Pins, on a fast deterministic fixture, the two properties the report's real-data
numbers rest on, using the SAME measurement code the report run uses
(``measure_rows`` -> production ``apply_coordination`` vs the faithful pre-fix
"ungated" arm):

1. A lone supporting detector (``style_match``) could elevate a member pre-fix;
   under the production gate it cannot — the member-level FPR mechanism.
2. A discriminative detector (``fingerprint_cluster``) elevates identically in
   both arms — coordination rescue is preserved, not traded away.
"""

from __future__ import annotations

from app.detection.coordination._types import CoordinationCluster
from app.detection.scoring import aggregate
from app.evaluation.member_elevation import (
    MemberElevationRow,
    measure_rows,
    summarize,
)
from app.schemas import SignalResult, Tier


def _low_base():
    """A sparse-ish organic-looking standalone scan (MODERATE, well below
    ELEVATED) — the population the elevation gate protects."""
    return aggregate([
        SignalResult(name="temporal", probability=0.2, confidence=0.4),
        SignalResult(name="semantic", probability=0.3, confidence=0.3),
        SignalResult(name="profile", probability=0.25, confidence=0.5),
    ])


def _cluster(method: str, score: float = 0.85):
    return CoordinationCluster(method=method, members=["a"], score=score,
                               evidence=[f"{method} evidence"])


def test_style_only_cluster_no_longer_elevates_but_used_to():
    base = _low_base()
    assert base.tier not in (Tier.ELEVATED, Tier.HIGH)

    rows = measure_rows({"a": base}, [_cluster("style_match")], {"a": "organic"})
    r = rows[0]
    assert r.in_cluster and r.methods == ("style_match",)
    # Pre-fix: the lone supporting cluster elevated the member (the 0.73-FPR harm).
    assert r.ungated_tier in (Tier.ELEVATED, Tier.HIGH)
    # Production gate: capped — never crosses ELEVATED off one supporting lens.
    assert r.gated_tier not in (Tier.ELEVATED, Tier.HIGH)
    assert r.gated_p < r.ungated_p


def test_discriminative_cluster_elevates_identically_in_both_arms():
    """Rescue preserved: for a corroborated member the gate is a no-op, so the
    gated and ungated arms compose the identical signal."""
    base = _low_base()
    rows = measure_rows({"a": base}, [_cluster("fingerprint_cluster", 0.9)], {"a": "bot"})
    r = rows[0]
    assert r.gated_p == r.ungated_p
    assert r.gated_tier == r.ungated_tier
    assert r.gated_tier in (Tier.ELEVATED, Tier.HIGH)  # the lift still happens


def test_no_cluster_member_is_untouched_in_both_arms():
    base = _low_base()
    rows = measure_rows({"a": base}, [], {"a": "organic"})
    r = rows[0]
    assert not r.in_cluster
    assert r.gated_p == r.standalone_p == r.ungated_p
    assert r.gated_tier == r.standalone_tier == r.ungated_tier


def test_summarize_reports_induced_elevation_separately_from_membership():
    """The report's headline split: membership (clustering, unchanged by the
    gate) vs INDUCED elevation (the harm/rescue number)."""
    base = _low_base()
    clusters = [CoordinationCluster(method="style_match", members=["a", "b"],
                                    score=0.85, evidence=["style"])]
    rows = measure_rows({"a": base, "b": base, "c": base}, clusters,
                        {"a": "organic", "b": "organic", "c": "organic"})
    s = summarize(rows)
    assert s["n"] == 3
    assert s["membership_rate"] == round(2 / 3, 3)   # clustering still visible
    assert s["standalone_elevated"] == 0.0
    assert s["induced_gated"] == 0.0                  # gate: no organic lifted
    assert s["induced_ungated"] == round(2 / 3, 3)    # pre-fix: both lifted
    assert s["elevated_gated"] == 0.0
    assert s["elevated_ungated"] == round(2 / 3, 3)


def test_summarize_handles_empty():
    assert summarize([]) == {"n": 0}


def test_borderline_base_is_held_at_moderate_by_the_boundary_hold():
    """Phase 5: the exact Phase-4 residual population — borderline-MODERATE
    standalone + style_match-only cluster. Pre-fix (ungated arm) crosses to
    ELEVATED; production now holds at MODERATE via the boundary hold, so the
    measured induced-elevation FPR on this population is the hold's effect."""
    borderline = aggregate([
        SignalResult(name="temporal", probability=0.5, confidence=0.4),
        SignalResult(name="semantic", probability=0.45, confidence=0.35),
    ])
    assert borderline.tier is Tier.MODERATE
    rows = measure_rows({"a": borderline}, [_cluster("style_match")], {"a": "organic"})
    r = rows[0]
    assert r.ungated_tier in (Tier.ELEVATED, Tier.HIGH)   # the old harm
    assert r.gated_tier is Tier.MODERATE                  # held in production
    assert r.gated_p <= 0.49
