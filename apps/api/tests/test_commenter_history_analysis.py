"""Phase P3.2 — AI-Native Commenter History Analysis (the second migrated reasoning stage).

Proves the identical canonical flow the Comment Analysis stage established: CommenterHistoryBundle →
Package Loader → Prompt Builder (package assets only, ZERO embedded prompt text) → the AI
Investigation Runtime (exactly one inference, the ONE endpoint + Governor + Floor + forensic path) →
Mistral → the MANDATORY Governor → a typed, immutable CommenterHistoryReport; that the model reasons
about every commenter's track record (structured CommenterHistoryAnalysis objects, no prose); that the
investigation-level wrapper is Governor-validated with the engine number echo-guarded; that the
deterministic Floor stays available; and that a compatibility mapping supplies the existing commenter
shape. The stage OWNS no orchestration/endpoint/Governor/fallback logic — all delegated to the runtime.
"""
from __future__ import annotations

import dataclasses
import json
from pathlib import Path

import pytest

from app.core.config import get_settings
from app.evidence import Binder
from app.reasoning import analyst as _analyst
from app.reasoning import commenter_history_analysis as CH
from app.reasoning.commenter_history_analysis import (
    CommenterHistoryAnalysis,
    CommenterHistoryReport,
    build_commenter_history_prompt_package,
    run_commenter_history_analysis,
    to_commenter_compat,
)
from app.reasoning.context import build_investigation_context
from app.reasoning.evidence_bundles import build_commenter_history_bundle
from app.reasoning.orchestrator.modules import build_ruling_assessment

_REQUIRED_FIELDS = (
    "commenter_ref", "track_record_assessment", "history_depth_reasoning", "recurrence_reasoning",
    "provenance_reasoning", "supporting_evidence", "contradictory_evidence", "uncertainty",
    "confidence", "reasoning_trace",
)


def _payload() -> dict:
    return {
        "overall_probability": 0.72, "overall_tier": "elevated", "confidence": 0.55, "video_id": "v1",
        "video": {
            "thread_scan": {"overall_probability": 0.5, "tier": "moderate"},
            "coordination_score": 0.66, "coordination_tier": "elevated",
            "commenters": [
                {"external_id": "a", "handle": "@a", "overall_probability": 0.8, "tier": "high",
                 "confidence": 0.6, "from_cache": False, "matched_prior_neighbors": 2,
                 "recent_activity": [{"text": "great!!", "created_at": "2026-01-01T00:00:00Z", "parent_id": "v9"},
                                     {"text": "nice", "created_at": "2026-01-02T00:00:00Z", "parent_id": "v9"}],
                 "signals": [{"name": "temporal", "probability": 0.8, "confidence": 0.7}]},
                {"external_id": "b", "handle": "@b", "overall_probability": 0.3, "tier": "low",
                 "confidence": 0.4, "from_cache": True, "matched_prior_neighbors": 0, "recent_activity": []}]},
    }


def _ctx(payload=None):
    return build_investigation_context(payload or _payload(), ref="slug1", platform="youtube",
                                       slug="slug1", kind="video")


def _enabled_settings(**over):
    base = {"analyst_enabled": True, "analyst_endpoint_url": "http://endpoint/generate"}
    base.update(over)
    return get_settings().model_copy(update=base)


def _ca_dict(**over) -> dict:
    d = {
        "commenter_ref": "chi:x", "track_record_assessment": "established",
        "history_depth_reasoning": "long, consistent posting history",
        "recurrence_reasoning": "recurs across multiple prior scans",
        "provenance_reasoning": "freshly scanned", "supporting_evidence": ["neighbours"],
        "contradictory_evidence": [], "uncertainty": ["single snapshot"], "confidence": 0.7,
        "reasoning_trace": ["read track record", "weigh recurrence", "assess"],
    }
    d.update(over)
    return d


def _model_wrapper(payload: dict, *, commenter_analyses=None, mutate=None) -> dict:
    ctx = _ctx(payload)
    ref = ctx.investigation.ref or _analyst._ref(ctx.context_id)
    gb = Binder().bind(payload, grain="comment_section", subject_ref=ref, platform="youtube")
    w = build_ruling_assessment(gb)
    w["commenter_analyses"] = commenter_analyses if commenter_analyses is not None else [_ca_dict()]
    if mutate:
        mutate(w)
    return w


def _fake_transport(return_value, calls=None):
    def factory(endpoint, **kw):
        def _call(system, user, config):
            if calls is not None:
                calls.append((system, user))
            return return_value(system, user) if callable(return_value) else return_value
        return _call
    return factory


