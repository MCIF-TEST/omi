"""Tests for first-run featured campaigns — real disclosed IO operations seeded
into the campaign store so a new user has a genuine campaign to explore.

These verify the seed is idempotent, the /featured endpoint returns the real
campaigns with their blurb, and the public report works on a seeded campaign
(so the share/export surfaces light up for free).
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.content.featured import (
    featured_definitions,
    featured_keys,
    seed_featured_campaigns,
)
from app.main import app
from app.storage.db import get_session, reset_db_for_tests
from app.storage.models import Campaign, CampaignMember


@pytest.fixture(autouse=True)
def _fresh_db():
    reset_db_for_tests()
    yield


def test_fixture_is_real_and_corroboration_gated():
    """The committed fixture must be real engine output: every featured
    campaign cleared the corroboration gate (>= 0.5) and lists detector
    methods + members. Guards against a fake/empty fixture slipping in."""
    defs = featured_definitions()
    assert len(defs) >= 1
    for d in defs:
        assert d["campaign_key"].startswith("feat_")
        assert d["coordination_score"] >= 0.5            # gate-cleared
        assert d["methods"]                              # at least one detector
        assert d["members"]                              # real members
        assert d.get("blurb")                            # editorial context
        # At least one campaign should be corroborated by a discriminative lens.
    assert any(
        set(d["methods"]) & {"fingerprint_cluster", "co_engagement", "co_tag"}
        for d in defs
    ), "no featured campaign is corroborated by a discriminative detector"


def test_seed_is_idempotent():
    with get_session() as s:
        n1 = seed_featured_campaigns(s)
    assert n1 == len(featured_keys())
    with get_session() as s:
        n2 = seed_featured_campaigns(s)          # second run inserts nothing
    assert n2 == 0
    with get_session() as s:
        assert s.query(Campaign).count() == len(featured_keys())
        # Members were seeded too.
        assert s.query(CampaignMember).count() > 0


def test_featured_endpoint_returns_real_campaigns_with_blurb():
    with get_session() as s:
        seed_featured_campaigns(s)
    with TestClient(app) as tc:
        r = tc.get("/v1/campaigns/featured")
        assert r.status_code == 200
        camps = r.json()["campaigns"]
        assert len(camps) == len(featured_keys())
        for c in camps:
            assert c["campaign_key"].startswith("feat_")
            assert c["blurb"]
            assert c["coordination_score"] >= 0.5
            assert c["is_public"] is True            # public by default
            assert c["share_token"]


def test_featured_path_not_captured_as_campaign_key():
    # The /featured route must win over /{campaign_key}.
    with TestClient(app) as tc:
        r = tc.get("/v1/campaigns/featured")
        assert r.status_code == 200
        assert "campaigns" in r.json()


def test_stable_tokens_match_the_landing_page_contract():
    """The marketing landing page hardcodes the Xinjiang featured token
    (`/rc/cmp_feat_cn_xinjiang`) as its primary no-signup CTA — the shortest
    path to the value moment. The token scheme is stable BY DESIGN
    (featured.py: ``cmp_`` + campaign_key); this pins it so any change to the
    scheme or the fixture keys breaks loudly instead of dead-linking the
    front door."""
    keys = featured_keys()
    assert "feat_cn_xinjiang" in keys and "feat_ru_gru_202012" in keys
    with get_session() as s:
        seed_featured_campaigns(s)
        camp = s.query(Campaign).filter_by(campaign_key="feat_cn_xinjiang").one()
        assert camp.share_token == "cmp_feat_cn_xinjiang"
        assert bool(camp.is_public)


def test_public_featured_report_offers_the_other_featured_campaign():
    """First-run cross-navigation: an anonymous visitor on one featured report
    can hop to the other featured example without an account."""
    with get_session() as s:
        seed_featured_campaigns(s)
    with TestClient(app) as tc:
        view = tc.get("/rc/cmp_feat_cn_xinjiang").json()["view"]
        others = view.get("other_featured")
        assert others and any(
            o["share_token"] == "cmp_feat_ru_gru_202012" for o in others
        )
        # A non-featured public campaign exposes nothing extra.
        from app.campaigns.service import CampaignService
        from app.detection.coordination._types import CoordinationCluster
        with get_session() as s:
            CampaignService(s).record_clusters(
                platform="x", context_id="vidz",
                clusters=[CoordinationCluster(
                    method="fingerprint_cluster", members=["a", "b", "c"],
                    score=0.9, evidence=["e"])],
                coordination_score=0.9)
        key = [c["campaign_key"] for c in tc.get("/v1/campaigns?min_score=0").json()["campaigns"]
               if not c["campaign_key"].startswith("feat_")][0]
        token = tc.post(f"/v1/campaigns/{key}/share").json()["share_token"]
        assert "other_featured" not in tc.get(f"/rc/{token}").json()["view"]


def test_seeded_campaign_has_working_public_report():
    with get_session() as s:
        seed_featured_campaigns(s)
    key = featured_keys()[0]
    with TestClient(app) as tc:
        # Detail endpoint works + reports it's already public.
        d = tc.get(f"/v1/campaigns/{key}").json()
        assert d["is_public"] is True and d["share_token"]
        token = d["share_token"]
        # Public report renders without auth, carrying the trust contract.
        rep = tc.get(f"/rc/{token}").json()["view"]
        assert rep["meta"]["campaign_key"] == key
        assert rep["verdict"]["corroborated"] in (True, False)
        assert rep["evidence_for"] and rep["evidence_against"]
