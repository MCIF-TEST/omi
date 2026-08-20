"""Stripe billing — the money path.

Every test here exists because the failure it pins costs somebody real money: a subscriber who pays
and receives nothing, a subscriber credited twice for one charge, or a stranger who grants themselves
credits by POSTing to the webhook. The signature check and the exactly-once grant are the two things
that must never regress.

No network: the Stripe SDK is only used to SIGN payloads exactly as Stripe does, so the endpoint's
real verification path runs against them.
"""

from __future__ import annotations

import json
import time

import pytest
import stripe
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.config import get_settings
from app.core.plans import STARTER
from app.main import app
from app.storage.db import get_session, reset_db_for_tests
from app.storage.models import BillingEvent, User

WEBHOOK_SECRET = "whsec_test_secret_for_signing"
CUSTOMER = "cus_test_123"


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("OMI_REQUIRE_AUTH", "true")
    monkeypatch.setenv("OMI_SESSION_SECRET", "x" * 64)
    monkeypatch.setenv("OMI_FREE_TRIAL_CREDITS", "3")
    monkeypatch.setenv("OMI_STRIPE_SECRET_KEY", "sk_test_dummy")
    monkeypatch.setenv("OMI_STRIPE_WEBHOOK_SECRET", WEBHOOK_SECRET)
    monkeypatch.setenv("OMI_STRIPE_PRICE_ID", "price_test_dummy")
    monkeypatch.setenv("OMI_STRIPE_PRICE_STARTER", "price_test_dummy")
    get_settings.cache_clear()
    reset_db_for_tests("sqlite:///:memory:")
    from app.core.rate_limit import SIGNUP_LIMITER, LOGIN_LIMITER
    SIGNUP_LIMITER._windows.clear()
    LOGIN_LIMITER._windows.clear()
    with TestClient(app) as tc:
        tc.post("/v1/auth/signup", json={"email": "payer@t.com", "password": "password12345"})
        # Link the Stripe customer the way checkout would.
        with get_session() as s:
            user = s.execute(select(User).where(User.email == "payer@t.com")).scalar_one()
            user.stripe_customer_id = CUSTOMER
        yield tc
    reset_db_for_tests("sqlite:///:memory:")
    get_settings.cache_clear()


def _credits() -> int:
    with get_session() as s:
        return s.execute(select(User).where(User.email == "payer@t.com")).scalar_one().credits_remaining


def _set_credits(n: int) -> None:
    with get_session() as s:
        s.execute(select(User).where(User.email == "payer@t.com")).scalar_one().credits_remaining = n


def _send(client: TestClient, event: dict, *, secret: str = WEBHOOK_SECRET):
    """POST a webhook signed exactly the way Stripe signs it."""
    # Real events carry a top-level "object": "event"; the SDK's construct_event requires it.
    event = {"object": "event", **event}
    payload = json.dumps(event)
    ts = int(time.time())
    sig = stripe.WebhookSignature._compute_signature(f"{ts}.{payload}", secret)
    return client.post(
        "/v1/billing/webhook",
        content=payload,
        headers={"stripe-signature": f"t={ts},v1={sig}", "content-type": "application/json"},
    )


#: The Price the fixture's subscription is on. A REAL invoice always names one, and since tiers
#: exist the Price is what decides which plan (and therefore how many credits) an invoice bought.
#: An invoice carrying no configured Price grants nothing, deliberately: guessing at what somebody
#: paid for is worse than telling the operator their Price ids are misconfigured.
PRICE = "price_test_dummy"

#: What that Price grants. Derived, never written out: the tier's credit figure is a pricing
#: decision that moves with the unit economics, and a literal here would silently start asserting
#: the wrong number the first time it does.
GRANT = STARTER.monthly_credits


def _lines(price: str = PRICE) -> dict:
    """Invoice line items in the CURRENT Stripe shape.

    ``invoice_price_ids`` reads three shapes because Stripe has moved this field twice; the other
    two are covered by their own tests. This is the modern one.
    """
    return {"data": [{"pricing": {"price_details": {"price": price}}}]}


def _invoice_paid(event_id: str, invoice_id: str, *, reason: str = "subscription_cycle",
                  amount: int = 999, price: str = PRICE) -> dict:
    return {
        "id": event_id, "type": "invoice.paid",
        "data": {"object": {
            "id": invoice_id, "customer": CUSTOMER,
            "billing_reason": reason, "amount_paid": amount,
            "lines": _lines(price),
        }},
    }


