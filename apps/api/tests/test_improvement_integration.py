"""Continuous Improvement Engine — integration tests (Sprint 011).

Covers building evaluation snapshots from the gold corpus (deterministic / replay-stable), the
engineering report, end-to-end recommendation over real snapshots, and the admin routes.
"""
from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app
from app.reasoning.evaluation import GoldCase, GoldCorpus
from app.reasoning.improvement import build_snapshot, engineering_report, recommend
from app.reasoning.model_providers import MockReasoningProvider
from app.storage.db import reset_db_for_tests


def _payload() -> dict:
    return {
        "overall_probability": 0.72, "overall_tier": "elevated", "confidence": 0.6,
        "weak_signals": ["only 8 posts"], "single_axis_capped": False,
        "contributions": [{"name": "temporal", "impact": 0.5, "direction": "raises"},
                          {"name": "community", "impact": 0.2, "direction": "lowers"}],
        "video": {"clusters": [{"method": "co_engagement", "members": ["@a", "@b", "@c"]}],
                  "commenters": [{"handle": "@a", "tier": "high"}]},
    }


def _control_payload() -> dict:
    return {"overall_probability": 0.18, "overall_tier": "low", "confidence": 0.55,
            "contributions": [{"name": "community", "impact": 0.2, "direction": "lowers"}]}


def _provider() -> MockReasoningProvider:
    return MockReasoningProvider(structured={"findings": [
        {"signal": "temporal", "claim": "Bursty.", "direction": "raises", "evidence_refs": ["ev:0002"]}]})


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


def _corpus() -> GoldCorpus:
    c = GoldCorpus()
    c.add(GoldCase(id="c1", payload=_payload(), label={"expected_coordination_label": "suspicious"}))
    c.add(GoldCase(id="ctrl1", payload=_control_payload(), label={"is_control": True}, reviewer="alice"))
    return c


# --- snapshot building ------------------------------------------------------ #
def test_build_snapshot_is_deterministic_and_replay_stable():
    cfg = {"prompt_version": "v1", "context_mode": "structured", "enrich": True}
    s1 = build_snapshot(_corpus(), config=cfg, settings=_Settings(), provider=_provider())
    s2 = build_snapshot(_corpus(), config=cfg, settings=_Settings(), provider=_provider())
    assert s1 == s2                                              # deterministic / replay-stable
    assert s1["control_fpr"] == 0.0 and s1["number_preserved_rate"] == 1.0
    assert s1["facet_coverage"] is not None                     # enrich -> evidence metrics present
    assert s1["citation_retention"] == 1.0                      # structured context fully attributed


def test_recommend_over_real_snapshots_is_clean_when_equal():
    cfg = {"prompt_version": "v1", "context_mode": "structured", "enrich": True}
    s1 = build_snapshot(_corpus(), config=cfg, settings=_Settings(), provider=_provider())
    s2 = build_snapshot(_corpus(), config={**cfg, "prompt_version": "v2"}, settings=_Settings(), provider=_provider())
    # offline both fall back to the same deterministic read -> no actionable difference
    assert recommend(s1, s2) == []


# --- engineering report ----------------------------------------------------- #
def test_engineering_report_selects_best_and_trends():
    snaps = [
        {"label": "p=v1", "config": {"prompt_version": "v1"}, "agreement_rate": 0.8, "control_fpr": 0.0,
         "avg_latency_ms": 100.0, "number_preserved_rate": 1.0, "governor_permit_rate": 1.0, "governor_floor_rate": 0.0},
        {"label": "p=v2", "config": {"prompt_version": "v2"}, "agreement_rate": 0.9, "control_fpr": 0.0,
         "avg_latency_ms": 120.0, "number_preserved_rate": 1.0, "governor_permit_rate": 1.0, "governor_floor_rate": 0.0},
    ]
    rep = engineering_report(snaps, recommendations=[{"action": "promote", "severity": "improvement"}])
    assert rep["best_prompt"]["config"]["prompt_version"] == "v2"
    assert rep["agreement_trend"] == [0.8, 0.9]
    assert rep["replay_stability"]["number_preserved"] is True
    assert rep["recommendations"]["by_action"] == {"promote": 1}


# --- admin routes ----------------------------------------------------------- #
def test_recommend_route():
    reset_db_for_tests("sqlite:///:memory:")
    with TestClient(app) as tc:
        body = {"baseline": {"config": {"prompt_version": "v1"}, "agreement_rate": 0.8, "control_fpr": 0.0},
                "candidate": {"config": {"prompt_version": "v2"}, "agreement_rate": 0.9, "control_fpr": 0.0,
                              "number_preserved_rate": 1.0}}
        r = tc.post("/v1/admin/improvement/recommend", json=body)
        assert r.status_code == 200, r.text
        assert any(x["kind"] == "prompt_improvement" and x["action"] == "promote"
                   for x in r.json()["recommendations"])


def test_report_route():
    reset_db_for_tests("sqlite:///:memory:")
    with TestClient(app) as tc:
        body = {"snapshots": [{"label": "p=v1", "config": {"prompt_version": "v1"},
                               "agreement_rate": 0.85, "control_fpr": 0.0, "number_preserved_rate": 1.0}]}
        r = tc.post("/v1/admin/improvement/report", json=body)
        assert r.status_code == 200 and r.json()["n_configs"] == 1


def test_recommend_route_rejects_bad_body():
    reset_db_for_tests("sqlite:///:memory:")
    with TestClient(app) as tc:
        assert tc.post("/v1/admin/improvement/recommend", json={"baseline": {}}).status_code == 400
