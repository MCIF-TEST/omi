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


class _Req:
    """Minimal stand-in for a Starlette Request — only .headers.get is used."""
    def __init__(self, token: str = "tok"):
        self.headers = {"authorization": f"Bearer {token}"}


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
