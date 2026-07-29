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
        "verdict": "mixed", "omi_score": 68, "suspicion_tier": "elevated", "confidence_band": "moderate",
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
    # AI-first per-account scoring: each account carries its OWN omi_score + tier (the AI produces
    # them), the eight-dimension breakdown behind that score, and one confidence for the account.
    assert item["required"] == [
        "ref", "omi_score", "suspicion_tier", "confidence", "signals", "assessment",
    ]
    assert item["properties"]["omi_score"]["type"] == "integer"
    assert item["properties"]["omi_score"]["maximum"] == 100
    assert item["properties"]["suspicion_tier"]["enum"] == ["low", "moderate", "elevated", "high"]
    assert "suspicion_probability" not in item["properties"]


def test_every_account_must_carry_all_eight_signals():
    """Exactly eight, no more and no fewer.

    An optional or short list would let the model quietly skip the dimensions it finds hard, which
    are precisely the ones a reader wants explained.
    """
    from app.reasoning.prompts.comprehensive_investigation_template import (
        COMPREHENSIVE_SIGNAL_NAMES,
    )
    s = comprehensive_investigation_canonical_schema()
    item = s["properties"][COMPREHENSIVE_COMMENTER_ASSESSMENTS_KEY]["items"]
    sig = item["properties"]["signals"]

    assert sig["minItems"] == len(COMPREHENSIVE_SIGNAL_NAMES) == 8
    assert sig["maxItems"] == 8
    assert sig["items"]["properties"]["name"]["enum"] == list(COMPREHENSIVE_SIGNAL_NAMES)
    assert sig["items"]["required"] == ["name", "score", "reason"]


def test_a_signal_score_may_be_null_but_confidence_may_not():
    """null score = "this dimension's evidence was never collected", which must stay expressible.

    Forcing a number there would make the model invent one for an account with no posting history,
    turning "we could not tell" into a measurement. Account confidence is different: it is always
    knowable, because how much evidence arrived is always knowable.
    """
    s = comprehensive_investigation_canonical_schema()
    item = s["properties"][COMPREHENSIVE_COMMENTER_ASSESSMENTS_KEY]["items"]

    assert item["properties"]["signals"]["items"]["properties"]["score"]["type"] == ["integer", "null"]
    assert item["properties"]["confidence"]["type"] == "integer"
    assert item["properties"]["confidence"]["maximum"] == 100


def test_output_contract_instructs_the_array():
    c = comprehensive_investigation_response_contract()
    assert COMPREHENSIVE_COMMENTER_ASSESSMENTS_KEY in c
    assert "every account alias" in c.lower()          # complete coverage — one item per account, no sampling


# =========================================================================== #
# End-to-end: validate + echo-join
# =========================================================================== #
def test_commenter_assessments_survive_and_are_echo_joined():
    out = _run(_model_output([
        {"ref": "A1", "omi_score": 82, "suspicion_tier": "high",
         "assessment": "A1 posts on a mechanically regular cadence, with comment timestamps landing "
                       "suspiciously close to a fixed interval across multiple threads, a pattern far more "
                       "consistent with scheduled or automated posting than an organic browsing habit from "
                       "a real person replying whenever they happen to be online.", "citations": ["A1"]},
        {"ref": "A2", "omi_score": 40, "suspicion_tier": "moderate",
         "assessment": "A2 has a noticeably lighter footprint than A1: its posting cadence shows some "
                       "irregularity, follower and following counts sit in an unremarkable range, and there "
                       "is not yet enough independently corroborating evidence to push this account higher "
                       "or lower than a moderate read at this time.", "citations": ["A2"]},
    ]))
    assert out["investigation_trace"]["model_backed"] is True
    rows = out["commenter_assessments"]
    assert len(rows) == 2
    by_handle = {r.get("handle"): r for r in rows}
    assert set(by_handle) == {"@a", "@b"}
    # model prose survived
    assert "mechanically regular" in by_handle["@a"]["assessment"]
    # AI-first: the per-account OMI score + tier are the MODEL'S (not the engine's), scored per account
    assert by_handle["@a"]["omi_score"] == 82 and by_handle["@a"]["suspicion_tier"] == "high"
    assert by_handle["@b"]["omi_score"] == 40 and by_handle["@b"]["suspicion_tier"] == "moderate"
    # the engine probability rides along ONLY as a secondary reference, never as the account's score
    assert by_handle["@a"]["engine_probability"] == 0.8
    assert by_handle["@b"]["engine_probability"] == 0.62
    assert all(r["resolved"] is True for r in rows)


def test_unresolved_alias_is_kept_but_flagged():
    out = _run(_model_output([
        {"ref": "A1", "omi_score": 55, "suspicion_tier": "elevated",
         "assessment": "A1 shows a regular cadence with several moderately suspicious signals: comment "
                       "timing clusters tightly, the account's history is thin, and there is not enough "
                       "independent corroboration to push this score higher than an elevated-but-uncertain "
                       "read at this time.", "citations": ["A1"]},
        {"ref": "A99", "omi_score": 70, "suspicion_tier": "elevated",
         "assessment": "This is a phantom account reference that does not appear anywhere in the "
                       "evidence's alias legend, so its per-account score and reasoning cannot be resolved "
                       "to any real commenter identity, yet the model's raw output must still be preserved "
                       "rather than silently dropped.", "citations": []},
    ]))
    rows = out["commenter_assessments"]
    assert len(rows) == 2                                                # never dropped
    bad = next(r for r in rows if r["ref"] == "A99")
    assert bad["resolved"] is False
    assert bad["omi_score"] == 70                                       # the model's per-account score survives
    assert "handle" not in bad                                          # no fabricated identity
    assert "engine_probability" not in bad                             # unresolved → no engine number


def test_response_without_the_array_still_validates():
    out = _run(_model_output(None))
    assert out["investigation_trace"]["model_backed"] is True           # optional — absence is fine
    assert out["commenter_assessments"] == []
