"""The Investigation Composer — assembles the ONE complete, model-facing InvestigationPackage.

Proves the frozen contract: the Composer consumes ONLY an EvidenceSnapshot and outputs ONLY an
immutable, content-addressed InvestigationPackage that carries the COMPLETE seven-bundle evidence set
losslessly (nothing budgeted away, all detector provenance retained); the package carries clean
provenance metadata + a stable evidence index; it is deterministic + sensitive to evidence; it holds
NO conclusion (no intent_label / suspected_intent / risk_level / verdict / prose); and the Composer
module imports nothing forbidden (no model / endpoint / runtime / governor / website / route / HF).
"""
from __future__ import annotations

import dataclasses
import json

from app.reasoning.evidence_repository import EvidenceRepository
from app.reasoning.investigation_composer import (
    INVESTIGATION_PACKAGE_SCHEMA_VERSION,
    InvestigationComposer,
    InvestigationPackage,
    compose_investigation_package,
)


def _payload() -> dict:
    """A realistic ComprehensiveScanResult payload that exercises every domain — and that CARRIES the
    heuristic interpretations (intent_label / suspected_intent / risk-ish bands) so the test can prove
    the package strips them."""
    return {
        "overall_probability": 0.72, "overall_tier": "elevated", "confidence": 0.55,
        "convergence_score": 0.3, "inputs_provided": ["video"], "video_id": "v1",
        "cross_links": [{"kind": "fellow_traveler", "severity": "elevated", "summary": "co-appeared",
                         "evidence": ["5 shared"], "related_entities": ["a", "b"]}],
        "video": {
            "video_id": "v1", "coordination_score": 0.66, "coordination_tier": "elevated",
            "clusters": [{"method": "co_engagement", "members": ["a", "b", "c"], "score": 0.7,
                          "evidence": ["tight"]},
                         {"method": "style_match", "members": ["a", "b"], "score": 0.3, "evidence": []}],
            "thread_scan": {"overall_probability": 0.5, "tier": "moderate"},
            "commenters": [
                {"external_id": "a", "handle": "@a", "overall_probability": 0.8, "tier": "high",
                 "confidence": 0.6, "matched_prior_neighbors": 2, "from_cache": False,
                 "intent_label": "astroturf", "suspected_intent": "astroturf", "risk_level": "high",
                 "reasons": ["bursty posting"], "weak_signals": ["few posts"],
                 "recent_activity": [{"text": "great video!!", "created_at": "2026-01-01T00:00:00Z",
                                      "parent_id": "v9"}],
                 "signals": [{"name": "temporal", "probability": 0.8, "confidence": 0.7,
                              "evidence": ["low variance"]},
                             {"name": "community", "probability": 0.18, "confidence": 0.5}],
                 "contributions": [{"name": "temporal", "impact": 0.4, "direction": "raises",
                                    "logit_delta": 0.9, "decorrelation_factor": 0.8,
                                    "evidence": "burst window 3s"}]},
                {"external_id": "b", "handle": "@b", "overall_probability": 0.55, "tier": "elevated",
                 "confidence": 0.4, "from_cache": True, "matched_prior_neighbors": 0,
                 "signals": [{"name": "temporal", "probability": 0.5, "confidence": 0.4}],
                 "contributions": []},
            ]},
        "focus_account": {"external_id": "focusX", "handle": "@focus", "overall_probability": 0.6,
                          "tier": "elevated", "confidence": 0.5, "intent_label": "coordinator",
                          "risk_level": "high", "reasons": ["runs the ring"], "history_size": 40},
    }


def _snapshot(payload=None):
    return EvidenceRepository().snapshot(payload if payload is not None else _payload(),
                                         ref="inv-1", platform="youtube")


# --------------------------------------------------------------------------- #
def test_compose_returns_immutable_content_addressed_package_over_seven_bundles():
    pkg = InvestigationComposer().compose(_snapshot())
    assert isinstance(pkg, InvestigationPackage)
    assert pkg.package_id.startswith("ipkg:")
    assert pkg.schema_version == INVESTIGATION_PACKAGE_SCHEMA_VERSION
    # the COMPLETE seven-bundle set is present (summary is the DAG root)
    assert set(pkg.stage_bundles()) == {
        "comment_analysis", "commenter_history", "account_analysis", "narrative_analysis",
        "coordination_analysis", "campaign_analysis", "investigation_summary"}
    assert pkg.summary_bundle() is pkg.bundles.summary
    # immutable
    with __import__("pytest").raises(dataclasses.FrozenInstanceError):
        pkg.platform = "x"


