"""Phase 5 item 2 — public-report rate limiting + view dedup.

Protects the unauthenticated /r and /rc routes (and the Q3 share-read metric)
from a single scraper, while keeping genuinely distinct viewers counted.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.campaigns.service import CampaignService
from app.core.rate_limit import PUBLIC_REPORT_LIMITER
from app.detection.coordination._types import CoordinationCluster
from app.main import app
from app.storage.db import get_session, reset_db_for_tests
from app.storage.models import EventLog


@pytest.fixture(autouse=True)
def _fresh():
    reset_db_for_tests()
    PUBLIC_REPORT_LIMITER._windows.clear()
    # Dedup uses the shared TTL cache; clear it so tokens from prior tests
    # don't suppress this test's first view.
    from app.core.cache import get_cache
    get_cache()._d.clear()
    yield
    PUBLIC_REPORT_LIMITER._windows.clear()


def _public_campaign_token(tc: TestClient, members=("a", "b", "c")) -> str:
    with get_session() as s:
        camps = CampaignService(s).record_clusters(
            platform="x", context_id="vid1",
            clusters=[CoordinationCluster(method="fingerprint_cluster",
                                          members=list(members), score=0.9,
                                          evidence=["e"])],
            coordination_score=0.9)
        key = camps[0].campaign_key
    return tc.post(f"/v1/campaigns/{key}/share").json()["share_token"]


def _views() -> int:
    with get_session() as s:
        return len(s.execute(
            select(EventLog).where(EventLog.kind == "public_report_view")
        ).scalars().all())


def test_repeat_views_from_same_client_are_deduped():
    with TestClient(app) as tc:
        token = _public_campaign_token(tc)
        for _ in range(5):
            assert tc.get(f"/rc/{token}").status_code == 200
    # 5 reads from one client (same IP) within the window -> a single logged view.
    assert _views() == 1


def test_distinct_tokens_each_count():
    with TestClient(app) as tc:
        t1 = _public_campaign_token(tc, members=("a", "b", "c"))
        t2 = _public_campaign_token(tc, members=("x", "y", "z"))  # distinct campaign
        assert t1 != t2
        tc.get(f"/rc/{t1}")
        tc.get(f"/rc/{t2}")
    assert _views() == 2


def test_public_route_is_rate_limited():
    with TestClient(app) as tc:
        token = _public_campaign_token(tc)
        # Generous budget (60/min); the 61st request from one IP is throttled.
        statuses = [tc.get(f"/rc/{token}").status_code for _ in range(61)]
        assert statuses.count(429) >= 1
        last_429 = next(tc.get(f"/rc/{token}") for _ in range(1))
        assert last_429.status_code == 429
        assert "Retry-After" in last_429.headers


def test_markdown_and_json_public_routes_are_also_limited():
    with TestClient(app) as tc:
        token = _public_campaign_token(tc)
        PUBLIC_REPORT_LIMITER._windows.clear()
        # Exhaust the budget on the markdown sub-route (router-level dependency).
        for _ in range(60):
            tc.get(f"/rc/{token}/markdown")
        assert tc.get(f"/rc/{token}/json").status_code == 429
