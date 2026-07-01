"""Live AI integration — institutional memory reaches the production AI specialist (Sprint 021).

The highest-priority missing connection in the live pipeline: the production analyst passed
``store=None``, so the Qwen specialist reasoned with NO institutional memory. Now PriorContext is
retrieved and injected into the analyst's input as ``prior_context`` — labeled background, never
proof, with no citable evidence id. The deterministic provider ignores the key (so its output is
byte-identical — zero regression), while the Qwen provider serializes the whole bundle, so the live
model reasons with memory. Self-gating: an empty / disabled memory store injects nothing.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.evidence import Binder
from app.reasoning import analyst
from app.storage.db import reset_db_for_tests

NOW = datetime(2026, 6, 28, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def _fresh():
    reset_db_for_tests("sqlite:///:memory:")
    yield


def _payload() -> dict:
    return {
        "overall_probability": 0.7, "overall_tier": "elevated", "confidence": 0.6,
        "contributions": [{"name": "temporal", "impact": 0.4, "direction": "raises"}],
        "video": {"clusters": [{"method": "co_engagement", "members": ["@a", "@b", "@c", "@d"]}]},
    }


def _seeded_store():
    from app.memory.graph import MemoryStore
    store = MemoryStore()
    for i in range(3):
        store.ingest(candidate={"type": "BehavioralArchetype", "signature": ["temporal"],
                                "label": "bursty posting archetype"},
                     investigation=f"i{i}", stance="supports", evidence_refs=["d"],
                     independence_key=f"k{i}", at=NOW.isoformat())
    return store


def _app_bundle():
    return Binder().bind(_payload(), grain="comment_section", subject_ref="x", platform="youtube")


# --------------------------------------------------------------------------- #
# Retrieval + injection + memory boundary
# --------------------------------------------------------------------------- #
def test_prior_context_retrieved_and_carries_no_citable_ref():
    pc = analyst._retrieve_prior_context(_seeded_store(), _app_bundle(), now=NOW)
    assert pc and pc[0]["label"] == "bursty posting archetype"
    assert pc[0]["note"].startswith("institutional memory")
    # the memory boundary: a prior carries no resolvable ev/ko id, so the model cannot cite it.
    assert all("evidence_refs" not in p and "ev:" not in str(p) and "ko:" not in str(p) for p in pc)


def test_empty_store_injects_nothing():
    from app.memory.graph import MemoryStore
    assert analyst._retrieve_prior_context(MemoryStore(), _app_bundle(), now=NOW) == []
    assert analyst._retrieve_prior_context(None, _app_bundle()) == []


# --------------------------------------------------------------------------- #
# Zero regression on the deterministic path + Qwen actually sees the memory
# --------------------------------------------------------------------------- #
def test_deterministic_output_byte_identical_with_or_without_memory():
    import json
    impl = analyst._impl()
    pc = analyst._retrieve_prior_context(_seeded_store(), _app_bundle(), now=NOW)
    b_no = analyst.build_bundle(_payload(), ref="x", platform="youtube", impl=impl)
    b_yes = analyst.build_bundle(_payload(), ref="x", platform="youtube", impl=impl, prior_context=pc)
    assert "prior_context" in b_yes and "prior_context" not in b_no
    det = impl.DeterministicAnalystProvider()
    r_no = det.generate(b_no, impl.load_analyst_config()).response
    r_yes = det.generate(b_yes, impl.load_analyst_config()).response
    assert json.dumps(r_no, sort_keys=True) == json.dumps(r_yes, sort_keys=True)   # zero regression


def test_qwen_user_message_includes_the_memory():
    impl = analyst._impl()
    pc = analyst._retrieve_prior_context(_seeded_store(), _app_bundle(), now=NOW)
    b = analyst.build_bundle(_payload(), ref="x", platform="youtube", impl=impl, prior_context=pc)
    msg = impl.QwenAnalystProvider(endpoint_url="http://x", system_prompt="SYS").build_user_message(b)
    assert "prior_context" in msg and "bursty posting archetype" in msg


# --------------------------------------------------------------------------- #
# End-to-end: assess_payload wires the durable store through to the analyst
# --------------------------------------------------------------------------- #
def test_assess_payload_wires_memory_and_preserves_number(monkeypatch):
    monkeypatch.setattr(analyst, "analyst_enabled", lambda settings=None: True)
    import app.memory.repository as repo
    monkeypatch.setattr(repo, "get_memory_store", lambda settings=None: _seeded_store())
    out = analyst.assess_payload(_payload(), ref="sub_x", platform="youtube")
    assert out is not None
    # memory is context-only: the engine number is still echoed, the Governor still permitted.
    assert out["suspicion_probability"] == 0.7 and out["suspicion_tier"] == "elevated"
    assert out["governance"]["verdict"] == "permit"


def test_assess_payload_unaffected_when_memory_disabled(monkeypatch):
    """Default (no persistent memory): get_memory_store returns an empty store -> no prior_context."""
    monkeypatch.setattr(analyst, "analyst_enabled", lambda settings=None: True)
    out = analyst.assess_payload(_payload(), ref="sub_x", platform="youtube")
    assert out is not None and out["suspicion_probability"] == 0.7
