#!/usr/bin/env python3
"""Tests for the working Omi Analyst (OMI_ANALYST_IMPLEMENTATION_V1).

Stdlib-only, offline (no model, no network, no HF token). Runnable two ways:
    python -m pytest ml/analyst/test_omi_analyst.py -q
    python ml/analyst/test_omi_analyst.py            # self-contained runner
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from omi_analyst import (  # noqa: E402
    AnalystOutputStore,
    DeterministicAnalystProvider,
    OmiAnalyst,
    QwenAnalystProvider,
    load_analyst_config,
    validate_analyst_response,
)
from omi_analyst.evidence_bundle import (  # noqa: E402
    project_account_bundle,
    project_campaign_bundle,
    project_narrative_bundle,
)
from omi_analyst.providers import derive_corroboration  # noqa: E402

CFG = load_analyst_config()
REQUIRED_ELEMENTS = ("evidence_for", "evidence_against", "confidence_band",
                     "confidence_rationale", "uncertainty", "what_would_change_this")


# --- fixtures --------------------------------------------------------------- #
def _scan(prob, conf, tier, *, single_axis=False, contributions=None, weak=None, supp=False):
    sig = [{"name": "temporal", "probability": prob, "confidence": conf,
            "evidence": ["low interval variance"]}]
    if supp:
        sig.append({"name": "ai_writing", "probability": 0.7, "confidence": 0.6,
                    "evidence": ["AI-assisted phrasing"], "supplemental": True})
    return {
        "overall_probability": prob, "confidence": conf, "tier": tier,
        "summary": "test", "signals": sig,
        "contributions": contributions if contributions is not None else [
            {"name": "temporal", "impact": 0.7, "direction": "raises", "logit_delta": 0.8,
             "headline": "Inter-post intervals show low variation, consistent with scheduling."},
        ] + ([{"name": "ai_writing", "impact": 0.0, "direction": "neutral", "logit_delta": 0.0,
               "supplemental": True, "headline": "AI-assisted phrasing observed."}] if supp else []),
        "score_breakdown": {"single_axis_capped": single_axis, "final_probability": prob},
        "weak_signals": weak or [],
    }


def _campaign(methods, label, *, single_axis=False):
    return {"coordination_score": 0.7, "member_count": 5, "methods": methods,
            "hashtags": ["#x"], "coordination_label": label, "single_axis_capped": single_axis,
            "members": [{"authenticity_score": 0.7}]}


def _narrative(inauth, label="suspicious"):
    return {"label": "identical praise across videos", "member_count": 100,
            "distinct_authors": 80, "spread_ratio": 0.5, "inauthenticity_score": inauth,
            "coordination_label": label, "sample_texts": ["buy now", "instant buy"]}


def _det(bundle):
    return DeterministicAnalystProvider().generate(bundle, CFG).response


# --- config ----------------------------------------------------------------- #
def test_config_loads_from_local_mirror():
    # No HF_TOKEN in this env -> local mirror, but base model is the registered one.
    cfg = load_analyst_config()
    assert cfg.base_model == "Qwen/Qwen3-4B-Thinking-2507-FP8"
    assert cfg.repo_id == "Andrewexiga/omi-analyst-v1"
    assert cfg.source in ("local-mirror", "registry")
    assert cfg.prompt_version == "v1"


# --- bundle projection ------------------------------------------------------ #
def test_account_bundle_shape():
    b = project_account_bundle(ref="a1", platform="youtube", scan=_scan(0.6, 0.5, "elevated"))
    assert b["subject"] == {"grain": "account", "ref": "a1", "platform": "youtube"}
    assert b["headline_scores"]["overall_probability"] == 0.6
    assert b["contributions"][0]["name"] == "temporal"


def test_bundle_normalizes_unknown_platform():
    b = project_account_bundle(ref="a1", platform="mastodon", scan=_scan(0.6, 0.5, "elevated"))
    assert b["subject"]["platform"] == "unknown"


# --- deterministic provider: validity + the five required elements ---------- #
def test_account_assessment_valid_and_complete():
    r = _det(project_account_bundle(ref="a1", platform="youtube",
                                    scan=_scan(0.68, 0.55, "elevated", single_axis=True)))
    assert validate_analyst_response(r) == []
    for el in REQUIRED_ELEMENTS:
        assert el in r, el
    assert len(r["uncertainty"]) >= 1 and len(r["what_would_change_this"]) >= 1


def test_echoes_probability_and_tier():
    r = _det(project_account_bundle(ref="a1", platform="youtube", scan=_scan(0.73, 0.6, "high")))
    assert r["suspicion_probability"] == 0.73 and r["suspicion_tier"] == "high"


def test_single_axis_cap_blocks_inauthentic_verdict():
    # High tier but single-axis-capped + no discriminative coordination -> at most "mixed".
    r = _det(project_account_bundle(ref="a1", platform="youtube",
                                    scan=_scan(0.9, 0.7, "high", single_axis=True)))
    assert r["verdict"] == "mixed"
    assert r["corroboration"]["single_axis_capped"] is True


def test_thin_data_forces_inconclusive():
    r = _det(project_account_bundle(ref="a1", platform="youtube",
             scan=_scan(0.71, 0.18, "elevated", weak=["only 5 posts; detectors abstained"])))
    assert r["confidence_band"] == "insufficient" and r["verdict"] == "inconclusive"


def test_low_tier_is_likely_authentic():
    r = _det(project_account_bundle(ref="a1", platform="youtube", scan=_scan(0.1, 0.85, "low")))
    assert r["verdict"] == "likely_authentic"


def test_empty_evidence_against_states_so_and_validates():
    # All-raising contributions -> evidence_against empty -> rationale must say so (F5).
    scan = _scan(0.6, 0.5, "elevated", contributions=[
        {"name": "temporal", "impact": 0.7, "direction": "raises", "logit_delta": 0.8,
         "headline": "low interval variation"}])
    scan["intelligence"] = {"authenticity_score": 0.2}  # not exculpatory
    r = _det(project_account_bundle(ref="a1", platform="youtube", scan=scan))
    assert r["evidence_against"] == []
    assert "no exculpatory" in r["confidence_rationale"].lower()
    assert validate_analyst_response(r) == []


def test_exculpatory_contribution_populates_evidence_against():
    scan = _scan(0.5, 0.6, "moderate", contributions=[
        {"name": "temporal", "impact": 0.5, "direction": "raises", "logit_delta": 0.4,
         "headline": "low interval variation"},
        {"name": "community", "impact": 0.3, "direction": "lowers", "logit_delta": -0.3,
         "headline": "established interaction footprint is consistent with an organic account"}])
    r = _det(project_account_bundle(ref="a1", platform="youtube", scan=scan))
    assert any(e["signal"] == "community" for e in r["evidence_against"])


def test_supplemental_signal_is_context_not_suspicion():
    r = _det(project_account_bundle(ref="a1", platform="youtube",
                                    scan=_scan(0.6, 0.5, "elevated", supp=True)))
    assert "supplemental_context" in r
    assert any(s["signal"] == "ai_writing" for s in r["supplemental_context"])
    assert all(e["signal"] != "ai_writing" for e in r["evidence_for"])


# --- corroboration gate (campaign) ------------------------------------------ #
def test_corroboration_gate_downgrades_noncorroborated_coordination():
    # 'coordinated' label but only non-discriminative methods -> gated to 'suspicious'.
    r = _det(project_campaign_bundle(ref="c1", platform="twitter",
             campaign=_campaign(["style_match", "temporal_semantic"], "coordinated")))
    assert r["coordination_label"] == "suspicious"


def test_discriminative_methods_keep_coordinated_label():
    r = _det(project_campaign_bundle(ref="c1", platform="twitter",
             campaign=_campaign(["co_engagement", "co_tag"], "coordinated")))
    assert r["coordination_label"] == "coordinated"
    assert set(r["corroboration"]["discriminative_methods"]) == {"co_engagement", "co_tag"}


def test_campaign_has_legitimate_hypothesis():
    r = _det(project_campaign_bundle(ref="c1", platform="twitter",
             campaign=_campaign(["co_tag"], "suspicious")))
    assert r.get("legitimate_hypothesis")


def test_derive_corroboration_filters_discriminative():
    b = project_campaign_bundle(ref="c1", platform="twitter",
                                campaign=_campaign(["co_tag", "style_match"], "suspicious"))
    corr = derive_corroboration(b)
    assert corr["discriminative_methods"] == ["co_tag"]


# --- narrative -------------------------------------------------------------- #
def test_narrative_assessment_valid():
    r = _det(project_narrative_bundle(ref="n1", platform="youtube", narrative=_narrative(0.58)))
    assert validate_analyst_response(r) == []
    assert r["subject"]["grain"] == "narrative"
    assert r["coordination_label"] in ("organic", "mixed", "suspicious", "coordinated", "manipulation_network")


# --- validator catches violations ------------------------------------------- #
def test_validator_flags_missing_field():
    r = _det(project_account_bundle(ref="a1", platform="youtube", scan=_scan(0.6, 0.5, "elevated")))
    del r["headline"]
    assert any("headline" in e for e in validate_analyst_response(r))


def test_validator_flags_bad_enum():
    r = _det(project_account_bundle(ref="a1", platform="youtube", scan=_scan(0.6, 0.5, "elevated")))
    r["verdict"] = "definitely_a_bot"
    assert any("verdict" in e for e in validate_analyst_response(r))


def test_validator_flags_evidence_without_refs():
    r = _det(project_account_bundle(ref="a1", platform="youtube", scan=_scan(0.6, 0.5, "elevated")))
    r["evidence_for"] = [{"signal": "x", "claim": "y", "evidence_refs": []}]
    assert any("evidence_refs" in e for e in validate_analyst_response(r))


def test_validator_flags_banned_phrase():
    r = _det(project_account_bundle(ref="a1", platform="youtube", scan=_scan(0.6, 0.5, "elevated")))
    r["assessment"] = "This account is a bot."
    assert any("banned" in e for e in validate_analyst_response(r))


def test_validator_flags_empty_evidence_against_without_rationale():
    r = _det(project_account_bundle(ref="a1", platform="youtube", scan=_scan(0.6, 0.5, "elevated")))
    r["evidence_against"] = []
    r["confidence_rationale"] = "moderate confidence."
    assert any("F5" in e for e in validate_analyst_response(r))


# --- Qwen provider falls back gracefully ------------------------------------ #
def test_qwen_provider_falls_back_without_endpoint():
    saved = {k: os.environ.pop(k, None) for k in ("OMI_ANALYST_ENDPOINT_URL", "HF_TOKEN")}
    try:
        res = QwenAnalystProvider().generate(
            project_account_bundle(ref="a1", platform="youtube", scan=_scan(0.6, 0.5, "elevated")), CFG)
        assert "fallback" in res.provider
        assert validate_analyst_response(res.response) == []
    finally:
        for k, v in saved.items():
            if v is not None:
                os.environ[k] = v


# --- storage ---------------------------------------------------------------- #
def test_store_round_trip():
    with tempfile.TemporaryDirectory() as d:
        store = AnalystOutputStore(path=Path(d) / "out.jsonl")
        a = OmiAnalyst(config=CFG, store=store)
        a.assess_account(ref="a1", platform="youtube", scan=_scan(0.6, 0.5, "elevated"))
        a.assess_narrative(ref="n1", platform="youtube", narrative=_narrative(0.4, "mixed"))
        rows = store.read_all()
        assert store.count() == 2
        assert {r["grain"] for r in rows} == {"account", "narrative"}
        assert all(r["response"]["analyst_version"] == "v1" for r in rows)
        assert rows[0]["bundle_digest"].startswith("ev_")


# --- investigation summary rolls up components ------------------------------ #
def test_investigation_summary_rolls_up_components():
    a = OmiAnalyst(config=CFG, store=None, record=False)
    acct = a.assess_account(ref="a_sus", platform="youtube",
                            scan=_scan(0.8, 0.6, "high", single_axis=True))
    camp = a.assess_campaign(ref="c1", platform="twitter",
                             campaign=_campaign(["co_tag", "co_engagement"], "coordinated"))
    inv = a.summarize_investigation(
        ref="scan1", platform="youtube",
        scan={"overall_probability": 0.6, "tier": "elevated", "confidence": 0.6, "summary": "s"},
        components=[acct, camp])
    assert inv.valid and inv.response["subject"]["grain"] == "comment_section"
    refs = [e for e in inv.response["evidence_for"] if "assessment" in e["signal"]]
    assert refs, "investigation summary should reference its component assessments"


# --- the four assessments each carry the five mandated elements ------------- #
def test_all_four_assessments_carry_required_elements():
    a = OmiAnalyst(config=CFG, store=None, record=False)
    outs = [
        a.assess_account(ref="a1", platform="youtube", scan=_scan(0.68, 0.55, "elevated")),
        a.assess_campaign(ref="c1", platform="twitter", campaign=_campaign(["co_tag"], "suspicious")),
        a.assess_narrative(ref="n1", platform="youtube", narrative=_narrative(0.5)),
    ]
    outs.append(a.summarize_investigation(ref="s1", platform="youtube",
                scan={"overall_probability": 0.5, "tier": "moderate", "confidence": 0.6, "summary": "s"},
                components=outs[:]))
    for oc in outs:
        assert oc.valid, oc.errors
        for el in REQUIRED_ELEMENTS:
            assert el in oc.response and oc.response[el] not in (None, ""), el
        assert len(oc.response["evidence_for"]) >= 1
        assert len(oc.response["uncertainty"]) >= 1
        assert len(oc.response["what_would_change_this"]) >= 1


def _run_all() -> bool:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for fn in tests:
        try:
            fn()
            print(f"PASS {fn.__name__}")
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(f"FAIL {fn.__name__}: {exc}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    return failed == 0


if __name__ == "__main__":
    sys.exit(0 if _run_all() else 1)
