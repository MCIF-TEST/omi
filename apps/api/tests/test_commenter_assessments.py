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
        # No alias appears in either paragraph, and neither refers to the other account. That is now
        # a HARD grounding rule (check_alias_in_prose), so a fixture written the old way would be
        # withheld rather than served, which is exactly what the live export was doing.
        {"ref": "A1", "omi_score": 82, "suspicion_tier": "high",
         "assessment": "This account posts on a mechanically regular cadence, with comment timestamps "
                       "landing suspiciously close to a fixed interval across multiple threads, a pattern "
                       "far more consistent with scheduled or automated posting than an organic browsing "
                       "habit from a real person replying whenever they happen to be online.",
         "citations": ["A1"]},
        {"ref": "A2", "omi_score": 40, "suspicion_tier": "moderate",
         "assessment": "The footprint here is lighter: posting cadence shows some irregularity, follower "
                       "and following counts sit in an unremarkable range, and there is not yet enough "
                       "independently corroborating evidence to push this account higher or lower than a "
                       "moderate read at this time.", "citations": ["A2"]},
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


# =========================================================================== #
# The eight model-scored signals, END TO END
#
# These exist because the first cut of per-signal scoring was tested only at the two ends: the
# schema declared `signals`/`confidence`, and `_normalise_signals` was unit-tested in isolation.
# Nothing asserted that a model response carrying signals still had them by the time the assessment
# was served. It did not: `coerce_comprehensive_object` built each per-account row from a hardcoded
# four-field allow-list, so both new fields were deleted in between. Every account rendered eight
# "n/a" rows and nothing failed anywhere to say so.
#
# So: assert against the SERVED assessment, never against an intermediate.
# =========================================================================== #
from app.reasoning.prompts.comprehensive_investigation_template import (  # noqa: E402
    COMPREHENSIVE_SIGNAL_NAMES,
)

_LONG_REASON = "an ordinary reading with nothing unusual in it either way"


def _signals(**overrides) -> list[dict]:
    """All eight at score 20, with named dimensions overridden."""
    return [
        {"name": n, "score": overrides.get(n, 20), "reason": _LONG_REASON}
        for n in COMPREHENSIVE_SIGNAL_NAMES
    ]


def _scored_account(ref: str, **over) -> dict:
    row = {
        "ref": ref, "omi_score": 40, "suspicion_tier": "moderate", "confidence": 70,
        "signals": _signals(),
        "assessment": ("A steady account with an unremarkable posting history and no strong tells "
                       "in either direction, so it lands mid-range on the evidence available."),
        "citations": [ref],
    }
    row.update(over)
    return row


def _a1(out: dict) -> dict:
    return next(r for r in out["commenter_assessments"] if r["ref"] == "A1")


def test_the_eight_signals_reach_the_served_assessment():
    """The regression test for the field shredder. Signals and confidence must survive the whole
    path: model response, structural coercion, echo-join, served assessment."""
    out = _run(_model_output([_scored_account("A1")]))

    row = _a1(out)
    assert row["confidence"] == 70
    assert [s["name"] for s in row["signals"]] == list(COMPREHENSIVE_SIGNAL_NAMES)
    assert all(s["score"] == 20 for s in row["signals"])
    assert all(s["reason"] == _LONG_REASON for s in row["signals"])


def test_a_dimension_the_model_omitted_arrives_null_not_zero():
    """Seven returned, eight rendered. The missing one is explicitly unscored, because zero would
    read as "this dimension looks like a real person" rather than "we never collected it"."""
    out = _run(_model_output([_scored_account("A1", signals=_signals()[:7])]))

    signals = _a1(out)["signals"]
    assert len(signals) == 8
    missing = COMPREHENSIVE_SIGNAL_NAMES[7]
    by_name = {s["name"]: s for s in signals}
    assert by_name[missing]["score"] is None
    assert all(by_name[n]["score"] == 20 for n in COMPREHENSIVE_SIGNAL_NAMES[:7])