# --------------------------------------------------------------------------- #
# Granting — the customer paid, so the customer gets credits
# --------------------------------------------------------------------------- #
def test_a_paid_invoice_grants_the_monthly_credits(client):
    _set_credits(0)
    assert _send(client, _invoice_paid("evt_1", "in_1")).status_code == 200
    assert _credits() == GRANT


def test_renewal_ADDS_credits_and_never_flattens_a_balance(client):
    """The bug this replaces: credits were assigned with max(balance, grant). A subscriber who
    renewed holding 20+ credits paid the full price and received NOTHING, because max(25, 20) == 25."""
    _set_credits(25)
    assert _send(client, _invoice_paid("evt_2", "in_2")).status_code == 200
    assert _credits() == 25 + GRANT, "a paid renewal must add its credits on top of the existing balance"


def test_unused_credits_survive_several_renewals(client):
    _set_credits(0)
    for i in range(3):
        _send(client, _invoice_paid(f"evt_r{i}", f"in_r{i}"))
    assert _credits() == 3 * GRANT


# --------------------------------------------------------------------------- #
# Exactly-once — one charge, one grant
# --------------------------------------------------------------------------- #
def test_a_redelivered_event_does_not_grant_twice(client):
    """Stripe retries for three days; the same event id can arrive many times."""
    _set_credits(0)
    _send(client, _invoice_paid("evt_dup", "in_dup"))
    _send(client, _invoice_paid("evt_dup", "in_dup"))
    _send(client, _invoice_paid("evt_dup", "in_dup"))
    assert _credits() == GRANT


def test_the_same_invoice_under_a_DIFFERENT_event_id_does_not_grant_twice(client):
    """Event-id idempotency alone is not enough: Stripe can describe one payment through more than
    one event. The grant is keyed on the INVOICE, so the second event is recorded and ignored."""
    _set_credits(0)
    _send(client, _invoice_paid("evt_a", "in_same"))
    _send(client, _invoice_paid("evt_b", "in_same"))
    assert _credits() == GRANT


def test_a_new_subscription_grants_once_despite_two_lifecycle_events(client):
    """A new subscription emits customer.subscription.created AND invoice.paid. Granting on both is
    the classic double-credit; only the invoice grants."""
    _set_credits(0)
    _send(client, {
        "id": "evt_sub_created", "type": "customer.subscription.created",
        "data": {"object": {
            "id": "sub_1", "customer": CUSTOMER, "status": "active",
            "current_period_end": int(time.time()) + 30 * 86400,
        }},
    })
    _send(client, _invoice_paid("evt_first_invoice", "in_first", reason="subscription_create"))
    assert _credits() == GRANT


# --------------------------------------------------------------------------- #
# Authenticity — the webhook is a public URL
# --------------------------------------------------------------------------- #
def test_an_unsigned_request_is_rejected_and_grants_nothing(client):
    _set_credits(0)
    r = client.post("/v1/billing/webhook", json=_invoice_paid("evt_forged", "in_forged"))
    assert r.status_code == 400
    assert _credits() == 0


def test_a_request_signed_with_the_wrong_secret_is_rejected(client):
    """Exactly what an attacker who knows the URL and the payload shape would send."""
    _set_credits(0)
    r = _send(client, _invoice_paid("evt_forged2", "in_forged2"), secret="whsec_attacker_guess")
    assert r.status_code == 400
    assert _credits() == 0


# --------------------------------------------------------------------------- #
# Retry safety — a failed handler must be retried, not swallowed
# --------------------------------------------------------------------------- #
def test_a_failed_handler_leaves_the_event_unclaimed_so_stripes_retry_works(client, monkeypatch):
    """The bug this replaces: the event row was committed BEFORE the handler ran, so a handler crash
    meant Stripe's retry was waved through as a duplicate and the customer's credits were never
    granted. Claim and work must commit together."""
    import app.routes.billing as B

    _set_credits(0)
    calls = {"n": 0}
    real = B._handle_invoice_paid

    def flaky(session, obj, settings):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("transient database blip")
        return real(session, obj, settings)

    monkeypatch.setattr(B, "_handle_invoice_paid", flaky)

    first = _send(client, _invoice_paid("evt_retry", "in_retry"))
    assert first.status_code == 500, "a failed handler must tell Stripe to retry"
    assert _credits() == 0
    with get_session() as s:
        claimed = s.execute(
            select(BillingEvent).where(BillingEvent.stripe_event_id == "evt_retry")
        ).scalar_one_or_none()
        assert claimed is None, "a rolled-back handler must not leave the event marked processed"

    second = _send(client, _invoice_paid("evt_retry", "in_retry"))
    assert second.status_code == 200
    assert _credits() == GRANT, "Stripe's retry must actually deliver the credits"


