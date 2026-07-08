"""Phase P3.1 — AI-Native Comment Analysis (the first migrated reasoning stage).

Proves the canonical flow: CommentEvidenceBundle → Package Loader → Prompt Builder (package assets
only, ZERO embedded prompt text) → the ONE Hugging Face transport (exactly one inference) → Mistral
→ the MANDATORY Governor → a typed, immutable CommentAnalysisReport; that the model reasons about
every individual comment (structured CommentAnalysis objects, no prose); that the wrapper is
Governor-validated with the engine number echo-guarded; that the deterministic Floor stays available
and content-addressed; and that the existing thread UI keeps working through the compatibility layer.
Only Comment Analysis is exercised — no other stage/prompt/package/endpoint/heuristic is touched.
"""
from __future__ import annotations

import dataclasses
import json
from pathlib import Path

import pytest

from app.core.config import get_settings
from app.evidence import Binder
from app.reasoning import analyst as _analyst
from app.reasoning import comment_analysis as CA
from app.reasoning.comment_analysis import (
    CommentAnalysis,
    CommentAnalysisReport,
    build_comment_prompt_package,
    run_comment_analysis,
    to_thread_compat,
)
from app.reasoning.context import build_investigation_context
from app.reasoning.evidence_bundles import build_comment_bundle
from app.reasoning.orchestrator.modules import build_ruling_assessment

_REQUIRED_COMMENT_FIELDS = (
    "comment_ref", "authenticity_assessment", "manipulation_likelihood", "behavioral_reasoning",
    "linguistic_reasoning", "engagement_reasoning", "supporting_evidence", "contradictory_evidence",
    "uncertainty", "confidence", "reasoning_trace",
)


def _payload() -> dict:
    return {
        "overall_probability": 0.72, "overall_tier": "elevated", "confidence": 0.55,
        "convergence_score": 0.3, "inputs_provided": ["video"], "video_id": "v1",
        "video": {
            "coordination_score": 0.66, "coordination_tier": "elevated",
            "clusters": [{"method": "co_engagement", "members": ["a", "b", "c"], "score": 0.7,
                          "evidence": ["tight"]}],
            "thread_scan": {"overall_probability": 0.5, "tier": "moderate"},
            "commenters": [{"external_id": "a", "handle": "@a", "overall_probability": 0.8, "tier": "high",
                            "confidence": 0.6,
                            "recent_activity": [{"text": "great video!!", "created_at": "2026-01-01T00:00:00Z",
                                                 "parent_id": "v9"}],
                            "signals": [{"name": "temporal", "probability": 0.8, "confidence": 0.7}],
                            "contributions": [{"name": "temporal", "impact": 0.4, "direction": "raises"}]}]},
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
        "comment_ref": "cm:x", "authenticity_assessment": "inauthentic", "manipulation_likelihood": 0.8,
        "behavioral_reasoning": "burst timing consistent with coordinated posting",
        "linguistic_reasoning": "generic low-effort praise", "engagement_reasoning": "reply seeded to top comment",
        "supporting_evidence": ["temporal"], "contradictory_evidence": [], "uncertainty": ["single snapshot"],
        "confidence": 0.6, "reasoning_trace": ["read signals", "weigh counter-evidence", "assess authenticity"],
    }
    d.update(over)
    return d


def _model_wrapper(payload: dict, *, comment_analyses=None, mutate=None) -> dict:
    """A Governor-valid comment-section wrapper (the canonical FloorJudge assessment) carrying the
    per-comment analyses — standing in for a good Mistral output. Built against the SAME bundle the
    runtime binds internally, so its evidence refs resolve and the echo matches."""
    ctx = _ctx(payload)
    ref = ctx.investigation.ref or _analyst._ref(ctx.context_id)
    gb = Binder().bind(payload, grain="comment_section", subject_ref=ref, platform="youtube")
    w = build_ruling_assessment(gb)
    w["comment_analyses"] = comment_analyses if comment_analyses is not None else [_ca_dict()]
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
# Deliverable 1/2 — Floor path (no endpoint): typed, Governor-validated, immutable
# --------------------------------------------------------------------------- #
def test_floor_when_disabled_is_typed_governed_immutable():
    r = run_comment_analysis(_ctx(), payload=_payload(), platform="youtube")
    assert isinstance(r, CommentAnalysisReport)
    with pytest.raises(dataclasses.FrozenInstanceError):
        r.provider = "x"
    assert r.model_backed is False and r.fallback is True and r.endpoint_called is False
    assert r.provider == "deterministic-analyst-v1"
    assert r.governor_verdict == "permit" and r.governor_trace_id.startswith("vt:")
    assert r.report_id.startswith("car:")
    assert r.package_hash.startswith("pkg:") and r.comment_template_hash.startswith("ctmpl:")
    assert r.model_id == "mistralai/Mistral-7B-Instruct-v0.3"
    # every comment got a typed, structured analysis (no prose object)
    assert r.comment_count == len(r.comment_analyses) == 1
    a = r.comment_analyses[0]
    assert isinstance(a, CommentAnalysis) and a.comment_ref.startswith("cm:")
    assert a.reasoning_trace and isinstance(a.reasoning_trace, tuple)


