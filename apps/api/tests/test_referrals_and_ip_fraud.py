"""End-to-end tests for the referral system + signup-IP fraud prevention.

Rules covered:
  * First signup from an IP receives the free trial credits.
  * Second signup from the same IP receives 0 free credits.
  * Every user gets a unique referral_code at signup.
  * Signing up with a valid referral_code awards the referrer +3 credits.
  * Signing up with an INVALID code does NOT block the signup; referrer just stays unawarded.
  * IP-suppressed signups do NOT trigger the referral signup bonus (closes
    the self-refer-from-same-IP scam).
  * The Stripe subscription bonus is granted once when the referred user's
    subscription becomes active, and is idempotent across redeliveries.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.core.referrals import (
    SIGNUP_BONUS_CREDITS,
    SUBSCRIPTION_BONUS_CREDITS,
    grant_subscription_bonus_if_due,
)
from app.main import app
from app.storage.db import get_session, reset_db_for_tests
from app.storage.models import User


@pytest.fixture
def auth_client(monkeypatch):
    """TestClient with auth on, a clean DB, and rate limiters reset."""
    monkeypatch.setenv("OMI_REQUIRE_AUTH", "true")
    monkeypatch.setenv("OMI_SESSION_SECRET", "x" * 64)
    monkeypatch.setenv("OMI_FREE_TRIAL_CREDITS", "3")
    get_settings.cache_clear()
    reset_db_for_tests("sqlite:///:memory:")
    from app.core.rate_limit import SIGNUP_LIMITER, LOGIN_LIMITER
    SIGNUP_LIMITER._windows.clear()
    LOGIN_LIMITER._windows.clear()
    with TestClient(app) as tc:
        yield tc
    reset_db_for_tests("sqlite:///:memory:")
    get_settings.cache_clear()


# ---------------------------------------------------------------------------
# Baseline: signup always returns a referral code and trial credits
# ---------------------------------------------------------------------------


def test_signup_grants_trial_credits_and_referral_code(auth_client):
    r = auth_client.post(
        "/v1/auth/signup",
        json={"email": "a@x.com", "password": "password123"},
        headers={"x-forwarded-for": "10.0.0.1"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["credits_remaining"] == 3
    assert body["referral_credits_earned"] == 0
    assert isinstance(body["referral_code"], str)
    assert 4 <= len(body["referral_code"]) <= 16


# ---------------------------------------------------------------------------
# IP fraud prevention
# ---------------------------------------------------------------------------


def test_second_signup_from_same_ip_gets_zero_free_credits(auth_client):
    auth_client.post(
        "/v1/auth/signup",
        json={"email": "first@x.com", "password": "password123"},
        headers={"x-forwarded-for": "10.0.0.42"},
    )
    # Clear cookie jar so the second signup is treated as a fresh visitor.
    auth_client.cookies.clear()

    r = auth_client.post(
        "/v1/auth/signup",
        json={"email": "second@x.com", "password": "password123"},
        headers={"x-forwarded-for": "10.0.0.42"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["credits_remaining"] == 0, "Same-IP signup must not get free credits."
    # Account still works — they just won't have a free trial.
    assert body["referral_code"] is not None


def test_signup_from_different_ip_still_gets_credits(auth_client):
    auth_client.post(
        "/v1/auth/signup",
        json={"email": "first@x.com", "password": "password123"},
        headers={"x-forwarded-for": "10.0.0.1"},
    )
    auth_client.cookies.clear()

    r = auth_client.post(
        "/v1/auth/signup",
        json={"email": "second@x.com", "password": "password123"},
        headers={"x-forwarded-for": "10.0.0.99"},
    )
    assert r.json()["credits_remaining"] == 3


# ---------------------------------------------------------------------------
# Referral signup bonus
# ---------------------------------------------------------------------------


def test_referral_code_awards_referrer_three_credits(auth_client):
    referrer = auth_client.post(
        "/v1/auth/signup",
        json={"email": "alice@x.com", "password": "password123"},
        headers={"x-forwarded-for": "10.0.0.1"},
    ).json()
    auth_client.cookies.clear()

    auth_client.post(
        "/v1/auth/signup",
        json={
            "email": "bob@x.com",
            "password": "password123",
            "referral_code": referrer["referral_code"],
        },
        headers={"x-forwarded-for": "10.0.0.2"},
    )

    with get_session() as session:
        alice = session.query(User).filter(User.email == "alice@x.com").first()
        bob = session.query(User).filter(User.email == "bob@x.com").first()
        assert alice.credits_remaining == 3 + SIGNUP_BONUS_CREDITS
        assert alice.referral_credits_earned == SIGNUP_BONUS_CREDITS
        assert bob.referred_by_user_id == alice.id
        # Bob still gets his own trial credits (different IP).
        assert bob.credits_remaining == 3


def test_invalid_referral_code_does_not_block_signup(auth_client):
    r = auth_client.post(
        "/v1/auth/signup",
        json={
            "email": "bob@x.com",
            "password": "password123",
            "referral_code": "totallyfake",
        },
        headers={"x-forwarded-for": "10.0.0.5"},
    )
    assert r.status_code == 200
    assert r.json()["credits_remaining"] == 3


def test_referral_bonus_suppressed_when_referee_is_ip_duplicate(auth_client):
    """Self-refer-on-same-IP scam: alice signs up, then 'refers' bob from her
    own IP. Bob gets 0 trial credits (good), and alice gets 0 referral bonus
    (also good) because the signup was IP-suppressed."""
    auth_client.post(
        "/v1/auth/signup",
        json={"email": "alice@x.com", "password": "password123"},
        headers={"x-forwarded-for": "10.0.0.7"},
    )
    auth_client.cookies.clear()
    with get_session() as session:
        alice_code = session.query(User).filter(User.email == "alice@x.com").first().referral_code

    auth_client.post(
        "/v1/auth/signup",
        json={
            "email": "bob@x.com",
            "password": "password123",
            "referral_code": alice_code,
        },
        headers={"x-forwarded-for": "10.0.0.7"},  # SAME IP
    )

    with get_session() as session:
        alice = session.query(User).filter(User.email == "alice@x.com").first()
        bob = session.query(User).filter(User.email == "bob@x.com").first()
        assert bob.credits_remaining == 0
        assert alice.credits_remaining == 3, (
            "Referrer must not get the +3 bonus from a same-IP referee."
        )
        assert alice.referral_credits_earned == 0


# ---------------------------------------------------------------------------
# Subscription conversion bonus
# ---------------------------------------------------------------------------


def test_subscription_bonus_awarded_once(auth_client):
    auth_client.post(
        "/v1/auth/signup",
        json={"email": "alice@x.com", "password": "password123"},
        headers={"x-forwarded-for": "10.0.0.1"},
    )
    with get_session() as session:
        alice_code = session.query(User).filter(User.email == "alice@x.com").first().referral_code
    auth_client.cookies.clear()
    auth_client.post(
        "/v1/auth/signup",
        json={
            "email": "bob@x.com",
            "password": "password123",
            "referral_code": alice_code,
        },
        headers={"x-forwarded-for": "10.0.0.2"},
    )

    # First subscription event → bonus paid
    with get_session() as session:
        bob = session.query(User).filter(User.email == "bob@x.com").first()
        granted = grant_subscription_bonus_if_due(session, bob)
        assert granted is True

    # Second event (Stripe redelivery) → no double-payment
    with get_session() as session:
        bob = session.query(User).filter(User.email == "bob@x.com").first()
        granted_again = grant_subscription_bonus_if_due(session, bob)
        assert granted_again is False

    with get_session() as session:
        alice = session.query(User).filter(User.email == "alice@x.com").first()
        # Alice has: +3 signup bonus + 3 trial + 5 subscription bonus = 11
        assert alice.credits_remaining == 3 + SIGNUP_BONUS_CREDITS + SUBSCRIPTION_BONUS_CREDITS
        assert alice.referral_credits_earned == SIGNUP_BONUS_CREDITS + SUBSCRIPTION_BONUS_CREDITS


def test_subscription_bonus_skipped_when_no_referrer(auth_client):
    auth_client.post(
        "/v1/auth/signup",
        json={"email": "solo@x.com", "password": "password123"},
        headers={"x-forwarded-for": "10.0.0.1"},
    )
    with get_session() as session:
        solo = session.query(User).filter(User.email == "solo@x.com").first()
        granted = grant_subscription_bonus_if_due(session, solo)
        assert granted is False


# ---------------------------------------------------------------------------
# /me exposes referral fields
# ---------------------------------------------------------------------------


def test_me_endpoint_includes_referral_fields(auth_client):
    auth_client.post(
        "/v1/auth/signup",
        json={"email": "a@x.com", "password": "password123"},
        headers={"x-forwarded-for": "10.0.0.1"},
    )
    r = auth_client.get("/v1/auth/me")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body is not None
    assert isinstance(body["referral_code"], str)
    assert body["referral_credits_earned"] == 0
