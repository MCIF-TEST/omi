"""Evidence enrichment (Sprint 010) — richer structured facets, projected, never invented.

Additive, **opt-in** projection that the Binder runs when ``enrich=True``. It assembles more of
the *existing* engine output into structured ``EvidenceItem``s and ``Relationship``s — it
computes nothing, runs no model, and changes no score. Every enriched item carries provenance +
a ``traceability_path`` back to the source it was derived from, so nothing loses traceability.
Each step degrades gracefully (no source data → no item), which is what keeps historical
bundles and replay correct: a payload that lacks a field simply yields no enrichment for it.

Default behavior is unchanged: with ``enrich=False`` the Binder adds none of this and the
``bundle_id`` is byte-identical to before.
"""
from __future__ import annotations

from typing import Any, Callable

from .bundle import EvidenceBundle, EvidenceItem, Relationship

# The atomic kinds the core Binder already emits — enrichment adds *derived* kinds on top.
BASE_KINDS = frozenset({"headline", "contribution", "detector_signal", "coordination_method"})


def _members_of(bundle: EvidenceBundle, coord_ev_id: str) -> list[str]:
    return [r.from_ for r in bundle.relationships if r.type == "member_of" and r.to == coord_ev_id]


def enrich_bundle(
    bundle: EvidenceBundle, payload: dict, *,
    mint_ev: Callable[[], str], mint_rel: Callable[[], str], subject_id: str, prov: dict,
) -> None:
    """Project the enriched facets onto ``bundle`` in a fixed, deterministic order."""
    _feature_importance(bundle, mint_ev, subject_id, prov)
    _temporal_pattern(bundle, mint_ev, subject_id, prov)
    _coordination_summary(bundle, mint_ev, subject_id, prov)
    _engagement_distribution(bundle, payload, mint_ev, subject_id, prov)
    _narrative_cluster(bundle, payload, mint_ev, subject_id, prov)
    _metadata_summary(bundle, payload, mint_ev, subject_id, prov)
    _detector_provenance(bundle, mint_ev, subject_id, prov)
    _co_engaged_edges(bundle, mint_rel)
    _cross_links(bundle, payload, mint_ev, subject_id, prov)
    _investigation_chronology(bundle, mint_ev, subject_id, prov)


# --------------------------------------------------------------------------- #
# Derived behavioral / coordination / detector evidence
# --------------------------------------------------------------------------- #
def _feature_importance(bundle, mint_ev, subject_id, prov) -> None:
    contribs = [it for it in bundle.evidence.values() if it.kind == "contribution" and not it.supplemental]
    if not contribs:
        return
    ranked = sorted(contribs, key=lambda it: (-abs(float((it.value or {}).get("impact") or 0.0)), it.id))
    eid = mint_ev()
    bundle.evidence[eid] = EvidenceItem(
        id=eid, facet="behavioral", kind="feature_importance", source="scoring.contributions",
        originating_detector="feature_importance",
        value={"ranking": [
            {"signal": it.originating_detector, "impact": round(float((it.value or {}).get("impact") or 0.0), 4),
             "direction": it.direction, "ref": it.id} for it in ranked
        ]},
        subject_refs=[subject_id], label="feature importance summary", provenance=prov,
        traceability_path=[{"from": it.id} for it in ranked],
    )


def _temporal_pattern(bundle, mint_ev, subject_id, prov) -> None:
    temporal = [it for it in bundle.evidence.values()
                if it.kind == "contribution" and it.originating_detector == "temporal"]
    if not temporal:
        return
    t = temporal[0]
    eid = mint_ev()
    bundle.evidence[eid] = EvidenceItem(
        id=eid, facet="behavioral", kind="temporal_pattern", source="detection.temporal",
        originating_detector="temporal_pattern", direction=t.direction,
        value={"signal": "temporal", "direction": t.direction, "impact": (t.value or {}).get("impact")},
        subject_refs=[subject_id], label="temporal pattern", provenance=prov,
        traceability_path=[{"from": t.id}],
    )


def _coordination_summary(bundle, mint_ev, subject_id, prov) -> None:
    methods = [it for it in bundle.evidence.values() if it.kind == "coordination_method"]
    if not methods:
        return
    disc = sorted({it.originating_detector for it in methods if it.discriminative})
    eid = mint_ev()
    bundle.evidence[eid] = EvidenceItem(
        id=eid, facet="coordination", kind="coordination_summary", source="coordination.aggregate",
        originating_detector="coordination_summary", discriminative=bool(disc),
        value={
            "methods": sorted({it.originating_detector for it in methods}),
            "discriminative_methods": disc,
            "total_members": sum(int((it.value or {}).get("members") or 0) for it in methods),
            "n_methods": len(methods),
        },
        subject_refs=[subject_id], label="coordination summary", provenance=prov,
        traceability_path=[{"from": m.id} for m in sorted(methods, key=lambda x: x.id)],
    )


