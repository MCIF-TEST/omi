"""Tests for public campaign sharing — mint/revoke token + the token-gated
read-only public report (no auth). Mirrors the investigation sharing system;
reuses the campaign data + evidence-pack renderers.
"""

from __future__ import annotations

import json

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


def _cluster(method: str, members: list[str], score: float = 0.9, evidence=None):
    return CoordinationCluster(
        method=method, members=list(members), score=score,
        evidence=evidence or [f"{method} fired across {len(members)} accounts"],
    )


def _seed(clusters, *, platform="x", context="vid1", score=0.9, texts=None) -> str:
    with get_session() as s:
        camps = CampaignService(s).record_clusters(
            platform=platform, context_id=context, clusters=clusters,
            coordination_score=score, texts_by_account=texts or {},
        )
        return camps[0].campaign_key


def test_mint_share_token_is_idempotent_and_makes_public():
    key = _seed([_cluster("fingerprint_cluster", ["a", "b", "c"]), _cluster("co_tag", ["a", "b", "c"])])
    with TestClient(app) as tc:
        r1 = tc.post(f"/v1/campaigns/{key}/share")
        assert r1.status_code == 200
        body = r1.json()
        assert body["is_public"] is True
        assert body["share_token"].startswith("cmp_")
        assert body["public_url"] == f"/rc/{body['share_token']}"
        # Idempotent — same token on a second call.
        r2 = tc.post(f"/v1/campaigns/{key}/share")
        assert r2.json()["share_token"] == body["share_token"]


def test_public_report_view_carries_the_trust_contract():
    key = _seed(
        [_cluster("fingerprint_cluster", ["a", "b", "c"]), _cluster("co_tag", ["a", "b", "c"])],
        texts={"a": ["love #drill @leader"], "b": ["#drill now @leader"]},
    )
    with TestClient(app) as tc:
        token = tc.post(f"/v1/campaigns/{key}/share").json()["share_token"]
        r = tc.get(f"/rc/{token}")
        assert r.status_code == 200
        v = r.json()["view"]
        # Summary + confidence + corroboration.
        assert v["meta"]["campaign_key"] == key
        assert v["verdict"]["corroborated"] is True
        assert "fingerprint_cluster" in v["verdict"]["discriminative_methods"]
        assert v["verdict"]["confidence"] >= 0
        # Evidence for AND against both present.
        assert any("fired" in e for e in v["evidence_for"])
        assert len(v["evidence_against"]) >= 1  # silent detectors surfaced
        # History / members / methodology / disclaimer.
        assert isinstance(v["members"], list)
        assert isinstance(v["observations"], list)
        assert v["methodology"] and v["disclaimer"]
        assert "#drill" in v["hashtags"]


def test_public_report_markdown_and_json_download():
    key = _seed([_cluster("fingerprint_cluster", ["a", "b", "c"])])
    with TestClient(app) as tc:
        token = tc.post(f"/v1/campaigns/{key}/share").json()["share_token"]
        md = tc.get(f"/rc/{token}/markdown")
        assert md.status_code == 200
        assert md.headers["content-type"].startswith("text/markdown")
        assert "OMISPHERE Campaign" in md.text
        js = tc.get(f"/rc/{token}/json")
        assert js.status_code == 200
        pack = json.loads(js.text)
        assert pack["campaign"]["campaign_key"] == key


def test_revoke_makes_public_report_404():
    key = _seed([_cluster("fingerprint_cluster", ["a", "b", "c"])])
    with TestClient(app) as tc:
        token = tc.post(f"/v1/campaigns/{key}/share").json()["share_token"]
        assert tc.get(f"/rc/{token}").status_code == 200
        assert tc.delete(f"/v1/campaigns/{key}/share").status_code == 200
        # Public URL dies immediately.
        assert tc.get(f"/rc/{token}").status_code == 404
        assert tc.get(f"/rc/{token}/markdown").status_code == 404


def test_unknown_token_is_404():
    with TestClient(app) as tc:
        assert tc.get("/rc/cmp_does_not_exist").status_code == 404


def test_detail_endpoint_exposes_share_state():
    key = _seed([_cluster("fingerprint_cluster", ["a", "b", "c"])])
    with TestClient(app) as tc:
        # Private by default.
        d0 = tc.get(f"/v1/campaigns/{key}").json()
        assert d0["is_public"] is False and d0["share_token"] is None
        # After sharing, the detail reflects the token (so the UI can init).
        tc.post(f"/v1/campaigns/{key}/share")
        d1 = tc.get(f"/v1/campaigns/{key}").json()
        assert d1["is_public"] is True and d1["share_token"].startswith("cmp_")


def test_share_unknown_campaign_is_404():
    with TestClient(app) as tc:
        assert tc.post("/v1/campaigns/nope/share").status_code == 404
