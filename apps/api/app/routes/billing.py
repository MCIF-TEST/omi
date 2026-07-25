"""Stripe billing: subscription checkout + webhook.

The product is created **once** in the Stripe dashboard:

    Product: "OmiSphere Monthly"
    Price:   $9.99 USD / month, recurring  ->  copy the price_… id into OMI_STRIPE_PRICE_ID

Each paid invoice grants ``settings.monthly_credit_grant`` credits (20).

WHY THIS FILE IS SHAPED THE WAY IT IS
This is the money path, so it is built around two rules that are easy to get
wrong and expensive when you do:

1. **Credits are granted by PAYMENT, never by subscription state.** Only
   ``invoice.paid`` adds credits. A new subscription produces BOTH a
   ``customer.subscription.created`` and an ``invoice.paid`` — granting on both
   charges the customer once and credits them twice. The subscription events
   move status and renewal date only.

2. **Exactly-once is enforced by the database, not by application logic.**
   Every grant claims a uniquely-indexed row keyed on the Stripe *invoice* id.
   Two concurrent deliveries of the same invoice race for that insert; one wins,
   the other sees the unique violation and does nothing. Event-id idempotency
   alone is not enough, because two DIFFERENT events can describe the same
   payment.

The webhook claims the event and performs its work in ONE transaction. Marking
an event processed before the work commits means a failed handler is retried by
Stripe, skipped as a duplicate, and the customer has paid for nothing.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.auth import CurrentUser, require_user
from app.core.billing_sync import reconcile_billing
from app.core.config import Settings, get_settings
from app.core.referrals import grant_subscription_bonus_if_due
from app.storage.db import get_session
from app.storage.models import BillingEvent, User

log = logging.getLogger("omi.billing")

router = APIRouter(prefix="/v1/billing", tags=["billing"])

# Subscription states in which the account is considered paid-up.
PAID_STATUSES = ("active", "trialing")

# Invoice reasons that represent money actually moving for a subscription.
GRANTING_BILLING_REASONS = (
    "subscription_cycle",    # the recurring monthly charge
    "subscription_create",   # the first charge
    "subscription_update",   # plan change / proration
)


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


class BillingStatusResponse(BaseModel):
    """What the UI needs to render the billing panel without guessing."""

    configured: bool                 # the server can actually take a payment
    credits_remaining: int
    subscription_status: str | None
    subscription_renews_at: datetime | None
    price_display: str               # e.g. "$9.99"
    credits_per_period: int          # e.g. 20


@router.get("/status", response_model=BillingStatusResponse)
def billing_status(
    current: CurrentUser = Depends(require_user),
    settings: Settings = Depends(get_settings),
) -> BillingStatusResponse:
    """Current billing state for the signed-in user. Always answers — when Stripe isn't configured
    it reports ``configured: false`` so the UI can say so instead of offering a button that 503s.

    Opening the billing page reconciles against Stripe first (throttled), so the figures shown are
    Stripe's, not a possibly-stale local copy."""
    with get_session() as session:
        user = session.get(User, current.id)
        if user is None:
            raise HTTPException(status_code=401, detail="Session invalid.")
        reconcile_billing(session, user, settings=settings, reason="status")
        return BillingStatusResponse(
            configured=bool(settings.stripe_secret_key and settings.stripe_price_id),
            credits_remaining=user.credits_remaining,
            subscription_status=user.subscription_status,
            subscription_renews_at=user.subscription_renews_at,
            price_display=settings.subscription_price_display,
            credits_per_period=settings.monthly_credit_grant,
        )


class SyncResponse(BaseModel):
    synced: bool
    granted: int          # invoices newly credited by this call
    credits_added: int
    credits_remaining: int
    subscription_status: str | None


