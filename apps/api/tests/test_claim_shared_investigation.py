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


# =========================================================================== #
# Funnel facts on the public report: real numbers or none at all
# =========================================================================== #
def test_the_report_states_how_much_of_the_post_it_actually_covers():
    """"Checked 25 of the 312 accounts that commented" is the whole argument for signing up, and it
    is checkable by anyone. It has to come from a recorded total, never an estimate."""
    with TestClient(app) as tc:
        owner = _signup(tc, "owner@t.com")
        token = "tok_public_abcdefgh"
        _seed_shared_report(owner, token=token)
        with get_session() as s:
            inv = s.execute(select(Investigation).where(
                Investigation.share_token == token)).scalar_one()
            inv.commenters_available = 312          # what the compile step found

        meta = tc.get(f"/r/{token}").json()["view"]["meta"]
        assert meta["commenters_available"] == 312
        assert meta["commenters_scanned"] == 2      # the payload's two commenters
        # And the visible stats line carries the gap rather than a bare count.
        stats = tc.get(f"/r/{token}").json()["view"]["stats"]
        assert stats["Commenters scanned"] == "2 of 312"


def test_a_report_with_no_recorded_total_says_nothing_rather_than_guessing():
    """Investigations saved before the total was recorded must not have one invented for them. The
    page falls back to a qualitative line; it does not estimate."""
    with TestClient(app) as tc:
        owner = _signup(tc, "owner@t.com")
        token = "tok_public_abcdefgh"
        _seed_shared_report(owner, token=token)   # commenters_available left NULL

        view = tc.get(f"/r/{token}").json()["view"]
        assert view["meta"]["commenters_available"] is None
        assert view["stats"]["Commenters scanned"] == 2   # plain count, no fabricated denominator


def test_the_gap_is_hidden_when_the_report_covered_everything():
    """No gap, no claim. Saying "2 of 2 have not been looked at" would be nonsense."""
    with TestClient(app) as tc:
        owner = _signup(tc, "owner@t.com")
        token = "tok_public_abcdefgh"
        _seed_shared_report(owner, token=token)
        with get_session() as s:
            inv = s.execute(select(Investigation).where(
                Investigation.share_token == token)).scalar_one()
            inv.commenters_available = 2          # everyone who commented was scanned

        assert tc.get(f"/r/{token}").json()["view"]["stats"]["Commenters scanned"] == 2


def test_the_read_count_is_real_and_counts_other_people_not_the_current_reader():
    """Social proof has to be a fact. It is also counted BEFORE this request is logged, so a first
    visitor is never told they are the second."""
    with TestClient(app) as tc:
        owner = _signup(tc, "owner@t.com")
        token = "tok_public_abcdefgh"
        _seed_shared_report(owner, token=token)

        first = tc.get(f"/r/{token}").json()["view"]["meta"]["read_count"]
        assert first == 0, "the first reader must not be counted as a prior view"
        # Views are deduped per (token, IP) per 10 minutes, so a distinct client is needed.
        tc.get(f"/r/{token}", headers={"X-Forwarded-For": "203.0.113.9"})
        second = tc.get(f"/r/{token}", headers={"X-Forwarded-For": "203.0.113.10"}
                        ).json()["view"]["meta"]["read_count"]
        assert second >= 1


def test_a_claimed_copy_inherits_the_coverage_total():
    """The copy is the same investigation, so it knows the same thing about the post. Without this the
    claimer's own report would forget how much of the post was left unchecked."""
    with TestClient(app) as tc:
        owner = _signup(tc, "owner@t.com")
        token = "tok_public_abcdefgh"
        _seed_shared_report(owner, token=token)
        with get_session() as s:
            inv = s.execute(select(Investigation).where(
                Investigation.share_token == token)).scalar_one()
            inv.commenters_available = 312
        tc.cookies.clear()
        claimer = _signup(tc, "claimer@t.com")
        tc.post("/v1/investigations/claim", json={"share_token": token})

        assert _rows(claimer)[0].commenters_available == 312


def test_the_methodology_note_describes_the_signals_that_actually_exist():
    """This renders on the public report, which is the page being promoted. It described `memory` and
    `coordination` as two of the eight long after they were replaced, so a reader checking the
    product's own description found it wrong about itself."""
    from app.reasoning.prompts.comprehensive_investigation_template import (
        COMPREHENSIVE_SIGNAL_NAMES,
    )
    from app.reports.templates import _methodology_note

    note = _methodology_note().lower()
    assert "memory" not in note
    assert "coordination) " not in note
    for human in ("posting rhythm", "content repetition", "machine-written prose",
                  "profile coherence", "personal voice", "engagement farming",
                  "account maturity", "history authenticity"):
        assert human in note, human
    assert len(COMPREHENSIVE_SIGNAL_NAMES) == 8
    # The doctrine that matters most to a sceptical reader is stated, not implied.
    assert "several independent indicators" in note
    assert "probabilistic" in note


