"""Per-account (per-commenter) AI assessments — the model emits aliased per-account reasoning in the ONE
comprehensive response; OmiSphere echo-joins it back to real identity + the engine's tier/probability.

Certifies the whole path with a mocked transport (no live call): the canonical schema accepts the
optional ``commenter_assessments`` array, it survives validation to the served assessment, aliases resolve
to the real commenters, the engine numbers are joined (never model-fabricated), and an unresolved alias is
kept-but-flagged rather than dropped. Also proves a response WITHOUT the array still validates (optional).
"""
from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.reasoning import analyst
from app.reasoning.prompts.comprehensive_investigation_template import (
    COMPREHENSIVE_COMMENTER_ASSESSMENTS_KEY,
    COMPREHENSIVE_SECTION_KEYS,
    comprehensive_investigation_canonical_schema,
    comprehensive_investigation_response_contract,
)
from app.storage.db import reset_db_for_tests

_API_KEY = "sk-or-v1-SECRET-testkey-0000"
_PRESET = "omi-master-v1"

_PAYLOAD = {
    "overall_probability": 0.72, "overall_tier": "elevated", "confidence": 0.55,
    "convergence_score": 0.3, "inputs_provided": ["video"], "video_id": "v1",
    "video": {"video_id": "v1", "coordination_score": 0.66, "coordination_tier": "elevated",
              "clusters": [{"method": "co_engagement", "members": ["a", "b"], "score": 0.7, "evidence": ["tight"]}],
              "thread_scan": {"overall_probability": 0.5, "tier": "moderate"},
              "commenters": [
                  {"external_id": "a", "handle": "@a", "overall_probability": 0.8, "tier": "high",
                   "confidence": 0.6, "signals": [{"name": "temporal", "probability": 0.8, "evidence": ["x"]}]},
                  {"external_id": "b", "handle": "@b", "overall_probability": 0.55, "tier": "elevated",
                   "coordination_adjusted_probability": 0.62,
                   "signals": [{"name": "temporal", "probability": 0.5}]}]},
}


@pytest.fixture(autouse=True)
def _fresh(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", _API_KEY)
    monkeypatch.delenv("HF_TOKEN", raising=False)
    reset_db_for_tests("sqlite:///:memory:")
    yield


def _prod_settings():
    return SimpleNamespace(
        analyst_enabled=True, analyst_provider="openrouter", openrouter_preset=_PRESET,
        openrouter_model=None, openrouter_base_url="https://openrouter.ai/api/v1/chat/completions",
        openrouter_structured_output=True, openrouter_referer=None, openrouter_title=None,
        analyst_endpoint_url=None, analyst_hf_repo="Andrewexiga/omi-analyst-v1", analyst_hf_revision=None,
        analyst_prompt_version=None, analyst_model_id="mistralai/Mistral-7B-Instruct-v0.3",
        analyst_timeout_seconds=30.0, analyst_max_retries=0, analyst_endpoint_api="messages",
        analyst_cost_per_1k_tokens_usd=0.0, analyst_prompt_assembly="registry",
        memory_persistence_enabled=False, memory_database_url=None)


def _model_output(commenter_assessments):
    domains = {k: {"assessment": "reasoning present", "citations": ["A1"]} for k in COMPREHENSIVE_SECTION_KEYS}
    out = {
        "verdict": "mixed", "confidence_band": "moderate",
        "confidence_rationale": "single-axis temporal over thin data",
        "headline": "Cadence unusually regular.",
        "assessment": "Consistent with mechanical regularity. Probabilistic; the analyst decides.",
        "evidence_for": [{"signal": "temporal", "claim": "low variance", "evidence_refs": ["A1"]}],
        "evidence_against": [{"signal": "community", "claim": "modest footprint", "evidence_refs": ["A1"]}],
        "uncertainty": ["thin data"], "what_would_change_this": ["more posts"],
        "limits_statement": "Probabilistic; the human analyst sets the final verdict.",
        **domains,
    }
    if commenter_assessments is not None:
        out[COMPREHENSIVE_COMMENTER_ASSESSMENTS_KEY] = commenter_assessments
    return out


class _Resp:
    def __init__(self, body): self._body = body
    def __enter__(self): return self
    def __exit__(self, *a): return False
    def read(self): return self._body
    status = 200


def _or_body(obj):
    return json.dumps({"id": "gen-1", "model": "openai/gpt-5-mini",
                       "choices": [{"message": {"role": "assistant", "content": json.dumps(obj)}}],
                       "usage": {"prompt_tokens": 1800, "completion_tokens": 320, "total_tokens": 2120}}).encode()


def _run(model_obj):
    with patch("app.reasoning.model_providers.openrouter.urllib.request.urlopen",
               lambda req, timeout=None: _Resp(_or_body(model_obj))):
        return analyst.assess_payload(_PAYLOAD, ref="sub_ca", platform="youtube", settings=_prod_settings())


# =========================================================================== #
# Schema + contract
# =========================================================================== #
def test_schema_carries_optional_commenter_assessments_array():
    s = comprehensive_investigation_canonical_schema()
    assert COMPREHENSIVE_COMMENTER_ASSESSMENTS_KEY in s["properties"]
    assert COMPREHENSIVE_COMMENTER_ASSESSMENTS_KEY not in s["required"]   # optional — channel-only never fails
    item = s["properties"][COMPREHENSIVE_COMMENTER_ASSESSMENTS_KEY]["items"]
    assert item["required"] == ["ref", "assessment"]                     # echo discipline: no suspicion number
    assert "suspicion_probability" not in item["properties"]


def test_output_contract_instructs_the_array():
    c = comprehensive_investigation_response_contract()
    assert COMPREHENSIVE_COMMENTER_ASSESSMENTS_KEY in c
    assert "one item per account alias" in c.lower()


# =========================================================================== #
# End-to-end: validate + echo-join
# =========================================================================== #
def test_commenter_assessments_survive_and_are_echo_joined():
    out = _run(_model_output([
        {"ref": "A1", "assessment": "A1 posts on a mechanically regular cadence.", "citations": ["A1"]},
        {"ref": "A2", "assessment": "A2 has a lighter footprint; weaker signal.", "citations": ["A2"]},
    ]))
    assert out["investigation_trace"]["model_backed"] is True
    rows = out["commenter_assessments"]
    assert len(rows) == 2
    by_handle = {r.get("handle"): r for r in rows}
    assert set(by_handle) == {"@a", "@b"}
    # model prose survived
    assert "mechanically regular" in by_handle["@a"]["assessment"]
    # engine numbers were JOINED (never emitted by the model): @a echoes overall, @b echoes the
    # coordination-adjusted probability.
    assert by_handle["@a"]["suspicion_tier"] == "high"
    assert by_handle["@a"]["suspicion_probability"] == 0.8
    assert by_handle["@b"]["suspicion_probability"] == 0.62
    assert all(r["resolved"] is True for r in rows)


def test_unresolved_alias_is_kept_but_flagged():
    out = _run(_model_output([
        {"ref": "A1", "assessment": "A1 regular cadence.", "citations": ["A1"]},
        {"ref": "A99", "assessment": "phantom account not in the legend.", "citations": []},
    ]))
    rows = out["commenter_assessments"]
    assert len(rows) == 2                                                # never dropped
    bad = next(r for r in rows if r["ref"] == "A99")
    assert bad["resolved"] is False
    assert "handle" not in bad                                          # no fabricated identity/number


def test_response_without_the_array_still_validates():
    out = _run(_model_output(None))
    assert out["investigation_trace"]["model_backed"] is True           # optional — absence is fine
    assert out["commenter_assessments"] == []
