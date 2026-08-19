"""Phase 5H — full-investigation AI coverage: every commenter is eligible for reasoning, the completion
budget is sized dynamically, and completeness is verified + reported (never silently truncated).

Certifies (mocked transport, no live call): the dynamic completion budget scales with commenter count and
clamps; the raised evidence ceiling shows EVERY commenter to the model (10 / 50 / 150) so all receive an
assessment; ``finish_reason == "length"`` is detected and marked ``truncated_output`` (with remaining work,
never a silent drop); a normal stop that leaves commenters unassessed is marked ``missing_assessments``; and
the Floor path surfaces no per-account content and reports completeness as not-applicable.
"""
from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.reasoning import analyst
from app.reasoning.completion import (
    COMPLETION_CEILING_TOKENS,
    COMPLETION_FLOOR_TOKENS,
    commenter_capacity,
    completion_budget,
    verify_completion,
)
from app.reasoning.prompts.comprehensive_investigation_template import COMPREHENSIVE_SECTION_KEYS
from app.storage.db import reset_db_for_tests

_API_KEY = "sk-or-v1-SECRET-0000"


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", _API_KEY)
    monkeypatch.delenv("HF_TOKEN", raising=False)
    yield


# =========================================================================== #
# Dynamic completion budget (pure)
# =========================================================================== #
def test_completion_budget_scales_and_clamps():
    """The budget is a flat 50,000 output tokens for every request this product makes.

    THESE ASSERTIONS CHANGED WITH THE SYSTEM, and the reason is worth stating. They used to describe
    a budget that grew with the investigation, because a single inference carried the whole scan and
    the ceiling sat far above anything real (150,000, set temporarily to measure true per-scan cost).
    Neither is true now: work is split into fixed 25-account batches, and ceiling == floor == 50,000,
    so the linear formula between them can never be reached. Asserting growth across sizes that all
    clamp to the same number would be asserting a behaviour the product no longer has.
    """
    assert completion_budget(0) == COMPLETION_FLOOR_TOKENS         # even 0 commenters gets the full synthesis
    # Never DECREASING with size, which is the property that survives clamping.
    assert completion_budget(10) <= completion_budget(50) <= completion_budget(150)
    # Flat, at every size the batcher can produce and well beyond it.
    assert COMPLETION_FLOOR_TOKENS == COMPLETION_CEILING_TOKENS
    for n in (0, 1, 17, 25, 150, 10**9):
        assert completion_budget(n) == COMPLETION_CEILING_TOKENS, n
    # The ceiling is what wins, so a deploy that lowers it to bound spend is honoured even below the
    # floor. Cost control must never be silently overridden by a floor nobody remembered to move.
    assert completion_budget(150, ceiling=8_000) == 8_000


def test_commenter_capacity_comfortably_exceeds_one_batch():
    """Capacity is only ever asked about ONE REQUEST, and a request is one batch.

    This used to assert `cap > 150`, from when a single inference carried a whole 150-commenter scan.
    A request now carries `batch_plan.BATCH_SIZE` accounts, so that is the number capacity has to
    clear, and tying the assertion to the constant keeps the two from drifting apart silently.
    """
    from app.reasoning.batch_plan import BATCH_SIZE

    cap = commenter_capacity()
    assert completion_budget(cap) <= COMPLETION_CEILING_TOKENS
    assert cap > BATCH_SIZE * 3, (
        f"one request carries {BATCH_SIZE} accounts; a capacity of {cap} leaves no headroom"
    )


def test_a_full_batch_fits_under_the_ceiling_without_truncation():
    from app.reasoning.batch_plan import BATCH_SIZE

    assert completion_budget(BATCH_SIZE) == COMPLETION_CEILING_TOKENS
    # Measured live: a 25-account batch spent 12,970 output tokens. The cap is the margin, and it is
    # a cap rather than a reservation, so the margin is free until it is used.
    assert completion_budget(BATCH_SIZE) > 12_970 * 2


def test_completion_budget_honors_a_custom_ceiling():
    # The knobs are env-overridable (OMI_ANALYST_COMPLETION_*): a lower ceiling caps spend immediately.
    assert completion_budget(150, ceiling=8000) == 8000            # clamps down to the tighter cap
    assert completion_budget(1, base=1000, per_commenter=10, floor=500, ceiling=9000) == 1010


