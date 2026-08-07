"""Campaign rows are deployment-global, so the library needs a gate, not a scope.

``Campaign`` has no ``user_id`` on purpose: one operation seen by two customers on two different
posts is ONE campaign, and that cross-customer accumulation is the point of the feature. The cost is
that these routes cannot be "scoped to your own data", because there is no such thing here.

Before this, ``require_user`` with no admin check meant any signed-in customer could:

* enumerate every campaign in the deployment, each with its ``share_token`` (a capability URL);
* read ``observations[].context_id``, the id of the post ANOTHER CUSTOMER SCANNED;
* mint a permanent public ``/rc/<token>`` report for any campaign, including one assembled from
  other customers' scans, and revoke anyone else's.

The existing campaign tests could not catch any of it: they run in local mode, where
``require_user`` returns ``is_admin=True``. Every test here signs up a real, non-admin user.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.campaigns.service import CampaignService
from app.core.config import get_settings
from app.detection.coordination._types import CoordinationCluster
from app.main import app
from app.storage.db import get_session, reset_db_for_tests
from app.storage.models import User


@pytest.fixture(autouse=True)
def _fresh(monkeypatch):
    monkeypatch.setenv("OMI_REQUIRE_AUTH", "true")
    monkeypatch.setenv("OMI_SESSION_SECRET", "x" * 64)
    get_settings.cache_clear()
    reset_db_for_tests()
    from app.core.rate_limit import PUBLIC_REPORT_LIMITER
    PUBLIC_REPORT_LIMITER._windows.clear()
    yield
    get_settings.cache_clear()


def _signup(tc: TestClient, email: str = "customer@t.com") -> int:
    r = tc.post("/v1/auth/signup", json={"email": email, "password": "password12345"})
    assert r.status_code == 200, r.text
    return r.json()["id"]


def _make_admin(user_id: int) -> None:
    with get_session() as s:
        s.get(User, user_id).is_admin = 1


def _seed(key_hint: str = "vid1") -> str:
    """A campaign built from someone else's scan of post `key_hint`."""
    with get_session() as s:
        camps = CampaignService(s).record_clusters(
            platform="x", context_id=key_hint,
            clusters=[
                CoordinationCluster(method="fingerprint_cluster", members=["a", "b", "c"],
                                    score=0.9, evidence=["fingerprint fired"]),
                CoordinationCluster(method="co_tag", members=["a", "b", "c"],
                                    score=0.9, evidence=["co_tag fired"]),
            ],
            coordination_score=0.9,
        )
        return camps[0].campaign_key


# --------------------------------------------------------------------------------------------- #
# Enumeration
# --------------------------------------------------------------------------------------------- #
def test_a_customer_cannot_enumerate_the_deployments_campaigns():
    _seed()
    with TestClient(app) as tc:
        _signup(tc)
        assert tc.get("/v1/campaigns").status_code == 403


def test_an_admin_still_can():
    _seed()
    with TestClient(app) as tc:
        _make_admin(_signup(tc, "admin@t.com"))
        r = tc.get("/v1/campaigns")
        assert r.status_code == 200
        assert r.json()["total"] >= 1


def test_a_customer_cannot_read_an_arbitrary_campaign():
    key = _seed()
    with TestClient(app) as tc:
        _signup(tc)
        assert tc.get(f"/v1/campaigns/{key}").status_code == 403


def test_a_customer_may_still_read_the_seeded_featured_examples():
    """Curated from public disclosure archives, owned by nobody, and the first thing a new user is
    meant to explore. Gating these would break the product's front door for no privacy gain."""
    with TestClient(app) as tc:
        _signup(tc)
        listing = tc.get("/v1/campaigns/featured")
        assert listing.status_code == 200
        keys = [c["campaign_key"] for c in listing.json()["campaigns"]]
        assert keys, "no featured campaigns were seeded"
        assert tc.get(f"/v1/campaigns/{keys[0]}").status_code == 200


# --------------------------------------------------------------------------------------------- #
# Provenance: context_id is the id of someone else's scanned post
# --------------------------------------------------------------------------------------------- #
def test_the_public_report_never_carries_provenance():
    """Unauthenticated route. This is the same class of bug as the /r/<token>/json leak: gating the
    detail route means nothing while a second route serves the same rows unfiltered."""
    key = _seed(key_hint="someone_elses_post_id")
    with TestClient(app) as tc:
        _make_admin(_signup(tc, "admin@t.com"))
        token = tc.post(f"/v1/campaigns/{key}/share").json()["share_token"]
        tc.cookies.clear()

        body = tc.get(f"/rc/{token}").text
        assert "someone_elses_post_id" not in body
        assert "someone_elses_post_id" not in tc.get(f"/rc/{token}/json").text
        assert "someone_elses_post_id" not in tc.get(f"/rc/{token}/markdown").text


