"""The webhook as the PRIMARY crediting path, with reconciliation kept as the backstop.

Running both paths is only safe because they claim the same per-invoice row. The test that matters
most in this file is the one proving that: a payment credited by the webhook must not be credited
again when reconciliation later sees the same invoice in Stripe's API. Get that wrong and every
subscriber is credited twice for one charge.

The rest pin the diagnostics, because a webhook that was never registered looks exactly like a
webhook that works until somebody pays.
"""

from __future__ import annotations

import inspect
import json
import re
import sys
import time
import types

import pytest
import stripe
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core import billing_sync
from app.core.config import get_settings
from app.main import app
from app.routes import billing
from app.storage.db import get_session, reset_db_for_tests
from app.storage.models import BillingEvent, User

WEBHOOK_SECRET = "whsec_test_secret_for_signing"
CUSTOMER = "cus_webhook_primary"


# --------------------------------------------------------------------------- #
# The event list is documentation that runs
# --------------------------------------------------------------------------- #
def test_webhook_events_match_the_dispatch_table():
    """WEBHOOK_EVENTS is what the operator ticks in the Stripe dashboard.

    If a handler is added to _dispatch and not to WEBHOOK_EVENTS, the dashboard is never told to
    send it and the feature is dead on arrival — silently, because nothing errors. If an event is
    listed but unhandled, we ask Stripe for traffic we ignore. Both drifts fail here.
    """
    source = inspect.getsource(billing._dispatch)
    dispatched = set(re.findall(r'"([a-z_]+\.[a-z_.]+)"', source))
    assert dispatched == set(billing.WEBHOOK_EVENTS), (
        f"_dispatch handles {sorted(dispatched)} but WEBHOOK_EVENTS lists "
        f"{sorted(billing.WEBHOOK_EVENTS)}"
    )


def test_only_invoice_paid_can_grant_credits():
    """A new subscription emits customer.subscription.created AND invoice.paid.

    Crediting on both bills the customer once and grants twice. This asserts the shape of the
    dispatch table rather than trusting a comment.
    """
    source = inspect.getsource(billing._handle_subscription_update)
    assert "_grant_credits_once" not in source
    assert "_grant_credits_once" in inspect.getsource(billing._handle_invoice_paid)


# --------------------------------------------------------------------------- #
# Fakes
# --------------------------------------------------------------------------- #
class _List:
    def __init__(self, data):
        self.data = data


class FakeStripe:
    """Enough Stripe for reconciliation + preflight, with no network."""

    def __init__(self, *, subscriptions=None, invoices=None, price=None):
        self.api_key = None
        self._subs = subscriptions or []
        self._invoices = invoices or []
        outer = self

        class Subscription:
            @staticmethod
            def list(**kw):
                return _List(list(outer._subs))

        class Invoice:
            @staticmethod
            def list(**kw):
                return _List(list(outer._invoices))

        class Customer:
            @staticmethod
            def list(**kw):
                return _List([])

        class Account:
            @staticmethod
            def retrieve(*a, **k):
                return types.SimpleNamespace(id="acct_test_1")

        class Price:
            @staticmethod
            def retrieve(pid, *a, **k):
                return price or types.SimpleNamespace(
                    unit_amount=999, currency="usd", active=True,
                    recurring={"interval": "month"},
                )

        self.Subscription = Subscription
        self.Invoice = Invoice
        self.Customer = Customer
        self.Account = Account
        self.Price = Price


