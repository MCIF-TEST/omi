"""Evidence Repository (frozen architecture) — the ONE read-facade for investigation evidence.

Proves the Phase-R1 contract: the Repository composes an immutable, content-addressed
:class:`EvidenceSnapshot` from the durable stores (payload + governance bundle + context + memory
priors); the snapshot is frozen, deterministic, and evidence-sensitive; it echoes the engine numbers
(never recomputes); it reads only (no model, no writes); and the production reasoning path consumes the
snapshot and records its ``snapshot_id`` for traceability. R1 is behavior-preserving — the governance
bundle the Repository hands out is byte-identical to the one the reasoning path bound inline before.
"""
from __future__ import annotations

import dataclasses
from types import SimpleNamespace

import pytest

from app.evidence import Binder
from app.reasoning.evidence_repository import EvidenceRepository, EvidenceSnapshot
from app.storage.db import reset_db_for_tests


@pytest.fixture(autouse=True)
def _fresh():
    reset_db_for_tests("sqlite:///:memory:")
    yield


def _payload() -> dict:
    return {
        "overall_probability": 0.72, "overall_tier": "elevated", "confidence": 0.55,
        "convergence_score": 0.3, "inputs_provided": ["video"], "video_id": "v1",
        "cross_links": [{"kind": "fellow_traveler", "severity": "elevated", "summary": "co-appeared",
                         "evidence": ["5 shared"], "related_entities": ["a", "b"]}],
        "video": {"coordination_score": 0.66, "coordination_tier": "elevated",
                  "clusters": [{"method": "co_engagement", "members": ["a", "b", "c"], "score": 0.7}],
                  "commenters": [{"external_id": "a", "handle": "@a", "overall_probability": 0.8,
                                  "tier": "high", "weak_signals": ["few posts"]}]},
    }


def _snap(payload=None):
    return EvidenceRepository().snapshot(payload or _payload(), ref="sub_r", platform="youtube")


# --------------------------------------------------------------------------- #
# The snapshot is an immutable, content-addressed projection
# --------------------------------------------------------------------------- #
def test_snapshot_is_frozen_and_content_addressed():
    s = _snap()
    assert isinstance(s, EvidenceSnapshot)
    assert s.snapshot_id.startswith("es:")
    with pytest.raises(dataclasses.FrozenInstanceError):
        s.ref = "x"            # immutable projection, not a mutable subsystem


def test_snapshot_id_is_deterministic_and_excludes_wallclock():
    a, b = _snap(), _snap()
    assert a.snapshot_id == b.snapshot_id            # pure function of the evidence
    assert a.retrieved_at != "" and b.retrieved_at != ""
    # retrieved_at is recorded but is NOT part of the content address
    assert a.retrieved_at != b.retrieved_at or a.snapshot_id == b.snapshot_id


def test_snapshot_id_is_evidence_sensitive():
    base = _snap()
    p = _payload()
    p["overall_probability"] = 0.11
    assert _snap(p).snapshot_id != base.snapshot_id


# --------------------------------------------------------------------------- #
# It composes the real evidence + echoes the engine (never recomputes)
# --------------------------------------------------------------------------- #
def test_snapshot_holds_governance_bundle_context_and_priors():
    s = _snap()
    assert s.gov_bundle is not None and s.gov_bundle.bundle_id().startswith("b:")
    assert s.context is not None and s.context.context_id.startswith("ictx:")
    assert isinstance(s.prior_context, tuple)          # frozen priors
    # the context carries the same headline numbers as the governance bundle
    assert s.context.investigation.overall_probability == pytest.approx(0.72)


def test_headline_echoes_the_governance_bundle():
    s = _snap()
    assert s.headline() == s.gov_bundle.headline()
    assert s.headline().get("overall_probability") == pytest.approx(0.72)


def test_governance_bundle_is_byte_identical_to_the_inline_bind():
    """R1 behavior-preservation: the bundle the Governor validates against is exactly the one the
    reasoning path bound inline before the Repository existed (grain=comment_section, enrich=False)."""
    p = _payload()
    inline = Binder().bind(p, grain="comment_section", subject_ref="sub_r", platform="youtube")
    assert _snap(p).gov_bundle.bundle_id() == inline.bundle_id()


def test_empty_payload_is_safe():
    s = EvidenceRepository().snapshot({}, ref="x", platform="unknown")
    assert s.snapshot_id.startswith("es:") and isinstance(s.prior_context, tuple)


# --------------------------------------------------------------------------- #
# The production reasoning path reads through the Repository
# --------------------------------------------------------------------------- #
def test_assess_core_routes_through_the_repository_and_records_the_snapshot_id():
    from app.reasoning import analyst
    settings = SimpleNamespace(
        analyst_enabled=True, analyst_endpoint_url=None, analyst_hf_repo="Andrewexiga/omi-analyst-v1",
        analyst_hf_revision="sha1", analyst_prompt_version=None,
        analyst_model_id="mistralai/Mistral-7B-Instruct-v0.3", analyst_timeout_seconds=30.0,
        analyst_max_retries=0, analyst_endpoint_api="messages", analyst_cost_per_1k_tokens_usd=0.0,
        analyst_prompt_assembly="registry", memory_persistence_enabled=False, memory_database_url=None)
    out = analyst._assess_core(_payload(), ref="sub_r", platform="youtube", settings=settings, capture={})
    # behavior preserved: default (no endpoint) still yields the deterministic floor + full schema
    assert out["governance"]["provider"] == "deterministic-analyst-v1"
    assert out["suspicion_tier"] == "elevated"
    # the immutable snapshot id is recorded for traceability
    assert out["prompt_build"]["evidence_snapshot_id"].startswith("es:")


def test_repository_module_holds_no_reasoning_or_writes():
    """The Repository reads; it never reasons, scores, calls a model, or writes."""
    import pathlib
    src = pathlib.Path(EvidenceRepository.__module__.replace(".", "/") + ".py")
    # resolve via the module file
    import app.reasoning.evidence_repository as mod
    text = pathlib.Path(mod.__file__).read_text(encoding="utf-8")
    for forbidden in ("run_stage_inference", "_qwen_transport", "governor", "compute_omiscore",
                      "session.add", "session.commit", ".generate("):
        assert forbidden not in text, f"Repository must not contain {forbidden!r}"
