"""Clerk provisioning — the backend half of the Clerk sign-in ↔ app redirect-loop fix.

Production failure: a user signs in with a Clerk DEVELOPMENT instance (pk_test). Its session token
carries no email claim, and the Clerk Backend API email lookup can be unconfigured or briefly
unreachable. The old code returned None in that case, so ``/v1/auth/me`` resolved to no user — the
app layout bounced the (Clerk-signed-in) user to /login, Clerk bounced them back to the app, and the
browser throttled after ~40 navigations (the blank screen + "client-side exception").

The fix: a VALID Clerk session token always resolves to a local user. When the email isn't available
yet, provision a stable placeholder keyed on the Clerk id and backfill the real email later. These
tests pin that behavior by stubbing token verification + email lookup (the real ones need Clerk's
JWKS / Backend API over the network).
"""
from __future__ import annotations

import pytest

from app.core import auth as auth_mod
from app.core import clerk_auth
from app.core.auth import _resolve_clerk_user, _is_placeholder_email
from app.core.config import get_settings
from app.storage.db import get_session, reset_db_for_tests
from app.storage.models import User


class _Client:
    def __init__(self, host: str):
        self.host = host


class _Req:
    """Minimal stand-in for a Starlette Request — .headers.get, .cookies, and .client.host are read."""
    def __init__(self, token: str = "tok", *, via_cookie: bool = False, cookie_name: str = "__session",
                 ip: str = "1.2.3.4", ref: str | None = None):
        self.headers = {} if via_cookie else {"authorization": f"Bearer {token}"}
        self.cookies = {cookie_name: token} if via_cookie else {}
        if ref:
            self.cookies["omi_ref"] = ref
        self.client = _Client(ip)


@pytest.fixture
def env(monkeypatch):
    monkeypatch.setenv("NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY", "pk_test_c3dlZXQtZmluY2gtNDUuY2xlcmsuYWNjb3VudHMuZGV2JA")
    monkeypatch.setenv("OMI_SUPER_ADMIN_EMAILS", "boss@omisphere.com")
    monkeypatch.setenv("OMI_FREE_TRIAL_CREDITS", "25")
    get_settings.cache_clear()
    reset_db_for_tests("sqlite:///:memory:")
    yield
    reset_db_for_tests("sqlite:///:memory:")
    get_settings.cache_clear()


def _patch(monkeypatch, *, sub: str, email):
    monkeypatch.setattr(clerk_auth, "verify_session_token", lambda t: {"sub": sub})
    monkeypatch.setattr(clerk_auth, "email_from_claims", lambda c: email)
    monkeypatch.setattr(clerk_auth, "fetch_user_email", lambda uid: None)


def test_valid_token_without_email_still_provisions_a_user(env, monkeypatch):
    """The exact loop trigger: valid token, NO email. Must resolve to a real (placeholder) user."""
    _patch(monkeypatch, sub="user_noemail", email=None)
    cu = _resolve_clerk_user(_Req(), get_settings())
    assert cu is not None, "a valid Clerk sign-in must never resolve to None (that is the loop)"
    with get_session() as s:
        row = s.query(User).filter(User.clerk_user_id == "user_noemail").one()
        assert _is_placeholder_email(row.email)
        assert row.is_admin == 0
        assert row.credits_remaining == 25


def test_clerk_user_gets_a_referral_code(env, monkeypatch):
    """Clerk-provisioned accounts must get a referral code (legacy signup minted one; provisioning
    forgot to) — else the referral feature is dead for everyone who signs up via Clerk."""
    _patch(monkeypatch, sub="user_ref", email="ref@x.com")
    cu = _resolve_clerk_user(_Req(), get_settings())
    assert cu is not None and cu.referral_code
    with get_session() as s:
        row = s.query(User).filter(User.clerk_user_id == "user_ref").one()
        assert row.referral_code and len(row.referral_code) >= 4