# =========================================================================== #
# Completion verification (pure)
# =========================================================================== #
def test_verify_complete():
    s = verify_completion(model_backed=True, finish_reason="stop", represented_commenters=150,
                          assessed_commenters=150, omitted_input_commenters=0)
    assert s.complete is True and s.incomplete_kind is None and s.estimated_remaining_commenters == 0


def test_verify_truncated_takes_precedence():
    s = verify_completion(model_backed=True, finish_reason="length", represented_commenters=150,
                          assessed_commenters=100, omitted_input_commenters=0)
    assert s.complete is False and s.incomplete_kind == "truncated_output"
    assert s.estimated_remaining_commenters == 50                   # not silently dropped — remaining recorded


def test_verify_missing_assessments():
    s = verify_completion(model_backed=True, finish_reason="stop", represented_commenters=150,
                          assessed_commenters=140, omitted_input_commenters=0)
    assert s.incomplete_kind == "missing_assessments" and s.missing_commenters == 10


def test_verify_omitted_input():
    s = verify_completion(model_backed=True, finish_reason="stop", represented_commenters=150,
                          assessed_commenters=150, omitted_input_commenters=20)
    assert s.incomplete_kind == "omitted_input" and s.estimated_remaining_commenters == 20


def test_verify_floor_not_applicable():
    s = verify_completion(model_backed=False, finish_reason=None, represented_commenters=150,
                          assessed_commenters=0, omitted_input_commenters=0)
    assert s.complete is False and s.incomplete_kind is None and "not produced" in s.reason.lower()


# =========================================================================== #
# End-to-end coverage (mocked transport)
# =========================================================================== #
def _payload(n: int) -> dict:
    commenters = [{
        "external_id": f"c{i}", "handle": f"@user{i}",
        "overall_probability": 0.3 + (i % 5) * 0.1, "tier": ["low", "moderate", "elevated", "high"][i % 4],
        "confidence": 0.5, "signals": [{"name": "temporal", "probability": 0.4 + (i % 3) * 0.1}]}
        for i in range(n)]
    return {
        "overall_probability": 0.6, "overall_tier": "elevated", "confidence": 0.55,
        "convergence_score": 0.3, "inputs_provided": ["video"], "video_id": "v1",
        "video": {"video_id": "v1", "coordination_score": 0.5, "coordination_tier": "moderate",
                  "clusters": [], "thread_scan": {"overall_probability": 0.4, "tier": "moderate"},
                  "commenters": commenters}}


def _model_output(num_assessments: int) -> dict:
    domains = {k: {"assessment": "domain reasoning", "citations": []} for k in COMPREHENSIVE_SECTION_KEYS}
    ca = [{"ref": f"A{i + 1}", "omi_score": 55, "suspicion_tier": "elevated",
           "assessment": (
               f"Account A{i + 1} was reviewed on its own evidence: its posting cadence, follower/"
               f"following balance, and the content of its own comments were all weighed independently of "
               f"any other account in this thread before landing on this elevated-but-uncertain read, "
               f"which is not derived from a default or from another account's score."),
           "citations": []}
          for i in range(num_assessments)]
    return {
        "verdict": "mixed", "omi_score": 68, "suspicion_tier": "elevated", "confidence_band": "moderate",
        "confidence_rationale": "single-axis temporal over thin data; no exculpatory signal was present.",
        "headline": "Investigation-level read.", "assessment": "Executive synthesis. Probabilistic.",
        "evidence_for": [{"signal": "temporal", "claim": "low variance", "evidence_refs": ["A1"]}],
        "evidence_against": [], "uncertainty": ["thin"], "what_would_change_this": ["more"],
        "limits_statement": "The human analyst decides.", "commenter_assessments": ca, **domains}


class _Resp:
    def __init__(self, b): self._b = b
    def __enter__(self): return self
    def __exit__(self, *a): return False
    def read(self): return self._b
    status = 200


def _or_body(obj, finish="stop"):
    return json.dumps({
        "id": "gen-1", "model": "openai/gpt-5-mini",
        "choices": [{"message": {"role": "assistant", "content": json.dumps(obj)}, "finish_reason": finish}],
        "usage": {"prompt_tokens": 5000, "completion_tokens": 4000, "total_tokens": 9000}}).encode()


