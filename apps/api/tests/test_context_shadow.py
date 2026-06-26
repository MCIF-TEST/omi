"""Context Builder × Shadow Mode tests (Sprint 009).

Covers structured-context selection in the AI analyst, context metrics surfaced through Shadow
Mode (even on fallback), the raw-vs-structured comparison, replay determinism, regression
safety (raw is the default and unchanged; production is context-independent), and the admin
context route.
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.evidence import Binder
from app.main import app
from app.reasoning.model_providers import MockReasoningProvider, ProviderTimeout
from app.reasoning.orchestrator import Blackboard, ai_behavior_analyst
from app.reasoning.shadow import compare_context_modes, run_shadow
from app.storage.db import get_session, reset_db_for_tests
from app.storage.models import Investigation, User

NOW = datetime(2026, 6, 25, tzinfo=timezone.utc)


def _payload() -> dict:
    return {
        "overall_probability": 0.72, "overall_tier": "elevated", "confidence": 0.6,
        "weak_signals": ["only 8 posts"], "single_axis_capped": False,
        "contributions": [
            {"name": "temporal", "impact": 0.5, "direction": "raises"},        # ev:0002
            {"name": "community", "impact": 0.2, "direction": "lowers"},       # ev:0003
        ],
        "video": {"clusters": [{"method": "co_engagement", "members": ["@a", "@b", "@c"]}]},  # ev:0004
    }


def _bundle():
    return Binder().bind(_payload(), grain="comment_section", subject_ref="inv1", platform="youtube")


def _valid_provider() -> MockReasoningProvider:
    return MockReasoningProvider(structured={
        "findings": [{"signal": "temporal", "claim": "Bursty posting raises suspicion.",
                      "direction": "raises", "evidence_refs": ["ev:0002"]}],
        "uncertainty": ["Only 8 posts."],
    })


class _Settings:
    def __init__(self, **kw):
        self.analyst_enabled = kw.get("analyst_enabled", False)
        self.analyst_endpoint_url = kw.get("analyst_endpoint_url", None)
        self.analyst_hf_repo = kw.get("analyst_hf_repo", "repo")
        self.analyst_hf_revision = kw.get("analyst_hf_revision", None)
        self.analyst_timeout_seconds = kw.get("analyst_timeout_seconds", 30.0)
        self.analyst_max_retries = kw.get("analyst_max_retries", 2)
        self.analyst_prompt_version = kw.get("analyst_prompt_version", None)
        self.analyst_context_mode = kw.get("analyst_context_mode", "raw")
        self.analyst_context_budget = kw.get("analyst_context_budget", "standard")


def _seed(slug: str) -> None:
    with get_session() as session:
        u = User(email="a@x.com", password_hash="x", credits_remaining=3)
        session.add(u); session.flush()
        session.add(Investigation(
            user_id=u.id, slug=slug, label="Video", input_url="https://youtube.com/watch?v=z",
            kind="video", overall_probability=0.72, overall_tier="elevated", summary="x",
            payload_json=_payload(),
        ))


# --- structured-context selection in the AI analyst ------------------------- #
def test_raw_is_the_default_and_unchanged():
    prov = _valid_provider()
    ai = ai_behavior_analyst(prov)                                   # no context_mode -> raw
    assert ai.prompt_meta["context_mode"] == "raw"
    ai.run(Blackboard(_bundle()).view_for(ai.contract))
    assert "BEHAVIORAL EVIDENCE" in prov.last_request.user and "never proof" in prov.last_request.user


def test_structured_mode_feeds_built_context_and_records_metrics():
    prov = _valid_provider()
    ai = ai_behavior_analyst(prov, context_mode="structured", context_budget="standard")
    ai.run(Blackboard(_bundle()).view_for(ai.contract))
    assert "STRUCTURED CONTEXT" in prov.last_request.user           # built context fed to the model
    assert ai.last_context["mode"] == "structured" and ai.last_context["metrics"]["citation_retention"] == 1.0


def test_context_mode_is_config_driven():
    assert ai_behavior_analyst(_valid_provider(), settings=_Settings(analyst_context_mode="structured")).prompt_meta["context_mode"] == "structured"
    assert ai_behavior_analyst(_valid_provider(), settings=_Settings()).prompt_meta["context_mode"] == "raw"


# --- context metrics through Shadow Mode (even on fallback) ------------------ #
def test_shadow_surfaces_structured_context_metrics():
    rep = run_shadow(_payload(), ref="inv1", settings=_Settings(), provider=_valid_provider(),
                     context_mode="structured")
    assert rep.context["mode"] == "structured" and rep.context["version"] == "ctx-v1"
    assert rep.context["metrics"]["citation_retention"] == 1.0
    assert rep.versioning["prompt"]["context_mode"] == "structured"


def test_structured_context_is_built_even_on_fallback():
    rep = run_shadow(_payload(), ref="inv1", settings=_Settings(),
                     provider=MockReasoningProvider(error=ProviderTimeout("slow")), context_mode="structured")
    assert rep.diagnostics["ai_mode"] == "fallback"                 # model failed...
    assert rep.context["mode"] == "structured" and rep.context["metrics"]["statements"] > 0   # ...context still built


def test_shadow_raw_mode_marks_raw():
    rep = run_shadow(_payload(), ref="inv1", settings=_Settings(), provider=_valid_provider())
    assert rep.context == {"mode": "raw"}


# --- raw vs structured comparison + determinism ----------------------------- #
def test_compare_context_modes_returns_both_contexts():
    result = compare_context_modes(_payload(), ref="inv1", settings=_Settings(), provider_raw=_valid_provider())
    assert result["raw_context"]["mode"] == "raw"
    assert result["structured_context"]["mode"] == "structured"
    assert result["structured_context"]["metrics"]["citation_retention"] == 1.0
    assert result["comparison"]["number_preserved"] is True


def test_structured_shadow_is_deterministic():
    def _run():
        return run_shadow(_payload(), ref="inv1", settings=_Settings(), provider=_valid_provider(),
                          context_mode="structured")
    a, b = _run(), _run()
    assert a.context == b.context and a.comparison == b.comparison


def test_production_is_independent_of_context_mode():
    raw = run_shadow(_payload(), ref="inv1", settings=_Settings(), provider=_valid_provider(), context_mode="raw")
    structured = run_shadow(_payload(), ref="inv1", settings=_Settings(), provider=_valid_provider(), context_mode="structured")
    assert raw.production["assessment"] == structured.production["assessment"]   # regression safety


# --- admin context route ---------------------------------------------------- #
def test_context_route_returns_metrics_offline():
    reset_db_for_tests("sqlite:///:memory:")
    _seed("inv_ctx")
    with TestClient(app) as tc:
        body = tc.post("/v1/admin/shadow/context/inv_ctx?budget=compact").json()
        assert body["budget"] == "compact"
        assert body["context"]["context_version"] == "ctx-v1"
        assert body["context"]["metrics"]["citation_retention"] == 1.0
        assert body["execution"] is None                            # no endpoint -> metrics only