def _install(monkeypatch, fake: FakeStripe) -> None:
    monkeypatch.setitem(sys.modules, "stripe", fake)


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("OMI_REQUIRE_AUTH", "true")
    monkeypatch.setenv("OMI_SESSION_SECRET", "x" * 64)
    monkeypatch.setenv("OMI_FREE_TRIAL_CREDITS", "3")
    monkeypatch.setenv("OMI_STRIPE_SECRET_KEY", "sk_test_dummy")
    monkeypatch.setenv("OMI_STRIPE_PRICE_ID", "price_test_dummy")
    monkeypatch.setenv("OMI_STRIPE_WEBHOOK_SECRET", WEBHOOK_SECRET)
    monkeypatch.setenv("OMI_MONTHLY_CREDIT_GRANT", "20")
    # Deliberately NOT setting OMI_PUBLIC_BASE_URL here: the session cookie is marked Secure when it
    # starts with https:// (app/core/auth.py), and TestClient speaks plain http, so an https value
    # set before signup means the cookie is never sent back and every authenticated call 401s.
    # Tests that need it set it themselves, after the fixture has signed in.
    get_settings.cache_clear()
    reset_db_for_tests("sqlite:///:memory:")
    billing_sync.reset_sync_throttle_for_tests()
    from app.core.rate_limit import SIGNUP_LIMITER, LOGIN_LIMITER
    SIGNUP_LIMITER._windows.clear()
    LOGIN_LIMITER._windows.clear()
    with TestClient(app) as tc:
        tc.post("/v1/auth/signup", json={"email": "payer@t.com", "password": "password12345"})
        with get_session() as s:
            s.execute(
                select(User).where(User.email == "payer@t.com")
            ).scalar_one().stripe_customer_id = CUSTOMER
        yield tc
    billing_sync.reset_sync_throttle_for_tests()
    reset_db_for_tests("sqlite:///:memory:")
    get_settings.cache_clear()


def _credits() -> int:
    with get_session() as s:
        return s.execute(
            select(User).where(User.email == "payer@t.com")
        ).scalar_one().credits_remaining


def _set_credits(n: int) -> None:
    with get_session() as s:
        s.execute(select(User).where(User.email == "payer@t.com")).scalar_one().credits_remaining = n


def _send(client: TestClient, event: dict, *, secret: str = WEBHOOK_SECRET):
    """POST a webhook signed exactly the way Stripe signs it (real verification path runs)."""
    event = {"object": "event", **event}
    payload = json.dumps(event)
    ts = int(time.time())
    sig = stripe.WebhookSignature._compute_signature(f"{ts}.{payload}", secret)
    return client.post(
        "/v1/billing/webhook",
        content=payload,
        headers={"stripe-signature": f"t={ts},v1={sig}", "content-type": "application/json"},
    )


def _invoice_paid_event(event_id: str, invoice_id: str) -> dict:
    return {
        "id": event_id, "type": "invoice.paid",
        "data": {"object": {
            "id": invoice_id, "customer": CUSTOMER,
            "billing_reason": "subscription_cycle", "amount_paid": 999,
        }},
    }


def _checks(body):
    return {c["name"]: c for c in body["checks"]}


# --------------------------------------------------------------------------- #
# The one that protects the customer's money
# --------------------------------------------------------------------------- #
def test_webhook_and_reconciliation_never_both_credit_the_same_invoice(client, monkeypatch):
    """The whole reason both paths can run at once.

    The webhook credits first (the fast path). Reconciliation then asks Stripe for paid invoices and
    sees the very same invoice — it must recognise it as already granted and add nothing.
    """
    _set_credits(0)

    # 1. Stripe pushes the payment. Instant credit.
    assert _send(client, _invoice_paid_event("evt_1", "in_shared")).status_code == 200
    assert _credits() == 20

    # 2. The backstop runs later over the same invoice.
    _install(monkeypatch, FakeStripe(
        subscriptions=[{"id": "sub_1", "status": "active",
                        "current_period_end": 2_000_000_000, "created": 1}],
        invoices=[{"id": "in_shared", "billing_reason": "subscription_cycle",
                   "amount_paid": 999, "status": "paid"}],
    ))
    r = client.post("/v1/billing/sync")
    assert r.status_code == 200, r.text

    assert r.json()["credits_added"] == 0, "reconciliation re-credited a webhook-granted invoice"
    assert _credits() == 20, "customer was credited twice for one charge"


def test_reconciliation_still_credits_when_the_webhook_never_arrives(client, monkeypatch):
    """The backstop earning its place: endpoint misregistered, so no event ever lands."""
    _set_credits(0)
    _install(monkeypatch, FakeStripe(
        subscriptions=[{"id": "sub_1", "status": "active",
                        "current_period_end": 2_000_000_000, "created": 1}],
        invoices=[{"id": "in_missed", "billing_reason": "subscription_cycle",
                   "amount_paid": 999, "status": "paid"}],
    ))
    assert client.post("/v1/billing/sync").json()["credits_added"] == 20
    assert _credits() == 20