# --------------------------------------------------------------------------- #
# What must NOT grant
# --------------------------------------------------------------------------- #
def test_a_zero_value_invoice_grants_nothing(client):
    """A fully-discounted or proration-only invoice is not a purchase."""
    _set_credits(0)
    _send(client, _invoice_paid("evt_zero", "in_zero", amount=0))
    assert _credits() == 0


def test_an_unrelated_billing_reason_grants_nothing(client):
    _set_credits(0)
    _send(client, _invoice_paid("evt_thresh", "in_thresh", reason="subscription_threshold"))
    assert _credits() == 0


def test_a_manual_invoice_whose_price_we_do_not_know_grants_nothing(client):
    """"manual" IS a granting reason, because a one-off credit pack arrives as one.

    That widening is only safe because the PRICE decides what an invoice bought. This is the test
    that keeps it safe: an invoice raised by hand in the Stripe dashboard, for anything that is not
    a configured Price, must grant nothing at all. Without this property, adding "manual" to the
    granting reasons would have turned any dashboard invoice into free credits.
    """
    _set_credits(0)
    _send(client, _invoice_paid("evt_hand", "in_hand", reason="manual", price="price_not_ours"))
    assert _credits() == 0


def test_a_top_up_grants_its_pack_and_does_not_imply_a_subscription(client, monkeypatch):
    """A credit pack adds credits and touches nothing else.

    The two failures this pins are opposite and both bad: a pack that grants nothing (the whole
    point of selling it), and a pack that marks a lapsed account as an active subscriber, which
    would hand them a paid tier's features for the price of some credits.
    """
    monkeypatch.setenv("OMI_STRIPE_PRICE_TOPUP", "price_topup_dummy")
    monkeypatch.setenv("OMI_TOPUP_PACK_CREDITS", "25")
    get_settings.cache_clear()
    _set_credits(0)

    _send(client, _invoice_paid("evt_top", "in_top", reason="manual", price="price_topup_dummy"))

    assert _credits() == 25
    with get_session() as s:
        user = s.execute(select(User).where(User.email == "payer@t.com")).scalar_one()
        assert user.plan_tier is None, "a credit pack is not a plan"
        assert user.subscription_status != "active", "a credit pack is not a subscription"


def test_an_event_for_an_unknown_customer_grants_nothing_and_still_acks(client):
    """Never 500 on an event we can't match — Stripe would retry it for three days."""
    _set_credits(0)
    r = _send(client, {
        "id": "evt_unknown", "type": "invoice.paid",
        "data": {"object": {"id": "in_unknown", "customer": "cus_nobody",
                            "billing_reason": "subscription_cycle", "amount_paid": 999}},
    })
    assert r.status_code == 200
    assert _credits() == 0


def test_metadata_resolves_the_user_when_the_customer_link_is_missing(client):
    """A payment must never credit nobody just because the customer id didn't match."""
    with get_session() as s:
        user = s.execute(select(User).where(User.email == "payer@t.com")).scalar_one()
        user.stripe_customer_id = None
        uid = user.id
    _set_credits(0)
    _send(client, {
        "id": "evt_meta", "type": "invoice.paid",
        "data": {"object": {"id": "in_meta", "customer": "cus_unlinked",
                            "billing_reason": "subscription_cycle", "amount_paid": 999,
                            "lines": _lines(),
                            "metadata": {"omi_user_id": str(uid)}}},
    })
    assert _credits() == GRANT
    with get_session() as s:
        # ...and the link is repaired so later events take the fast path.
        assert s.get(User, uid).stripe_customer_id == "cus_unlinked"


