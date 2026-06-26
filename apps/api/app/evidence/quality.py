"""Evidence quality metrics (Sprint 010) — deterministic, model-free measurements.

Quantify how rich and traceable a bundle's evidence is, so enrichment can be measured (a
baseline bundle scores lower; an enriched bundle scores higher) and exposed through Shadow Mode
+ engineering APIs. Pure functions of the bundle — no model, no wall-clock.

- **evidence_completeness** — share of the target evidence kinds present.
- **facet_coverage** — share of the enrichable facets present.
- **provenance_completeness** — share of evidence items carrying provenance.
- **graph_density** — relationships per member account.
- **timeline_completeness** — share of evidence covered by the investigation chronology.
- **citation_integrity** — share of bundle-id references (traceability + edges) that resolve.
"""
from __future__ import annotations

from typing import Any

_ENRICHABLE_FACETS = ("behavioral", "coordination", "detector", "narrative", "graph", "metadata")
_TARGET_KINDS = (
    "headline", "contribution", "coordination_method", "feature_importance", "temporal_pattern",
    "coordination_summary", "engagement_distribution", "narrative_cluster", "metadata_summary",
    "detector_provenance", "cross_link", "investigation_chronology",
)


def evidence_quality(bundle: Any) -> dict:
    """Compute the six evidence-quality metrics for a bundle. Deterministic + model-free."""
    items = list(bundle.evidence.values())
    n = len(items)
    facets_present = {it.facet for it in items}
    kinds_present = {it.kind for it in items}

    facet_coverage = round(len(facets_present & set(_ENRICHABLE_FACETS)) / len(_ENRICHABLE_FACETS), 4)
    evidence_completeness = round(len(kinds_present & set(_TARGET_KINDS)) / len(_TARGET_KINDS), 4)
    provenance_completeness = round(sum(1 for it in items if it.provenance) / n, 4) if n else 1.0

    accounts = sum(1 for e in bundle.entities.values() if e.kind == "account")
    graph_density = round(len(bundle.relationships) / accounts, 4) if accounts else 0.0

    chrono = next((it for it in items if it.kind == "investigation_chronology"), None)
    if chrono is not None and n:
        covered = len(set((chrono.value or {}).get("order") or []) & set(bundle.evidence.keys()))
        timeline_completeness = round(covered / n, 4)
    else:
        timeline_completeness = 0.0

    total_refs = 0
    ok_refs = 0
    for it in items:
        for step in (it.traceability_path or []):
            ref = step.get("from") if isinstance(step, dict) else None
            if isinstance(ref, str) and ref.startswith("ev:"):
                total_refs += 1
                ok_refs += 1 if ref in bundle.evidence else 0
    for rel in bundle.relationships:
        for ref in (rel.evidence_refs or []):
            if isinstance(ref, str) and ref.startswith("ev:"):
                total_refs += 1
                ok_refs += 1 if ref in bundle.evidence else 0
    citation_integrity = round(ok_refs / total_refs, 4) if total_refs else 1.0

    return {
        "evidence_completeness": evidence_completeness,
        "facet_coverage": facet_coverage,
        "provenance_completeness": provenance_completeness,
        "graph_density": graph_density,
        "timeline_completeness": timeline_completeness,
        "citation_integrity": citation_integrity,
        "facets_present": sorted(facets_present),
        "kinds_present": sorted(kinds_present),
        "n_evidence": n,
        "n_relationships": len(bundle.relationships),
        "n_entities": len(bundle.entities),
    }
