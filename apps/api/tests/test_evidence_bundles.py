"""Phase P3.0 — the canonical per-stage Evidence Bundle layer.

Proves the seven bundles are immutable, deterministic, content-addressed, hashable, serializable, and
independently buildable; that each carries ONLY its stage's evidence (no prose / presentation / UI /
AI text); that shared entities are referenced by id (no field or cluster duplication across bundles);
and that the summary bundle is the DAG root referencing the other six by bundle_id. Pure evidence
layer — no prompt, no model, no runtime change.
"""
from __future__ import annotations

import dataclasses
import json

import pytest

from app.reasoning.context import build_investigation_context
from app.reasoning.evidence_bundles import (
    AccountEvidenceBundle,
    CampaignEvidenceBundle,
    CommentEvidenceBundle,
    CommenterHistoryBundle,
    CoordinationEvidenceBundle,
    EvidenceBundleSet,
    InvestigationSummaryBundle,
    NarrativeEvidenceBundle,
    build_account_bundle,
    build_campaign_bundle,
    build_comment_bundle,
    build_coordination_bundle,
    build_evidence_bundles,
)

_PROSE_FORBIDDEN = ("summary", "headline", "reasons", "intent_label", "matrix", "tier_distribution",
                    "assessment", "verdict")


def _payload() -> dict:
    return {
        "overall_probability": 0.72, "overall_tier": "elevated", "confidence": 0.55,
        "convergence_score": 0.3, "inputs_provided": ["video"], "video_id": "v1",
        "cross_links": [{"kind": "fellow_traveler", "severity": "elevated", "summary": "co-appeared",
                         "evidence": ["5 shared"], "related_entities": ["a", "b"]}],
        "video": {
            "coordination_score": 0.66, "coordination_tier": "elevated",
            "clusters": [{"method": "co_engagement", "members": ["a", "b", "c"], "score": 0.7,
                          "evidence": ["tight"]},
                         {"method": "style_match", "members": ["a", "b"], "score": 0.3, "evidence": []}],
            "thread_scan": {"overall_probability": 0.5, "tier": "moderate"},
            "commenters": [{"external_id": "a", "handle": "@a", "overall_probability": 0.8, "tier": "high",
                            "confidence": 0.6, "matched_prior_neighbors": 2, "from_cache": False,
                            "recent_activity": [{"text": "great video!!", "created_at": "2026-01-01T00:00:00Z",
                                                 "parent_id": "v9"}],
                            "signals": [{"name": "temporal", "probability": 0.8, "confidence": 0.7}],
                            "contributions": [{"name": "temporal", "impact": 0.4, "direction": "raises"}],
                            "weak_signals": ["few posts"], "intent_label": "astroturf",
                            "suspected_intent": "astroturf"}]},
    }


def _ctx(payload=None):
    return build_investigation_context(payload or _payload(), ref="slug1", platform="youtube",
                                       slug="slug1", kind="video")


def _all(bundles: EvidenceBundleSet):
    return list(bundles.stage_bundles().values())


def test_builds_seven_bundles():
    s = build_evidence_bundles(_ctx())
    assert isinstance(s, EvidenceBundleSet)
    assert set(s.stage_bundles()) == {
        "comment_analysis", "commenter_history", "account_analysis", "narrative_analysis",
        "coordination_analysis", "campaign_analysis", "investigation_summary"}
    assert isinstance(s.comment, CommentEvidenceBundle)
    assert isinstance(s.account, AccountEvidenceBundle)
    assert isinstance(s.summary, InvestigationSummaryBundle)


def test_bundles_are_immutable_hashable_content_addressed_serializable():
    s = build_evidence_bundles(_ctx())
    for b in _all(s):
        assert b.bundle_id().startswith("eb:")               # content-addressed
        assert isinstance(hash(b), int)                       # hashable
        d = b.to_dict()
        assert d["bundle_id"] == b.bundle_id() and json.loads(json.dumps(d))  # serializable
        with pytest.raises(dataclasses.FrozenInstanceError):  # immutable
            b.stage = "x"


def test_deterministic_and_sensitive():
    a = build_evidence_bundles(_ctx())
    b = build_evidence_bundles(_ctx())
    for k in a.stage_bundles():
        assert a.stage_bundles()[k].bundle_id() == b.stage_bundles()[k].bundle_id()
    # a change in the evidence changes the addressed bundle
    p = _payload()
    p["video"]["commenters"][0]["overall_probability"] = 0.11
    assert build_account_bundle(_ctx(p)).bundle_id() != a.account.bundle_id()