@router.post("/sync", response_model=SyncResponse)
def sync_billing(
    current: CurrentUser = Depends(require_user),
    settings: Settings = Depends(get_settings),
) -> SyncResponse:
    """Reconcile this user against Stripe RIGHT NOW, ignoring the throttle.

    This is how a purchase completes without a webhook: the browser comes back from Stripe Checkout,
    calls this, and the server asks Stripe what was actually paid. Idempotent — call it as often as
    you like; credits are keyed per invoice and granted once.
    """
    with get_session() as session:
        user = session.get(User, current.id)
        if user is None:
            raise HTTPException(status_code=401, detail="Session invalid.")
        result = reconcile_billing(session, user, settings=settings, force=True, reason="explicit")
        return SyncResponse(
            synced=bool(result["synced"]),
            granted=int(result["granted"]),
            credits_added=int(result["credits_added"]),
            credits_remaining=user.credits_remaining,
            subscription_status=user.subscription_status,
        )


class PreflightCheck(BaseModel):
    name: str
    ok: bool
    detail: str


class PreflightResponse(BaseModel):
    """Can this deployment actually take a payment right now?"""

    ready: bool
    checks: list[PreflightCheck]
    next_steps: list[str]


@router.get("/preflight", response_model=PreflightResponse)
def billing_preflight(
    current: CurrentUser = Depends(require_user),
    settings: Settings = Depends(get_settings),
) -> PreflightResponse:
    """Verify the billing configuration of THIS deployment, against Stripe.

    Setting the env vars and hoping is the failure mode this exists to remove: the secret key alone
    is not enough, and a price id that points at a one-off or the wrong amount fails only at the
    moment a customer tries to pay. This actually calls Stripe with the configured key, retrieves
    the configured price, and reports what a customer would hit.

    Never returns a secret — presence, mode, and public price facts only.
    """
    checks: list[PreflightCheck] = []
    steps: list[str] = []

    # --- 1. Secret key -----------------------------------------------------------------------
    key = (settings.stripe_secret_key or "").strip()
    if not key:
        checks.append(PreflightCheck(
            name="secret_key", ok=False,
            detail="OMI_STRIPE_SECRET_KEY is not set on the API service.",
        ))
        steps.append("Set OMI_STRIPE_SECRET_KEY (sk_test_… or sk_live_…) on the API service.")
    else:
        mode = "live" if key.startswith("sk_live") else "test" if key.startswith("sk_test") else "unknown"
        checks.append(PreflightCheck(
            name="secret_key", ok=True,
            detail=f"Set ({mode} mode key).",
        ))

    # --- 2. Can we actually reach Stripe with it? --------------------------------------------
    stripe = None
    if key:
        try:
            import stripe as _stripe_sdk  # type: ignore
            _stripe_sdk.api_key = key
            acct = _stripe_sdk.Account.retrieve()
            stripe = _stripe_sdk
            checks.append(PreflightCheck(
                name="stripe_reachable", ok=True,
                detail=f"Authenticated with Stripe account {getattr(acct, 'id', '?')}.",
            ))
        except ImportError:
            checks.append(PreflightCheck(
                name="stripe_reachable", ok=False,
                detail="The stripe SDK isn't installed in this environment.",
            ))
            steps.append("Redeploy the API service so `stripe` is installed from requirements.")
        except Exception as e:  # noqa: BLE001
            checks.append(PreflightCheck(
                name="stripe_reachable", ok=False,
                detail=f"Stripe rejected or could not be reached: {type(e).__name__}.",
            ))
            steps.append(
                "Check the key is correct, complete, and from the same mode (test/live) as your price."
            )

    # --- 3. The price: exists, recurring, and the amount you think it is ----------------------
    price_id = (settings.stripe_price_id or "").strip()
    if not price_id:
        checks.append(PreflightCheck(
            name="price", ok=False,
            detail="OMI_STRIPE_PRICE_ID is not set — checkout returns 503 and nobody can subscribe.",
        ))
        steps.append(
            "Create the $9.99/month recurring price in Stripe and set OMI_STRIPE_PRICE_ID to its "
            "price_… id."
        )
    elif stripe is not None:
        try:
            price = stripe.Price.retrieve(price_id)
            recurring = getattr(price, "recurring", None)
            interval = (recurring or {}).get("interval") if recurring else None
            amount = getattr(price, "unit_amount", None)
            currency = (getattr(price, "currency", "") or "").upper()
            active = bool(getattr(price, "active", False))
            pretty = f"{amount / 100:.2f} {currency}" if isinstance(amount, int) else "?"
            if not recurring:
                checks.append(PreflightCheck(
                    name="price", ok=False,
                    detail=f"Price {price_id} is a ONE-OFF price ({pretty}). Checkout runs in "
                           f"subscription mode and will fail.",
                ))
                steps.append("Recreate the price as a RECURRING monthly price and update OMI_STRIPE_PRICE_ID.")
            elif not active:
                checks.append(PreflightCheck(
                    name="price", ok=False, detail=f"Price {price_id} is archived in Stripe.",
                ))
                steps.append("Activate the price in Stripe, or point OMI_STRIPE_PRICE_ID at a live one.")
            else:
                checks.append(PreflightCheck(
                    name="price", ok=True,
                    detail=f"{pretty} per {interval} — this is what a customer is charged.",
                ))
        except Exception as e:  # noqa: BLE001
            checks.append(PreflightCheck(
                name="price", ok=False,
                detail=f"Could not retrieve price {price_id}: {type(e).__name__}. It may belong to "
                       f"the other mode (test vs live).",
            ))
            steps.append("Confirm OMI_STRIPE_PRICE_ID is from the SAME Stripe mode as your secret key.")
    else:
        checks.append(PreflightCheck(
            name="price", ok=False, detail="Set, but could not be verified without a working key.",
        ))

    # --- 4. Where Stripe sends the customer back ---------------------------------------------
    base = (settings.public_base_url or "").strip().rstrip("/")
    if not base or "localhost" in base or "127.0.0.1" in base:
        checks.append(PreflightCheck(
            name="return_url", ok=False,
            detail=f"OMI_PUBLIC_BASE_URL is '{base or 'unset'}' — paying customers would be "
                   f"redirected somewhere unreachable.",
        ))
        steps.append(
            "Set OMI_PUBLIC_BASE_URL to your WEB service URL (e.g. https://omisphere-web.onrender.com)."
        )
    else:
        checks.append(PreflightCheck(
            name="return_url", ok=True,
            detail=f"Customers return to {base}/settings after paying.",
        ))

    # --- 5. What they get ---------------------------------------------------------------------
    checks.append(PreflightCheck(
        name="credit_grant", ok=settings.monthly_credit_grant > 0,
        detail=f"{settings.monthly_credit_grant} credits granted per paid invoice.",
    ))

    # --- 6. Crediting mode (informational — the webhook is optional) --------------------------
    checks.append(PreflightCheck(
        name="crediting", ok=True,
        detail=(
            "Instant: the optional webhook is configured."
            if settings.stripe_webhook_secret else
            "API reconciliation (no webhook) — credits land on return from checkout, on the billing "
            "page, and before any scan would be refused."
        ),
    ))

    blocking = [c for c in checks if not c.ok and c.name in
                ("secret_key", "stripe_reachable", "price", "return_url", "credit_grant")]
    return PreflightResponse(ready=not blocking, checks=checks, next_steps=steps)