# --------------------------------------------------------------------------- #
# Floor path — typed, Governor-validated, immutable, deterministic
# --------------------------------------------------------------------------- #
def test_floor_when_disabled_is_typed_governed_immutable():
    r = run_commenter_history_analysis(_ctx(), payload=_payload(), platform="youtube")
    assert isinstance(r, CommenterHistoryReport)
    with pytest.raises(dataclasses.FrozenInstanceError):
        r.provider = "x"
    assert r.model_backed is False and r.fallback is True and r.endpoint_called is False
    assert r.provider == "deterministic-analyst-v1"
    assert r.governor_verdict == "permit" and r.governor_trace_id.startswith("vt:")
    assert r.report_id.startswith("chr:")
    assert r.package_hash.startswith("pkg:") and r.template_hash.startswith("chtmpl:")
    assert r.model_id == "mistralai/Mistral-7B-Instruct-v0.3"
    assert r.commenter_count == len(r.commenter_analyses) == 2
    a = r.commenter_analyses[0]
    assert isinstance(a, CommenterHistoryAnalysis) and a.commenter_ref.startswith("chi:")
    # the Floor bands the track record from the deterministic evidence
    assert a.track_record_assessment == "established"          # matched_prior_neighbors = 2
    assert r.commenter_analyses[1].track_record_assessment == "fresh"  # 0 samples, 0 neighbours


def test_report_serializes_and_every_commenter_has_required_fields():
    r = run_commenter_history_analysis(_ctx(), payload=_payload())
    d = json.loads(json.dumps(r.to_dict()))
    for cd in d["commenter_analyses"]:
        for f in _REQUIRED_FIELDS:
            assert f in cd, f
        assert cd["track_record_assessment"] in ("established", "emerging", "fresh", "inconclusive")
        assert isinstance(cd["reasoning_trace"], list) and cd["reasoning_trace"]


# --------------------------------------------------------------------------- #
# Model path — EXACTLY ONE inference via the runtime, Governor-gated
# --------------------------------------------------------------------------- #
def test_exactly_one_inference_model_backed(monkeypatch):
    payload = _payload()
    calls: list = []
    wrapper = _model_wrapper(payload)
    monkeypatch.setattr(_analyst, "_qwen_transport", _fake_transport(json.dumps(wrapper), calls))
    r = run_commenter_history_analysis(_ctx(payload), payload=payload, platform="youtube",
                                       settings=_enabled_settings())
    assert len(calls) == 1                                        # exactly one inference
    assert r.endpoint_called is True and r.model_backed is True and r.fallback is False
    assert r.provider == "qwen-omi-analyst-v1" and r.governor_verdict == "permit"
    # the model's per-commenter track-record reasoning is what surfaces (not the floor's)
    assert r.commenter_analyses[0].history_depth_reasoning == "long, consistent posting history"
    # the prompt actually sent is the canonically-built commenter-history PromptPackage
    pp = build_commenter_history_prompt_package(
        build_commenter_history_bundle(_ctx(payload)),
        investigation={"overall_probability": 0.72, "tier": "elevated"})
    assert calls[0][0] == pp.system and calls[0][1] == pp.user


def test_echo_guard_pins_engine_number(monkeypatch):
    payload = _payload()
    wrapper = _model_wrapper(payload, mutate=lambda w: w.update(suspicion_probability=0.999,
                                                               suspicion_tier="high"))
    monkeypatch.setattr(_analyst, "_qwen_transport", _fake_transport(json.dumps(wrapper)))
    r = run_commenter_history_analysis(_ctx(payload), payload=payload, settings=_enabled_settings())
    assert r.model_backed is True and r.governor_verdict == "permit"
    # the report echoes the engine investigation number (0.72), never the model's 0.999
    assert r.investigation_probability == pytest.approx(0.72)


# --------------------------------------------------------------------------- #
# The deterministic Floor stays available on every failure mode
# --------------------------------------------------------------------------- #
def test_fallback_when_endpoint_unreachable(monkeypatch):
    payload = _payload()
    monkeypatch.setattr(_analyst, "_qwen_transport", _fake_transport(None))
    r = run_commenter_history_analysis(_ctx(payload), payload=payload, settings=_enabled_settings())
    assert r.model_backed is False and r.fallback is True
    assert r.provider == "deterministic-analyst-v1" and r.governor_verdict == "permit"


def test_fallback_when_model_output_invalid_json(monkeypatch):
    payload = _payload()
    monkeypatch.setattr(_analyst, "_qwen_transport", _fake_transport("not json at all"))
    r = run_commenter_history_analysis(_ctx(payload), payload=payload, settings=_enabled_settings())
    assert r.model_backed is False and r.fallback is True
    assert r.provider.startswith("qwen-omi-analyst-v1->fallback:")
    assert r.governor_verdict == "permit"


def test_fallback_when_wrapper_rejected_by_governor(monkeypatch):
    payload = _payload()
    wrapper = _model_wrapper(payload, mutate=lambda w: w.pop("what_would_change_this"))
    monkeypatch.setattr(_analyst, "_qwen_transport", _fake_transport(json.dumps(wrapper)))
    r = run_commenter_history_analysis(_ctx(payload), payload=payload, settings=_enabled_settings())
    assert r.model_backed is False and r.fallback is True
    assert r.provider.startswith("qwen-omi-analyst-v1->fallback:")
    assert r.governor_verdict == "permit"  # the FLOOR wrapper is itself Governor-valid


