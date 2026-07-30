"""The funnel: a visitor reads someone's shared report, signs up, and it lands in THEIR archive.

Without this the signup is a dead end. Someone clicks a public `/r/<token>` link, decides they want
to check more accounts on that post, signs up, and arrives at an empty dashboard with no idea which
post they were looking at. Claiming carries it across: the report becomes the first thing in their own
archive, with the source URL ready for the scan they signed up to run.

The traps this pins, in rough order of how expensive they would be:

1. `share_token` must NOT be copied. It is unique and it drives the public `/r/<token>` lookup, so a
   second row holding the same token either fails the insert or makes the public report ambiguous
   for every visitor. This is the one that would break the feature it is part of.
2. Claiming must be idempotent. The web app fires it on a page load it cannot guarantee happens once,
   and `payload_json` is routinely megabytes.
3. The original must be untouched. It belongs to someone else.
4. No credits move. Reading is free; scanning is what costs.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.config import get_settings
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


_PAYLOAD = {
    "overall_probability": 0.61, "overall_tier": "elevated", "summary": "Mixed section.",
    "video": {"video_id": "v1", "commenters": [
        {"external_id": "a", "handle": "@a", "overall_probability": 0.8, "tier": "high"},
        {"external_id": "b", "handle": "@b", "overall_probability": 0.2, "tier": "low"},
    ]},
}


def _signup(tc: TestClient, email: str) -> int:
    r = tc.post("/v1/auth/signup", json={"email": email, "password": "password12345"})
    assert r.status_code == 200, r.text
    return r.json()["id"]


def _seed_shared_report(owner_id: int, *, token: str = "tok_public_abcdefgh") -> str:
    """An investigation owned by someone else, shared publicly. Returns its slug."""
    with get_session() as s:
        from app.storage.repository import AccountRepository
        inv = AccountRepository(s).create_investigation(
            user_id=owner_id, slug="inv_owner01", label="Someone else's investigation",
            input_url="https://x.com/someone/status/1234567890", target_id="1234567890",
            kind="comprehensive", overall_probability=0.61, overall_tier="elevated",
            summary="Mixed section.", quota_used=3, payload_json=_PAYLOAD,
        )
        inv.share_token = token
        inv.is_public = 1
        s.flush()
        return inv.slug


def _rows(user_id: int) -> list[Investigation]:
    with get_session() as s:
        return list(s.execute(
            select(Investigation).where(Investigation.user_id == user_id)
            .order_by(Investigation.id.asc())
        ).scalars().all())


def _credits(user_id: int) -> int:
    with get_session() as s:
        return s.get(User, user_id).credits_remaining


# =========================================================================== #
# The happy path
# =========================================================================== #
def test_claiming_puts_a_copy_in_the_claimers_archive():
    with TestClient(app) as tc:
        owner = _signup(tc, "owner@t.com")
        token = "tok_public_abcdefgh"
        _seed_shared_report(owner, token=token)
        tc.cookies.clear()
        claimer = _signup(tc, "claimer@t.com")

        r = tc.post("/v1/investigations/claim", json={"share_token": token})
        assert r.status_code == 200, r.text
        body = r.json()

        assert body["already_claimed"] is False
        assert body["slug"] != "inv_owner01", "the claimer must get their OWN row, not the original"
        # The source URL comes back so the web app can send them to /investigate?url=...
        assert body["input_url"] == "https://x.com/someone/status/1234567890"
        assert body["label"] == "Someone else's investigation"

        mine = _rows(claimer)
        assert len(mine) == 1
        assert mine[0].slug == body["slug"]
        # The whole scan result came with it, so the report renders for its new owner.
        assert mine[0].payload_json == _PAYLOAD
        assert mine[0].overall_tier == "elevated"
        assert mine[0].claimed_from_token == token


def test_the_claimed_copy_shows_up_in_the_archive_list():
    """It has to be reachable the normal way, which is the point of "adds to their previous
    investigations". This also exercises the denormalised list columns."""
    with TestClient(app) as tc:
        owner = _signup(tc, "owner@t.com")
        _seed_shared_report(owner)
        tc.cookies.clear()
        _signup(tc, "claimer@t.com")
        slug = tc.post("/v1/investigations/claim",
                       json={"share_token": "tok_public_abcdefgh"}).json()["slug"]

        listing = tc.get("/v1/investigations").json()
        slugs = [i["slug"] for i in listing["investigations"]]
        assert slug in slugs
        # And it opens.
        assert tc.get(f"/v1/investigations/{slug}").status_code == 200