def test_referral_code_backfills_for_a_codeless_existing_account(env, monkeypatch):
    _patch(monkeypatch, sub="user_bf", email="bf@x.com")
    with get_session() as s:
        s.add(User(email="bf@x.com", password_hash="h", credits_remaining=5, referral_code=None))
    cu = _resolve_clerk_user(_Req(), get_settings())
    assert cu is not None and cu.referral_code, "an existing code-less account must be backfilled"


def test_referral_link_credits_the_referrer_on_clerk_signup(env, monkeypatch):
    """A Clerk signup arriving via a referral link (code stashed in the omi_ref cookie) links the
    referrer and pays the +3 signup bonus — the acquisition half of the referral system."""
    with get_session() as s:
        s.add(User(email="advocate@x.com", password_hash="h", credits_remaining=10,
                   referral_code="REFCODE1", referral_credits_earned=0))
    _patch(monkeypatch, sub="user_referred", email="new@x.com")
    cu = _resolve_clerk_user(_Req(ip="7.7.7.7", ref="REFCODE1"), get_settings())
    assert cu is not None
    with get_session() as s:
        referred = s.query(User).filter(User.clerk_user_id == "user_referred").one()
        advocate = s.query(User).filter(User.referral_code == "REFCODE1").one()
        assert referred.referred_by_user_id == advocate.id
        assert advocate.credits_remaining == 13  # +3 signup bonus
        assert advocate.referral_credits_earned == 3


def test_second_signup_from_same_ip_gets_no_trial_credits(env, monkeypatch):
    """Anti-farming parity with the legacy signup: the first Clerk account from an IP gets the trial,
    later ones from the same IP get 0 — so trial credits (real API spend) can't be stacked."""
    _patch(monkeypatch, sub="user_ip1", email="ip1@x.com")
    first = _resolve_clerk_user(_Req(ip="9.9.9.9"), get_settings())
    assert first is not None and first.credits_remaining == 25
    _patch(monkeypatch, sub="user_ip2", email="ip2@x.com")
    second = _resolve_clerk_user(_Req(ip="9.9.9.9"), get_settings())
    assert second is not None and second.credits_remaining == 0


def test_placeholder_is_upgraded_when_the_real_email_arrives(env, monkeypatch):
    """Second sign-in, email now available → placeholder swapped for the real email, same account."""
    _patch(monkeypatch, sub="user_up", email=None)
    first = _resolve_clerk_user(_Req(), get_settings())
    assert first is not None

    _patch(monkeypatch, sub="user_up", email="real@person.com")
    second = _resolve_clerk_user(_Req(), get_settings())
    assert second is not None and second.email == "real@person.com"
    with get_session() as s:
        rows = s.query(User).filter(User.clerk_user_id == "user_up").all()
        assert len(rows) == 1, "must upgrade in place, not create a duplicate account"
        assert not _is_placeholder_email(rows[0].email)


def test_session_cookie_authenticates_without_a_bearer_header(env, monkeypatch):
    """A client fetch fired before window.Clerk.session is ready sends the __session cookie but no
    Bearer — it must still resolve, or app pages 401 on first paint."""
    _patch(monkeypatch, sub="user_cookie", email="cookie@x.com")
    cu = _resolve_clerk_user(_Req(via_cookie=True), get_settings())
    assert cu is not None and cu.email == "cookie@x.com"


def test_suffixed_session_cookie_also_authenticates(env, monkeypatch):
    _patch(monkeypatch, sub="user_suffixed", email="suffix@x.com")
    cu = _resolve_clerk_user(_Req(via_cookie=True, cookie_name="__session_abc123"), get_settings())
    assert cu is not None and cu.email == "suffix@x.com"


def test_super_admin_email_grants_admin(env, monkeypatch):
    _patch(monkeypatch, sub="user_boss", email="boss@omisphere.com")
    cu = _resolve_clerk_user(_Req(), get_settings())
    assert cu is not None and cu.is_admin


