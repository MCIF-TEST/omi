"""Unit tests for the Constitutional Governor (Sprint 002).

Verifies PERMIT on a faithful ruling, REJECT for each violation class, content-addressed
+ reproducible ValidationTraces, the append-only audit log, and — the Floor-hardening
deliverable — that the REAL deterministic Floor output passes the REAL Governor.
"""
from __future__ import annotations

import pytest

from app.evidence import Binder
from app.governor import AuditLog, Governor


def _payload() -> dict:
    return {
        "overall_probability": 0.72,
        "overall_tier": "elevated",
        "confidence": 0.6,
        "weak_signals": ["only 8 posts — temporal abstained"],
        "single_axis_capped": False,
        "contributions": [
            {"name": "temporal", "impact": 0.5, "logit_delta": 0.8, "direction": "raises"},
            {"name": "community", "impact": 0.2, "logit_delta": -0.3, "direction": "lowers"},
            {"name": "ai_writing", "impact": 0.1, "logit_delta": 0.0,
             "direction": "neutral", "supplemental": True},
        ],
        "video": {
            "clusters": [{"method": "co_engagement", "members": ["@a", "@b", "@c"]}],
            "commenters": [{"handle": "@a", "tier": "high"}],
        },
    }


def _bundle():
    return Binder().bind(_payload(), grain="comment_section", subject_ref="inv1", platform="youtube")


def _valid_ruling(b) -> dict:
    hl = b.headline()
    temporal_id = next(it.id for it in b.evidence.values() if it.originating_detector == "temporal")
    community_id = next(it.id for it in b.evidence.values() if it.originating_detector == "community")
    return {
        "verdict": "mixed",
        "suspicion_tier": hl["tier"],
        "suspicion_probability": hl["overall_probability"],
        "confidence_band": "moderate",
        "confidence_rationale": "moderate confidence; one discriminative method fired.",
        "headline": "Patterns are consistent with elevated, corroborated suspicion.",
        "assessment": "The evidence indicates elevated suspicion, read probabilistically.",
        "evidence_for": [{"signal": "temporal", "claim": "regular cadence",
                          "evidence_refs": [temporal_id]}],
        "evidence_against": [{"signal": "community", "claim": "established footprint",
                              "evidence_refs": [community_id]}],
        "uncertainty": ["only 8 posts available"],
        "what_would_change_this": ["more posts to corroborate the cadence finding"],
        "corroboration": {"discriminative_methods": ["co_engagement"],
                          "single_axis_capped": False, "convergence": True},
        "coordination_label": "suspicious",
        "limits_statement": "Probabilistic; the human analyst sets the verdict.",
    }


# --- PERMIT ----------------------------------------------------------------- #
def test_permits_faithful_ruling():
    b = _bundle()
    t = Governor().validate(_valid_ruling(b), b)
    assert t.verdict == "permit", (t.violation_codes, [s for s in t.stage_results if not s["pass"]])
    assert t.fallback_path == "none"


# --- REJECT (one per violation class) --------------------------------------- #
def test_reject_fabricated_citation():
    b = _bundle(); r = _valid_ruling(b)
    r["evidence_for"][0]["evidence_refs"] = ["ev:9999"]
    assert "fabrication" in Governor().validate(r, b).violation_codes


def test_reject_echo_override():
    b = _bundle(); r = _valid_ruling(b)
    r["suspicion_probability"] = 0.10
    assert "engine_override" in Governor().validate(r, b).violation_codes


def test_reject_gate_breach():
    b = _bundle(); r = _valid_ruling(b)
    r["coordination_label"] = "coordinated"
    r["corroboration"] = {"discriminative_methods": [], "single_axis_capped": False}
    assert "gate_breach" in Governor().validate(r, b).violation_codes


def test_reject_confidence_inflation():
    b = _bundle(); r = _valid_ruling(b)
    r["confidence_band"] = "high"  # engine confidence 0.6 caps at moderate
    assert "confidence_violation" in Governor().validate(r, b).violation_codes


def test_reject_insufficient_must_be_inconclusive():
    b = _bundle(); r = _valid_ruling(b)
    r["confidence_band"] = "insufficient"  # but verdict is "mixed", not "inconclusive"
    assert "confidence_violation" in Governor().validate(r, b).violation_codes