# =========================================================================== #
# The share-token trap
# =========================================================================== #
def test_the_copy_does_not_carry_the_share_token():
    """The token is unique and drives /r/<token>. Copying it would either fail the insert or make the
    public report ambiguous for every visitor, breaking the very link that produced the signup."""
    with TestClient(app) as tc:
        owner = _signup(tc, "owner@t.com")
        token = "tok_public_abcdefgh"
        _seed_shared_report(owner, token=token)
        tc.cookies.clear()
        claimer = _signup(tc, "claimer@t.com")
        tc.post("/v1/investigations/claim", json={"share_token": token})

        copy = _rows(claimer)[0]
        assert copy.share_token is None, "the claimed copy must not carry the original's token"
        assert not copy.is_public, "a claimed copy is private until its new owner shares it"

        # Exactly one row in the whole table still answers to that token, and it is the original.
        with get_session() as s:
            holders = list(s.execute(
                select(Investigation).where(Investigation.share_token == token)
            ).scalars().all())
        assert len(holders) == 1
        assert holders[0].user_id == owner


def test_the_public_link_still_works_after_being_claimed():
    """The end-to-end version of the above: the funnel must not consume the link that feeds it."""
    with TestClient(app) as tc:
        owner = _signup(tc, "owner@t.com")
        token = "tok_public_abcdefgh"
        _seed_shared_report(owner, token=token)
        assert tc.get(f"/r/{token}").status_code == 200
        tc.cookies.clear()
        _signup(tc, "claimer@t.com")
        tc.post("/v1/investigations/claim", json={"share_token": token})
        tc.cookies.clear()

        # A second visitor can still read it.
        assert tc.get(f"/r/{token}").status_code == 200


def test_the_original_is_left_completely_alone():
    with get_session():
        pass
    with TestClient(app) as tc:
        owner = _signup(tc, "owner@t.com")
        token = "tok_public_abcdefgh"
        _seed_shared_report(owner, token=token)
        before = _rows(owner)[0]
        snapshot = (before.user_id, before.slug, before.share_token, before.is_public,
                    before.quota_used, before.label)
        tc.cookies.clear()
        _signup(tc, "claimer@t.com")
        tc.post("/v1/investigations/claim", json={"share_token": token})

        after = _rows(owner)
        assert len(after) == 1, "the owner must not gain or lose a row"
        a = after[0]
        assert (a.user_id, a.slug, a.share_token, a.is_public, a.quota_used, a.label) == snapshot


# =========================================================================== #
# Idempotency
# =========================================================================== #
def test_claiming_twice_returns_the_same_copy():
    """The web app fires this from a page it cannot guarantee renders once (a refresh, a double mount
    in development, a retried request). Duplicating a megabyte payload per attempt is not acceptable."""
    with TestClient(app) as tc:
        owner = _signup(tc, "owner@t.com")
        token = "tok_public_abcdefgh"
        _seed_shared_report(owner, token=token)
        tc.cookies.clear()
        claimer = _signup(tc, "claimer@t.com")

        first = tc.post("/v1/investigations/claim", json={"share_token": token}).json()
        second = tc.post("/v1/investigations/claim", json={"share_token": token}).json()
        third = tc.post("/v1/investigations/claim", json={"share_token": token}).json()

        assert first["already_claimed"] is False
        assert second["already_claimed"] is True and third["already_claimed"] is True
        assert first["slug"] == second["slug"] == third["slug"]
        assert len(_rows(claimer)) == 1, "three claims produced more than one row"