def _detector_provenance(bundle, mint_ev, subject_id, prov) -> None:
    items = [it for it in bundle.evidence.values() if it.kind in BASE_KINDS and it.kind != "headline"]
    if not items:
        return
    eid = mint_ev()
    bundle.evidence[eid] = EvidenceItem(
        id=eid, facet="detector", kind="detector_provenance", source="provenance",
        originating_detector="detector_provenance",
        value={
            "detectors": sorted({it.originating_detector for it in items}),
            "engine_version": prov.get("engine_version"), "binder_version": prov.get("binder_version"),
            "n_signals": len(items),
        },
        subject_refs=[subject_id], label="detector provenance", provenance=prov,
        traceability_path=[{"from": it.id} for it in sorted(items, key=lambda x: x.id)],
    )


# --------------------------------------------------------------------------- #
# Metadata / narrative / engagement
# --------------------------------------------------------------------------- #
def _engagement_distribution(bundle, payload, mint_ev, subject_id, prov) -> None:
    commenters = (payload.get("video") or {}).get("commenters") or payload.get("commenters") or []
    if not commenters:
        return
    dist: dict[str, int] = {}
    for c in commenters:
        tier = str(c.get("tier") or "unknown")
        dist[tier] = dist.get(tier, 0) + 1
    eid = mint_ev()
    bundle.evidence[eid] = EvidenceItem(
        id=eid, facet="metadata", kind="engagement_distribution", source="intelligence.commenters",
        originating_detector="engagement_distribution",
        value={"distribution": dict(sorted(dist.items())), "n": len(commenters)},
        subject_refs=[subject_id], label="commenter tier distribution", provenance=prov,
        traceability_path=[{"from": "video.commenters", "n": len(commenters)}],
    )


def _narrative_cluster(bundle, payload, mint_ev, subject_id, prov) -> None:
    narr = payload.get("narrative") or {}
    if not narr:
        return
    score = float(narr.get("inauthenticity_score") or narr.get("coordination_score") or 0.0)
    eid = mint_ev()
    bundle.evidence[eid] = EvidenceItem(
        id=eid, facet="narrative", kind="narrative_cluster", source="narrative.aggregate",
        originating_detector=str(narr.get("label") or "narrative"),
        direction="raises" if score >= 0.5 else "neutral",
        value={"label": narr.get("label"), "inauthenticity_score": narr.get("inauthenticity_score"),
               "distinct_authors": narr.get("distinct_authors"), "signals": narr.get("signals")},
        subject_refs=[subject_id], label="narrative cluster", provenance=prov,
        traceability_path=[{"from": "narrative"}],
    )


def _metadata_summary(bundle, payload, mint_ev, subject_id, prov) -> None:
    eid = mint_ev()
    bundle.evidence[eid] = EvidenceItem(
        id=eid, facet="metadata", kind="metadata_summary", source="investigation",
        originating_detector="metadata_summary",
        value={
            "platform": bundle.subject.get("platform"), "grain": bundle.grain,
            "weak_signals": list(payload.get("weak_signals") or []),
            "single_axis_capped": bool(payload.get("single_axis_capped")),
        },
        subject_refs=[subject_id], label="metadata summary", provenance=prov,
        traceability_path=[{"from": "payload.metadata"}],
    )


# --------------------------------------------------------------------------- #
# Graph + chronology
# --------------------------------------------------------------------------- #
def _co_engaged_edges(bundle, mint_rel) -> None:
    coord_ids = [it.id for it in bundle.evidence.values() if it.kind == "coordination_method"]
    for cid in sorted(coord_ids):
        members = sorted(_members_of(bundle, cid))
        for other in members[1:]:                       # bounded star from the first member
            rid = mint_rel()
            bundle.relationships.append(Relationship(
                id=rid, type="co_engaged", from_=members[0], to=other, weight=1.0, evidence_refs=[cid],
            ))


def _cross_links(bundle, payload, mint_ev, subject_id, prov) -> None:
    for link in (payload.get("cross_links") or []):
        if not isinstance(link, dict):
            continue
        eid = mint_ev()
        bundle.evidence[eid] = EvidenceItem(
            id=eid, facet="graph", kind="cross_link", source="investigation.cross_links",
            originating_detector=str(link.get("kind") or "cross_link"),
            value={"kind": link.get("kind"), "summary": (link.get("summary") or "")[:240]},
            subject_refs=[subject_id], label="cross link", provenance=prov,
            traceability_path=[{"from": "cross_links"}],
        )


def _investigation_chronology(bundle, mint_ev, subject_id, prov) -> None:
    refs = sorted(bundle.evidence.keys())
    if not refs:
        return
    eid = mint_ev()
    bundle.evidence[eid] = EvidenceItem(
        id=eid, facet="metadata", kind="investigation_chronology", source="bundle",
        originating_detector="investigation_chronology",
        value={"order": refs, "n": len(refs)},
        subject_refs=[subject_id], label="investigation chronology", provenance=prov,
        traceability_path=[{"from": r} for r in refs],
    )
