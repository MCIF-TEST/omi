"""Intelligence Optimization Framework integration tests (Sprint 008).

Covers versioned prompt execution (the AI analyst runs a registry prompt, not embedded text),
config-driven selection, the full benchmark versioning recorded per investigation, A/B
evaluation between prompt versions, the gold evaluation corpus (label agreement + control FPR +
replay determinism), and the admin observability routes — all preserving the constitutional
guarantees (the engine number is never moved, production is prompt-independent).
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.main import app
from app.reasoning.evaluation import GoldCase, GoldCorpus, evaluate_corpus
from app.reasoning.model_providers import MockReasoningProvider
from app.reasoning.orchestrator import Blackboard, ai_behavior_analyst
from app.reasoning.prompts import PromptExperiment, default_registry
from app.reasoning.shadow import ab_evaluate, run_shadow
from app.evidence import Binder
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


def _control_payload() -> dict:
    # legitimate-looking: low suspicion, no discriminative coordination → never read as hostile.
    return {
        "overall_probability": 0.18, "overall_tier": "low", "confidence": 0.55,
        "contributions": [{"name": "community", "impact": 0.2, "direction": "lowers"}],
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
        self.analyst_hf_repo = kw.get("analyst_hf_repo", "Andrewexiga/omi-analyst-v1")
        self.analyst_hf_revision = kw.get("analyst_hf_revision", None)
        self.analyst_timeout_seconds = kw.get("analyst_timeout_seconds", 30.0)
        self.analyst_max_retries = kw.get("analyst_max_retries", 2)
        self.analyst_prompt_version = kw.get("analyst_prompt_version", None)


def _seed(slug: str) -> None:
    with get_session() as session:
        u = User(email="a@x.com", password_hash="x", credits_remaining=3)
        session.add(u); session.flush()
        session.add(Investigation(
            user_id=u.id, slug=slug, label="Video", input_url="https://youtube.com/watch?v=z",
            kind="video", overall_probability=0.72, overall_tier="elevated",
            summary="x", payload_json=_payload(),
        ))


# --- versioned prompt execution --------------------------------------------- #
def test_ai_analyst_executes_a_versioned_prompt():
    reg = default_registry()
    prov = _valid_provider()
    ai = ai_behavior_analyst(prov, prompt_version="v2", registry=reg)
    assert ai.prompt_meta["version"] == "v2" and ai.prompt_meta["hash"].startswith("ph:")
    ai.run(Blackboard(_bundle()).view_for(ai.contract))
    assert prov.last_request.system == reg.resolve("behavior_analyst", "v2").template   # registry, not embedded


def test_config_drives_prompt_selection():
    assert ai_behavior_analyst(_valid_provider(), settings=_Settings(analyst_prompt_version="v2")).prompt_meta["version"] == "v2"
    assert ai_behavior_analyst(_valid_provider(), settings=_Settings()).prompt_meta["version"] == "v1"  # active default


# --- benchmark versioning recorded per investigation ------------------------ #
def test_shadow_records_full_benchmark_versioning():
    rep = run_shadow(_payload(), ref="inv1", settings=_Settings(), provider=_valid_provider(), prompt_version="v2")
    v = rep.versioning
    assert v["prompt"]["version"] == "v2" and v["prompt"]["hash"].startswith("ph:")
    assert v["governor_revision"] and v["bundle_id"].startswith("b:")
    assert v["bundle_version"]["binder_version"] and "model_revision" in v
    assert v["memory_revision"] == "none"


def test_shadow_versioning_marks_the_deterministic_path():
    rep = run_shadow(_payload(), ref="inv1", settings=_Settings())          # no provider
    assert rep.versioning["prompt"] == {"mode": "deterministic"}


def test_production_is_independent_of_prompt_version():
    a = run_shadow(_payload(), ref="inv1", settings=_Settings(), provider=_valid_provider(), prompt_version="v1")
    b = run_shadow(_payload(), ref="inv1", settings=_Settings(), provider=_valid_provider(), prompt_version="v2")
    assert a.production["assessment"] == b.production["assessment"]         # regression safety


# --- A/B evaluation between prompt versions --------------------------------- #
def test_ab_evaluate_compares_prompt_variants():
    prov_a = MockReasoningProvider(structured={"findings": [
        {"signal": "temporal", "claim": "a", "direction": "raises", "evidence_refs": ["ev:0002"]}]})
    prov_b = MockReasoningProvider(structured={"findings": [
        {"signal": "community", "claim": "b", "direction": "raises", "evidence_refs": ["ev:0003"]}]})
    result = ab_evaluate(_payload(), ref="inv1", settings=_Settings(),
                         experiment=PromptExperiment("behavior_analyst", "v1", "v2"),
                         provider_a=prov_a, provider_b=prov_b)
    assert result["prompts"]["template_changed"] is True
    assert result["variant_a"]["versioning"]["prompt"]["version"] == "v1"
    assert result["variant_b"]["versioning"]["prompt"]["version"] == "v2"
    va = {e["signal"] for e in result["variant_a"]["shadow"]["assessment"]["evidence_for"]}
    vb = {e["signal"] for e in result["variant_b"]["shadow"]["assessment"]["evidence_for"]}
    assert "temporal" in va and "community" in vb                          # variants produced different reads
    assert result["comparison"]["number_preserved"] is True               # neither moved the number


# --- gold evaluation corpus ------------------------------------------------- #
def test_evaluate_corpus_scores_labels_and_control_fpr():
    corpus = GoldCorpus()
    corpus.add(GoldCase(id="c1", payload=_payload(), label={"expected_coordination_label": "suspicious"}))
    corpus.add(GoldCase(id="ctrl1", payload=_control_payload(), label={"is_control": True}, reviewer="alice"))
    report = evaluate_corpus(corpus, settings=_Settings())
    s = report["summary"]
    assert s["n"] == 2 and s["controls"] == 1
    assert s["production_control_fpr"] == 0.0          # baseline does not flag the legitimate control
    assert s["number_preserved_rate"] == 1.0
    assert {r["id"] for r in report["cases"]} == {"c1", "ctrl1"}


def test_evaluate_corpus_is_deterministic():
    corpus = GoldCorpus()
    corpus.add(GoldCase(id="c1", payload=_payload(), label={"expected_coordination_label": "suspicious"}))
    r1 = evaluate_corpus(corpus, settings=_Settings())
    r2 = evaluate_corpus(corpus, settings=_Settings())
    assert r1["summary"] == r2["summary"] and r1["cases"] == r2["cases"]    # replay / regression


# --- admin observability routes --------------------------------------------- #
def test_prompts_route_lists_the_registry():
    reset_db_for_tests("sqlite:///:memory:")
    with TestClient(app) as tc:
        body = tc.get("/v1/admin/shadow/prompts").json()
        assert "behavior_analyst" in body["analysts"]
        versions = {r["prompt_version"]: r for r in body["prompts"]}
        assert versions["v1"]["active"] is True and "v2" in versions


def test_ab_route_returns_prompt_diff_offline():
    reset_db_for_tests("sqlite:///:memory:")
    _seed("inv_ab")
    with TestClient(app) as tc:
        body = tc.post("/v1/admin/shadow/ab/inv_ab?variant_a=v1&variant_b=v2").json()
        assert body["prompts"]["template_changed"] is True
        assert body["execution"] is None and "note" in body                # no endpoint → null execution


def test_ab_route_unknown_version_404():
    reset_db_for_tests("sqlite:///:memory:")
    _seed("inv_ab2")
    with TestClient(app) as tc:
        assert tc.post("/v1/admin/shadow/ab/inv_ab2?variant_b=v999").status_code == 404