def test_each_bundle_carries_only_its_stage_evidence_no_prose():
    s = build_evidence_bundles(_ctx())
    # Comment owns comment text + thread signal; not signals/clusters
    cd = s.comment.to_dict()
    assert cd["comments"][0]["text"] and "signals" not in cd and "clusters" not in cd
    # Account owns signals/contributions/omiscore; not raw comment text / clusters
    ad = s.account.to_dict()
    assert ad["accounts"][0]["signals"][0]["name"] == "temporal"
    assert ad["accounts"][0]["omiscore"] is not None
    assert "clusters" not in ad and "comments" not in ad
    # Ruling 3: suspected_intent (a heuristic interpretation) is NOT evidence — absent even though the
    # payload commenter carries it.
    assert "suspected_intent" not in ad["accounts"][0]
    # Coordination owns clusters + graph; Campaign owns only refs (no cluster copies)
    assert s.coordination.cluster_count == 2 and s.coordination.clusters
    cad = s.campaign.to_dict()
    assert "clusters" not in cad and set(cad) >= {"candidate_cluster_refs", "count"}
    # NO prose / presentation / UI / verdict fields anywhere
    for b in _all(s):
        keys = set(dataclasses.asdict(b))
        assert not (keys & set(_PROSE_FORBIDDEN)), f"{b.stage} leaked presentation: {keys & set(_PROSE_FORBIDDEN)}"


def test_no_cluster_duplication_campaign_references_coordination_by_ref():
    s = build_evidence_bundles(_ctx())
    coord_refs = {c.cluster_ref for c in s.coordination.clusters}
    # every campaign candidate is a REFERENCE into the coordination clusters — not a copy
    assert set(s.campaign.candidate_cluster_refs) <= coord_refs
    # only the corroboration-gated (>=0.5) cluster is a campaign candidate
    assert len(s.campaign.candidate_cluster_refs) == 1
    gated = next(c for c in s.coordination.clusters if c.cluster_ref in s.campaign.candidate_cluster_refs)
    assert gated.score >= 0.5


def test_summary_is_the_dag_root_referencing_the_six_by_id():
    s = build_evidence_bundles(_ctx())
    comp = s.summary.component_map()
    assert set(comp) == {"comment_analysis", "commenter_history", "account_analysis",
                         "narrative_analysis", "coordination_analysis", "campaign_analysis"}
    assert comp["account_analysis"] == s.account.bundle_id()
    assert comp["coordination_analysis"] == s.coordination.bundle_id()
    # the summary owns investigation-level evidence (echoed numbers + cross-links) + the six DAG refs
    assert s.summary.overall_probability == pytest.approx(0.72)
    assert s.summary.cross_links and s.summary.cross_links[0].kind == "fellow_traveler"


def test_summary_is_enriched_with_pure_synthesis_evidence_no_prose():
    """P3.4 — the summary bundle carries the investigation-synthesis EVIDENCE the AI stage reasons over
    (coordination digest, signed drivers, account roll-up, data-quality caveats), sourced from the
    Investigation Context. Pure measured evidence: no prose/verdict field leaks in."""
    s = build_evidence_bundles(_ctx())
    sm = s.summary
    assert sm.coordination is not None and sm.coordination.coordination_score == pytest.approx(0.66)
    assert sm.coordination.discriminative_methods == ("co_engagement",)
    assert sm.accounts_digest is not None and sm.accounts_digest.count == 1
    assert sm.accounts_digest.flagged_count == 1 and sm.accounts_digest.high_count == 1
    assert any(c.name == "temporal" for c in sm.contributions)
    assert "few posts" in sm.weak_signals
    # the enrichment is EVIDENCE only — no prose/presentation/verdict top-level fields
    keys = set(dataclasses.asdict(sm))
    assert not (keys & set(_PROSE_FORBIDDEN)), f"summary leaked presentation: {keys & set(_PROSE_FORBIDDEN)}"


def test_builders_are_independent():
    ctx = _ctx()
    assert build_comment_bundle(ctx).comment_count == 1
    assert build_coordination_bundle(ctx).cluster_count == 2
    assert build_campaign_bundle(ctx).count == 1
    assert build_account_bundle(ctx).count == 1


def test_empty_payload_is_safe_and_typed():
    s = build_evidence_bundles(build_investigation_context({}, ref="x", platform="unknown"))
    assert s.comment.comment_count == 0 and s.account.count == 0
    assert s.coordination.cluster_count == 0 and s.campaign.count == 0
    assert s.narrative.count == 0
    for b in _all(s):
        assert b.bundle_id().startswith("eb:")
