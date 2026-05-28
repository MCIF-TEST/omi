"""Stripe billing: subscription checkout + webhook.

Subscription product is created **once** in the Stripe dashboard:
    Product: "OMI Monthly"
    Price: $9.99 USD / month recurring → copy the price_xxx ID into
    OMI_STRIPE_PRICE_ID

Webhook events handled:
  * customer.subscription.created  -> mark active, grant monthly credits
  * customer.subscription.updated  -> reflect status changes
  * customer.subscription.deleted  -> mark canceled (credits remain until used)
  * invoice.paid                   -> grant credits on monthly renewal

Idempotency: each event's Stripe ID is stored; duplicate deliveries are
ignored. Stripe retries failed webhooks for 3 days, which this handles.
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel

from app.core.auth import CurrentUser, require_user
from app.core.config import Settings, get_settings
from app.core.referrals import grant_subscription_bonus_if_due
from app.storage.db import get_session
from app.storage.models import BillingEvent, User


router = APIRouter(prefix="/v1/billing", tags=["billing"])


def _stripe(settings: Settings):
    """Lazy import: keep stripe optional. Raises 503 when not configured."""
    if not settings.stripe_secret_key or not settings.stripe_price_id:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Billing isn't configured on this server yet. "
                "Contact support or check back later."
            ),
        )
    try:
        import stripe  # type: ignore
    except ImportError as e:
        raise HTTPException(
            status_code=503,
            detail="The stripe SDK is not installed in this environment.",
        ) from e
    stripe.api_key = settings.stripe_secret_key
    return stripe


class CheckoutResponse(BaseModel):
    url: str


@router.post("/create-checkout-session", response_model=CheckoutResponse)
def create_checkout_session(
    current: CurrentUser = Depends(require_user),
    settings: Settings = Depends(get_settings),
) -> CheckoutResponse:
    """Create a Stripe Checkout session for the $9.99/mo subscription.

    Returns the hosted-checkout URL; the frontend opens it in a new tab.
    On success Stripe redirects to ``/?billing=success`` on your domain.
    """
    stripe = _stripe(settings)

    # Reuse Stripe customer if we have one for this user
    customer_id: str | None = None
    with get_session() as session:
        user = session.get(User, current.id)
        if user is None:
            raise HTTPException(status_code=401, detail="Session invalid.")
        if user.stripe_customer_id:
            customer_id = user.stripe_customer_id
        else:
            customer = stripe.Customer.create(
                email=user.email,
                metadata={"omi_user_id": str(user.id)},
            )
            customer_id = customer.id
            user.stripe_customer_id = customer_id

    s = stripe.checkout.Session.create(
        mode="subscription",
        customer=customer_id,
        line_items=[{"price": settings.stripe_price_id, "quantity": 1}],
        success_url=f"{settings.public_base_url}/?billing=success",
        cancel_url=f"{settings.public_base_url}/?billing=cancel",
        allow_promotion_codes=True,
        metadata={"omi_user_id": str(current.id)},
    )
    return CheckoutResponse(url=s.url)


@router.post("/portal", response_model=CheckoutResponse)
def customer_portal(
    current: CurrentUser = Depends(require_user),
    settings: Settings = Depends(get_settings),
) -> CheckoutResponse:
    """Open the Stripe-hosted Customer Portal so the user can manage or
    cancel their subscription, update payment method, etc."""
    stripe = _stripe(settings)
    with get_session() as session:
        user = session.get(User, current.id)
        if user is None or not user.stripe_customer_id:
            raise HTTPException(
                status_code=400,
                detail="No subscription found. Subscribe first.",
            )
        portal = stripe.billing_portal.Session.create(
            customer=user.stripe_customer_id,
            return_url=f"{settings.public_base_url}/",
        )
        return CheckoutResponse(url=portal.url)


@router.post("/webhook")
async def stripe_webhook(
    request: Request,
    settings: Settings = Depends(get_settings),
) -> Response:
    """Webhook endpoint Stripe calls after billing events."""
    if not settings.stripe_secret_key or not settings.stripe_webhook_secret:
        # Silent 200: keeps Stripe from retrying when billing isn't set up.
        return Response(status_code=200)

    try:
        import stripe  # type: ignore
    except ImportError:
        return Response(status_code=200)

    stripe.api_key = settings.stripe_secret_key
    payload = await request.body()
    sig = request.headers.get("stripe-signature", "")
    try:
        event = stripe.Webhook.construct_event(
            payload, sig, settings.stripe_webhook_secret
        )
    except (ValueError, stripe.error.SignatureVerificationError):  # type: ignore[attr-defined]
        raise HTTPException(status_code=400, detail="Invalid webhook signature.")

    # Idempotency: each Stripe event id stored once.
    with get_session() as session:
        existing = (
            session.query(BillingEvent)
            .filter(BillingEvent.stripe_event_id == event["id"])
            .first()
        )
        if existing is not None:
            return Response(status_code=200)
        session.add(BillingEvent(
            stripe_event_id=event["id"],
            event_type=event["type"],
            payload_json=event.get("data", {}).get("object", {}) or {},
        ))

    etype = event["type"]
    obj = event["data"]["object"]

    if etype in ("customer.subscription.created", "customer.subscription.updated"):
        _handle_subscription_update(obj, settings)
    elif etype == "customer.subscription.deleted":
        _handle_subscription_deleted(obj)
    elif etype == "invoice.paid":
        _handle_invoice_paid(obj, settings)

    return Response(status_code=200)


def _find_user_by_customer(stripe_customer_id: str | None) -> User | None:
    if not stripe_customer_id:
        return None
    with get_session() as session:
        return (
            session.query(User)
            .filter(User.stripe_customer_id == stripe_customer_id)
            .first()
        )


def _handle_subscription_update(obj: dict, settings: Settings) -> None:
    cust = obj.get("customer")
    sub_id = obj.get("id")
    sub_status = obj.get("status")
    period_end = obj.get("current_period_end")
    renews_at = (
        datetime.fromtimestamp(period_end, tz=timezone.utc)
        if isinstance(period_end, (int, float))
        else None
    )
    with get_session() as session:
        user = session.query(User).filter(User.stripe_customer_id == cust).first()
        if user is None:
            return
        user.stripe_subscription_id = sub_id
        user.subscription_status = sub_status
        user.subscription_renews_at = renews_at
        # Subscription just became active for the first time: grant credits.
        if sub_status == "active" and user.credits_remaining < settings.monthly_credit_grant:
            user.credits_remaining = settings.monthly_credit_grant

        # Referral conversion bonus: if this user was referred and they just
        # became a paying subscriber, award their referrer +5 credits. The
        # helper is idempotent so Stripe webhook redeliveries are safe.
        if sub_status in ("active", "trialing"):
            grant_subscription_bonus_if_due(session, user)


def _handle_subscription_deleted(obj: dict) -> None:
    cust = obj.get("customer")
    with get_session() as session:
        user = session.query(User).filter(User.stripe_customer_id == cust).first()
        if user is None:
            return
        user.subscription_status = "canceled"


def _handle_invoice_paid(obj: dict, settings: Settings) -> None:
    """Recurring monthly invoice paid → refill credits."""
    cust = obj.get("customer")
    billing_reason = obj.get("billing_reason")
    if billing_reason not in (
        "subscription_cycle",      # the monthly recurring charge
        "subscription_create",     # very first charge
        "subscription_update",
    ):
        return
    with get_session() as session:
        user = session.query(User).filter(User.stripe_customer_id == cust).first()
        if user is None:
            return
        # On each successful invoice, top up to (or add) the monthly grant.
        # We add rather than overwrite, so accumulating unused credits is fine.
        user.credits_remaining = max(
            user.credits_remaining, settings.monthly_credit_grant
        )
        if user.subscription_status not in ("active", "trialing"):
            user.subscription_status = "active"
        # First successful invoice is also the "they paid" moment for the
        # referral bonus, in case subscription.created arrives out of order.
        if billing_reason == "subscription_create":
            grant_subscription_bonus_if_due(session, user)