# --------------------------------------------------------------------------- #
# Prompt from package assets only; stage delegates inference to the runtime
# --------------------------------------------------------------------------- #
def test_prompt_assembled_from_package_assets_only():
    from app.reasoning.package_loader import load_commenter_history_assets, load_package
    bundle = build_commenter_history_bundle(_ctx())
    lp = load_package()
    cha = load_commenter_history_assets()
    pp = build_commenter_history_prompt_package(
        bundle, investigation={"overall_probability": 0.72, "tier": "elevated"}, loaded=lp, assets=cha)
    assert lp.system_prompt in pp.system and lp.constitution in pp.system
    assert cha.system_task in pp.system and cha.response_contract in pp.system
    # the user message carries the investigation number to echo + the per-commenter track record
    assert '"overall_probability": 0.72' in pp.user
    assert '"matched_prior_neighbors": 2' in pp.user
    assert pp.manifest["package_hash"] == lp.package_hash
    assert pp.manifest["template_hash"] == cha.template_hash
    assert pp.manifest["commenter_bundle_id"] == bundle.bundle_id()
    assert pp.schema_ref == "commenter_history_v1"


def test_stage_embeds_no_prompt_text_and_delegates_inference_to_the_runtime():
    src = Path(CH.__file__).read_text(encoding="utf-8")
    from app.reasoning.prompts.commenter_history_template import (
        COMMENTER_HISTORY_RESPONSE_CONTRACT,
        COMMENTER_HISTORY_SYSTEM_TASK,
    )
    assert COMMENTER_HISTORY_SYSTEM_TASK[:40] not in src
    assert COMMENTER_HISTORY_RESPONSE_CONTRACT[:40] not in src
    assert "# COMMENTER HISTORY TASK" not in src
    # reaches inference ONLY through the runtime — never the transport or the Governor directly
    assert "run_stage_inference" in src
    assert "_qwen_transport" not in src
    assert "governor.validate(" not in src.lower()
    assert "urlopen(" not in src and "import urllib" not in src
    assert "for attempt in range" not in src


# --------------------------------------------------------------------------- #
# Determinism + compatibility + empty-safety
# --------------------------------------------------------------------------- #
def test_report_is_content_addressed_and_deterministic():
    a = run_commenter_history_analysis(_ctx(), payload=_payload())
    b = run_commenter_history_analysis(_ctx(), payload=_payload())
    assert a.report_id == b.report_id and a.report_id.startswith("chr:")


def test_compat_mapping_supplies_commenter_shape():
    r = run_commenter_history_analysis(_ctx(), payload=_payload())
    compat = to_commenter_compat(r)
    assert set(compat) == {"investigation_probability", "investigation_tier", "commenter_count",
                           "provider", "model_backed", "commenters"}
    assert compat["investigation_probability"] == pytest.approx(0.72)
    assert compat["commenter_count"] == 2 and len(compat["commenters"]) == 2
    assert compat["commenters"][0]["track_record_assessment"] == "established"


def test_empty_commenters_is_safe_and_typed():
    r = run_commenter_history_analysis(build_investigation_context({}, ref="x", platform="unknown"),
                                       payload={})
    assert r.commenter_count == 0 and r.commenter_analyses == ()
    assert r.governor_verdict == "permit" and r.report_id.startswith("chr:")


# --------------------------------------------------------------------------- #
# The package asset is published through the existing pipeline (drift-guarded)
# --------------------------------------------------------------------------- #
def test_commenter_history_template_published_and_drift_guarded():
    from app.reasoning.package_loader import load_commenter_history_assets
    from app.reasoning.prompts.export import (
        COMMENTER_HISTORY_TEMPLATE_PATH,
        commenter_history_template_manifest,
        commenter_history_template_matches_committed,
    )
    assert commenter_history_template_matches_committed() is True
    assert COMMENTER_HISTORY_TEMPLATE_PATH.exists()
    man = commenter_history_template_manifest()
    cha = load_commenter_history_assets()
    assert man["template_hash"] == cha.template_hash
    assert man["response_contract_hash"] == cha.contract_hash
    assert man["output_schema_hash"] == cha.schema_hash
    assert man["stage"] == "commenter_history" and man["schema_ref"] == "commenter_history_v1"


def test_hf_manifest_publishes_commenter_history_template():
    import importlib.util
    root = Path(__file__).resolve().parents[3]
    spec = importlib.util.spec_from_file_location(
        "register_hf_model", root / "ml" / "analyst" / "register_hf_model.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    target, files = mod.load_manifest(root / "ml" / "analyst" / "hf_repo_manifest.toml")
    ok, resolved, errors = mod.validate(target, files)
    assert ok, errors
    published = {dst for _s, dst, _k in resolved}
    assert "prompts/commenter_history_prompt_template.json" in published