# =========================================================================== #
# The report lists EVERY account it scored, not just the flagged ones
# =========================================================================== #
def test_the_report_lists_every_account_scanned_including_the_clean_ones():
    """A list of only flagged accounts reads as a hit list, and it hides the most reassuring thing in
    the report: that most of the section came back clean. It also makes the product look like it
    flags everything, which is the opposite of what the scoring discipline is for."""
    with TestClient(app) as tc:
        owner = _signup(tc, "owner@t.com")
        token = "tok_public_abcdefgh"
        _seed_shared_report(owner, token=token)

        view = tc.get(f"/r/{token}").json()["view"]
        handles = [c["handle"] for c in view["all_commenters"]]
        assert handles == ["@a", "@b"], "worst first, and the low-tier account is present"
        assert view["total_scanned"] == 2
        # The flagged summary still exists for the sections that use it.
        assert view["total_flagged"] == 1
        assert [c["handle"] for c in view["top_flagged"]] == ["@a"]


def test_the_full_list_is_sorted_worst_first():
    with TestClient(app) as tc:
        owner = _signup(tc, "owner@t.com")
        token = "tok_public_abcdefgh"
        with get_session() as s:
            from app.storage.repository import AccountRepository
            AccountRepository(s).create_investigation(
                user_id=owner, slug="inv_sort01", label="Sorted", input_url="https://x.com/p/1",
                target_id="1", kind="comprehensive", overall_probability=0.5,
                overall_tier="moderate", summary="s", quota_used=1,
                payload_json={"video": {"commenters": [
                    {"external_id": "lo", "handle": "@lo", "tier": "low", "overall_probability": 0.05},
                    {"external_id": "hi", "handle": "@hi", "tier": "high", "overall_probability": 0.91},
                    {"external_id": "mid", "handle": "@mid", "tier": "moderate",
                     "overall_probability": 0.44},
                ]}},
            )
            inv = s.execute(select(Investigation).where(
                Investigation.slug == "inv_sort01")).scalar_one()
            inv.share_token, inv.is_public = token, 1

        rows = tc.get(f"/r/{token}").json()["view"]["all_commenters"]
        assert [c["handle"] for c in rows] == ["@hi", "@mid", "@lo"]


def test_the_full_list_stays_light():
    """No per-account evidence blobs on the full list. Carrying `recent_activity` for every account in
    a 150-account comment section would multiply the public response by data the table never renders."""
    with TestClient(app) as tc:
        owner = _signup(tc, "owner@t.com")
        token = "tok_public_abcdefgh"
        _seed_shared_report(owner, token=token)

        row = tc.get(f"/r/{token}").json()["view"]["all_commenters"][0]
        assert set(row) == {"handle", "external_id", "tier", "overall_probability", "intent_label"}
        assert "recent_activity" not in row and "reasons" not in row


def test_the_markdown_export_lists_everyone_too():
    """Someone who downloads the report as evidence must have the same document they read. A page and
    an export that disagree about who was scanned is worse than either alone."""
    with TestClient(app) as tc:
        owner = _signup(tc, "owner@t.com")
        token = "tok_public_abcdefgh"
        _seed_shared_report(owner, token=token)

        md = tc.get(f"/r/{token}/markdown").text
        assert "Accounts scanned" in md
        assert "@a" in md and "@b" in md, "the clean account must appear in the export as well"


def test_a_report_with_no_commenters_renders_without_the_table():
    with TestClient(app) as tc:
        owner = _signup(tc, "owner@t.com")
        token = "tok_public_abcdefgh"
        with get_session() as s:
            from app.storage.repository import AccountRepository
            AccountRepository(s).create_investigation(
                user_id=owner, slug="inv_empty1", label="Empty", input_url="https://x.com/p/2",
                target_id="2", kind="comprehensive", overall_probability=0.0, overall_tier="low",
                summary="none", quota_used=0, payload_json={"video": {"commenters": []}},
            )
            inv = s.execute(select(Investigation).where(
                Investigation.slug == "inv_empty1")).scalar_one()
            inv.share_token, inv.is_public = token, 1

        view = tc.get(f"/r/{token}").json()["view"]
        assert view["all_commenters"] == []
        assert view["total_scanned"] == 0


# =========================================================================== #
# The shared link is the FULL investigation, including what the analyst wrote
# =========================================================================== #
def _seed_with_analyst(owner_id: int, token: str) -> None:
    """A shared report whose analyst entry carries per-account reads AND admin-only signals."""
    from app.reasoning.analyst import CACHE_KEY

    payload = dict(_PAYLOAD)
    payload[CACHE_KEY] = {
        "provider": "openrouter-omi-analyst-v1",
        "generated_at": "2026-07-29T00:00:00Z",
        "assessment": {
            "investigation_trace": {"model_backed": True},
            "commenter_assessments": [
                {"ref": "A1", "external_id": "a", "handle": "@a", "resolved": True,
                 "omi_score": 88, "suspicion_tier": "high", "confidence": 90,
                 "signals": [{"name": "temporal", "score": 90, "reason": "machine-regular"}],
                 "assessment": "Posted the identical sentence on four separate days."},
                {"ref": "A2", "external_id": "b", "handle": "@b", "resolved": True,
                 "omi_score": 9, "suspicion_tier": "low", "confidence": 85,
                 "signals": [{"name": "temporal", "score": 5, "reason": "ordinary hours"}],
                 "assessment": "Years of varied posts that read as one person's life."},
                {"ref": "A99", "resolved": False, "omi_score": 70,
                 "suspicion_tier": "elevated", "assessment": "Unresolved alias."},
            ],
        },
    }
    with get_session() as s:
        from app.storage.repository import AccountRepository
        inv = AccountRepository(s).create_investigation(
            user_id=owner_id, slug="inv_full001", label="Full", input_url="https://x.com/p/9",
            target_id="9", kind="comprehensive", overall_probability=0.61,
            overall_tier="elevated", summary="Mixed.", quota_used=2, payload_json=payload,
        )
        inv.share_token, inv.is_public = token, 1