def test_an_explicit_null_score_survives_as_null():
    """The documented case: no posting history collected, so rhythm is unscorable. Must stay null
    all the way to the UI rather than being coerced to a number anywhere along the path."""
    sig = _signals()
    sig[0] = {"name": COMPREHENSIVE_SIGNAL_NAMES[0], "score": None,
              "reason": "no posting history was collected for this account"}
    out = _run(_model_output([_scored_account("A1", signals=sig)]))

    first = _a1(out)["signals"][0]
    assert first["score"] is None
    assert "no posting history" in first["reason"]


def test_junk_scores_are_bounded_rather_than_dropped():
    """A model that returns 900 or 42.7 has still made a real judgment about that dimension. Clamp
    and round it; dropping the row would cost the reader a dimension over a formatting slip."""
    sig = _signals()
    sig[0] = {**sig[0], "score": 900}
    sig[1] = {**sig[1], "score": 42.7}
    out = _run(_model_output([_scored_account("A1", signals=sig)]))

    scores = {s["name"]: s["score"] for s in _a1(out)["signals"]}
    assert scores[COMPREHENSIVE_SIGNAL_NAMES[0]] == 100
    assert scores[COMPREHENSIVE_SIGNAL_NAMES[1]] == 43


def test_an_unknown_dimension_name_is_dropped_and_its_slot_left_unscored():
    """The model inventing a ninth dimension must not shift the other eight or smuggle in a row the
    UI has no metadata for. The slot it displaced reports honestly as unscored."""
    sig = _signals()
    sig[0] = {"name": "vibes", "score": 50, "reason": "a dimension that does not exist in the list"}
    out = _run(_model_output([_scored_account("A1", signals=sig)]))

    signals = _a1(out)["signals"]
    assert [s["name"] for s in signals] == list(COMPREHENSIVE_SIGNAL_NAMES)
    assert signals[0]["score"] is None


def test_a_missing_signal_block_does_not_floor_the_investigation():
    """A non-compliant account degrades alone. The whole run falling back to the Floor would mean a
    customer paid for an AI investigation and got deterministic prose because one account's array
    was malformed."""
    out = _run(_model_output([
        _scored_account("A1", signals="not-a-list", confidence="high"),
        _scored_account("A2"),
    ]))

    assert out["investigation_trace"]["model_backed"] is True
    assert len(out["commenter_assessments"]) == 2
    bad = _a1(out)
    assert [s["name"] for s in bad["signals"]] == list(COMPREHENSIVE_SIGNAL_NAMES)
    assert all(s["score"] is None for s in bad["signals"])
    assert bad["confidence"] is None                       # unparseable, so honestly absent
    good = next(r for r in out["commenter_assessments"] if r["ref"] == "A2")
    assert all(s["score"] == 20 for s in good["signals"])   # its neighbour is untouched


def test_the_coercion_passes_through_every_declared_per_account_field():
    """The class-level guard, not just the instance.

    `coerce_comprehensive_object` used to rebuild each per-account row from a hardcoded field list,
    which silently deleted anything added to the schema later. It is now driven by the schema, so
    this asserts the general property: every property the item schema declares survives coercion.
    A future field then cannot be lost by nobody remembering to update that list.
    """
    from app.governor.comprehensive import coerce_comprehensive_model_output

    schema = comprehensive_investigation_canonical_schema()
    item_props = schema["properties"][COMPREHENSIVE_COMMENTER_ASSESSMENTS_KEY]["items"]["properties"]

    coerced = coerce_comprehensive_model_output(
        _model_output([_scored_account("A1")]),
        schema=schema, section_keys=COMPREHENSIVE_SECTION_KEYS,
    )
    row = coerced["commenter_assessments"][0]
    assert set(item_props) - set(row) == set(), (
        "coercion dropped per-account fields the schema declares: "
        f"{sorted(set(item_props) - set(row))}"
    )