# --------------------------------------------------------------------------- #
# Subscription lifecycle
# --------------------------------------------------------------------------- #
def test_subscription_status_and_renewal_date_are_recorded(client):
    renews = int(time.time()) + 30 * 86400
    _send(client, {
        "id": "evt_su", "type": "customer.subscription.updated",
        "data": {"object": {"id": "sub_9", "customer": CUSTOMER, "status": "active",
                            "current_period_end": renews}},
    })
    with get_session() as s:
        u = s.execute(select(User).where(User.email == "payer@t.com")).scalar_one()
        assert u.subscription_status == "active"
        assert u.stripe_subscription_id == "sub_9"
        assert u.subscription_renews_at is not None


def test_renewal_date_is_read_from_the_item_when_stripe_puts_it_there(client):
    """Recent API versions moved current_period_end onto the subscription's items; reading only the
    top level silently leaves the renewal date blank."""
    renews = int(time.time()) + 30 * 86400
    _send(client, {
        "id": "evt_items", "type": "customer.subscription.updated",
        "data": {"object": {"id": "sub_i", "customer": CUSTOMER, "status": "active",
                            "items": {"data": [{"current_period_end": renews}]}}},
    })
    with get_session() as s:
        u = s.execute(select(User).where(User.email == "payer@t.com")).scalar_one()
        assert u.subscription_renews_at is not None


def test_cancellation_marks_canceled_but_leaves_bought_credits_alone(client):
    _set_credits(17)
    _send(client, {
        "id": "evt_del", "type": "customer.subscription.deleted",
        "data": {"object": {"id": "sub_x", "customer": CUSTOMER, "status": "canceled"}},
    })
    with get_session() as s:
        u = s.execute(select(User).where(User.email == "payer@t.com")).scalar_one()
        assert u.subscription_status == "canceled"
    assert _credits() == 17, "credits already paid for are the user's"


def test_a_failed_payment_marks_past_due_and_a_later_payment_restores_active(client):
    _send(client, {
        "id": "evt_pf", "type": "invoice.payment_failed",
        "data": {"object": {"id": "in_pf", "customer": CUSTOMER}},
    })
    with get_session() as s:
        assert s.execute(select(User).where(User.email == "payer@t.com")).scalar_one().subscription_status == "past_due"

    _send(client, _invoice_paid("evt_recover", "in_recover"))
    with get_session() as s:
        assert s.execute(select(User).where(User.email == "payer@t.com")).scalar_one().subscription_status == "active"


# --------------------------------------------------------------------------- #
# Configuration
# --------------------------------------------------------------------------- #
def test_billing_status_reports_the_plan_the_customer_is_actually_on(client):
    """The figures follow the TIER, not a single global setting.

    With one plan a global price string was correct. With three it would show a Research subscriber
    the Starter price, on the page where they check what they are paying.
    """
    # Before paying: the free tier's own figures, which are honestly zero rather than a preview of
    # what subscribing would grant.
    body = client.get("/v1/billing/status").json()
    assert body["configured"] is True
    assert body["plan_tier"] == "free"
    assert body["credits_per_period"] == 0

    _send(client, _invoice_paid("evt_status", "in_status"))

    body = client.get("/v1/billing/status").json()
    assert body["plan_tier"] == STARTER.slug
    assert body["plan_name"] == STARTER.display_name
    assert body["credits_per_period"] == GRANT
    assert body["price_display"] == STARTER.price_display
    # The call ceiling is part of what they bought, so the page can show it rather than letting the
    # customer discover it at a refusal.
    assert body["calls_included"] == STARTER.monthly_call_ceiling


def test_an_unconfigured_server_acks_webhooks_instead_of_making_stripe_retry(monkeypatch):
    """A deploy without Stripe keys must not black-hole into three days of Stripe retries."""
    monkeypatch.setenv("OMI_REQUIRE_AUTH", "true")
    monkeypatch.setenv("OMI_SESSION_SECRET", "x" * 64)
    monkeypatch.delenv("OMI_STRIPE_SECRET_KEY", raising=False)
    monkeypatch.delenv("OMI_STRIPE_WEBHOOK_SECRET", raising=False)
    get_settings.cache_clear()
    reset_db_for_tests("sqlite:///:memory:")
    with TestClient(app) as tc:
        r = tc.post("/v1/billing/webhook", json={"id": "evt", "type": "invoice.paid"})
        assert r.status_code == 200
    reset_db_for_tests("sqlite:///:memory:")
    get_settings.cache_clear()
