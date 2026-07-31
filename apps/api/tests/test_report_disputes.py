"""The recourse an accused account has.

OmiSphere publishes scored claims about named real people who never agreed to be analysed, and the
product owner intends to post those claims into comment sections. A person who believes a report is
wrong about them needs a way to say so, and the operator needs a way to withdraw a public claim fast.

Two properties this pins that pull in opposite directions:

* Filing must be EASY and unauthenticated. The person disputing is not a customer, and making them
  sign up to the product accusing them would make the recourse theatre.
* Filing must NOT unpublish anything. Otherwise anyone silences any report by claiming to be in it.

The reconciliation is on the admin side: one call resolves the dispute and revokes the token, and it
works on any report rather than only the admin's own, because the person harmed is never the owner.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.config import get_settings
from app.main import app
from app.storage.db import get_session, reset_db_for_tests
from app.storage.models import Investigation, ReportDispute, User

_TOKEN = "tok_public_abcdefgh"
_REASON = "This is my account and the posts it describes are not mine. Please review it."


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


def _signup(tc: TestClient, email: str) -> int:
    r = tc.post("/v1/auth/signup", json={"email": email, "password": "password12345"})
    assert r.status_code == 200, r.text
    return r.json()["id"]


def _make_admin(user_id: int) -> None:
    with get_session() as s:
        s.get(User, user_id).is_admin = 1


def _seed_report(owner_id: int, token: str = _TOKEN) -> None:
    with get_session() as s:
        from app.storage.repository import AccountRepository
        inv = AccountRepository(s).create_investigation(
            user_id=owner_id, slug="inv_disp001", label="A report", input_url="https://x.com/p/1",
            target_id="1", kind="comprehensive", overall_probability=0.8, overall_tier="high",
            summary="Mostly bought.", quota_used=1,
            payload_json={"video": {"commenters": [
                {"external_id": "a", "handle": "@accused", "tier": "high",
                 "overall_probability": 0.88},
            ]}},
        )
        inv.share_token, inv.is_public = token, 1


def _disputes() -> list[ReportDispute]:
    with get_session() as s:
        return list(s.execute(select(ReportDispute).order_by(ReportDispute.id.asc())).scalars().all())


# =========================================================================== #
# Filing: easy, anonymous, and it does not silence anything
# =========================================================================== #
def test_anyone_can_file_without_an_account():
    """The person disputing is not a customer. Requiring signup would make this theatre."""
    with TestClient(app) as tc:
        owner = _signup(tc, "owner@t.com")
        _seed_report(owner)
        tc.cookies.clear()                      # anonymous from here

        r = tc.post(f"/r/{_TOKEN}/dispute",
                    json={"subject_handle": "@accused", "contact": "me@example.com",
                          "reason": _REASON})
        assert r.status_code == 201, r.text
        assert r.json()["recorded"] is True

        rows = _disputes()
        assert len(rows) == 1
        assert rows[0].share_token == _TOKEN
        assert rows[0].subject_handle == "@accused"
        assert rows[0].status == "open"
        assert rows[0].investigation_id is not None


def test_filing_does_not_unpublish_the_report():
    """Otherwise anyone silences any report by claiming to be named in it. The takedown is a decision,
    not a side effect of a form submission."""
    with TestClient(app) as tc:
        owner = _signup(tc, "owner@t.com")
        _seed_report(owner)
        tc.cookies.clear()
        tc.post(f"/r/{_TOKEN}/dispute", json={"reason": _REASON})

        assert tc.get(f"/r/{_TOKEN}").status_code == 200, "a filing must not take the report down"


def test_the_ip_is_hashed_never_stored():
    with TestClient(app) as tc:
        owner = _signup(tc, "owner@t.com")
        _seed_report(owner)
        tc.cookies.clear()
        tc.post(f"/r/{_TOKEN}/dispute", json={"reason": _REASON},
                headers={"X-Forwarded-For": "203.0.113.7"})

        row = _disputes()[0]
        assert row.ip_hash and "203.0.113.7" not in row.ip_hash
        assert len(row.ip_hash) >= 32


def test_a_duplicate_submission_does_not_create_a_second_queue_entry():
    """Someone hitting submit twice must not produce two entries an operator has to reconcile."""
    with TestClient(app) as tc:
        owner = _signup(tc, "owner@t.com")
        _seed_report(owner)
        tc.cookies.clear()
        body = {"subject_handle": "@accused", "reason": _REASON}

        first = tc.post(f"/r/{_TOKEN}/dispute", json=body).json()
        second = tc.post(f"/r/{_TOKEN}/dispute", json=body).json()

        assert second["already_open"] is True
        assert first["id"] == second["id"]
        assert len(_disputes()) == 1


def test_a_dispute_about_an_already_unshared_report_is_still_recorded():
    """Someone objecting to a report that was just taken down still deserves a record of having
    objected. A 404 here would read as stonewalling at the worst possible moment."""
    with TestClient(app) as tc:
        _signup(tc, "owner@t.com")
        tc.cookies.clear()

        r = tc.post("/r/tok_never_existed/dispute", json={"reason": _REASON})
        assert r.status_code == 201
        assert _disputes()[0].investigation_id is None


def test_an_empty_reason_is_refused():
    with TestClient(app) as tc:
        owner = _signup(tc, "owner@t.com")
        _seed_report(owner)
        tc.cookies.clear()
        assert tc.post(f"/r/{_TOKEN}/dispute", json={"reason": "nope"}).status_code == 422
        assert _disputes() == []


# =========================================================================== #
# The queue: admin only, because it holds complainants' contact details
# =========================================================================== #
def test_the_queue_is_admin_only():
    with TestClient(app) as tc:
        owner = _signup(tc, "owner@t.com")
        _seed_report(owner)
        tc.cookies.clear()
        tc.post(f"/r/{_TOKEN}/dispute", json={"reason": _REASON})

        tc.cookies.clear()
        _signup(tc, "nosy@t.com")                       # ordinary signed-in user
        assert tc.get("/v1/admin/disputes").status_code == 403


def test_an_admin_sees_the_queue_and_whether_the_report_is_still_live():
    with TestClient(app) as tc:
        owner = _signup(tc, "owner@t.com")
        _seed_report(owner)
        tc.cookies.clear()
        tc.post(f"/r/{_TOKEN}/dispute",
                json={"subject_handle": "@accused", "contact": "me@example.com",
                      "reason": _REASON})

        tc.cookies.clear()
        admin = _signup(tc, "admin@t.com")
        _make_admin(admin)
        rows = tc.get("/v1/admin/disputes").json()

        assert len(rows) == 1
        assert rows[0]["subject_handle"] == "@accused"
        assert rows[0]["contact"] == "me@example.com"
        assert rows[0]["report_still_public"] is True, (
            "the operator has to see whether the claim is still live before deciding"
        )


# =========================================================================== #
# The takedown, which is the point of the whole feature
# =========================================================================== #
def test_an_admin_can_unpublish_a_report_they_do_not_own():
    """The owner-scoped revoke cannot serve here by construction: the person harmed is not the owner,
    and waiting for the owner to act is not a takedown process."""
    with TestClient(app) as tc:
        owner = _signup(tc, "owner@t.com")
        _seed_report(owner)
        tc.cookies.clear()
        did = tc.post(f"/r/{_TOKEN}/dispute", json={"reason": _REASON}).json()["id"]

        tc.cookies.clear()
        admin = _signup(tc, "admin@t.com")
        _make_admin(admin)
        r = tc.post(f"/v1/admin/disputes/{did}",
                    json={"status": "upheld", "note": "Could not stand it up.",
                          "unpublish": True})
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "upheld"
        assert r.json()["report_still_public"] is False

        # The public link is dead immediately, including for links already posted publicly.
        tc.cookies.clear()
        assert tc.get(f"/r/{_TOKEN}").status_code == 404


def test_a_takedown_withdraws_the_public_claim_without_destroying_the_customers_work():
    """What caused the harm is the PUBLIC claim. The customer keeps their investigation."""
    with TestClient(app) as tc:
        owner = _signup(tc, "owner@t.com")
        _seed_report(owner)
        tc.cookies.clear()
        did = tc.post(f"/r/{_TOKEN}/dispute", json={"reason": _REASON}).json()["id"]
        tc.cookies.clear()
        admin = _signup(tc, "admin@t.com")
        _make_admin(admin)
        tc.post(f"/v1/admin/disputes/{did}", json={"status": "upheld", "unpublish": True})

        with get_session() as s:
            inv = s.execute(select(Investigation).where(
                Investigation.slug == "inv_disp001")).scalar_one()
            assert inv.share_token is None and not inv.is_public
            assert inv.payload_json, "the investigation itself must survive"
            assert inv.user_id == owner


def test_rejecting_a_dispute_leaves_the_report_up_and_records_why():
    """Not every objection is upheld, and the record of the decision is the point of the audit trail."""
    with TestClient(app) as tc:
        owner = _signup(tc, "owner@t.com")
        _seed_report(owner)
        tc.cookies.clear()
        did = tc.post(f"/r/{_TOKEN}/dispute", json={"reason": _REASON}).json()["id"]
        tc.cookies.clear()
        admin = _signup(tc, "admin@t.com")
        _make_admin(admin)

        r = tc.post(f"/v1/admin/disputes/{did}",
                    json={"status": "rejected", "note": "Quoted posts verified on the account."})
        assert r.json()["status"] == "rejected"
        assert r.json()["report_still_public"] is True
        assert _disputes()[0].resolution_note.startswith("Quoted posts verified")
        assert _disputes()[0].resolved_at is not None
        tc.cookies.clear()
        assert tc.get(f"/r/{_TOKEN}").status_code == 200


def test_resolving_is_admin_only():
    with TestClient(app) as tc:
        owner = _signup(tc, "owner@t.com")
        _seed_report(owner)
        tc.cookies.clear()
        did = tc.post(f"/r/{_TOKEN}/dispute", json={"reason": _REASON}).json()["id"]

        tc.cookies.clear()
        _signup(tc, "attacker@t.com")
        r = tc.post(f"/v1/admin/disputes/{did}", json={"status": "rejected"})
        assert r.status_code == 403
        # And crucially, an ordinary user cannot use this to unpublish someone's report.
        r2 = tc.post(f"/v1/admin/disputes/{did}", json={"status": "upheld", "unpublish": True})
        assert r2.status_code == 403
        tc.cookies.clear()
        assert tc.get(f"/r/{_TOKEN}").status_code == 200


def test_an_unknown_status_is_refused():
    with TestClient(app) as tc:
        owner = _signup(tc, "owner@t.com")
        _seed_report(owner)
        tc.cookies.clear()
        did = tc.post(f"/r/{_TOKEN}/dispute", json={"reason": _REASON}).json()["id"]
        tc.cookies.clear()
        admin = _signup(tc, "admin@t.com")
        _make_admin(admin)

        assert tc.post(f"/v1/admin/disputes/{did}",
                       json={"status": "vanished"}).status_code == 422


# =========================================================================== #
# The scope statement: what the report is claiming, said out loud
# =========================================================================== #
def test_the_markdown_export_leads_with_the_scope_statement():
    """The export is the version that circulates as a document, often screenshotted from the first
    page. A caveat at the very bottom is the part nobody reads and the first thing cropped out, so the
    statement goes at the top, above the verdict."""
    with TestClient(app) as tc:
        owner = _signup(tc, "owner@t.com")
        _seed_report(owner)
        tc.cookies.clear()

        md = tc.get(f"/r/{_TOKEN}/markdown").text
        head = md[: md.index("## Verdict")]

        assert "not findings of fact" in head
        assert "not an allegation" in head
        assert "Request a review" in head, "the recourse must travel with the document"
        for shape in ("businesses", "fan accounts", "news feeds", "second"):
            assert shape in head, f"the confusable shape '{shape}' is not disclosed"


def test_the_export_disclaims_identity_and_intent():
    """The two claims the evidence can never support, and the two most likely to cause real harm if a
    reader assumes them."""
    with TestClient(app) as tc:
        owner = _signup(tc, "owner@t.com")
        _seed_report(owner)
        tc.cookies.clear()

        md = tc.get(f"/r/{_TOKEN}/markdown").text
        assert "who operates an account" in md
        assert "money changed hands" in md
        assert "intent" in md


def test_the_dispute_endpoint_the_report_points_at_actually_works():
    """The report tells a reader to use "Request a review". This asserts the thing it points at exists
    and accepts a submission, so the promise on the page is not a dead end."""
    with TestClient(app) as tc:
        owner = _signup(tc, "owner@t.com")
        _seed_report(owner)
        tc.cookies.clear()

        assert "Request a review" in tc.get(f"/r/{_TOKEN}/markdown").text
        r = tc.post(f"/r/{_TOKEN}/dispute", json={"reason": _REASON})
        assert r.status_code == 201


# =========================================================================== #
# The admin queue has an interface
#
# The routes above shipped before any UI existed, which meant the only way to read the queue was
# curl. That is not a takedown process: the operational value of the whole feature is being able to
# say "reviewed and acted within a day", and a queue nobody looks at cannot deliver that.
#
# These are source-level assertions against apps/web, in the same spirit as the signal gate's guard:
# a page whose only protection is a hidden nav link is not protected, and TypeScript will not tell
# anyone if the server check is dropped.
# =========================================================================== #
from pathlib import Path  # noqa: E402 — kept beside the tests that use it

_WEB = Path(__file__).resolve().parents[3] / "apps" / "web"
_QUEUE_DIR = _WEB / "app" / "(app)" / "disputes"


def test_the_queue_page_exists():
    assert (_QUEUE_DIR / "page.tsx").exists(), "the dispute queue API has no interface"


def test_the_queue_page_is_gated_on_the_server():
    """Hiding the nav item is presentation. The route would still answer to anyone who typed the URL,
    and this page reads complainants' contact details and can unpublish any report in the system."""
    src = (_QUEUE_DIR / "page.tsx").read_text()
    assert "is_admin" in src
    assert "notFound()" in src
    assert "force-dynamic" in src, "a cached render would serve one user's gate result to another"


def test_the_queue_link_is_admin_only_in_both_navs():
    for nav in ("sidebar.tsx", "mobile-nav.tsx"):
        src = (_WEB / "components" / "layout" / nav).read_text()
        line = next((ln for ln in src.splitlines() if "'/disputes'" in ln), None)
        assert line is not None, f"{nav} has no link to the dispute queue"
        assert "adminOnly: true" in line, f"{nav} shows the dispute queue to customers"


def test_the_takedown_is_not_a_one_click_action():
    """Revoking clears the share token, so every link already posted publicly 404s and re-sharing
    mints a different one. That is the right outcome when we got someone wrong, and the wrong one to
    reach by a stray click."""
    src = (_QUEUE_DIR / "dispute-queue.tsx").read_text()
    assert "confirmingTakedown" in src
    assert "unpublish: true" not in src, "unpublish must be passed deliberately, not hardcoded on"
    assert "act('upheld', true)" in src
