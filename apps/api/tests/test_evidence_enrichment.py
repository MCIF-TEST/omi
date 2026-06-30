"""Evidence enrichment tests (Sprint 010).

Covers the opt-in Binder enrichment: deterministic projection (never invents), provenance +
traceability preservation, graceful degradation when source data is absent, backward
compatibility (enrich off is byte-identical), and the evidence-quality metrics.
"""
from __future__ import annotations

from app.evidence import Binder, evidence_quality
from app.evidence.enrich import BASE_KINDS


def _rich_payload() -> dict:
    return {
        "overall_probability": 0.72, "overall_tier": "elevated", "confidence": 0.6,
        "weak_signals": ["only 8 posts"], "single_axis_capped": False,
        "contributions": [
            {"name": "temporal", "impact": 0.5, "direction": "raises"},
            {"name": "community", "impact": 0.2, "direction": "lowers"},
        ],
        "cross_links": [{"kind": "focus_in_cluster", "summary": "Focus in cluster"}],
        "narrative": {"label": "anti-X narrative", "inauthenticity_score": 0.6, "distinct_authors": 40},
        "video": {
            "clusters": [{"method": "co_engagement", "members": ["@a", "@b", "@c"]}],
            "commenters": [{"handle": "@a", "tier": "high"}, {"handle": "@b", "tier": "elevated"},
                           {"handle": "@c", "tier": "low"}],
        },
    }


def _minimal_payload() -> dict:
    return {"overall_probability": 0.3, "overall_tier": "low", "confidence": 0.4,
            "contributions": [{"name": "temporal", "impact": 0.3, "direction": "raises"}]}


def _bind(payload, **kw):
    return Binder().bind(payload, grain="comment_section", subject_ref="inv1", platform="youtube", **kw)


# --- backward compatibility (enrich off is unchanged) ----------------------- #
def test_enrich_off_is_backward_compatible():
    base = _bind(_rich_payload())
    assert all(it.kind in BASE_KINDS for it in base.evidence.values())   # only atomic kinds
    assert _bind(_rich_payload()).bundle_id() == base.bundle_id()        # deterministic
    assert _bind(_rich_payload(), enrich=True).bundle_id() != base.bundle_id()   # enrichment is a different bundle


# --- deterministic projection + richer facets ------------------------------- #
def test_enrichment_is_deterministic_and_richer():
    a, b = _bind(_rich_payload(), enrich=True), _bind(_rich_payload(), enrich=True)
    assert a.bundle_id() == b.bundle_id()                               # deterministic
    assert len(a.evidence) > len(_bind(_rich_payload()).evidence)       # richer
    facets = {it.facet for it in a.evidence.values()}
    assert {"behavioral", "coordination", "detector", "graph", "metadata", "narrative"} <= facets
    kinds = {it.kind for it in a.evidence.values()}
    assert {"feature_importance", "temporal_pattern", "coordination_summary", "engagement_distribution",
            "narrative_cluster", "metadata_summary", "detector_provenance", "cross_link",
            "investigation_chronology"} <= kinds


def test_enrichment_adds_co_engaged_edges():
    rich = _bind(_rich_payload(), enrich=True)
    assert any(r.type == "co_engaged" for r in rich.relationships)      # graph relationships projected


# --- never invent: provenance + traceability preserved ---------------------- #
def test_every_enriched_item_is_traceable():
    rich = _bind(_rich_payload(), enrich=True)
    derived = [it for it in rich.evidence.values() if it.kind not in BASE_KINDS]
    assert derived and all(it.provenance and it.traceability_path for it in derived)
    # every traceability ev: reference resolves against the bundle (no fabricated provenance)
    for it in derived:
        for step in it.traceability_path:
            ref = step.get("from")
            if isinstance(ref, str) and ref.startswith("ev:"):
                assert ref in rich.evidence


# --- graceful degradation --------------------------------------------------- #
def test_enrichment_degrades_gracefully_on_thin_payload():
    rich = _bind(_minimal_payload(), enrich=True)
    kinds = {it.kind for it in rich.evidence.values()}
    assert {"feature_importance", "temporal_pattern", "metadata_summary",
            "detector_provenance", "investigation_chronology"} <= kinds   # what IS derivable
    assert "engagement_distribution" not in kinds and "narrative_cluster" not in kinds  # absent sources -> absent
    assert "coordination_summary" not in kinds                            # no coordination methods
    assert not any(r.type == "co_engaged" for r in rich.relationships)


# --- evidence quality metrics ----------------------------------------------- #
def test_evidence_quality_rises_with_enrichment():
    base = evidence_quality(_bind(_rich_payload()))
    rich = evidence_quality(_bind(_rich_payload(), enrich=True))
    assert rich["evidence_completeness"] > base["evidence_completeness"]
    assert rich["facet_coverage"] > base["facet_coverage"]
    assert rich["graph_density"] >= base["graph_density"]
    assert rich["timeline_completeness"] > base["timeline_completeness"]


def test_enriched_evidence_has_full_integrity_and_provenance():
    rich = evidence_quality(_bind(_rich_payload(), enrich=True))
    assert rich["citation_integrity"] == 1.0          # every bundle-id reference resolves
    assert rich["provenance_completeness"] == 1.0      # every item carries provenance
    assert rich["facet_coverage"] == 1.0 and rich["evidence_completeness"] == 1.0


def test_evidence_quality_is_deterministic():
    assert evidence_quality(_bind(_rich_payload(), enrich=True)) == evidence_quality(_bind(_rich_payload(), enrich=True))