def test_a_featured_campaign_read_by_a_customer_carries_no_provenance():
    with TestClient(app) as tc:
        _signup(tc)
        keys = [c["campaign_key"] for c in tc.get("/v1/campaigns/featured").json()["campaigns"]]
        detail = tc.get(f"/v1/campaigns/{keys[0]}").json()
        assert all(o["context_id"] is None for o in detail["observations"])


def test_an_admin_does_see_provenance_on_the_detail_route():
    """The gate must not blind the operator. Admins are who investigates a campaign, and the post
    an observation came from is the first thing they need."""
    key = _seed(key_hint="post_abc")
    with TestClient(app) as tc:
        _make_admin(_signup(tc, "admin@t.com"))
        detail = tc.get(f"/v1/campaigns/{key}").json()
        assert any(o["context_id"] == "post_abc" for o in detail["observations"])


def test_the_export_pack_is_stripped_even_for_an_admin():
    """The pack is a file that leaves the app to be forwarded to someone else. That is exactly when
    provenance must not ride along."""
    key = _seed(key_hint="post_abc")
    with TestClient(app) as tc:
        _make_admin(_signup(tc, "admin@t.com"))
        assert "post_abc" not in tc.get(f"/v1/campaigns/{key}/export?format=json").text
        assert "post_abc" not in tc.get(f"/v1/campaigns/{key}/export?format=markdown").text


# --------------------------------------------------------------------------------------------- #
# Publishing: the gate that mattered most
# --------------------------------------------------------------------------------------------- #
def test_a_customer_cannot_publish_a_campaign():
    """Without this, a customer could take a campaign assembled partly from other customers' scans
    and mint a permanent unauthenticated URL naming its member accounts. Publishing a claim about
    named real people is the operator's decision, never a customer's on their behalf."""
    key = _seed()
    with TestClient(app) as tc:
        _signup(tc)
        r = tc.post(f"/v1/campaigns/{key}/share")
        assert r.status_code == 403
    with get_session() as s:
        from sqlalchemy import select

        from app.storage.models import Campaign
        c = s.execute(select(Campaign).where(Campaign.campaign_key == key)).scalar_one()
        assert c.share_token is None and not c.is_public


def test_a_customer_cannot_unpublish_someone_elses_campaign():
    """The mirror image: otherwise any customer could take down the featured examples."""
    key = _seed()
    with TestClient(app) as tc:
        _make_admin(_signup(tc, "admin@t.com"))
        token = tc.post(f"/v1/campaigns/{key}/share").json()["share_token"]
        tc.cookies.clear()
        _signup(tc, "customer@t.com")
        assert tc.delete(f"/v1/campaigns/{key}/share").status_code == 403
        tc.cookies.clear()
        assert tc.get(f"/rc/{token}").status_code == 200, "the report was taken down by a customer"


def test_share_tokens_are_not_handed_out_by_the_listing():
    """A share token is a capability URL. The listing carries one per campaign, which is a second
    reason the listing itself has to be admin-only."""
    key = _seed()
    with TestClient(app) as tc:
        _make_admin(_signup(tc, "admin@t.com"))
        tc.post(f"/v1/campaigns/{key}/share")
        tc.cookies.clear()
        _signup(tc, "customer@t.com")
        r = tc.get("/v1/campaigns")
        assert r.status_code == 403
        assert "cmp_" not in r.text


# --------------------------------------------------------------------------- #
# Narratives have no owner either, and were missed by the campaign tenancy pass
# --------------------------------------------------------------------------- #
def test_narratives_are_admin_only_because_they_have_no_owner():
    """`Narrative` has no user_id: it is a cross-customer cluster built from every scan the
    deployment has run. `samples` and `members` are comment texts and accounts drawn from OTHER
    customers' investigations, so `require_user` alone let any signed-in customer enumerate them.

    Same exposure `app/routes/campaigns.py` was fixed for, and narratives were missed by that pass.
    Nothing legitimate breaks: the /narratives page is already admin-only and server-gated, so no
    customer flow reaches these routes.
    """
    with TestClient(app) as tc:
        _signup(tc, "narrative-probe@t.com")
        for path in ("/v1/narratives", "/v1/narratives/1", "/v1/narratives/1/members"):
            assert tc.get(path).status_code == 403, f"{path} is reachable by a plain customer"


def test_an_admin_still_reaches_the_narrative_library():
    """The gate must not lock the operator out of their own investigative surface."""
    with TestClient(app) as tc:
        uid = _signup(tc, "narrative-admin@t.com")
        _make_admin(uid)
        assert tc.get("/v1/narratives").status_code == 200
