"""Runtime instrumentation — per-investigation metrics + cache-effectiveness counters.

The architecture-refactor sprint's measurement mandate: every governed assessment carries an
additive ``metrics`` block (stage latencies + labeled token/cost estimates), and the AI runtime
exposes cache effectiveness. These are observability only — they never change the assessment, the
Governor, or the deterministic floor.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.reasoning import analyst
from app.storage.db import get_session, reset_db_for_tests
from app.storage.repository import AccountRepository


def _settings(**over):
    base = dict(analyst_enabled=True, analyst_endpoint_url=None,
                analyst_hf_repo="Andrewexiga/omi-analyst-v1", analyst_hf_revision=None,
                analyst_prompt_version=None, analyst_model_id="mistralai/Mistral-7B-Instruct-v0.3",
                analyst_timeout_seconds=30.0, analyst_max_retries=0, analyst_endpoint_api="generate",
                analyst_cost_per_1k_tokens_usd=0.0, memory_persistence_enabled=False,
                memory_database_url=None)
    base.update(over)
    return SimpleNamespace(**base)


_PAYLOAD = {"overall_probability": 0.74, "overall_tier": "elevated", "confidence": 0.6,
            "contributions": [{"name": "temporal", "impact": 0.5, "direction": "raises"}],
            "video": {"clusters": [{"method": "co_engagement", "members": ["@a", "@b", "@c"]}]}}


@pytest.fixture(autouse=True)
def _fresh():
    reset_db_for_tests("sqlite:///:memory:")
    analyst._cache_stats.update(served_from_cache=0, generated=0)
    yield
    reset_db_for_tests("sqlite:///:memory:")


# --------------------------------------------------------------------------- #
# The per-assessment metrics block
# --------------------------------------------------------------------------- #
def test_assessment_carries_a_metrics_block_on_the_floor_path():
    out = analyst.assess_payload(_PAYLOAD, ref="sub_m", platform="youtube", settings=_settings())
    assert out is not None
    m = out["metrics"]
    for k in ("total_reasoning_ms", "model_ms", "governor_and_assembly_ms", "memory_store_ms",
              "memory_durable", "model_backed", "est_completion_tokens", "prompt_version", "prompt_hash"):
        assert k in m, k
    assert m["model_backed"] is False                # no endpoint -> deterministic floor, not model-backed
    assert m["model_ms"] >= 0.0                       # provider latency (floor here); model_backed is the flag
    assert m["est_completion_tokens"] > 0
    assert m["total_reasoning_ms"] >= 0.0
    assert m["prompt_version"] == "v1" and m["prompt_hash"].startswith("ph:")


def test_metrics_never_disturb_the_governed_assessment():
    out = analyst.assess_payload(_PAYLOAD, ref="sub_m", platform="youtube", settings=_settings())
    # governance stays intact and authoritative; metrics is a sibling, not a replacement.
    assert out["governance"]["verdict"] in ("permit", "reject")
    assert out["suspicion_probability"] == 0.74     # engine number preserved (echo discipline)


def test_cost_estimate_reported_only_when_a_rate_is_set():
    off = analyst.assess_payload(_PAYLOAD, ref="s1", platform="youtube", settings=_settings())
    assert off["metrics"]["est_completion_cost_usd"] is None
    on = analyst.assess_payload(_PAYLOAD, ref="s2", platform="youtube",
                                settings=_settings(analyst_cost_per_1k_tokens_usd=0.20))
    assert on["metrics"]["est_completion_cost_usd"] is not None
    assert on["metrics"]["est_completion_cost_usd"] > 0.0


# --------------------------------------------------------------------------- #
# Cache effectiveness — generated vs served-from-cache
# --------------------------------------------------------------------------- #
def test_runtime_metrics_counts_generate_then_cache_hit(monkeypatch):
    monkeypatch.setenv("OMI_ANALYST_ENABLED", "true")
    from app.core.config import get_settings
    get_settings.cache_clear()
    with get_session() as s:
        AccountRepository(s).create_investigation(
            user_id=1, slug="inv_metrics", label="m", input_url="https://youtube.com/watch?v=x",
            target_id="x", kind="comprehensive", overall_probability=0.74, overall_tier="elevated",
            summary="m", quota_used=0, payload_json=_PAYLOAD)

    # first call generates (cache miss), second returns the cache (hit)
    analyst.generate_and_persist("inv_metrics", 1, False)
    analyst.generate_and_persist("inv_metrics", 1, False)
    rm = analyst.runtime_metrics()["assessment_cache"]
    assert rm["generated"] == 1
    assert rm["served_from_cache"] == 1
    assert rm["total"] == 2 and rm["hit_rate"] == 0.5
    get_settings.cache_clear()


def test_runtime_metrics_shape_is_stable():
    rm = analyst.runtime_metrics()
    assert set(rm["assessment_cache"]) == {"served_from_cache", "generated", "total", "hit_rate"}