def test_report_serializes_and_every_comment_has_required_fields():
    r = run_comment_analysis(_ctx(), payload=_payload())
    d = json.loads(json.dumps(r.to_dict()))  # the fully-serialized (JSON-native) form
    for cd in d["comment_analyses"]:
        for f in _REQUIRED_COMMENT_FIELDS:
            assert f in cd, f
        assert cd["authenticity_assessment"] in ("authentic", "inauthentic", "mixed", "inconclusive")
        assert 0.0 <= float(cd["manipulation_likelihood"]) <= 1.0
        assert isinstance(cd["reasoning_trace"], list) and cd["reasoning_trace"]


# --------------------------------------------------------------------------- #
# Deliverable 6/8 — EXACTLY ONE inference via the ONE transport, Governor-gated
# --------------------------------------------------------------------------- #
def test_exactly_one_inference_model_backed(monkeypatch):
    payload = _payload()
    calls: list = []
    wrapper = _model_wrapper(payload)
    monkeypatch.setattr(_analyst, "_qwen_transport", _fake_transport(json.dumps(wrapper), calls))
    r = run_comment_analysis(_ctx(payload), payload=payload, platform="youtube", settings=_enabled_settings())

    assert len(calls) == 1                                        # exactly one inference
    assert r.endpoint_called is True and r.model_backed is True and r.fallback is False
    assert r.provider == "qwen-omi-analyst-v1" and r.governor_verdict == "permit"
    # the model's individual-comment reasoning is what surfaces (not the floor's)
    a = r.comment_analyses[0]
    assert a.behavioral_reasoning == "burst timing consistent with coordinated posting"
    assert a.authenticity_assessment == "inauthentic"
    # the prompt actually sent is the canonically-built comment PromptPackage (system+user)
    pp = build_comment_prompt_package(build_comment_bundle(_ctx(payload)))
    assert calls[0][0] == pp.system and calls[0][1] == pp.user


def test_echo_guard_pins_engine_number(monkeypatch):
    """The model cannot move the engine number: a wrapper claiming suspicion 0.999 is pinned back to
    the engine's 0.72 before the Governor, so it PERMITS (S4) and stays model-backed."""
    payload = _payload()
    wrapper = _model_wrapper(payload, mutate=lambda w: w.update(suspicion_probability=0.999,
                                                               suspicion_tier="high"))
    monkeypatch.setattr(_analyst, "_qwen_transport", _fake_transport(json.dumps(wrapper)))
    r = run_comment_analysis(_ctx(payload), payload=payload, settings=_enabled_settings())
    assert r.model_backed is True and r.governor_verdict == "permit"


# --------------------------------------------------------------------------- #
# Deliverable 8 — the deterministic Floor stays available on every failure mode
# --------------------------------------------------------------------------- #
def test_fallback_when_endpoint_unreachable(monkeypatch):
    payload = _payload()
    monkeypatch.setattr(_analyst, "_qwen_transport", _fake_transport(None))  # transport gave up
    r = run_comment_analysis(_ctx(payload), payload=payload, settings=_enabled_settings())
    assert r.model_backed is False and r.fallback is True
    assert r.provider == "deterministic-analyst-v1" and r.governor_verdict == "permit"
    assert len(r.comment_analyses) == 1


def test_fallback_when_model_output_invalid_json(monkeypatch):
    payload = _payload()
    monkeypatch.setattr(_analyst, "_qwen_transport", _fake_transport("not json at all"))
    r = run_comment_analysis(_ctx(payload), payload=payload, settings=_enabled_settings())
    assert r.model_backed is False and r.fallback is True
    assert r.provider.startswith("qwen-omi-analyst-v1->fallback:")
    assert r.governor_verdict == "permit"


def test_fallback_when_wrapper_rejected_by_governor(monkeypatch):
    """A model wrapper missing a constitutional field (falsifiability) is REJECTED by the Governor,
    so the stage degrades to the Floor — never emitting an unvalidated ruling."""
    payload = _payload()
    wrapper = _model_wrapper(payload, mutate=lambda w: w.pop("what_would_change_this"))
    monkeypatch.setattr(_analyst, "_qwen_transport", _fake_transport(json.dumps(wrapper)))
    r = run_comment_analysis(_ctx(payload), payload=payload, settings=_enabled_settings())
    assert r.model_backed is False and r.fallback is True
    assert r.provider.startswith("qwen-omi-analyst-v1->fallback:")
    assert r.governor_verdict == "permit"  # the FLOOR wrapper is itself Governor-valid


