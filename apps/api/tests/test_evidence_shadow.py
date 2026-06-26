"""Evidence enrichment × Context Builder × Shadow Mode tests (Sprint 010).

Covers the Context Builder auto-consuming enriched evidence (no prompt change), evidence
quality surfaced through Shadow Mode, the baseline-vs-enriched comparison, replay compatibility
(missing facets degrade gracefully; historical bundles still reproduce), regression safety
(production read is unchanged by enrichment), and the admin evidence route.
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.evidence import Binder
from app.main import app
from app.reasoning.context import build_context
from app.reasoning.model_providers import MockReasoningProvider
from app.reasoning.shadow import compare_evidence_modes, replay, run_shadow
from app.storage.db import get_session, reset_db_for_tests
from app.storage.models import Investigation, User

NOW = datetime(2026, 6, 25, tzinfo=timezone.utc)


def _payload() -> dict:
    return {
        "overall_probability": 0.72, "overall_tier": "elevated", "confidence": 0.6,
        "weak_signals": ["only 8 posts"], "single_axis_capped": False,
        "contributions": [
            {"name": "temporal", "impact": 0.5, "direction": "raises"},
            {"name": "community", "impact": 0.2, "direction": "lowers"},
        ],
        "cross_links": [{"kind": "focus_in_cluster", "summary": "Focus in cluster"}],
        "narrative": {"label": "anti-X narrative", "inauthenticity_score": 0.6},
        "video": {"clusters": [{"method": "co_engagement", "members": ["@a", "@b", "@c"]}],
                  "commenters": [{"handle": "@a", "tier": "high"}, {"handle": "@b", "tier": "low"}]},
    }


def _thin_payload() -> dict:
    return {"overall_probability": 0.3, "overall_tier": "low", "confidence": 0.4,
            "contributions": [{"name": "temporal", "impact": 0.3, "direction": "raises"}]}


def _bundle(payload, **kw):
    return Binder().bind(payload, grain="comment_section", subject_ref="inv1", platform="youtube", **kw)


def _valid_provider() -> MockReasoningProvider:
    return MockReasoningProvider(structured={
        "findings": [{"signal": "temporal", "claim": "Bursty posting raises suspicion.",
                      "direction": "raises", "evidence_refs": ["ev:0002"]}]})


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


# --- Context Builder auto-consumes enriched evidence (no prompt change) ------ #
def test_context_builder_auto_consumes_enriched_evidence():
    base = build_context(_bundle(_payload()), budget="comprehensive")
    rich = build_context(_bundle(_payload(), enrich=True), budget="comprehensive")
    base_derived = next(s for s in base.sections if s.name == "derived_evidence")
    rich_derived = next(s for s in rich.sections if s.name == "derived_evidence")
    assert not base_derived.statements and rich_derived.statements          # empty baseline, populated enriched
    assert rich.metrics["context_completeness"] > base.metrics["context_completeness"]
    assert rich.metrics["citation_retention"] == 1.0                        # still fully attributed


# --- evidence quality through Shadow Mode ----------------------------------- #
def test_shadow_surfaces_evidence_quality():
    rep = run_shadow(_payload(), ref="inv1", settings=_Settings(), provider=_valid_provider(), enrich=True)
    assert rep.evidence["facet_coverage"] == 1.0 and rep.evidence["citation_integrity"] == 1.0
    assert rep.versioning["enrich"] is True
    baseline = run_shadow(_payload(), ref="inv1", settings=_Settings(), provider=_valid_provider())
    assert baseline.versioning["enrich"] is False
    assert baseline.evidence["facet_coverage"] < rep.evidence["facet_coverage"]


def test_compare_evidence_modes_reports_quality_deltas():
    result = compare_evidence_modes(_payload(), ref="inv1", settings=_Settings(), provider=_valid_provider())
    assert result["enriched_evidence"]["evidence_completeness"] > result["baseline_evidence"]["evidence_completeness"]
    assert result["quality_deltas"]["facet_coverage"] > 0
    assert result["comparison"]["number_preserved"] is True


# --- regression safety: production read is unchanged by enrichment ----------- #
def test_production_read_is_unchanged_by_enrichment():
    base = run_shadow(_payload(), ref="inv1", settings=_Settings(), provider=_valid_provider(), enrich=False)
    rich = run_shadow(_payload(), ref="inv1", settings=_Settings(), provider=_valid_provider(), enrich=True)
    assert base.production["assessment"] == rich.production["assessment"]   # enrichment adds evidence, not verdicts
    assert base.production["trace"]["permitted"] and rich.production["trace"]["permitted"]


# --- replay compatibility --------------------------------------------------- #
def test_enriched_shadow_replays_deterministically():
    first = run_shadow(_payload(), ref="inv1", settings=_Settings(), provider=_valid_provider(), enrich=True)
    res = replay(_payload(), previous=first, ref="inv1", settings=_Settings(),
                 provider=_valid_provider(), enrich=True)
    assert res["production_reproduced"] and res["shadow_reproduced"]


def test_replay_degrades_gracefully_on_missing_facets():
    # a thin payload (no narrative/commenters/cross_links) still enriches + replays.
    first = run_shadow(_thin_payload(), ref="inv2", settings=_Settings(), provider=_valid_provider(), enrich=True)
    res = replay(_thin_payload(), previous=first, ref="inv2", settings=_Settings(),
                 provider=_valid_provider(), enrich=True)
    assert res["reproduced"] and first.evidence["citation_integrity"] == 1.0


# --- admin evidence route --------------------------------------------------- #
def test_evidence_route_returns_baseline_and_enriched_metrics():
    reset_db_for_tests("sqlite:///:memory:")
    _seed("inv_ev")
    with TestClient(app) as tc:
        body = tc.post("/v1/admin/shadow/evidence/inv_ev").json()
        assert body["enriched_evidence"]["facet_coverage"] > body["baseline_evidence"]["facet_coverage"]
        assert body["enriched_evidence"]["citation_integrity"] == 1.0
        assert body["execution"] is None                            # no endpoint -> metrics only