def test_package_carries_clean_provenance_metadata_and_the_stable_index():
    pkg = InvestigationComposer().compose(_snapshot())
    assert pkg.platform == "youtube"
    assert pkg.post_content_id == "v1"
    assert pkg.inputs_provided == ("video",)
    assert pkg.context_id.startswith("ictx:")
    assert pkg.snapshot_id.startswith("es:")
    # the evidence index carries every bundle id + the structural entity refs (accounts, clusters)
    idx = set(pkg.evidence_index)
    assert pkg.summary_bundle().bundle_id() in idx
    assert pkg.stage_bundle("account_analysis").bundle_id() in idx
    assert any(r.startswith("sub_") for r in idx), "account refs must be in the evidence index"
    assert any(r.startswith("cl:") for r in idx), "cluster refs must be in the evidence index"
    # component_ids is the DAG in id form
    comp = pkg.component_ids()
    assert comp["coordination_analysis"] == pkg.stage_bundle("coordination_analysis").bundle_id()


def test_package_is_complete_and_lossless_full_evidence_and_detector_provenance():
    """The package is the COMPLETE model-facing evidence — every bundle's full content is present, and
    detector provenance (evidence strings, logit_delta, decorrelation_factor) survives, so the model
    can weigh detector disagreement. Nothing is budgeted away at composition time."""
    pkg = InvestigationComposer().compose(_snapshot())
    acct = pkg.stage_bundle("account_analysis").to_dict()
    a0 = acct["accounts"][0]
    # detector disagreement is preserved verbatim: temporal=0.8 vs community=0.18 both present
    probs = {s["name"]: s["probability"] for s in a0["signals"]}
    assert probs["temporal"] == 0.8 and probs["community"] == 0.18
    # signal + contribution provenance survives (step 3)
    temporal_sig = next(s for s in a0["signals"] if s["name"] == "temporal")
    assert tuple(temporal_sig["evidence"]) == ("low variance",)
    k0 = a0["contributions"][0]
    assert k0["logit_delta"] == 0.9 and k0["decorrelation_factor"] == 0.8
    assert k0["evidence"] == "burst window 3s"
    # the comment bundle still carries the verbatim comment text (the evidence, not a summary)
    cd = pkg.stage_bundle("comment_analysis").to_dict()
    assert any("great video" in c["text"] for c in cd["comments"])
    # coordination owns the full clusters; campaign references them by ref (no duplication, but complete)
    assert pkg.stage_bundle("coordination_analysis").cluster_count == 2


def test_package_holds_no_conclusion_no_heuristic_interpretation_anywhere():
    """The package must NEVER carry a conclusion. Even though the payload is full of heuristic
    interpretations (intent_label / suspected_intent / risk_level / reasons / verdict), none may appear
    anywhere in the serialized complete package."""
    dump = json.dumps(compose_investigation_package(_snapshot()).to_dict())
    for forbidden in ("intent_label", "suspected_intent", "risk_level", "verdict", "recommendation",
                      "astroturf", "coordinator", "runs the ring", "bursty posting"):
        assert forbidden not in dump, f"conclusion/interpretation {forbidden!r} leaked into the package"


def test_deterministic_and_sensitive_to_evidence():
    a = InvestigationComposer().compose(_snapshot()).package_id
    b = InvestigationComposer().compose(_snapshot()).package_id
    assert a == b and a.startswith("ipkg:")
    # a change in the evidence changes the package address
    p = _payload()
    p["video"]["commenters"][0]["overall_probability"] = 0.11
    assert InvestigationComposer().compose(_snapshot(p)).package_id != a


def test_empty_payload_is_safe_and_typed():
    pkg = InvestigationComposer().compose(_snapshot({}))
    assert isinstance(pkg, InvestigationPackage)
    assert pkg.package_id.startswith("ipkg:")
    assert set(pkg.stage_bundles()) and pkg.stage_bundle("account_analysis").count == 0
    assert json.loads(json.dumps(pkg.to_dict()))  # serializable even when empty


def test_composer_module_imports_nothing_forbidden():
    """The Composer knows nothing about the model / endpoint / runtime / governor / website / routes /
    Hugging Face — it imports only the evidence layer + the content hash. Proven by scanning the module
    source for forbidden import targets."""
    import inspect

    import app.reasoning.investigation_composer as mod

    src = inspect.getsource(mod)
    forbidden = ("runtime", "governor", "model_providers", "transport", "_qwen", "prompt",
                 "package_loader", "huggingface", "requests", "httpx", "app.routes", "app.main",
                 "presentation")
    # only inspect the actual import statements, not prose in the docstring
    import_lines = [ln for ln in src.splitlines()
                    if ln.strip().startswith(("import ", "from "))]
    joined = "\n".join(import_lines).lower()
    for f in forbidden:
        assert f not in joined, f"Composer must not import {f!r}; imports:\n{joined}"