# --------------------------------------------------------------------------- #
# Deliverable 4/5 — the Prompt Builder assembles from package assets with ZERO embedded text
# --------------------------------------------------------------------------- #
def test_prompt_assembled_from_package_assets_only():
    from app.reasoning.package_loader import load_comment_assets, load_package
    bundle = build_comment_bundle(_ctx())
    lp = load_package()
    ca = load_comment_assets()
    pp = build_comment_prompt_package(bundle, loaded=lp, comment_assets=ca)
    # system carries the shared package assets + the comment task/contract — all from the loader
    assert lp.system_prompt in pp.system
    assert lp.constitution in pp.system
    assert ca.comment_system_task in pp.system
    assert ca.comment_response_contract in pp.system
    # user carries the evidence: the thread number to echo + the individual comment text
    assert '"thread_probability": 0.5' in pp.user
    assert "great video!!" in pp.user
    # provenance the runtime records
    assert pp.manifest["package_hash"] == lp.package_hash
    assert pp.manifest["comment_template_hash"] == ca.comment_template_hash
    assert pp.manifest["comment_bundle_id"] == bundle.bundle_id()
    assert pp.schema_ref == "comment_analysis_v1"


def test_runtime_embeds_no_prompt_text_and_owns_no_endpoint_primitive():
    src = Path(CA.__file__).read_text(encoding="utf-8")
    # the scaffolding text lives ONLY in the comment_template package asset, never in the runtime
    from app.reasoning.prompts.comment_template import COMMENT_RESPONSE_CONTRACT, COMMENT_SYSTEM_TASK
    assert COMMENT_SYSTEM_TASK[:40] not in src
    assert COMMENT_RESPONSE_CONTRACT[:40] not in src
    assert "# COMMENT ANALYSIS TASK" not in src
    # the endpoint is reached ONLY through the ONE shared transport factory (no bespoke HTTP/retry)
    assert "_qwen_transport" in src
    assert "urlopen(" not in src and "import urllib" not in src
    assert "for attempt in range" not in src
    # the Governor is invoked, not reimplemented
    assert "governor.validate(" in src


# --------------------------------------------------------------------------- #
# Deliverable 9/10 — determinism + the compatibility mapping for the existing UI
# --------------------------------------------------------------------------- #
def test_report_is_content_addressed_and_deterministic():
    a = run_comment_analysis(_ctx(), payload=_payload())
    b = run_comment_analysis(_ctx(), payload=_payload())
    assert a.report_id == b.report_id and a.report_id.startswith("car:")


def test_compat_mapping_preserves_thread_shape():
    r = run_comment_analysis(_ctx(), payload=_payload())
    compat = to_thread_compat(r)
    assert set(compat) == {"overall_probability", "tier", "comment_count", "provider", "model_backed"}
    # the thread UI shape is the comment bundle's thread signal (0.5 / moderate), not the wrapper number
    assert compat["overall_probability"] == pytest.approx(0.5)
    assert compat["tier"] == "moderate" and compat["comment_count"] == 1


def test_empty_comments_is_safe_and_typed():
    r = run_comment_analysis(build_investigation_context({}, ref="x", platform="unknown"), payload={})
    assert r.comment_count == 0 and r.comment_analyses == ()
    assert r.governor_verdict == "permit" and r.report_id.startswith("car:")


# --------------------------------------------------------------------------- #
# Deliverable — the comment package asset is published through the existing pipeline (drift-guarded)
# --------------------------------------------------------------------------- #
def test_comment_template_published_and_drift_guarded():
    from app.reasoning.package_loader import load_comment_assets
    from app.reasoning.prompts.export import (
        COMMENT_TEMPLATE_PATH,
        comment_template_manifest,
        comment_template_matches_committed,
    )
    assert comment_template_matches_committed() is True
    assert COMMENT_TEMPLATE_PATH.exists()
    man = comment_template_manifest()
    ca = load_comment_assets()
    # the published asset carries the SAME content hashes the runtime loads (GitHub == HF)
    assert man["template_hash"] == ca.comment_template_hash
    assert man["response_contract_hash"] == ca.comment_contract_hash
    assert man["output_schema_hash"] == ca.comment_schema_hash
    assert man["stage"] == "comment_analysis" and man["schema_ref"] == "comment_analysis_v1"


def test_hf_manifest_publishes_comment_template():
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
    assert "prompts/comment_prompt_template.json" in published