@router.post("/create-checkout-session", response_model=CheckoutResponse)
def create_checkout_session(
    current: CurrentUser = Depends(require_user),
    settings: Settings = Depends(get_settings),
) -> CheckoutResponse:
    """Create a Stripe Checkout session for the monthly subscription.

    Returns the hosted-checkout URL for the browser to follow. Stripe collects the card; no card
    detail ever reaches this server.
    """
    stripe = _stripe(settings)

    with get_session() as session:
        user = session.get(User, current.id)
        if user is None:
            raise HTTPException(status_code=401, detail="Session invalid.")
        customer_id = user.stripe_customer_id
        if not customer_id:
            # Never seed Stripe with the synthetic placeholder address a Clerk account carries before
            # its real email resolves — Stripe would store a junk email and mail receipts nowhere.
            # Omit it; Checkout collects a real email at payment time.
            from app.core.auth import _is_placeholder_email
            customer_email = None if _is_placeholder_email(user.email) else user.email
            try:
                customer = stripe.Customer.create(
                    email=customer_email,
                    metadata={"omi_user_id": str(user.id)},
                    # A double-clicked Subscribe button must not create two Stripe customers for one
                    # user — the second call replays the first customer instead.
                    idempotency_key=f"omi-customer-{user.id}",
                )
            except Exception as e:  # noqa: BLE001 — surface a clean error, never a 500 traceback
                log.exception("stripe customer create failed for user=%s", user.id)
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail="Could not reach Stripe to start checkout. Please try again.",
                ) from e
            customer_id = customer.id
            user.stripe_customer_id = customer_id

    try:
        s = stripe.checkout.Session.create(
            mode="subscription",
            customer=customer_id,
            line_items=[{"price": settings.stripe_price_id, "quantity": 1}],
            success_url=f"{settings.public_base_url}/settings?billing=success",
            cancel_url=f"{settings.public_base_url}/settings?billing=cancel",
            allow_promotion_codes=True,
            # Carried through to the subscription + invoices, so the webhook can resolve the user
            # even if the customer link is somehow missing.
            metadata={"omi_user_id": str(current.id)},
            subscription_data={"metadata": {"omi_user_id": str(current.id)}},
        )
    except Exception as e:  # noqa: BLE001
        log.exception("stripe checkout session create failed for user=%s", current.id)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Could not start Stripe checkout. Please try again.",
        ) from e
    return CheckoutResponse(url=s.url)