def test_reject_suppressed_counter_evidence():
    b = _bundle(); r = _valid_ruling(b)
    r["evidence_against"] = []
    r["confidence_rationale"] = "moderate confidence"  # no "no exculpatory" justification
    assert "suppressed_counter_evidence" in Governor().validate(r, b).violation_codes


def test_reject_banned_phrase():
    b = _bundle(); r = _valid_ruling(b)
    r["headline"] = "this account is a bot, without a doubt"
    assert "policy_violation" in Governor().validate(r, b).violation_codes


def test_reject_supplemental_as_suspicion():
    b = _bundle(); r = _valid_ruling(b)
    sup_id = next(it.id for it in b.evidence.values() if it.originating_detector == "ai_writing")
    r["evidence_for"].append({"signal": "ai_writing", "claim": "AI phrasing", "evidence_refs": [sup_id]})
    assert "policy_violation" in Governor().validate(r, b).violation_codes


def test_reject_non_falsifiable():
    b = _bundle(); r = _valid_ruling(b)
    r["what_would_change_this"] = []
    assert "non_falsifiable" in Governor().validate(r, b).violation_codes


def test_reject_confirmed_without_anchor():
    b = _bundle(); r = _valid_ruling(b)
    r["verdict"] = "confirmed_bot_ring"  # no E1/E2 (label) anchor in the bundle
    assert "gate_breach" in Governor().validate(r, b).violation_codes


# --- audit / reproducibility ------------------------------------------------ #
def test_trace_is_content_addressed_and_reproducible():
    b = _bundle()
    t1 = Governor().validate(_valid_ruling(b), b)
    t2 = Governor().validate(_valid_ruling(b), b)
    assert t1.trace_id() == t2.trace_id()  # deterministic — same inputs, same id
    assert t1.trace_id().startswith("vt:")


def test_audit_log_is_append_only():
    b = _bundle()
    log = AuditLog()
    log.record(Governor().validate(_valid_ruling(b), b))
    log.record(Governor().validate(_valid_ruling(b), b))
    assert len(log) == 2 and all(e.decided_at for e in log.entries)


# --- Floor hardening: the REAL Floor output passes the REAL Governor --------- #
def _floor_payload() -> dict:
    return {
        "overall_probability": 0.72, "overall_tier": "elevated", "confidence": 0.6,
        "summary": "Elevated suspicion across multiple signals.",
        "weak_signals": ["only 8 posts — temporal abstained"], "single_axis_capped": False,
        "contributions": [
            {"name": "temporal", "impact": 0.5, "logit_delta": 0.8, "direction": "raises"},
            {"name": "community", "impact": 0.2, "logit_delta": -0.3, "direction": "lowers"},
            {"name": "ai_writing", "impact": 0.1, "logit_delta": 0.0,
             "direction": "neutral", "supplemental": True},
        ],
        "video": {
            "clusters": [{"method": "co_engagement", "members": ["@a", "@b", "@c"]}],
            "commenters": [
                {"handle": "@bot1", "tier": "high", "overall_probability": 0.91,
                 "intent_label": "Engagement farming", "summary": "Spam"},
                {"handle": "@bot2", "tier": "elevated", "overall_probability": 0.7},
            ],
        },
        "cross_links": [{"kind": "focus_in_cluster", "summary": "Focus in cluster"}],
    }


def test_governor_permits_real_deterministic_floor_output(monkeypatch):
    from app.reasoning import analyst as ra
    monkeypatch.setattr(ra, "analyst_enabled", lambda settings=None: True)
    monkeypatch.delenv("OMI_ANALYST_ENDPOINT_URL", raising=False)

    payload = _floor_payload()
    assessment = ra.assess_payload(payload, ref="inv1", platform="youtube")
    assert assessment is not None, "deterministic Floor should always produce an assessment"

    bundle = Binder().bind(payload, grain="comment_section", subject_ref="inv1", platform="youtube")
    trace = Governor().validate(assessment, bundle, corroboration=assessment.get("corroboration"))
    failed = [s for s in trace.stage_results if not s["pass"]]
    assert trace.verdict == "permit", (trace.violation_codes, failed)
