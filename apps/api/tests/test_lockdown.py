"""Pre-launch lockdown: only admins can use the product.

WHAT IS ACTUALLY BEING PROTECTED. Not secrecy — the marketing pages stay public and the code is
unchanged. MONEY. Every scan and every comment-section compile spends real upstream budget, and
during a pre-launch campaign the site is being promoted to people who have not bought anything. The
refusal therefore has to live on the API, because the API is what spends: a redirect in the web app
stops somebody browsing to the product and does nothing about the same person calling the scan
endpoint directly with the cookie their browser already holds.

Every test here signs up a REAL user against ``OMI_REQUIRE_AUTH=true``. Local mode resolves to
``is_admin=True``, so a test written against it would pass whether or not the gate existed.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.config import get_settings
from app.main import app
from app.storage.db import get_session, reset_db_for_tests
from app.storage.models import User, WaitlistEntry

ADMIN_EMAIL = "boss@omi.test"


@pytest.fixture
def locked(monkeypatch):
    monkeypatch.setenv("OMI_REQUIRE_AUTH", "true")
    monkeypatch.setenv("OMI_SESSION_SECRET", "x" * 64)
    monkeypatch.setenv("OMI_LOCKDOWN", "true")
    monkeypatch.setenv("OMI_SUPER_ADMIN_EMAILS", ADMIN_EMAIL)
    get_settings.cache_clear()
    reset_db_for_tests("sqlite:///:memory:")
    from app.core.rate_limit import reset_all_limiters_for_tests

    reset_all_limiters_for_tests()
    with TestClient(app) as tc:
        yield tc
    reset_db_for_tests("sqlite:///:memory:")
    get_settings.cache_clear()


@pytest.fixture
def open_site(monkeypatch):
    """The same deployment with the switch off. Proves lifting it restores everything."""
    monkeypatch.setenv("OMI_REQUIRE_AUTH", "true")
    monkeypatch.setenv("OMI_SESSION_SECRET", "x" * 64)
    monkeypatch.setenv("OMI_LOCKDOWN", "false")
    get_settings.cache_clear()
    reset_db_for_tests("sqlite:///:memory:")
    from app.core.rate_limit import reset_all_limiters_for_tests

    reset_all_limiters_for_tests()
    with TestClient(app) as tc:
        yield tc
    reset_db_for_tests("sqlite:///:memory:")
    get_settings.cache_clear()


def _signup(tc: TestClient, email: str = "visitor@t.test") -> dict:
    r = tc.post("/v1/auth/signup", json={"email": email, "password": "password12345"})
    assert r.status_code == 200, r.text
    return r.json()


# --------------------------------------------------------------------------------------------- #
# The refusal
# --------------------------------------------------------------------------------------------- #
@pytest.mark.parametrize("method,path,body", [
    ("post", "/v1/scan/link/commenters", {"url": "https://x.com/a/status/1"}),
    ("post", "/v1/scan/link/score", {"url": "https://x.com/a/status/1", "selected": ["u1"]}),
    ("get", "/v1/investigations", None),
    ("get", "/v1/graphs", None),
    ("get", "/v1/watchlists", None),
    ("get", "/v1/billing/status", None),
])
def test_a_signed_in_non_admin_is_refused_on_every_product_route(locked, method, path, body):
    """The control. Each of these is reachable with nothing but the session cookie a browser holds
    after signing in, so each is a way to spend upstream budget without the UI being involved."""
    _signup(locked)
    r = getattr(locked, method)(path, **({"json": body} if body is not None else {}))
    assert r.status_code == 403, f"{path} answered {r.status_code}"
    assert "not open yet" in r.json()["detail"]


def test_an_admin_can_use_the_product_normally(locked):
    """The operator has to be able to run and demonstrate the whole thing while it is shut."""
    _signup(locked, ADMIN_EMAIL)
    assert locked.get("/v1/auth/me").json()["is_admin"] is True
    # 403 is the lockdown; anything else means the gate let them through to the real handler.
    assert locked.get("/v1/investigations").status_code != 403
    assert locked.get("/v1/graphs").status_code != 403


def test_the_anonymous_demo_is_off(locked):
    """It never reaches require_user (no auth), so it needs its own refusal — and it is the single
    most expensive anonymous surface there is: a demo runs the real engine AND a real model call."""
    for path in ("/v1/scan/demo/commenters", "/v1/scan/demo/score"):
        r = locked.post(path, json={"url": "https://x.com/a/status/1", "selected": []})
        assert r.status_code == 403, path


# --------------------------------------------------------------------------------------------- #
# What must stay reachable
# --------------------------------------------------------------------------------------------- #
def test_auth_stays_open_or_nobody_can_be_told_they_are_locked_out(locked):
    """The web app has to be able to ask who you are in order to redirect you to the waitlist."""
    _signup(locked)
    r = locked.get("/v1/auth/me")
    assert r.status_code == 200
    assert r.json()["lockdown"] is True, "the browser learns the mode from the server, not its own env"


def test_the_waitlist_is_reachable_because_it_is_the_only_thing_a_visitor_can_do(locked):
    assert locked.post("/v1/waitlist", json={"email": "someone@t.test"}).status_code == 200


def test_signing_up_during_lockdown_puts_you_on_the_waitlist(locked):
    """They cannot use the product, so what they have actually done is ask to be told when they can.
    Without this a visitor who goes straight to sign-up is silently left off the launch email."""
    _signup(locked, "eager@t.test")
    with get_session() as s:
        rows = {r.email: r.source for r in s.execute(select(WaitlistEntry)).scalars()}
    assert rows.get("eager@t.test") == "signup"


# --------------------------------------------------------------------------------------------- #
# Lifting it
# --------------------------------------------------------------------------------------------- #
def test_turning_the_switch_off_restores_the_product_for_everyone(open_site):
    """The launch-day path. One env var, and a non-admin is an ordinary customer again."""
    _signup(open_site)
    assert open_site.get("/v1/auth/me").json()["lockdown"] is False
    for path in ("/v1/investigations", "/v1/graphs", "/v1/watchlists"):
        assert open_site.get(path).status_code != 403, path


def test_the_code_default_is_open_so_deleting_the_variable_does_not_strand_the_site():
    """A stale lockdown outliving its launch date would be its own outage, and the person who could
    fix it would be looking for a bug rather than a leftover env var. render.yaml commits 'true'
    explicitly while the campaign runs."""
    from app.core.config import Settings

    assert Settings.model_fields["lockdown"].default is False