@router.post("/portal", response_model=CheckoutResponse)
def customer_portal(
    current: CurrentUser = Depends(require_user),
    settings: Settings = Depends(get_settings),
) -> CheckoutResponse:
    """Open the Stripe-hosted Customer Portal so the user can update their card, see invoices, or
    cancel. Cancelling is deliberately Stripe's screen, not ours — it is the flow customers trust."""
    stripe = _stripe(settings)
    with get_session() as session:
        user = session.get(User, current.id)
        if user is None or not user.stripe_customer_id:
            raise HTTPException(
                status_code=400,
                detail="No subscription found. Subscribe first.",
            )
        customer_id = user.stripe_customer_id
    try:
        portal = stripe.billing_portal.Session.create(
            customer=customer_id,
            return_url=f"{settings.public_base_url}/settings",
        )
    except Exception as e:  # noqa: BLE001
        log.exception("stripe portal session failed for user=%s", current.id)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=(
                "Could not open the billing portal. If this persists, the Customer Portal may not "
                "be enabled in the Stripe dashboard."
            ),
        ) from e
    return CheckoutResponse(url=portal.url)


# --------------------------------------------------------------------------- #
# Webhook
# --------------------------------------------------------------------------- #
@router.post("/webhook")
async def stripe_webhook(
    request: Request,
    settings: Settings = Depends(get_settings),
) -> Response:
    """Stripe calls this after billing events. Signature-verified, exactly-once, atomic."""
    if not settings.stripe_secret_key or not settings.stripe_webhook_secret:
        # Silent 200: keeps Stripe from retrying for three days when billing isn't set up here.
        return Response(status_code=200)

    try:
        import stripe  # type: ignore
    except ImportError:
        return Response(status_code=200)

    stripe.api_key = settings.stripe_secret_key
    payload = await request.body()
    sig = request.headers.get("stripe-signature", "")
    try:
        stripe.Webhook.construct_event(payload, sig, settings.stripe_webhook_secret)
    except ValueError as e:                       # malformed body
        raise HTTPException(status_code=400, detail="Invalid webhook payload.") from e
    except stripe.SignatureVerificationError as e:  # forged or wrong secret
        # The ONLY thing standing between this endpoint and anyone granting themselves credits.
        log.warning("rejected a Stripe webhook with a bad signature")
        raise HTTPException(status_code=400, detail="Invalid webhook signature.") from e

    # The SDK is used to VERIFY only; everything downstream reads the plain parsed JSON. The objects
    # construct_event returns are StripeObjects, which in stripe>=8 are not dict subclasses and are
    # NOT json-serializable — persisting one into the payload_json column raises TypeError and 500s
    # the webhook, which would fail every real payment while passing any test that hand-builds dicts.
    # Re-parsing the bytes we already verified keeps this immune to SDK object changes.
    event = json.loads(payload)
    etype = event.get("type") or ""
    obj = (event.get("data") or {}).get("object") or {}
    event_id = event.get("id")
    if not event_id:
        raise HTTPException(status_code=400, detail="Webhook event has no id.")

    # Claim the event and do its work in ONE transaction. If the handler raises, the claim rolls
    # back with it and Stripe's retry gets a real second attempt — instead of being waved through as
    # a duplicate while the customer's credits were never granted.
    try:
        with get_session() as session:
            session.add(BillingEvent(
                stripe_event_id=event_id,
                event_type=etype,
                payload_json=obj,
            ))
            session.flush()          # unique violation here == already processed
            _dispatch(session, etype, obj, settings)
    except IntegrityError:
        log.info("stripe event %s already processed; ignoring redelivery", event_id)
        return Response(status_code=200)
    except Exception:  # noqa: BLE001
        # 500 tells Stripe to retry. Nothing was committed, so the retry is clean.
        log.exception("stripe webhook handler failed for event=%s type=%s", event_id, etype)
        raise HTTPException(
            status_code=500, detail="Webhook handler failed; please retry.",
        )

    return Response(status_code=200)