_SETTINGS = SimpleNamespace(
    analyst_enabled=True, analyst_provider="openrouter", openrouter_preset="omi-master-v1",
    openrouter_model=None, openrouter_base_url="https://openrouter.ai/api/v1/chat/completions",
    openrouter_structured_output=True, openrouter_referer=None, openrouter_title=None,
    analyst_endpoint_url=None, analyst_hf_repo="Andrewexiga/omi-analyst-v1", analyst_hf_revision=None,
    analyst_prompt_version=None, analyst_model_id="mistralai/Mistral-7B-Instruct-v0.3",
    analyst_timeout_seconds=30.0, analyst_max_retries=0, analyst_endpoint_api="messages",
    analyst_cost_per_1k_tokens_usd=0.0, analyst_prompt_assembly="registry",
    memory_persistence_enabled=False, memory_database_url=None)


def _run(n_commenters: int, n_assessed: int, finish="stop") -> dict:
    reset_db_for_tests("sqlite:///:memory:")
    with patch("app.reasoning.model_providers.openrouter.urllib.request.urlopen",
               lambda req, timeout=None: _Resp(_or_body(_model_output(n_assessed), finish))):
        return analyst.assess_payload(_payload(n_commenters), ref="sub_x", platform="youtube",
                                      settings=_SETTINGS)


@pytest.mark.parametrize("n", [10, 50, 150])
def test_every_commenter_receives_reasoning(n):
    out = _run(n, n)
    tr = out["investigation_trace"]
    comp = out["completion"]
    assert tr["model_backed"] is True
    # all N shown to the model (no upstream sampling) and all N assessed
    assert tr["evidence_omitted_accounts"] == 0
    assert comp["represented_commenters"] == n
    assert comp["assessed_commenters"] == n
    assert comp["omitted_input_commenters"] == 0
    assert comp["complete"] is True and comp["incomplete_kind"] is None
    # dynamic budget was sized for THIS investigation
    assert comp["max_output_tokens"] == completion_budget(n)
    assert len([r for r in out["commenter_assessments"] if r["resolved"]]) == n
    # self-certification: schema + Governor + structured-JSON all certified on a complete run
    assert comp["schema_valid"] is True and comp["governor_valid"] is True
    assert comp["json_complete"] is True and comp["stopped_on_token_limit"] is False


def test_truncation_is_marked_not_silently_dropped():
    out = _run(150, 100, finish="length")            # model hit the ceiling: only 100 of 150 assessed
    comp = out["completion"]
    assert comp["complete"] is False
    assert comp["incomplete_kind"] == "truncated_output"
    assert comp["assessed_commenters"] == 100
    assert comp["estimated_remaining_commenters"] == 50
    assert out["investigation_trace"]["finish_reason"] == "length"
    # certification: the token-limit stop + incomplete JSON are recorded explicitly
    assert comp["stopped_on_token_limit"] is True and comp["json_complete"] is False


def test_normal_stop_with_missing_is_marked():
    out = _run(50, 40)                                # stopped normally but 10 unassessed
    comp = out["completion"]
    assert comp["incomplete_kind"] == "missing_assessments"
    assert comp["missing_commenters"] == 10


def test_floor_surfaces_no_per_account_content():
    # A response with NOTHING salvageable floors; per-account content must NOT leak, and completion is
    # reported as not-applicable. Coercion repairs harmless shape gaps, and a wrapper omitted while
    # per-account results ARE present is now salvaged from those results (see
    # test_wrapper_is_salvaged_from_per_account_results_...). To force a genuine Floor we remove the core
    # verdict AND leave no per-account results to derive an overall read from.
    bad = _model_output(50)
    del bad["verdict"]                                # missing core substance
    bad["commenter_assessments"] = []                # nothing to salvage a wrapper from → genuine Floor
    reset_db_for_tests("sqlite:///:memory:")
    with patch("app.reasoning.model_providers.openrouter.urllib.request.urlopen",
               lambda req, timeout=None: _Resp(_or_body(bad))):
        out = analyst.assess_payload(_payload(50), ref="sub_f", platform="youtube", settings=_SETTINGS)
    assert out["investigation_trace"]["model_backed"] is False
    assert out["commenter_assessments"] == []         # rejected model content never surfaced
    assert out["completion"]["complete"] is False