def test_the_shared_report_carries_what_the_analyst_wrote_about_each_account():
    """A summary of an investigation is not the investigation. The per-account prose and OMI score are
    the substance, and without them a promoted link is just a percentage."""
    with TestClient(app) as tc:
        owner = _signup(tc, "owner@t.com")
        token = "tok_public_abcdefgh"
        _seed_with_analyst(owner, token)

        rows = {c["handle"]: c for c in tc.get(f"/r/{token}").json()["view"]["all_commenters"]}
        assert rows["@a"]["omi_score"] == 88
        assert rows["@a"]["analyst_tier"] == "high"
        assert "identical sentence" in rows["@a"]["assessment"]
        # The clean account carries its read too, which is what makes the report analysis not a list.
        assert rows["@b"]["omi_score"] == 9
        assert "one person's life" in rows["@b"]["assessment"]


def test_the_public_report_never_leaks_the_admin_only_signal_breakdown():
    """This route is anonymous, so `is_admin=True` must be unreachable on it. The eight-signal
    breakdown is an unfinished feature and must not appear in a public response even though the
    analyst entry stored underneath it has one."""
    with TestClient(app) as tc:
        owner = _signup(tc, "owner@t.com")
        token = "tok_public_abcdefgh"
        _seed_with_analyst(owner, token)

        raw = tc.get(f"/r/{token}").text
        assert "machine-regular" not in raw, "a signal reason leaked into the public report"
        assert '"signals"' not in raw
        for row in tc.get(f"/r/{token}").json()["view"]["all_commenters"]:
            assert "signals" not in row
            assert "confidence" not in row


def test_an_unresolved_alias_is_not_published():
    """An unresolved alias has no identity to attach a public claim to. Publishing one would be a
    statement about nobody."""
    with TestClient(app) as tc:
        owner = _signup(tc, "owner@t.com")
        token = "tok_public_abcdefgh"
        _seed_with_analyst(owner, token)

        raw = tc.get(f"/r/{token}").text
        assert "Unresolved alias" not in raw


def test_accounts_the_analyst_never_reached_keep_their_engine_row():
    """Half an investigation is still an investigation. An account with no model read must still be
    listed rather than silently dropped from the count."""
    with TestClient(app) as tc:
        owner = _signup(tc, "owner@t.com")
        token = "tok_public_abcdefgh"
        _seed_shared_report(owner, token=token)   # no analyst entry at all

        rows = tc.get(f"/r/{token}").json()["view"]["all_commenters"]
        assert [c["handle"] for c in rows] == ["@a", "@b"]
        assert all("assessment" not in c for c in rows), (
            "not assessed must be absent, not an empty string"
        )


def test_the_export_carries_the_analyst_prose_too():
    with TestClient(app) as tc:
        owner = _signup(tc, "owner@t.com")
        token = "tok_public_abcdefgh"
        _seed_with_analyst(owner, token)

        md = tc.get(f"/r/{token}/markdown").text
        assert "What the analyst found" in md
        assert "identical sentence" in md
        assert "machine-regular" not in md, "the export must respect the same admin gate"


def test_the_public_json_export_does_not_hand_over_the_analyst_cache():
    """The leak this closes: /r/<token>/json dumped payload_json raw on an unauthenticated route, and
    that blob carries the analyst entry with its admin-only signal breakdown and internal provenance
    (trace ids, prompt hashes, token counts). The page and the markdown export both filter; this one
    handed over everything, so the admin gate was one URL away from meaning nothing.

    The filtered per-account reads stay, so a programmatic consumer still gets the conclusions.
    """
    from app.reasoning.analyst import CACHE_KEY

    with TestClient(app) as tc:
        owner = _signup(tc, "owner@t.com")
        token = "tok_public_abcdefgh"
        _seed_with_analyst(owner, token)

        body = tc.get(f"/r/{token}/json").json()
        assert CACHE_KEY not in body["payload"], "the analyst cache is still in the public export"
        raw = tc.get(f"/r/{token}/json").text
        assert "machine-regular" not in raw, "a signal reason leaked through the JSON export"
        assert '"signals"' not in raw
        # The scan result itself is still exported, and so are the filtered reads.
        assert body["payload"]["video"]["commenters"]
        assert any(r["handle"] == "@a" for r in body["investigation"]["account_reads"])