def test_two_different_visitors_can_each_claim_the_same_report():
    """The token is deliberately not unique on the copy, because a shared report going out to many
    people and each of them claiming it is the entire point of the funnel."""
    with TestClient(app) as tc:
        owner = _signup(tc, "owner@t.com")
        token = "tok_public_abcdefgh"
        _seed_shared_report(owner, token=token)

        slugs = []
        for email in ("one@t.com", "two@t.com"):
            tc.cookies.clear()
            uid = _signup(tc, email)
            r = tc.post("/v1/investigations/claim", json={"share_token": token})
            assert r.status_code == 200, r.text
            slugs.append(r.json()["slug"])
            assert len(_rows(uid)) == 1
        assert slugs[0] != slugs[1], "each claimer needs their own row"


def test_claiming_your_own_report_does_not_duplicate_it():
    with TestClient(app) as tc:
        owner = _signup(tc, "owner@t.com")
        token = "tok_public_abcdefgh"
        slug = _seed_shared_report(owner, token=token)

        r = tc.post("/v1/investigations/claim", json={"share_token": token})
        assert r.status_code == 200, r.text
        assert r.json()["slug"] == slug
        assert r.json()["already_claimed"] is True
        assert len(_rows(owner)) == 1


# =========================================================================== #
# Refusals and money
# =========================================================================== #
def test_an_unknown_token_is_a_404():
    with TestClient(app) as tc:
        _signup(tc, "claimer@t.com")
        r = tc.post("/v1/investigations/claim", json={"share_token": "tok_does_not_exist"})
        assert r.status_code == 404


def test_a_revoked_share_cannot_be_claimed():
    """Unsharing has to actually stop the funnel, or revoking a link would be cosmetic."""
    with TestClient(app) as tc:
        owner = _signup(tc, "owner@t.com")
        token = "tok_public_abcdefgh"
        _seed_shared_report(owner, token=token)
        with get_session() as s:
            inv = s.execute(select(Investigation).where(
                Investigation.share_token == token)).scalar_one()
            inv.is_public = 0
        tc.cookies.clear()
        _signup(tc, "claimer@t.com")

        assert tc.post("/v1/investigations/claim",
                       json={"share_token": token}).status_code == 404


def test_claiming_requires_being_signed_in():
    with TestClient(app) as tc:
        owner = _signup(tc, "owner@t.com")
        _seed_shared_report(owner)
        tc.cookies.clear()
        r = tc.post("/v1/investigations/claim", json={"share_token": "tok_public_abcdefgh"})
        assert r.status_code == 401


def test_claiming_neither_grants_nor_spends_credits():
    """Reading someone's report is free and stays free. The credit is for the scan they came to run,
    and a claim that quietly spent it would strand them at the moment of conversion."""
    with TestClient(app) as tc:
        owner = _signup(tc, "owner@t.com")
        token = "tok_public_abcdefgh"
        _seed_shared_report(owner, token=token)
        tc.cookies.clear()
        claimer = _signup(tc, "claimer@t.com")
        before = _credits(claimer)

        tc.post("/v1/investigations/claim", json={"share_token": token})
        assert _credits(claimer) == before

        # And the copy records that its new owner spent no quota on it.
        assert _rows(claimer)[0].quota_used == 0


def test_a_short_token_is_rejected_before_any_lookup():
    with TestClient(app) as tc:
        _signup(tc, "claimer@t.com")
        assert tc.post("/v1/investigations/claim",
                       json={"share_token": "short"}).status_code == 422


# =========================================================================== #
# Route shape
# =========================================================================== #
def test_the_claim_route_is_not_shadowed_by_the_slug_route():
    """`/v1/investigations/claim` is declared after `/v1/investigations/{slug}`. It is safe today only
    because `{slug}` is GET and PATCH while claim is POST. Adding `POST /{slug}` later would shadow
    this silently, and the symptom would be a 404 or a wrong handler on the funnel's key call."""
    import app.routes.investigations as m

    post_paths = [r.path for r in m.router.routes if "POST" in (r.methods or set())]
    assert "/v1/investigations/claim" in post_paths
    assert "/v1/investigations/{slug}" not in post_paths, (
        "a POST /{slug} route now shadows POST /claim; move the claim route above it"
    )
