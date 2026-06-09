"""Tests for the /v1/accounts/{platform}/{external_id}/campaigns endpoint.

The reverse-link from an account to every Campaign it appears in. Closes the
"this account is in N campaigns" affordance the audit identified without a
new table — single join over CampaignMember -> Campaign.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.campaigns.service import CampaignService
from app.detection.coordination._types import CoordinationCluster
from app.main import app
from app.storage.db import get_session, reset_db_for_tests


@pytest.fixture(autouse=True)
def _fresh_db():
    reset_db_for_tests()
    yield


def _cluster(method: str, members: list[str], score: float = 0.9):
    return CoordinationCluster(
        method=method, members=list(members), score=score,
        evidence=[f"{method} evidence"],
    )


def test_campaigns_endpoint_returns_empty_for_unknown_account():
    with TestClient(app) as tc:
        r = tc.get("/v1/accounts/youtube/UC_unknown/campaigns")
        assert r.status_code == 200
        data = r.json()
        assert data["platform"] == "youtube"
        assert data["external_id"] == "UC_unknown"
        assert data["total"] == 0
        assert data["campaigns"] == []


def test_campaigns_endpoint_returns_campaigns_account_appears_in():
    # Seed two campaigns, both containing account "a"; one also contains "b".
    with get_session() as s:
        CampaignService(s).record_clusters(
            platform="x", context_id="vid1",
            clusters=[_cluster("fingerprint_cluster", ["a", "b", "c"])],
            coordination_score=0.90,
        )
        CampaignService(s).record_clusters(
            platform="x", context_id="vid2",
            clusters=[_cluster("co_tag", ["a", "d", "e"])],
            coordination_score=0.85,
        )

    with TestClient(app) as tc:
        r = tc.get("/v1/accounts/x/a/campaigns")
        assert r.status_code == 200
        data = r.json()
        assert data["total"] == 2
        keys = {c["campaign_key"] for c in data["campaigns"]}
        assert len(keys) == 2
        # Each campaign carries the per-account observation count.
        for c in data["campaigns"]:
            assert c["times_observed_here"] == 1
            assert c["platform"] == "x"
            assert c["status"] in {"observed", "recurring"}
            assert isinstance(c["methods"], list) and c["methods"]


def test_campaigns_endpoint_per_account_recurrence_counts_match_member_table():
    # Account "a" observed in two scans of the SAME recurring campaign — the
    # endpoint should report times_observed_here = 2.
    with get_session() as s:
        svc = CampaignService(s)
        svc.record_clusters(
            platform="x", context_id="vid1",
            clusters=[_cluster("fingerprint_cluster", ["a", "b", "c", "d"])],
            coordination_score=0.90,
        )
        # Same member-set => recurrence on the same campaign.
        svc.record_clusters(
            platform="x", context_id="vid2",
            clusters=[_cluster("fingerprint_cluster", ["a", "b", "c", "d"])],
            coordination_score=0.92,
        )

    with TestClient(app) as tc:
        r = tc.get("/v1/accounts/x/a/campaigns")
        assert r.status_code == 200
        data = r.json()
        assert data["total"] == 1
        c = data["campaigns"][0]
        assert c["times_observed_here"] == 2
        assert c["observation_count"] == 2
        assert c["status"] == "recurring"


def test_campaigns_endpoint_does_not_leak_other_platforms():
    # Same external_id "a" on YouTube and X — must not cross-link.
    with get_session() as s:
        CampaignService(s).record_clusters(
            platform="x", context_id="x_vid",
            clusters=[_cluster("fingerprint_cluster", ["a", "b", "c"])],
            coordination_score=0.90,
        )
        CampaignService(s).record_clusters(
            platform="youtube", context_id="yt_vid",
            clusters=[_cluster("co_engagement", ["a", "d", "e"])],
            coordination_score=0.85,
        )

    with TestClient(app) as tc:
        r_x = tc.get("/v1/accounts/x/a/campaigns")
        r_yt = tc.get("/v1/accounts/youtube/a/campaigns")
        assert r_x.status_code == 200 and r_yt.status_code == 200
        assert r_x.json()["total"] == 1
        assert r_yt.json()["total"] == 1
        # Distinct campaign_keys — they don't merge across platforms.
        assert r_x.json()["campaigns"][0]["campaign_key"] != \
               r_yt.json()["campaigns"][0]["campaign_key"]
