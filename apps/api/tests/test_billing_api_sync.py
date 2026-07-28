"""Billing without a webhook — reconciling straight against Stripe's API.

Instead of being told what happened, the server asks Stripe what is true and makes its records match:
which subscription exists, and which invoices were actually paid. Every paid invoice grants its
credits exactly once, keyed on the invoice id.

These tests replace a fake Stripe module, so no network is involved but the real code path runs.
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

CUSTOMER = "cus_sync_1"


class _List:
    """Mimics a Stripe ListObject: an object with a .data attribute."""

    def __init__(self, data):
        self.data = data


class FakeStripe:
    """A Stripe stand-in whose objects are plain dicts — the same shape ``_plain`` normalises."""

    def __init__(self, *, subscriptions=None, invoices=None, customers=None):
        self.api_key = None
        self._subs = subscriptions if subscriptions is not None else []
        self._invoices = invoices if invoices is not None else []
        self._customers = customers if customers is not None else []
        self.calls: list[str] = []

        outer = self

        class Subscription:
            @staticmethod
            def list(**kw):
                outer.calls.append("Subscription.list")
                return _List(list(outer._subs))

        class Invoice:
            @staticmethod
            def list(**kw):
                outer.calls.append("Invoice.list")
                return _List(list(outer._invoices))

        class Customer:
            @staticmethod
            def list(**kw):
                outer.calls.append("Customer.list")
                return _List(list(outer._customers))

        self.Subscription = Subscription
        self.Invoice = Invoice
        self.Customer = Customer


def _sub(status="active", sub_id="sub_1", period_end=2_000_000_000):
    return {"id": sub_id, "status": status, "current_period_end": period_end, "created": 1}


def _invoice(invoice_id, *, reason="subscription_cycle", amount=999):
    return {"id": invoice_id, "billing_reason": reason, "amount_paid": amount, "status": "paid"}


def _install(monkeypatch, fake: FakeStripe) -> None:
    """Make ``import stripe`` inside billing_sync resolve to the fake."""
    monkeypatch.setitem(sys.modules, "stripe", fake)


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("OMI_REQUIRE_AUTH", "true")
    monkeypatch.setenv("OMI_SESSION_SECRET", "x" * 64)
    monkeypatch.setenv("OMI_FREE_TRIAL_CREDITS", "3")
    monkeypatch.setenv("OMI_STRIPE_SECRET_KEY", "sk_test_dummy")
    monkeypatch.setenv("OMI_STRIPE_PRICE_ID", "price_test_dummy")
    monkeypatch.setenv("OMI_MONTHLY_CREDIT_GRANT", "20")
    monkeypatch.delenv("OMI_STRIPE_WEBHOOK_SECRET", raising=False)  # NO webhook configured
    get_settings.cache_clear()
    reset_db_for_tests("sqlite:///:memory:")
    billing_sync.reset_sync_throttle_for_tests()
    from app.core.rate_limit import SIGNUP_LIMITER, LOGIN_LIMITER
    SIGNUP_LIMITER._windows.clear()
    LOGIN_LIMITER._windows.clear()
    with TestClient(app) as tc:
        tc.post("/v1/auth/signup", json={"email": "sub@t.com", "password": "password12345"})
        with get_session() as s:
            s.execute(select(User).where(User.email == "sub@t.com")).scalar_one().stripe_customer_id = CUSTOMER
        yield tc
    billing_sync.reset_sync_throttle_for_tests()
    reset_db_for_tests("sqlite:///:memory:")
    get_settings.cache_clear()


def _user() -> User:
    with get_session() as s:
        return s.execute(select(User).where(User.email == "sub@t.com")).scalar_one()


def _credits() -> int:
    return _user().credits_remaining


def _set_credits(n: int) -> None:
    with get_session() as s:
        s.execute(select(User).where(User.email == "sub@t.com")).scalar_one().credits_remaining = n


# --------------------------------------------------------------------------- #
# The purchase completes without any webhook
# --------------------------------------------------------------------------- #
def test_sync_grants_credits_for_a_paid_invoice(client, monkeypatch):
    _set_credits(0)
    _install(monkeypatch, FakeStripe(subscriptions=[_sub()], invoices=[_invoice("in_1")]))

    r = client.post("/v1/billing/sync")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["granted"] == 1 and body["credits_added"] == 20
    assert body["credits_remaining"] == 20
    assert body["subscription_status"] == "active"
    assert _credits() == 20


def test_sync_is_idempotent_however_many_times_it_runs(client, monkeypatch):
    """The browser retries this on the way back from Checkout; it must never over-credit."""
    _set_credits(0)
    _install(monkeypatch, FakeStripe(subscriptions=[_sub()], invoices=[_invoice("in_dup")]))
    for _ in range(5):
        client.post("/v1/billing/sync")
    assert _credits() == 20


def test_a_renewal_is_picked_up_on_the_next_sync_and_ADDS(client, monkeypatch):
    _set_credits(0)
    fake = FakeStripe(subscriptions=[_sub()], invoices=[_invoice("in_month1")])
    _install(monkeypatch, fake)
    client.post("/v1/billing/sync")
    assert _credits() == 20

    # A month later Stripe has charged again.
    fake._invoices = [_invoice("in_month2"), _invoice("in_month1")]
    client.post("/v1/billing/sync")
    assert _credits() == 40, "the renewal must add on top, not flatten the balance"


def test_a_long_absence_replays_every_missed_invoice_once(client, monkeypatch):
    """Nothing is lost while the user is away — unlike a missed webhook, which is gone for good."""
    _set_credits(0)
    _install(monkeypatch, FakeStripe(
        subscriptions=[_sub()],
        invoices=[_invoice(f"in_{i}") for i in range(3)],
    ))
    client.post("/v1/billing/sync")
    assert _credits() == 60
    client.post("/v1/billing/sync")
    assert _credits() == 60


# --------------------------------------------------------------------------- #
# What must not grant
# --------------------------------------------------------------------------- #
def test_a_zero_value_invoice_grants_nothing(client, monkeypatch):
    _set_credits(0)
    _install(monkeypatch, FakeStripe(subscriptions=[_sub()], invoices=[_invoice("in_zero", amount=0)]))
    client.post("/v1/billing/sync")
    assert _credits() == 0


def test_an_unrelated_billing_reason_grants_nothing(client, monkeypatch):
    _set_credits(0)
    _install(monkeypatch, FakeStripe(subscriptions=[_sub()], invoices=[_invoice("in_x", reason="manual")]))
    client.post("/v1/billing/sync")
    assert _credits() == 0


def test_a_customer_with_no_stripe_record_is_left_alone(client, monkeypatch):
    _set_credits(3)
    _install(monkeypatch, FakeStripe(subscriptions=[], invoices=[]))
    r = client.post("/v1/billing/sync")
    assert r.status_code == 200
    assert _credits() == 3


# --------------------------------------------------------------------------- #
# Subscription state mirrors Stripe
# --------------------------------------------------------------------------- #
def test_status_and_renewal_date_come_from_stripe(client, monkeypatch):
    _install(monkeypatch, FakeStripe(subscriptions=[_sub(status="active")], invoices=[]))
    client.post("/v1/billing/sync")
    u = _user()
    assert u.subscription_status == "active"
    assert u.stripe_subscription_id == "sub_1"
    assert u.subscription_renews_at is not None


def test_a_cancellation_made_in_stripe_is_reflected_locally(client, monkeypatch):
    _install(monkeypatch, FakeStripe(subscriptions=[_sub(status="active")], invoices=[]))
    client.post("/v1/billing/sync")
    assert _user().subscription_status == "active"

    _install(monkeypatch, FakeStripe(subscriptions=[_sub(status="canceled")], invoices=[]))
    client.post("/v1/billing/sync")
    assert _user().subscription_status == "canceled"


def test_a_subscription_deleted_in_stripe_clears_a_stale_active(client, monkeypatch):
    _install(monkeypatch, FakeStripe(subscriptions=[_sub(status="active")], invoices=[]))
    client.post("/v1/billing/sync")
    _install(monkeypatch, FakeStripe(subscriptions=[], invoices=[]))
    client.post("/v1/billing/sync")
    assert _user().subscription_status == "canceled"


def test_the_renewal_date_is_read_from_the_item_when_stripe_puts_it_there(client, monkeypatch):
    sub = {"id": "sub_i", "status": "active", "created": 1,
           "items": {"data": [{"current_period_end": 2_000_000_000}]}}
    _install(monkeypatch, FakeStripe(subscriptions=[sub], invoices=[]))
    client.post("/v1/billing/sync")
    assert _user().subscription_renews_at is not None


# --------------------------------------------------------------------------- #
# Resilience — reconciliation must never break the app
# --------------------------------------------------------------------------- #
def test_a_stripe_outage_does_not_fail_the_request(client, monkeypatch):
    class Broken(FakeStripe):
        def __init__(self):
            super().__init__(subscriptions=[], invoices=[])
            class Subscription:
                @staticmethod
                def list(**kw):
                    raise RuntimeError("stripe is down")
            self.Subscription = Subscription

    _set_credits(4)
    _install(monkeypatch, Broken())
    r = client.post("/v1/billing/sync")
    assert r.status_code == 200, "a Stripe outage must not surface as a server error"
    assert r.json()["synced"] is False
    assert _credits() == 4


def test_billing_works_with_no_webhook_secret_configured(client, monkeypatch):
    """The whole point: OMI_STRIPE_WEBHOOK_SECRET is unset in this fixture, and money still works."""
    assert get_settings().stripe_webhook_secret is None
    _set_credits(0)
    _install(monkeypatch, FakeStripe(subscriptions=[_sub()], invoices=[_invoice("in_nowebhook")]))
    client.post("/v1/billing/sync")
    assert _credits() == 20


# --------------------------------------------------------------------------- #
# Throttling — automatic syncs are cheap, explicit ones are always fresh
# --------------------------------------------------------------------------- #
def test_the_status_endpoint_does_not_hit_stripe_on_every_load(client, monkeypatch):
    fake = FakeStripe(subscriptions=[_sub()], invoices=[])
    _install(monkeypatch, fake)
    client.get("/v1/billing/status")
    first = len(fake.calls)
    assert first > 0
    for _ in range(4):
        client.get("/v1/billing/status")
    assert len(fake.calls) == first, "automatic syncs must be throttled per user"


def test_an_explicit_sync_ignores_the_throttle(client, monkeypatch):
    fake = FakeStripe(subscriptions=[_sub()], invoices=[])
    _install(monkeypatch, fake)
    client.get("/v1/billing/status")
    before = len(fake.calls)
    client.post("/v1/billing/sync")
    assert len(fake.calls) > before, "returning from checkout must never be served a stale answer"


# --------------------------------------------------------------------------- #
# The moment that matters most
# --------------------------------------------------------------------------- #
def test_a_renewed_subscriber_is_not_refused_a_scan_over_a_stale_balance(client, monkeypatch):
    """A local balance of 0 with a paid invoice sitting in Stripe must not produce a 402 telling a
    paying customer to subscribe. consume_credits reconciles before it refuses."""
    from app.core.auth import consume_credits

    _set_credits(0)
    _install(monkeypatch, FakeStripe(subscriptions=[_sub()], invoices=[_invoice("in_justpaid")]))
    billing_sync.reset_sync_throttle_for_tests()

    remaining = consume_credits(
        _user().id, 1, platform="x", scan_type="link", target_input=None,
    )
    assert remaining == 19, "the renewal should have been picked up and the scan allowed"


def test_a_genuinely_broke_user_still_gets_a_clean_402(client, monkeypatch):
    from fastapi import HTTPException

    from app.core.auth import consume_credits

    _set_credits(0)
    _install(monkeypatch, FakeStripe(subscriptions=[], invoices=[]))
    billing_sync.reset_sync_throttle_for_tests()

    with pytest.raises(HTTPException) as exc:
        consume_credits(_user().id, 1, platform="x", scan_type="link", target_input=None)
    assert exc.value.status_code == 402


# --------------------------------------------------------------------------- #
# Preflight — "did I configure this correctly?" answered against Stripe
# --------------------------------------------------------------------------- #
def _preflight_stripe(monkeypatch, *, price=None, account_ok=True, price_raises=False):
    fake = FakeStripe()

    class Account:
        @staticmethod
        def retrieve(*a, **k):
            if not account_ok:
                raise RuntimeError("bad key")
            return types.SimpleNamespace(id="acct_test_1")

    class Price:
        @staticmethod
        def retrieve(pid, *a, **k):
            if price_raises:
                raise RuntimeError("No such price")
            return price

    fake.Account = Account
    fake.Price = Price
    _install(monkeypatch, fake)
    return fake


def _price_obj(*, amount=999, currency="usd", interval="month", active=True):
    return types.SimpleNamespace(
        unit_amount=amount, currency=currency, active=active,
        recurring={"interval": interval} if interval else None,
    )


def _checks(body):
    return {c["name"]: c for c in body["checks"]}


def test_preflight_reports_ready_when_everything_is_set(client, monkeypatch):
    _preflight_stripe(monkeypatch, price=_price_obj())
    monkeypatch.setenv("OMI_PUBLIC_BASE_URL", "https://omisphere-web.onrender.com")
    get_settings.cache_clear()

    body = client.get("/v1/billing/preflight").json()
    assert body["ready"] is True, body
    c = _checks(body)
    assert c["secret_key"]["ok"] and c["stripe_reachable"]["ok"] and c["price"]["ok"]
    assert "9.99 USD per month" in c["price"]["detail"]


def test_preflight_catches_the_secret_key_set_but_no_price(client, monkeypatch):
    """The exact half-configured state: the key is set, so it LOOKS done, but checkout 503s."""
    _preflight_stripe(monkeypatch, price=_price_obj())
    monkeypatch.delenv("OMI_STRIPE_PRICE_ID", raising=False)
    monkeypatch.setenv("OMI_PUBLIC_BASE_URL", "https://omisphere-web.onrender.com")
    get_settings.cache_clear()

    body = client.get("/v1/billing/preflight").json()
    assert body["ready"] is False
    c = _checks(body)
    assert c["secret_key"]["ok"] is True
    assert c["price"]["ok"] is False
    assert "OMI_STRIPE_PRICE_ID" in c["price"]["detail"]
    assert any("OMI_STRIPE_PRICE_ID" in s for s in body["next_steps"])


def test_preflight_catches_a_one_off_price_used_for_a_subscription(client, monkeypatch):
    _preflight_stripe(monkeypatch, price=_price_obj(interval=None))
    monkeypatch.setenv("OMI_PUBLIC_BASE_URL", "https://omisphere-web.onrender.com")
    get_settings.cache_clear()

    body = client.get("/v1/billing/preflight").json()
    assert body["ready"] is False
    assert "ONE-OFF" in _checks(body)["price"]["detail"]


def test_preflight_catches_a_price_from_the_wrong_stripe_mode(client, monkeypatch):
    _preflight_stripe(monkeypatch, price=None, price_raises=True)
    monkeypatch.setenv("OMI_PUBLIC_BASE_URL", "https://omisphere-web.onrender.com")
    get_settings.cache_clear()

    body = client.get("/v1/billing/preflight").json()
    assert body["ready"] is False
    assert any("mode" in s for s in body["next_steps"])


def test_preflight_catches_a_bad_key(client, monkeypatch):
    _preflight_stripe(monkeypatch, price=_price_obj(), account_ok=False)
    get_settings.cache_clear()
    body = client.get("/v1/billing/preflight").json()
    assert body["ready"] is False
    assert _checks(body)["stripe_reachable"]["ok"] is False


def test_preflight_catches_a_return_url_left_on_localhost(client, monkeypatch):
    """Default config would redirect a paying customer to localhost."""
    _preflight_stripe(monkeypatch, price=_price_obj())
    monkeypatch.setenv("OMI_PUBLIC_BASE_URL", "http://localhost:8000")
    get_settings.cache_clear()

    body = client.get("/v1/billing/preflight").json()
    assert body["ready"] is False
    assert _checks(body)["return_url"]["ok"] is False


def test_preflight_never_returns_the_secret(client, monkeypatch):
    _preflight_stripe(monkeypatch, price=_price_obj())
    get_settings.cache_clear()
    raw = client.get("/v1/billing/preflight").text
    assert "sk_test_dummy" not in raw and "sk_live" not in raw


def test_preflight_says_reconciliation_is_the_crediting_mode_with_no_webhook(client, monkeypatch):
    """No webhook secret is a DEGRADED but working state, not a broken one.

    Reconciliation still credits every payment, so preflight must keep reporting ready — while
    saying plainly that the instant path is off.
    """
    _preflight_stripe(monkeypatch, price=_price_obj())
    monkeypatch.setenv("OMI_PUBLIC_BASE_URL", "https://omisphere-web.onrender.com")
    get_settings.cache_clear()
    body = client.get("/v1/billing/preflight").json()
    c = _checks(body)
    assert "reconciliation only" in c["crediting"]["detail"]
    assert c["webhook_secret"]["ok"] is False
    assert "inert" in c["webhook_secret"]["detail"]
    # Degraded, not blocking: money still arrives correctly.
    assert body["ready"] is True, body
