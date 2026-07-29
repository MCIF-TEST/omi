"""Checkout must not lose a sale over a payment method Stripe has not approved yet.

A brand new Stripe account routinely has Link live while Cards are still in review. We ask for
`payment_method_types=[link, card]`, Stripe rejects the whole Session because one of them is not
activated, and the customer sees a dead Subscribe button. The account CAN take money; our hardcoded
list is what refuses it.

So a payment-method rejection retries once WITHOUT payment_method_types, which makes Stripe offer
whatever the dashboard actually has enabled. These pin that, and pin that the retry does not quietly
lose the metadata a payment needs to be attributable to a user.
"""

from __future__ import annotations

import sys
import types

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core import billing_sync
from app.core.config import get_settings
from app.main import app
from app.storage.db import get_session, reset_db_for_tests
from app.storage.models import User


class _StripeError(Exception):
    """Stands in for stripe.error.InvalidRequestError, which we only match on by message."""


class _List:
    def __init__(self, data):
        self.data = data


class FakeStripe:
    """Records every Checkout Session attempt so the test can assert on the retry."""

    def __init__(self, *, reject_payment_methods: bool):
        self.api_key = None
        self.attempts: list[dict] = []
        outer = self

        class Session:
            @staticmethod
            def create(**kw):
                outer.attempts.append(kw)
                if reject_payment_methods and "payment_method_types" in kw:
                    raise _StripeError(
                        "The payment method type \"card\" is not activated for your account. "
                        "You cannot use payment_method_types[1]=card."
                    )
                return types.SimpleNamespace(
                    id="cs_test_1", url="https://checkout.stripe.com/c/pay/cs_test_1",
                )

        # NOT `class Checkout: Session = Session`. A class body resolves names with LOAD_NAME,
        # which checks locals then GLOBALS and skips the enclosing function scope, so it would
        # NameError on the Session defined just above. Same family as the closure trap in CLAUDE.md.
        checkout_ns = types.SimpleNamespace(Session=Session)

        class Customer:
            @staticmethod
            def create(**kw):
                return types.SimpleNamespace(id="cus_pmtest")

            @staticmethod
            def retrieve(cid, *a, **k):
                return types.SimpleNamespace(id=cid)

        class Price:
            @staticmethod
            def retrieve(pid, *a, **k):
                return types.SimpleNamespace(
                    unit_amount=1399, currency="usd", active=True,
                    recurring={"interval": "month"},
                )

        class Subscription:
            @staticmethod
            def list(**kw):
                return _List([])

        class BillingPortal:
            class Session:
                @staticmethod
                def create(**kw):
                    return types.SimpleNamespace(url="https://billing.stripe.com/p/session/x")

        self.checkout = checkout_ns
        self.Customer = Customer
        self.Price = Price
        self.Subscription = Subscription
        self.billing_portal = BillingPortal


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("OMI_REQUIRE_AUTH", "true")
    monkeypatch.setenv("OMI_SESSION_SECRET", "x" * 64)
    monkeypatch.setenv("OMI_STRIPE_SECRET_KEY", "sk_test_dummy")
    monkeypatch.setenv("OMI_STRIPE_PRICE_ID", "price_test_dummy")
    monkeypatch.setenv("OMI_STRIPE_PAYMENT_METHOD_TYPES", "link,card")
    # Not set before signup: an https base url marks the session cookie Secure and TestClient,
    # which speaks http, would never send it back. See test_billing_webhook_primary.
    get_settings.cache_clear()
    reset_db_for_tests("sqlite:///:memory:")
    billing_sync.reset_sync_throttle_for_tests()
    from app.core.rate_limit import SIGNUP_LIMITER, LOGIN_LIMITER
    SIGNUP_LIMITER._windows.clear()
    LOGIN_LIMITER._windows.clear()
    with TestClient(app) as tc:
        tc.post("/v1/auth/signup", json={"email": "buyer@t.com", "password": "password12345"})
        yield tc
    billing_sync.reset_sync_throttle_for_tests()
    reset_db_for_tests("sqlite:///:memory:")
    get_settings.cache_clear()


def _install(monkeypatch, fake: FakeStripe) -> None:
    monkeypatch.setitem(sys.modules, "stripe", fake)


def test_unactivated_payment_method_falls_back_to_the_accounts_own_methods(client, monkeypatch):
    """Cards pending review must not stop someone paying by Link."""
    fake = FakeStripe(reject_payment_methods=True)
    _install(monkeypatch, fake)
    monkeypatch.setenv("OMI_PUBLIC_BASE_URL", "https://omisphere.online")
    get_settings.cache_clear()

    r = client.post("/v1/billing/create-checkout-session")
    assert r.status_code == 200, r.text
    assert r.json()["url"].startswith("https://checkout.stripe.com/")

    assert len(fake.attempts) == 2, "expected one rejected attempt then one fallback"
    assert "payment_method_types" in fake.attempts[0]
    # The fallback omits the list entirely, so Stripe offers what the account has enabled.
    assert "payment_method_types" not in fake.attempts[1]


def test_the_fallback_keeps_everything_a_payment_needs_to_be_attributable(client, monkeypatch):
    """A retry that dropped metadata would produce a paid invoice crediting nobody."""
    fake = FakeStripe(reject_payment_methods=True)
    _install(monkeypatch, fake)
    monkeypatch.setenv("OMI_PUBLIC_BASE_URL", "https://omisphere.online")
    get_settings.cache_clear()

    assert client.post("/v1/billing/create-checkout-session").status_code == 200
    first, retry = fake.attempts

    with get_session() as s:
        uid = s.execute(select(User).where(User.email == "buyer@t.com")).scalar_one().id

    for key in ("mode", "customer", "line_items", "success_url", "cancel_url",
                "metadata", "subscription_data", "client_reference_id"):
        assert retry[key] == first[key], f"fallback changed {key}"
    assert retry["metadata"]["omi_user_id"] == str(uid)
    assert retry["subscription_data"]["metadata"]["omi_user_id"] == str(uid)


def test_no_retry_when_the_first_attempt_succeeds(client, monkeypatch):
    """The fallback is for a rejection, not an extra call on the happy path."""
    fake = FakeStripe(reject_payment_methods=False)
    _install(monkeypatch, fake)
    monkeypatch.setenv("OMI_PUBLIC_BASE_URL", "https://omisphere.online")
    get_settings.cache_clear()

    assert client.post("/v1/billing/create-checkout-session").status_code == 200
    assert len(fake.attempts) == 1
    assert fake.attempts[0]["payment_method_types"] == ["link", "card"]


def test_link_only_is_honoured_when_configured(client, monkeypatch):
    """Setting OMI_STRIPE_PAYMENT_METHOD_TYPES=link is the explicit way to skip cards."""
    monkeypatch.setenv("OMI_STRIPE_PAYMENT_METHOD_TYPES", "link")
    fake = FakeStripe(reject_payment_methods=False)
    _install(monkeypatch, fake)
    monkeypatch.setenv("OMI_PUBLIC_BASE_URL", "https://omisphere.online")
    get_settings.cache_clear()

    assert client.post("/v1/billing/create-checkout-session").status_code == 200
    assert fake.attempts[0]["payment_method_types"] == ["link"]
