"""Putting a scanned account into one of the operator's named graphs.

Both `/v1/graphs`' own module docstring and the `/graph` page's lede have promised this surface
since the API shipped ("add profiles from the commenter detail panel during an investigation").
Every endpoint existed; nothing in the product could reach them, so the only way to build a graph
was to already know an account's external id and add it by hand.

These pin the API contract the picker depends on, and the one fact it needs that the detail response
did not carry.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.core.plans import REPORTER
from app.main import app
from app.storage.db import get_session, reset_db_for_tests
from app.storage.models import Investigation, User


@pytest.fixture(autouse=True)
def _fresh(monkeypatch):
    monkeypatch.setenv("OMI_REQUIRE_AUTH", "true")
    monkeypatch.setenv("OMI_SESSION_SECRET", "x" * 64)
    get_settings.cache_clear()
    reset_db_for_tests()
    yield
    get_settings.cache_clear()


def _signup(tc: TestClient, email: str = "op@t.com", *, tier: str | None = REPORTER.slug) -> int:
    """Sign up and, by default, put the account on the tier that includes saved graphs.

    Saved graphs are a Reporter feature, so a Free signup gets 402 from every write here. These
    tests are about graph BEHAVIOUR, not about entitlement, so the fixture grants the plan rather
    than each test asserting the gate. ``test_the_graph_is_a_paid_feature`` below is where the gate
    itself is pinned; pass ``tier=None`` to exercise an unentitled caller.
    """
    r = tc.post("/v1/auth/signup", json={"email": email, "password": "password12345"})
    assert r.status_code == 200, r.text
    uid = r.json()["id"]
    if tier:
        with get_session() as s:
            s.get(User, uid).plan_tier = tier
    return uid


def _seed_investigation(user_id: int, *, slug: str = "inv_g1", platform: str = "x") -> None:
    with get_session() as s:
        s.add(Investigation(
            slug=slug, user_id=user_id, label="A post", kind="x_post",
            input_url="https://x.com/someone/status/123", target_id="123",
            overall_probability=0.2, overall_tier="low", confidence=0.5, summary="",
            quota_used=0, batch_count=1, platform=platform,
            payload_json={"video": {"commenters": []}},
        ))


class TestTheDetailResponseCarriesThePlatform:
    """The picker cannot be correct without it, and deriving it in the browser would mean re-parsing
    a multi-megabyte payload the page deliberately never touches."""

    def test_an_x_investigation_says_x(self):
        with TestClient(app) as tc:
            uid = _signup(tc)
            _seed_investigation(uid, platform="x")
            r = tc.get("/v1/investigations/inv_g1")
            assert r.status_code == 200, r.text
            assert r.json()["platform"] == "x"

    def test_a_youtube_investigation_says_youtube(self):
        with TestClient(app) as tc:
            uid = _signup(tc)
            _seed_investigation(uid, platform="youtube")
            assert tc.get("/v1/investigations/inv_g1").json()["platform"] == "youtube"


class TestAddingAnAccountToAGraph:
    def _graph(self, tc: TestClient, platform: str = "x", name: str = "Thread") -> int:
        r = tc.post("/v1/graphs", json={"name": name, "platform": platform})
        assert r.status_code == 201, r.text
        return r.json()["id"]

    def test_an_account_lands_in_the_graph_with_its_handle(self):
        with TestClient(app) as tc:
            _signup(tc)
            gid = self._graph(tc)
            r = tc.post(f"/v1/graphs/{gid}/members",
                        json={"external_id": "1500000000", "handle": "quietfern000", "tier": "low"})
            assert r.status_code == 201, r.text
            body = r.json()
            assert body["external_id"] == "1500000000"
            # Not the id standing in for a name: the API defaults `handle` to the external_id when
            # it is empty, which renders a numeric id where a handle belongs.
            assert body["handle"] == "quietfern000"
            assert body["tier"] == "low"

    def test_adding_twice_is_idempotent(self):
        """The picker is a button in a list of a hundred rows. Pressing it twice, or a double-tap on
        a phone, must not produce two memberships or an error the reader has to interpret."""
        with TestClient(app) as tc:
            _signup(tc)
            gid = self._graph(tc)
            payload = {"external_id": "42", "handle": "someone", "tier": "moderate"}
            first = tc.post(f"/v1/graphs/{gid}/members", json=payload)
            second = tc.post(f"/v1/graphs/{gid}/members", json=payload)
            assert first.status_code == 201, first.text
            assert second.status_code in (200, 201), second.text
            detail = tc.get(f"/v1/graphs/{gid}").json()
            assert len(detail["members"]) == 1

    def test_the_member_count_the_picker_shows_moves(self):
        with TestClient(app) as tc:
            _signup(tc)
            gid = self._graph(tc)
            assert tc.get("/v1/graphs").json()[0]["member_count"] == 0
            tc.post(f"/v1/graphs/{gid}/members", json={"external_id": "1", "handle": "a"})
            tc.post(f"/v1/graphs/{gid}/members", json={"external_id": "2", "handle": "b"})
            assert tc.get("/v1/graphs").json()[0]["member_count"] == 2

    def test_a_member_inherits_the_GRAPH_platform_which_is_why_the_ui_filters(self):
        """THE REASON `graphsAcceptingPlatform` EXISTS.

        The API stores the member with the graph's platform, not the account's, and the
        coordination-edge query filters on that same value. So an X account added to a YouTube graph
        is written down as a YouTube account and can never draw an edge: it sits there looking like a
        finding that failed to connect. The API cannot catch this (it has no idea what platform the
        caller believes the account is on), so the client must not offer the mismatch.
        """
        with TestClient(app) as tc:
            _signup(tc)
            gid = self._graph(tc, platform="youtube")
            r = tc.post(f"/v1/graphs/{gid}/members",
                        json={"external_id": "1500000000", "handle": "an_x_account"})
            assert r.json()["platform"] == "youtube", (
                "the member takes the graph's platform, so the picker must never offer a mismatch"
            )

    def test_another_operator_cannot_add_to_your_graph(self):
        with TestClient(app) as tc:
            _signup(tc, "owner@t.com")
            gid = self._graph(tc)
        with TestClient(app) as tc2:
            _signup(tc2, "stranger@t.com")
            r = tc2.post(f"/v1/graphs/{gid}/members", json={"external_id": "1", "handle": "a"})
            assert r.status_code == 404, r.text


class TestSavedGraphsAreAPaidFeature:
    """The entitlement gate itself.

    Split from the behaviour tests above deliberately: those grant the plan in their fixture so they
    can be about graphs, and this class is the one place that proves the gate exists at all. Without
    it, a fixture that silently grants Reporter to everybody would make the whole feature free and
    every test would still pass.
    """

    def test_a_free_account_cannot_create_a_graph_and_is_told_it_costs_money(self):
        with TestClient(app) as tc:
            _signup(tc, tier=None)
            r = tc.post("/v1/graphs", json={"name": "mine", "platform": "x"})
            # 402, not 403. "Forbidden" reads as a permissions bug and sends the customer to
            # support; "payment required" is true and is answerable with one click.
            assert r.status_code == 402, r.text
            assert "Reporter" in r.json()["detail"]

    def test_a_free_account_cannot_add_members_to_a_graph_it_somehow_has(self):
        with TestClient(app) as tc:
            uid = _signup(tc)                       # Reporter: create the graph
            gid = tc.post("/v1/graphs", json={"name": "g", "platform": "x"}).json()["id"]
            _seed_investigation(uid, platform="x")
            with get_session() as s:                # ...then the plan lapses
                s.get(User, uid).plan_tier = None

            r = tc.post(f"/v1/graphs/{gid}/members", json={
                "external_id": "u1", "handle": "one", "platform": "x",
            })
            assert r.status_code == 402, r.text

    def test_a_lapsed_customer_can_still_READ_the_graphs_they_built(self):
        """Downgrading must not make somebody's own saved work vanish.

        Deleting access to their data on a plan change would arrive as "the product lost my work"
        rather than as an upgrade prompt, and it is a worse failure than letting them read it. What
        a lapsed customer loses is the ability to build MORE.
        """
        with TestClient(app) as tc:
            uid = _signup(tc)
            gid = tc.post("/v1/graphs", json={"name": "kept", "platform": "x"}).json()["id"]
            with get_session() as s:
                s.get(User, uid).plan_tier = None

            assert tc.get("/v1/graphs").status_code == 200
            assert [g["name"] for g in tc.get("/v1/graphs").json()] == ["kept"]
            assert tc.get(f"/v1/graphs/{gid}").status_code == 200
