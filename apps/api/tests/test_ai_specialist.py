"""First live reasoning module tests (Sprint 006).

Proves the constitutional architecture can host a real model: the AI-backed Behavior Analyst
is a drop-in for its contract, cites only resolvable bundle evidence (never fabricates), falls
back to the deterministic analyst on every failure mode, passes the mandatory Governor, never
moves the engine number, and replays deterministically with a deterministic provider.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.evidence import Binder
from app.reasoning.contracts import validate_artifact
from app.reasoning.orchestrator import (
    AnalystModule,
    BehaviorAnalyst,
    Blackboard,
    CounterEvidenceAnalyst,
    Orchestrator,
    RemoteAnalyst,
    ai_behavior_analyst,
    build_council,
)
from app.reasoning.model_providers import (
    MockReasoningProvider,
    ProviderTimeout,
    ProviderUnavailable,
    ReasoningProvider,
    ReasoningRequest,
    RemoteReasoningProvider,
    assemble_stream,
    build_remote_provider,
    extract_json,
    provider_status,
)

NOW = datetime(2026, 6, 25, tzinfo=timezone.utc)


def _payload() -> dict:
    return {
        "overall_probability": 0.72, "overall_tier": "elevated", "confidence": 0.6,
        "weak_signals": ["only 8 posts"], "single_axis_capped": False,
        "contributions": [
            {"name": "temporal", "impact": 0.5, "direction": "raises"},        # ev:0002
            {"name": "community", "impact": 0.2, "direction": "lowers"},       # ev:0003
            {"name": "ai_writing", "impact": 0.1, "direction": "neutral", "supplemental": True},  # ev:0004
        ],
        "video": {"clusters": [{"method": "co_engagement", "members": ["@a", "@b", "@c"]}]},  # ev:0005
    }


def _bundle():
    return Binder().bind(_payload(), grain="comment_section", subject_ref="inv1", platform="youtube")


def _valid_provider() -> MockReasoningProvider:
    return MockReasoningProvider(structured={
        "findings": [{
            "signal": "temporal",
            "claim": "Bursty synchronized posting is consistent with elevated suspicion.",
            "direction": "raises", "evidence_refs": ["ev:0002"],
        }],
        "uncertainty": ["Only 8 posts; single snapshot."],
    })


class _Settings:
    """Minimal settings stand-in for the config-driven factory tests."""

    def __init__(self, **kw):
        self.analyst_enabled = kw.get("analyst_enabled", False)
        self.analyst_endpoint_url = kw.get("analyst_endpoint_url", None)
        self.analyst_hf_repo = kw.get("analyst_hf_repo", "Andrewexiga/omi-analyst-v1")
        self.analyst_hf_revision = kw.get("analyst_hf_revision", None)
        self.analyst_timeout_seconds = kw.get("analyst_timeout_seconds", 30.0)
        self.analyst_max_retries = kw.get("analyst_max_retries", 2)


# --- contract compatibility ------------------------------------------------- #
def test_ai_behavior_analyst_is_drop_in_for_contract():
    ai = ai_behavior_analyst(_valid_provider())
    assert ai.contract == BehaviorAnalyst().contract        # SAME contract → true drop-in
    assert isinstance(ai, AnalystModule)


def test_providers_satisfy_the_provider_protocol():
    assert isinstance(MockReasoningProvider(), ReasoningProvider)
    assert isinstance(RemoteReasoningProvider(endpoint_url="https://x"), ReasoningProvider)


# --- the AI specialist produces contract-valid, evidence-cited findings ----- #
def test_ai_specialist_produces_contract_valid_findings():
    bb = Blackboard(_bundle())
    ai = ai_behavior_analyst(_valid_provider())
    arts = ai.run(bb.view_for(ai.contract))
    assert arts and all(a.kind == "finding" for a in arts)
    assert validate_artifact(ai.contract, arts[0], bb)[0]
    assert arts[0].evidence_refs == ["ev:0002"]
    assert ai.last_diagnostics["mode"] == "ai"


def test_ai_specialist_consumes_prior_context():
    from app.memory.graph import MemoryStore
    store = MemoryStore()
    store.ingest(
        candidate={"type": "LegitimateCoordinationControl", "signature": ["co_engagement"],
                   "label": "regional newsroom", "is_control": True},
        investigation="h1", stance="supports", evidence_refs=["d"],
        independence_key="a", at=NOW.isoformat(),
    )
    mock = _valid_provider()
    ai = ai_behavior_analyst(mock, store=store, now=NOW)
    ai.run(Blackboard(_bundle()).view_for(ai.contract))
    assert "regional newsroom" in mock.last_request.user      # PriorContext surfaced...
    assert "never proof" in mock.last_request.user.lower()    # ...as background, not evidence


# --- never fabricate evidence; fall back on every failure mode -------------- #
def test_fabricated_evidence_falls_back_to_deterministic():
    bad = MockReasoningProvider(structured={"findings": [
        {"signal": "temporal", "claim": "x", "direction": "raises", "evidence_refs": ["ev:9999"]}]})
    bb = Blackboard(_bundle())
    ai = ai_behavior_analyst(bad)
    arts = ai.run(bb.view_for(ai.contract))
    assert ai.last_diagnostics["mode"] == "fallback" and "fabricated" in ai.last_diagnostics["detail"]
    det = BehaviorAnalyst().run(bb.view_for(BehaviorAnalyst.contract))
    assert [a.evidence_refs for a in arts] == [a.evidence_refs for a in det]   # deterministic output


@pytest.mark.parametrize("provider, reason", [
    (MockReasoningProvider(error=ProviderTimeout("slow")), "ProviderTimeout"),
    (MockReasoningProvider(error=ProviderUnavailable("no endpoint")), "ProviderUnavailable"),
    (MockReasoningProvider(text="not json at all"), "ValueError"),          # malformed → no artifacts
])
def test_failures_fall_back_to_deterministic(provider, reason):
    bb = Blackboard(_bundle())
    ai = ai_behavior_analyst(provider)
    arts = ai.run(bb.view_for(ai.contract))
    assert ai.last_diagnostics["mode"] == "fallback" and ai.last_diagnostics["reason"] == reason
    assert arts                                                              # council still gets findings


def test_supplemental_signal_cannot_be_raised_by_the_model():
    mock = MockReasoningProvider(structured={"findings": [
        {"signal": "ai_writing", "claim": "x", "direction": "raises", "evidence_refs": ["ev:0004"]},
        {"signal": "temporal", "claim": "y", "direction": "raises", "evidence_refs": ["ev:0002"]},
    ]})
    bb = Blackboard(_bundle())
    ai = ai_behavior_analyst(mock)
    signals = {a.signal for a in ai.run(bb.view_for(ai.contract))}
    assert "temporal" in signals and "ai_writing" not in signals            # supplemental raise dropped


# --- Governor compatibility + council execution with one AI specialist ------ #
def test_council_with_ai_specialist_passes_governor_and_preserves_echo():
    council = [ai_behavior_analyst(_valid_provider()), CounterEvidenceAnalyst()]
    res = Orchestrator(modules=council).run(_payload(), ref="inv1", platform="youtube")
    assert res.permitted and not res.fallback, res.trace.violation_codes
    a = res.assessment
    assert a["suspicion_probability"] == 0.72                                # AI never moves the number
    assert any(e["signal"] == "temporal" for e in a["evidence_for"])         # AI finding flowed in


def test_council_with_ai_specialist_is_deterministic():
    def _run():
        council = [ai_behavior_analyst(_valid_provider()), CounterEvidenceAnalyst()]
        return Orchestrator(modules=council).run(_payload(), ref="inv1", platform="youtube")
    r1, r2 = _run(), _run()
    assert r1.assessment == r2.assessment and r1.trace.trace_id() == r2.trace.trace_id()


# --- remote provider: revision pinning, unavailable, retries, timeout ------- #
def test_remote_provider_unavailable_without_token(monkeypatch):
    monkeypatch.delenv("HF_TOKEN", raising=False)
    monkeypatch.delenv("HUGGINGFACE_HUB_TOKEN", raising=False)
    p = RemoteReasoningProvider(endpoint_url="https://example.invalid")
    with pytest.raises(ProviderUnavailable):
        p.complete(ReasoningRequest(system="s", user="u"))


def test_remote_provider_retries_then_raises_timeout(monkeypatch):
    monkeypatch.setenv("HF_TOKEN", "x")
    calls = {"n": 0}

    def fake_urlopen(req, timeout=None):
        calls["n"] += 1
        raise TimeoutError("timed out")

    monkeypatch.setattr("app.reasoning.model_providers.remote.urllib.request.urlopen", fake_urlopen)
    p = RemoteReasoningProvider(endpoint_url="https://x", max_retries=2, backoff_cap=0.0)
    with pytest.raises(ProviderTimeout):
        p.complete(ReasoningRequest(system="s", user="u"))
    assert calls["n"] == 3                                                   # 1 try + 2 retries


# --- streaming compatibility + structured-output parsing -------------------- #
def test_assemble_stream_concatenates_token_chunks():
    lines = [
        b'data: {"token":{"text":"Hello"}}',
        b': keep-alive',
        b'data: {"token":{"text":" world"}}',
        b'data: [DONE]',
    ]
    assert assemble_stream(lines) == "Hello world"


def test_extract_json_strips_thinking_trace():
    assert extract_json('<think>weighing the evidence</think>\n{"findings": []}') == {"findings": []}
    assert extract_json("no json here") is None


# --- runtime readiness: activation is configuration ------------------------- #
def test_build_council_is_deterministic_when_disabled():
    assert isinstance(build_council(_Settings(analyst_enabled=False))[0], BehaviorAnalyst)


def test_build_council_uses_ai_specialist_when_configured():
    council = build_council(_Settings(analyst_enabled=True, analyst_endpoint_url="https://x"))
    assert isinstance(council[0], RemoteAnalyst)
    assert council[0].contract == BehaviorAnalyst().contract                 # still the same contract


def test_build_remote_provider_pins_revision_and_requires_endpoint():
    assert build_remote_provider(_Settings(analyst_endpoint_url=None)) is None
    p = build_remote_provider(_Settings(analyst_endpoint_url="https://x", analyst_hf_revision="abc123"))
    assert isinstance(p, RemoteReasoningProvider) and p.revision == "abc123"


def test_provider_status_reports_readiness(monkeypatch):
    monkeypatch.setenv("HF_TOKEN", "x")
    ready = provider_status(_Settings(analyst_enabled=True, analyst_endpoint_url="https://x"))
    assert ready["ai_specialist_ready"] is True and ready["governor"] == "mandatory"
    monkeypatch.delenv("HF_TOKEN", raising=False)
    monkeypatch.delenv("HUGGINGFACE_HUB_TOKEN", raising=False)
    assert provider_status(_Settings(analyst_enabled=False))["ai_specialist_ready"] is False
