"""Batched analyst inference — the 50-account cap per OpenRouter request.

A selection larger than the per-request account cap is split into ≤cap batches, run as PARALLEL
inferences, merged strictly first-to-last, and persisted progressively so the UI can render batch 1's
accounts while later batches still generate. These tests pin the pure core (split + ordered merge)
and the progressive semantics — no model, no network.
"""
from __future__ import annotations

from app.reasoning.analyst import _merge_batch_parts, _split_batches


def _payload(n_accounts: int) -> dict:
    return {
        "video": {
            "url": "https://x.com/i/status/1",
            "commenters": [{"handle": f"user{i}", "external_id": f"id{i}"} for i in range(n_accounts)],
        },
        "overall_probability": 0.4,
    }


def _part(*, scores: list[int], overall: int, model_backed: bool = True,
          in_tok: int = 100, cost: float = 0.01) -> dict:
    return {
        "omi_score": overall,
        "suspicion_tier": "moderate",
        "verdict": "mixed",
        "commenter_assessments": [
            {"ref": f"A{i+1}", "omi_score": s, "suspicion_tier": "low", "assessment": f"account {i} read"}
            for i, s in enumerate(scores)
        ],
        "evidence_for": [{"signal": f"s{overall}", "claim": f"claim-{overall}", "evidence_refs": ["A1"]}],
        "completion": {"complete": True, "represented_commenters": len(scores),
                       "assessed_commenters": len(scores)},
        "investigation_trace": {"model_backed": model_backed, "input_tokens": in_tok,
                                "output_tokens": 50, "total_tokens": in_tok + 50,
                                "endpoint_cost_usd": cost, "endpoint_request_id": f"req-{overall}"},
        "governance": {"provider": "openrouter"},
    }


# --------------------------------------------------------------------------- #
# Split
# --------------------------------------------------------------------------- #
def test_small_selection_is_not_split():
    assert _split_batches(_payload(50), 50) is None
    assert _split_batches(_payload(1), 50) is None


def test_large_selection_splits_in_order_at_the_cap():
    chunks = _split_batches(_payload(120), 50)
    assert chunks is not None and len(chunks) == 3
    sizes = [len(c["video"]["commenters"]) for c in chunks]
    assert sizes == [50, 50, 20]
    # Selection order preserved across the boundary: chunk 2 starts where chunk 1 ended.
    assert chunks[0]["video"]["commenters"][0]["handle"] == "user0"
    assert chunks[1]["video"]["commenters"][0]["handle"] == "user50"
    assert chunks[2]["video"]["commenters"][-1]["handle"] == "user119"
    # Non-account context rides along; the cached-assessment key never leaks into a chunk.
    assert all(c["overall_probability"] == 0.4 for c in chunks)


# --------------------------------------------------------------------------- #
# Merge — ordered, progressive, telemetry-summing
# --------------------------------------------------------------------------- #
def test_merge_concatenates_accounts_first_to_last():
    parts = [_part(scores=[10, 20], overall=15), _part(scores=[80, 90], overall=85)]
    merged = _merge_batch_parts(parts, batch_size=2, done=2)
    assert merged is not None
    scores = [a["omi_score"] for a in merged["commenter_assessments"]]
    assert scores == [10, 20, 80, 90]
    assert merged["batching"] == {"total": 2, "done": 2, "batch_size": 2, "complete": True}


def test_merge_overall_is_account_weighted_mean_of_batch_overalls():
    # 2 accounts at overall 10 + 2 accounts at overall 90 -> 50; tier follows the band.
    parts = [_part(scores=[10, 10], overall=10), _part(scores=[90, 90], overall=90)]
    merged = _merge_batch_parts(parts, batch_size=2, done=2)
    assert merged["omi_score"] == 50
    assert merged["suspicion_tier"] == "elevated"


def test_partial_merge_reports_progress_and_incomplete():
    parts = [_part(scores=[10], overall=10), None, None]
    merged = _merge_batch_parts(parts, batch_size=1, done=1)
    assert merged is not None
    assert len(merged["commenter_assessments"]) == 1
    assert merged["batching"] == {"total": 3, "done": 1, "batch_size": 1, "complete": False}
    assert merged["completion"]["complete"] is False


def test_merge_sums_usage_and_collects_batch_traces():
    parts = [_part(scores=[10], overall=10, in_tok=100, cost=0.01),
             _part(scores=[20], overall=20, in_tok=200, cost=0.02)]
    merged = _merge_batch_parts(parts, batch_size=1, done=2)
    tr = merged["investigation_trace"]
    assert tr["input_tokens"] == 300
    assert abs(tr["endpoint_cost_usd"] - 0.03) < 1e-9
    assert tr["inference_count"] == 2
    assert [b["batch"] for b in tr["batches"]["traces"]] == [1, 2]
    assert tr["model_backed"] is True


def test_a_floored_batch_marks_the_merge_not_model_backed():
    parts = [_part(scores=[10], overall=10), _part(scores=[20], overall=20, model_backed=False)]
    merged = _merge_batch_parts(parts, batch_size=1, done=2)
    assert merged["investigation_trace"]["model_backed"] is False


def test_merge_with_no_parts_is_none():
    assert _merge_batch_parts([None, None], batch_size=50, done=0) is None