def _dispatch(session: Session, etype: str, obj: dict, settings: Settings) -> None:
    if etype == "invoice.paid":
        _handle_invoice_paid(session, obj, settings)
    elif etype in ("customer.subscription.created", "customer.subscription.updated"):
        _handle_subscription_update(session, obj)
    elif etype == "customer.subscription.deleted":
        _handle_subscription_deleted(session, obj)
    elif etype == "invoice.payment_failed":
        _handle_payment_failed(session, obj)
    elif etype == "checkout.session.completed":
        _handle_checkout_completed(session, obj)
    # Anything else is recorded and acknowledged without action.


def _resolve_user(session: Session, obj: dict) -> User | None:
    """Find the OmiSphere user an event belongs to.

    Primary link is the Stripe customer id we stored at checkout. ``omi_user_id`` metadata is the
    fallback for the case that link is missing — a customer created outside our checkout, or a row
    lost to a restore. Without a fallback those payments would silently credit nobody.
    """
    cust = obj.get("customer")
    if cust:
        user = session.query(User).filter(User.stripe_customer_id == cust).first()
        if user is not None:
            return user

    meta = obj.get("metadata") or {}
    raw_id = meta.get("omi_user_id")
    if raw_id:
        try:
            user = session.get(User, int(raw_id))
        except (TypeError, ValueError):
            user = None
        if user is not None:
            # Repair the link so later events resolve on the fast path.
            if cust and not user.stripe_customer_id:
                user.stripe_customer_id = cust
            return user

    log.error(
        "stripe event could not be matched to a user (customer=%s, metadata omi_user_id=%s) — "
        "credits were NOT granted; link the customer manually",
        cust, raw_id,
    )
    return None


def _grant_credits_once(session: Session, user: User, *, key: str, amount: int, reason: str) -> bool:
    """Add ``amount`` credits to ``user``, at most once for ``key``. Returns whether it granted.

    The uniquely-indexed ``stripe_event_id`` column is the lock: the grant marker is inserted inside
    a SAVEPOINT, so a concurrent or repeat delivery hits the unique violation, rolls back just the
    marker, and leaves the surrounding transaction intact. This is what makes double-crediting
    impossible rather than merely unlikely — application-level "have we seen this?" checks lose that
    race under Stripe's parallel retries.
    """
    if amount <= 0:
        return False
    try:
        with session.begin_nested():
            session.add(BillingEvent(
                stripe_event_id=f"grant:{key}",
                event_type=f"credit_grant:{reason}",
                user_id=user.id,
                payload_json={"amount": amount, "reason": reason, "key": key},
            ))
    except IntegrityError:
        log.info("credits already granted for %s; not granting again", key)
        return False

    before = user.credits_remaining
    # ADD. Never "top up to N": a subscriber who renews with credits still banked has paid for this
    # period's credits and must receive them on top, not have their balance flattened to N.
    user.credits_remaining = before + amount
    log.info(
        "granted %d credits to user=%s for %s (%d -> %d)",
        amount, user.id, key, before, user.credits_remaining,
    )
    return True


