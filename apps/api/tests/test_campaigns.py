"""Campaign intelligence — durable, evolving coordination-cluster records.

Pins the principle: store observations + evidence (recurring detections merge
into one campaign that EVOLVES), never a verdict-as-truth.
"""

from __future__ import annotations

from app.campaigns.service import CampaignService, merge_clusters
from app.detection.coordination._types import CoordinationCluster
from app.storage.db import get_session
from app.storage.models import Campaign, CampaignMember, CampaignObservation


def _cluster(method, members, score=0.9, evidence=None):
    return CoordinationCluster(method=method, members=list(members), score=score,
                              evidence=evidence or [f"{method} evidence"])


def test_records_cluster_as_campaign_with_evidence_not_verdict():
    with get_session() as s:
        clusters = [_cluster("fingerprint_cluster", ["a", "b", "c", "d"]),
                    _cluster("co_tag", ["a", "b", "c"])]
        texts = {"a": ["love #FreeX @Leader"], "b": ["#freex now @leader"]}
        camps = CampaignService(s).record_clusters(
            platform="x", context_id="vid1", clusters=clusters,
            coordination_score=0.95, texts_by_account=texts)
        assert len(camps) == 1
        c = camps[0]
        assert c.member_count == 4 and c.observation_count == 1
        assert set(c.methods_json) == {"fingerprint_cluster", "co_tag"}  # clusters merged
        assert "#freex" in c.hashtags_json and "@leader" in c.mentions_json
        assert c.evidence_json                       # evidence retained
        assert c.coordination_score == 0.95
        assert c.status == "observed"
        # No verdict-as-truth: there is no boolean "this is a manipulation campaign".
        assert not hasattr(c, "is_manipulation") and not hasattr(c, "verdict")


def test_recurrence_merges_into_same_evolving_campaign():
    with get_session() as s:
        svc = CampaignService(s)
        svc.record_clusters(platform="x", context_id="v1",
                            clusters=[_cluster("fingerprint_cluster", ["a", "b", "c", "d"])],
                            coordination_score=0.90)
        svc.record_clusters(platform="x", context_id="v2",
                            clusters=[_cluster("style_match", ["a", "b", "c", "e"])],
                            coordination_score=0.85)
        camps = s.query(Campaign).all()
        assert len(camps) == 1                       # recurrence: same group, not a new campaign
        c = camps[0]
        assert c.observation_count == 2
        assert c.member_count == 5                   # a,b,c,d + e merged in (evolves)
        assert set(c.methods_json) == {"fingerprint_cluster", "style_match"}
        assert c.status == "recurring"
        assert c.max_coordination_score == 0.90
        m_a = s.query(CampaignMember).filter_by(campaign_id=c.id, account_external_id="a").one()
        assert m_a.times_observed == 2               # per-member recurrence
        assert s.query(CampaignObservation).filter_by(campaign_id=c.id).count() == 2  # history kept


def test_distinct_groups_are_separate_campaigns():
    with get_session() as s:
        svc = CampaignService(s)
        svc.record_clusters(platform="x", context_id="v1",
                            clusters=[_cluster("fingerprint_cluster", ["a", "b", "c"])],
                            coordination_score=0.9)
        svc.record_clusters(platform="x", context_id="v2",
                            clusters=[_cluster("fingerprint_cluster", ["x", "y", "z"])],
                            coordination_score=0.9)
        assert s.query(Campaign).count() == 2


def test_small_groups_not_persisted():
    with get_session() as s:
        camps = CampaignService(s).record_clusters(
            platform="x", context_id="v1",
            clusters=[_cluster("style_match", ["a", "b"])], coordination_score=0.9)
        assert camps == [] and s.query(Campaign).count() == 0


def test_merge_clusters_connected_components():
    comps = merge_clusters([
        _cluster("a", ["1", "2", "3"]), _cluster("b", ["3", "4"]),
        _cluster("c", ["7", "8", "9"]),
    ])
    assert sorted(len(c.members) for c in comps) == [3, 4]  # {1,2,3,4} merged; {7,8,9} separate