# --------------------------------------------------------------------------- #
# Diagnostics
# --------------------------------------------------------------------------- #
def test_preflight_hands_over_the_url_and_events_to_register(client, monkeypatch):
    """Everything needed to fill in the Stripe form, so nobody types the host from memory."""
    _install(monkeypatch, FakeStripe())
    get_settings.cache_clear()

    body = client.get("/v1/billing/preflight").json()
    assert body["webhook_url"].endswith("/v1/billing/webhook")
    assert set(body["webhook_events"]) == set(billing.WEBHOOK_EVENTS)
    assert _checks(body)["webhook_url"]["ok"] is True


def test_preflight_refuses_to_print_a_url_when_it_is_being_proxied_through_the_web_app(
    client, monkeypatch
):
    """Called via the web app's /api proxy, the host we see is the WEB host.

    Printing that as the endpoint to register would send Stripe's events to a service with no
    webhook route — and the failure would only surface as customers not being credited.
    """
    _install(monkeypatch, FakeStripe())
    # Set only now — before signup an https base url marks the session cookie Secure and TestClient
    # would never send it back. See the fixture.
    monkeypatch.setenv("OMI_PUBLIC_BASE_URL", "https://omisphere-web.onrender.com")
    get_settings.cache_clear()

    body = client.get(
        "/v1/billing/preflight",
        headers={"host": "omisphere-web.onrender.com", "x-forwarded-proto": "https"},
    ).json()

    assert body["webhook_url"] is None
    c = _checks(body)["webhook_url"]
    assert c["ok"] is False and "WEB host" in c["detail"]


def test_preflight_reports_no_delivery_before_any_event_has_landed(client, monkeypatch):
    _install(monkeypatch, FakeStripe())
    get_settings.cache_clear()

    c = _checks(client.get("/v1/billing/preflight").json())["webhook_delivery"]
    # The secret IS set here, so never having heard from Stripe is a real problem.
    assert c["ok"] is False
    assert "never been received" in c["detail"] or "No Stripe event" in c["detail"]


def test_preflight_reports_the_last_delivery_once_stripe_has_reached_us(client, monkeypatch):
    assert _send(client, _invoice_paid_event("evt_seen", "in_seen")).status_code == 200
    _install(monkeypatch, FakeStripe())
    get_settings.cache_clear()

    c = _checks(client.get("/v1/billing/preflight").json())["webhook_delivery"]
    assert c["ok"] is True
    assert "invoice.paid" in c["detail"]
    # The 24h counter must actually count. A tz-aware/naive mismatch would make it silently 0 and
    # the diagnostic would read as "nothing is arriving" on a perfectly healthy webhook.
    assert "1 in the last 24h" in c["detail"], c["detail"]


def test_grant_markers_are_not_mistaken_for_webhook_deliveries(client, monkeypatch):
    """Reconciliation writes grant rows into the same table.

    If those counted as deliveries, a deployment whose webhook was never registered would report a
    healthy webhook — the exact false negative this diagnostic exists to prevent.
    """
    _set_credits(0)
    _install(monkeypatch, FakeStripe(
        subscriptions=[{"id": "sub_1", "status": "active",
                        "current_period_end": 2_000_000_000, "created": 1}],
        invoices=[{"id": "in_api_only", "billing_reason": "subscription_cycle",
                   "amount_paid": 999, "status": "paid"}],
    ))
    client.post("/v1/billing/sync")
    assert _credits() == 20  # a grant row now exists

    with get_session() as s:
        assert s.query(BillingEvent).count() >= 1

    c = _checks(client.get("/v1/billing/preflight").json())["webhook_delivery"]
    assert c["ok"] is False, "a reconciliation grant was counted as a webhook delivery"


def test_preflight_flags_a_secret_that_is_not_a_signing_secret(client, monkeypatch):
    """Pasting the API key or the endpoint id instead of whsec_… fails every delivery."""
    monkeypatch.setenv("OMI_STRIPE_WEBHOOK_SECRET", "sk_test_wrong_thing_entirely")
    _install(monkeypatch, FakeStripe())
    get_settings.cache_clear()

    c = _checks(client.get("/v1/billing/preflight").json())["webhook_secret"]
    assert c["ok"] is False
    assert "whsec_" in c["detail"]


def test_preflight_never_leaks_the_webhook_secret(client, monkeypatch):
    _install(monkeypatch, FakeStripe())
    get_settings.cache_clear()
    assert WEBHOOK_SECRET not in client.get("/v1/billing/preflight").text