def test_existing_email_account_is_linked_not_duplicated(env, monkeypatch):
    """A local account already exists for this email (legacy signup) → link it, carry data over."""
    with get_session() as s:
        s.add(User(email="carry@x.com", password_hash="h", credits_remaining=7))
    _patch(monkeypatch, sub="user_link", email="carry@x.com")
    cu = _resolve_clerk_user(_Req(), get_settings())
    assert cu is not None and cu.email == "carry@x.com"
    with get_session() as s:
        rows = s.query(User).filter(User.email == "carry@x.com").all()
        assert len(rows) == 1 and rows[0].clerk_user_id == "user_link"
        assert rows[0].credits_remaining == 7, "existing credits must be preserved on link"


# ---------------------------------------------------------------------------
# Moving from the development Clerk instance to the production one
#
# Every user gets a BRAND NEW Clerk id when the deployment switches from pk_test to pk_live: the two
# instances are separate user pools and nothing migrates between them. So the owner signs in on the
# production instance, `clerk_user_id` misses, and the account is found by email instead. These pin
# what has to happen next.
# ---------------------------------------------------------------------------
def test_a_new_instance_id_re_points_the_existing_account(env, monkeypatch):
    """The link must be made DURABLE, not just used once.

    Leaving the stale development id in place still returned the right account, but only through the
    email path, which means every request re-resolves the user through the Clerk Backend API. The
    moment that call fails (a rotated secret, a Clerk outage) `email` is None and the create branch
    runs instead, minting an EMPTY DUPLICATE account for someone who has credits, investigations and
    possibly a subscription.
    """
    with get_session() as s:
        s.add(User(email="owner@x.com", password_hash="h", credits_remaining=11,
                   clerk_user_id="user_from_the_dev_instance"))

    _patch(monkeypatch, sub="user_from_the_live_instance", email="owner@x.com")
    cu = _resolve_clerk_user(_Req(), get_settings())
    assert cu is not None and cu.email == "owner@x.com"
    assert cu.credits_remaining == 11, "credits and history must survive the instance switch"

    with get_session() as s:
        rows = s.query(User).filter(User.email == "owner@x.com").all()
        assert len(rows) == 1, "must re-link, never duplicate"
        assert rows[0].clerk_user_id == "user_from_the_live_instance"

    # And now the fast path resolves it directly, with no Backend API call at all.
    monkeypatch.setattr(clerk_auth, "email_from_claims", lambda c: None)
    monkeypatch.setattr(clerk_auth, "fetch_user_email", _fail_if_called)
    again = _resolve_clerk_user(_Req(), get_settings())
    assert again is not None and again.email == "owner@x.com"


def _fail_if_called(uid):  # pragma: no cover - the assertion is that it is NOT called
    raise AssertionError(
        "the Clerk Backend API was called again after the account was re-linked; the link did not "
        "stick, and a failure of this call would create a duplicate empty account"
    )


def test_re_linking_restores_admin_for_a_super_admin_email(env, monkeypatch):
    """is_admin is granted from OMI_SUPER_ADMIN_EMAILS at CREATION, and this path skips creation.

    Without this the owner comes back from the instance switch as an ordinary customer: no
    /disputes, no /narratives, no admin routes, and no signal breakdown on their own investigations.
    """
    with get_session() as s:
        s.add(User(email="boss@omisphere.com", password_hash="h", clerk_user_id="old_dev_id"))
    _patch(monkeypatch, sub="new_live_id", email="boss@omisphere.com")
    cu = _resolve_clerk_user(_Req(), get_settings())
    assert cu is not None and cu.is_admin


def test_an_unrelated_account_is_not_touched(env, monkeypatch):
    """Guard against over-reach: re-pointing happens only for the row matching the signed-in email."""
    with get_session() as s:
        s.add(User(email="someone@else.com", password_hash="h", clerk_user_id="their_id"))
        s.add(User(email="owner@x.com", password_hash="h", clerk_user_id="old_dev_id"))
    _patch(monkeypatch, sub="new_live_id", email="owner@x.com")
    _resolve_clerk_user(_Req(), get_settings())
    with get_session() as s:
        other = s.query(User).filter(User.email == "someone@else.com").one()
        assert other.clerk_user_id == "their_id"