def _handle_invoice_paid(session: Session, obj: dict, settings: Settings) -> None:
    """Money moved — this is the ONLY place credits are granted."""
    if obj.get("billing_reason") not in GRANTING_BILLING_REASONS:
        return
    # A zero-value invoice (a full discount, or a proration credit) is not a purchase of credits.
    if (obj.get("amount_paid") or 0) <= 0:
        log.info("invoice %s paid 0; no credits granted", obj.get("id"))
        return

    user = _resolve_user(session, obj)
    if user is None:
        return

    invoice_id = obj.get("id")
    if not invoice_id:
        log.error("invoice.paid with no invoice id; refusing to grant un-keyable credits")
        return

    _grant_credits_once(
        session, user, key=str(invoice_id),
        amount=settings.monthly_credit_grant, reason="invoice_paid",
    )

    if user.subscription_status not in PAID_STATUSES:
        user.subscription_status = "active"
    if obj.get("billing_reason") == "subscription_create":
        # Also the "they actually paid" moment for the referrer's bonus, in case the subscription
        # event arrives out of order. The helper is itself idempotent.
        grant_subscription_bonus_if_due(session, user)


def _period_end(obj: dict) -> datetime | None:
    """Renewal timestamp for a subscription object.

    Recent Stripe API versions moved ``current_period_end`` off the subscription and onto its items,
    so reading only the top level silently yields None and the UI shows no renewal date.
    """
    raw = obj.get("current_period_end")
    if raw is None:
        items = ((obj.get("items") or {}).get("data") or [])
        if items and isinstance(items[0], dict):
            raw = items[0].get("current_period_end")
    if isinstance(raw, (int, float)):
        return datetime.fromtimestamp(raw, tz=timezone.utc)
    return None


def _handle_subscription_update(session: Session, obj: dict) -> None:
    """Status + renewal date only. Credits follow the invoice, not the subscription."""
    user = _resolve_user(session, obj)
    if user is None:
        return
    user.stripe_subscription_id = obj.get("id")
    user.subscription_status = obj.get("status")
    renews_at = _period_end(obj)
    if renews_at is not None:
        user.subscription_renews_at = renews_at
    if obj.get("status") in PAID_STATUSES:
        grant_subscription_bonus_if_due(session, user)


def _handle_subscription_deleted(session: Session, obj: dict) -> None:
    """Cancelled. Credits already bought are the user's — they keep them."""
    user = _resolve_user(session, obj)
    if user is None:
        return
    user.subscription_status = "canceled"
    user.subscription_renews_at = None


def _handle_payment_failed(session: Session, obj: dict) -> None:
    """A renewal charge failed. Reflect it so the UI can prompt for a new card; Stripe keeps
    retrying on its own dunning schedule, and a later invoice.paid restores 'active'."""
    user = _resolve_user(session, obj)
    if user is None:
        return
    # Record it whatever we currently think the status is — an invoice only fails for a real
    # subscription, so if our local status disagrees it is our copy that is stale. The one state not
    # to overwrite is 'canceled': a late failure for a subscription the user already ended must not
    # resurrect it as merely past due.
    if user.subscription_status != "canceled":
        user.subscription_status = "past_due"


def _handle_checkout_completed(session: Session, obj: dict) -> None:
    """Safety net: bind the Stripe customer to the user as soon as checkout completes, so every
    later invoice resolves even if the customer was created outside ``create_checkout_session``.
    Grants nothing — the invoice does that."""
    user = _resolve_user(session, obj)
    if user is None:
        return
    cust = obj.get("customer")
    if cust and not user.stripe_customer_id:
        user.stripe_customer_id = cust
