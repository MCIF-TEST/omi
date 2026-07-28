"""Stripe billing: subscription checkout, credited by webhook with an API backstop.

CREDITS ARRIVE BY TWO ROUTES AND THAT IS DELIBERATE
The webhook (``POST /v1/billing/webhook``) is the PRIMARY path: Stripe pushes
``invoice.paid`` and credits land in seconds. It is inert until
``OMI_STRIPE_WEBHOOK_SECRET`` is set, because an unverified webhook is an open
door to anyone who wants to grant themselves credits.

API reconciliation (``app/core/billing_sync.py``) is the BACKSTOP, and removing
it would be a mistake even with webhooks working. A webhook can be missed: the
endpoint can be registered against the wrong host, the secret can be rotated out
of sync, Stripe can exhaust its retries during an outage. Reconciliation asks
Stripe what was actually paid, and it runs at the three moments that matter — on
return from checkout, on the billing page, and inside ``consume_credits`` just
before a scan would be refused. That last one is why a subscriber whose renewal
just landed is never told to subscribe.

Running both is safe for exactly one reason: **both claim the same per-invoice
row** (see ``_grant_credits_once``). Whichever arrives first grants; the other
loses the unique-index race and does nothing. Neither path trusts the other to
have run.

The product is created **once** in the Stripe dashboard:

    Product: "OmiSphere Monthly"
    Price:   $14.99 USD / month, recurring  ->  copy the price_… id into OMI_STRIPE_PRICE_ID

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
import time
from datetime import datetime, timedelta, timezone

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

# The events to tick when registering the endpoint in the Stripe dashboard.
#
# This is the ONE list: /preflight prints it for the operator and
# test_webhook_events_match_the_dispatch_table asserts it equals what `_dispatch` actually handles.
# Selecting fewer in Stripe silently drops that behaviour; selecting more just costs a stored row,
# since anything unrecognised is recorded and acknowledged without action.
#
# `invoice.paid` is the only one that moves credits — everything else moves status, renewal date, or
# the customer link. Do not add a second granting event: a new subscription emits BOTH
# `customer.subscription.created` and `invoice.paid`, and crediting on both bills once but grants
# twice.
WEBHOOK_EVENTS = (
    "invoice.paid",
    "invoice.payment_failed",
    "customer.subscription.created",
    "customer.subscription.updated",
    "customer.subscription.deleted",
    "checkout.session.completed",
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


def _payment_method_types(settings: Settings) -> list[str]:
    """Checkout payment methods for this deployment.

    Default is link + card:
      * **Link** — works when Cards are still pending Stripe approval.
      * **card** — required for Apple Pay / Google Pay on Checkout (wallets ride on the card type).

    Override with env ``OMI_STRIPE_PAYMENT_METHOD_TYPES`` (comma-separated), e.g. ``link`` only
    if card is fully blocked, or ``card,link`` to prefer card wallets first.
    """
    raw = (getattr(settings, "stripe_payment_method_types", None) or "link,card").strip()
    types = [t.strip().lower() for t in raw.split(",") if t.strip()]
    # De-dupe, preserve order
    seen: set[str] = set()
    out: list[str] = []
    for t in types:
        if t not in seen:
            seen.add(t)
            out.append(t)
    return out or ["link", "card"]


def _billing_is_configured(settings: Settings) -> bool:

    """True only when Subscribe can actually open a Checkout session.

    Requires a secret key, a real ``price_…`` id (not a dollar amount), and a non-empty
    public base URL. In production, localhost is treated as misconfigured so the UI
    does not offer a button that redirects paying customers into nowhere.
    """
    if not (settings.stripe_secret_key or "").strip():
        return False
    price = (settings.stripe_price_id or "").strip()
    if not price.startswith("price_"):
        return False
    base = (settings.public_base_url or "").strip()
    if not base:
        return False
    if settings.env == "production" and (
        "localhost" in base or "127.0.0.1" in base
    ):
        return False
    return True


def _require_price_id(settings: Settings) -> str:
    """Stripe Price ids look like ``price_1ABC…``. Dollar amounts are not valid."""
    raw = (settings.stripe_price_id or "").strip()
    if not raw:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "OMI_STRIPE_PRICE_ID is not set. In Stripe Dashboard → Product catalogue, open "
                "your monthly recurring price and copy the id that starts with price_ (not the "
                "dollar amount)."
            ),
        )
    if not raw.startswith("price_"):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                f"OMI_STRIPE_PRICE_ID is set to {raw!r}, which is not a Stripe Price id. "
                "It must look like price_1ABC… (Dashboard → Product catalogue → your product → "
                "the recurring monthly price → copy Price ID). Do not put 14.99 or $14.99 here, "
                "the amount lives on the Price object in Stripe."
            ),
        )
    return raw


def _public_base(settings: Settings) -> str:
    """Normalize OMI_PUBLIC_BASE_URL so success/cancel URLs never double-slash."""
    base = (settings.public_base_url or "").strip().rstrip("/")
    if not base:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "OMI_PUBLIC_BASE_URL is not set. Set it to your web app URL "
                "(e.g. https://omisphere-web.onrender.com) so Stripe can return "
                "customers after checkout."
            ),
        )
    if settings.env == "production" and ("localhost" in base or "127.0.0.1" in base):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                f"OMI_PUBLIC_BASE_URL is {base!r} — that is not reachable by paying customers. "
                "Set it to your public web URL (https://…), not localhost."
            ),
        )
    return base


def _stripe_user_message(exc: BaseException) -> str:
    """Safe, short message from a Stripe SDK error for the browser.

    The real reasons checkout fails (wrong-mode price, deleted customer, one-off
    price used as subscription, automatic-tax needs address, bad key) live on the
    Stripe exception. Surfacing them is the difference between a dead-end
    "please try again" and a fixable config error.
    """
    user_msg = getattr(exc, "user_message", None) or getattr(exc, "_message", None)
    if isinstance(user_msg, str) and user_msg.strip():
        msg = user_msg.strip()
    else:
        msg = str(exc).strip() or type(exc).__name__
    if len(msg) > 280:
        msg = msg[:277] + "..."
    code = getattr(exc, "code", None)
    if code and str(code) not in msg:
        return f"{msg} (Stripe code: {code})"
    return msg


def _ensure_stripe_customer(stripe, user: User, *, recreate: bool = False) -> str:
    """Return a live Stripe customer id for this user, creating one if needed.

    Handles three failure modes that otherwise 502 the Subscribe button:
      1. No customer linked yet → create one.
      2. Linked customer was deleted / wrong Stripe mode → clear + recreate.
      3. Passing email=None into Customer.create — some SDK paths serialize that
         as JSON null and Stripe rejects it. Only send email when real.
    """
    from app.core.auth import _is_placeholder_email

    if not recreate and user.stripe_customer_id:
        try:
            stripe.Customer.retrieve(user.stripe_customer_id)
            return user.stripe_customer_id
        except Exception as e:  # noqa: BLE001
            log.warning(
                "stale stripe customer %s for user=%s (%s); recreating",
                user.stripe_customer_id,
                user.id,
                type(e).__name__,
            )
            user.stripe_customer_id = None
            recreate = True

    params: dict = {
        "metadata": {"omi_user_id": str(user.id)},
        # First create is stable; after a wipe, salt so we don't replay a deleted id
        # via Stripe's idempotency cache.
        "idempotency_key": (
            f"omi-customer-{user.id}-recreate" if recreate else f"omi-customer-{user.id}"
        ),
    }
    email = None if _is_placeholder_email(user.email) else (user.email or None)
    if email:
        params["email"] = email

    try:
        customer = stripe.Customer.create(**params)
    except Exception as e:  # noqa: BLE001
        log.exception("stripe customer create failed for user=%s", user.id)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Could not create Stripe customer: {_stripe_user_message(e)}",
        ) from e
    user.stripe_customer_id = customer.id
    return customer.id



def _claim_checkout_session(stripe, user: User, checkout_session_id: str) -> None:
    """Bind a completed Checkout Session to this user (pure-API purchase handshake).

    Stripe's success URL can include ``{CHECKOUT_SESSION_ID}``. Retrieving that session
    lets us link the customer *before* invoice list reconciliation, which is more reliable
    than waiting for the invoice list alone on a slow network.
    """
    try:
        cs = stripe.checkout.Session.retrieve(checkout_session_id)
    except Exception as e:  # noqa: BLE001
        log.warning(
            "checkout session retrieve failed id=%s user=%s: %s",
            checkout_session_id, user.id, type(e).__name__,
        )
        return

    # Ownership: client_reference_id and metadata are set at session create.
    ref = getattr(cs, "client_reference_id", None) or (
        cs.get("client_reference_id") if isinstance(cs, dict) else None
    )
    meta = getattr(cs, "metadata", None) or (
        cs.get("metadata") if isinstance(cs, dict) else None
    ) or {}
    if hasattr(meta, "to_dict"):
        try:
            meta = meta.to_dict()
        except Exception:  # noqa: BLE001
            meta = dict(meta) if meta else {}
    omi_uid = None
    if isinstance(meta, dict):
        omi_uid = meta.get("omi_user_id")
    for candidate in (ref, omi_uid):
        if candidate is not None and str(candidate) != str(user.id):
            log.warning(
                "checkout session %s ownership mismatch for user=%s (got %s)",
                checkout_session_id, user.id, candidate,
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="That checkout session does not belong to this account.",
            )

    cust = getattr(cs, "customer", None) or (
        cs.get("customer") if isinstance(cs, dict) else None
    )
    if isinstance(cust, dict):
        cust = cust.get("id")
    if cust and user.stripe_customer_id != cust:
        user.stripe_customer_id = str(cust)
        log.info("linked stripe customer %s to user=%s via checkout session", cust, user.id)


def _customer_has_live_subscription(stripe, customer_id: str) -> bool:
    """True if Stripe already shows an active/trialing subscription for this customer."""
    try:
        for status_name in ("active", "trialing"):
            found = stripe.Subscription.list(
                customer=customer_id, status=status_name, limit=1,
            )
            data = getattr(found, "data", None) or []
            if data:
                return True
    except Exception:  # noqa: BLE001
        log.exception("subscription list failed for customer=%s", customer_id)
    return False


class CheckoutResponse(BaseModel):
    url: str


class BillingStatusResponse(BaseModel):
    """What the UI needs to render the billing panel without guessing."""

    configured: bool                 # the server can actually take a payment
    credits_remaining: int
    subscription_status: str | None
    subscription_renews_at: datetime | None
    price_display: str               # e.g. "$14.99"
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
            configured=_billing_is_configured(settings),
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
    session_id: str | None = None,
) -> SyncResponse:
    """Reconcile this user against Stripe RIGHT NOW, ignoring the throttle.

    This is how a purchase completes without a webhook: the browser comes back from Stripe Checkout,
    calls this, and the server asks Stripe what was actually paid. Idempotent — call it as often as
    you like; credits are keyed per invoice and granted once.

    Optional ``session_id`` (from Checkout success URL ``{CHECKOUT_SESSION_ID}``) links the Stripe
    customer immediately, which is more reliable right after payment than invoice-list lag alone.
    """
    with get_session() as session:
        user = session.get(User, current.id)
        if user is None:
            raise HTTPException(status_code=401, detail="Session invalid.")
        if session_id and settings.stripe_secret_key:
            try:
                stripe = _stripe(settings)
                _claim_checkout_session(stripe, user, session_id.strip())
            except HTTPException:
                raise
            except Exception:  # noqa: BLE001
                log.exception("optional checkout session claim failed for user=%s", current.id)
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
    # Everything needed to register the endpoint in the Stripe dashboard, so the operator does not
    # have to reconstruct it by hand (getting the host wrong is the usual failure).
    webhook_url: str | None = None
    webhook_events: list[str] = []


def _request_origin(request: Request) -> str:
    """Best-effort public origin of THIS service, from the request that reached it.

    Render terminates TLS at its proxy, so the ASGI scheme can read `http` while the world sees
    `https`; X-Forwarded-Proto is the truth. Returns "" when the host cannot be determined rather
    than guessing, so callers can say "unknown" instead of printing a wrong URL confidently.
    """
    host = (
        request.headers.get("x-forwarded-host")
        or request.headers.get("host")
        or (request.url.hostname or "")
    ).split(",")[0].strip()
    if not host:
        return ""
    proto = (
        request.headers.get("x-forwarded-proto") or request.url.scheme or "https"
    ).split(",")[0].strip()
    return f"{proto}://{host}"


def _webhook_delivery(session: Session) -> tuple[datetime | None, str | None, int]:
    """(when the last real Stripe event landed, its type, how many landed in the last 24h).

    Grant markers share this table but are not deliveries — they are written by whichever path
    granted, including reconciliation — so they are excluded by their `credit_grant:` type prefix.
    Counting them would report a healthy webhook on a deployment that has never received one.
    """
    real = ~BillingEvent.event_type.like("credit_grant:%")
    row = (
        session.query(BillingEvent)
        .filter(real)
        .order_by(BillingEvent.created_at.desc())
        .first()
    )
    since = datetime.now(timezone.utc) - timedelta(hours=24)
    recent = session.query(BillingEvent).filter(real, BillingEvent.created_at >= since).count()
    if row is None:
        return None, None, 0
    return row.created_at, row.event_type, recent


@router.get("/preflight", response_model=PreflightResponse)
def billing_preflight(
    request: Request,
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
            "Create the $14.99/month recurring price in Stripe and set OMI_STRIPE_PRICE_ID to its "
            "price_… id (not the dollar amount)."
        )
    elif not price_id.startswith("price_"):
        checks.append(PreflightCheck(
            name="price", ok=False,
            detail=(
                f"OMI_STRIPE_PRICE_ID is {price_id!r} — that is not a Stripe Price id. "
                "It must start with price_ (Dashboard → Product catalogue → recurring price → "
                "copy Price ID). Values like 14.99 or $14.99 will never work."
            ),
        ))
        steps.append(
            "Replace OMI_STRIPE_PRICE_ID with the Price ID that starts with price_ from Stripe."
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

    # --- 6. The webhook: the primary crediting path -------------------------------------------
    # Derived from the request rather than from config, because there is no env var holding the
    # API's own public URL and hand-typing it into Stripe is where this usually goes wrong.
    origin = _request_origin(request)
    webhook_url = f"{origin}/v1/billing/webhook" if origin else None

    # Preflight is commonly called through the web app's /api proxy, in which case the host we just
    # derived is the WEB host — registering that in Stripe points the webhook at a service that does
    # not implement it. Detect it instead of printing a confidently wrong URL.
    web_host = (settings.public_base_url or "").strip().rstrip("/").split("://")[-1]
    proxied = bool(origin and web_host and origin.split("://")[-1] == web_host)
    if proxied:
        checks.append(PreflightCheck(
            name="webhook_url", ok=False,
            detail=(
                f"Cannot determine the API's public URL: this request arrived via {origin}, which is "
                f"OMI_PUBLIC_BASE_URL (the WEB host). Call /v1/billing/preflight directly on the API "
                f"host to get the URL to register."
            ),
        ))
        steps.append(
            "Open https://<your-api-host>/v1/billing/preflight directly (not through the web app) "
            "to read the exact webhook URL."
        )
        webhook_url = None
    elif webhook_url:
        checks.append(PreflightCheck(
            name="webhook_url", ok=True,
            detail=f"Register this endpoint in Stripe: {webhook_url}",
        ))

    if not settings.stripe_webhook_secret:
        checks.append(PreflightCheck(
            name="webhook_secret", ok=False,
            detail=(
                "OMI_STRIPE_WEBHOOK_SECRET is not set, so the webhook route is inert and returns 200 "
                "without crediting. Credits currently arrive only by API reconciliation, which is "
                "slower but correct."
            ),
        ))
        steps.append(
            "Stripe Dashboard → Developers → Webhooks → Add endpoint, then set the signing secret "
            "(whsec_…) as OMI_STRIPE_WEBHOOK_SECRET on the API service and redeploy."
        )
    else:
        secret = settings.stripe_webhook_secret.strip()
        looks_right = secret.startswith("whsec_")
        checks.append(PreflightCheck(
            name="webhook_secret", ok=looks_right,
            detail=(
                "Set — signatures are verified and the webhook credits on invoice.paid."
                if looks_right else
                "Set, but it does not start with 'whsec_'. A signing secret is not the API key and "
                "not the endpoint id; every delivery will fail signature verification."
            ),
        ))
        if not looks_right:
            steps.append(
                "Copy the SIGNING SECRET (whsec_…) from the endpoint's page in Stripe, not the key."
            )

    # Has Stripe ever actually reached us? Configuration can be perfect and delivery still fail —
    # wrong host, a firewall, an endpoint registered in the other Stripe mode.
    try:
        with get_session() as s:
            last_at, last_type, recent = _webhook_delivery(s)
    except Exception:  # noqa: BLE001 — a diagnostic must never be the thing that breaks
        last_at, last_type, recent = None, None, 0

    if last_at is None:
        checks.append(PreflightCheck(
            name="webhook_delivery",
            # Only a problem once the secret is set: with no secret, zero deliveries is expected.
            ok=not settings.stripe_webhook_secret,
            detail=(
                "No Stripe event has ever been received by this deployment."
                + ("" if not settings.stripe_webhook_secret else
                   " The secret is set, so either the endpoint is not registered, points at the "
                   "wrong host, or belongs to the other Stripe mode. Use 'Send test webhook' in the "
                   "dashboard to check.")
            ),
        ))
    else:
        checks.append(PreflightCheck(
            name="webhook_delivery", ok=True,
            detail=(
                f"Last event {last_type} at {last_at.isoformat()} · {recent} in the last 24h."
            ),
        ))

    # --- 7. Crediting mode --------------------------------------------------------------------
    checks.append(PreflightCheck(
        name="crediting", ok=True,
        detail=(
            "Webhook (instant) with API reconciliation as the backstop."
            if settings.stripe_webhook_secret else
            "API reconciliation only — credits land on return from checkout, on the billing page, "
            "and before any scan would be refused."
        ),
    ))

    # webhook_secret and webhook_delivery are deliberately NOT blocking: reconciliation still
    # credits every payment without them, so a deployment with no webhook can take money correctly.
    # They report degraded-but-working, which is exactly what it is.
    blocking = [c for c in checks if not c.ok and c.name in
                ("secret_key", "stripe_reachable", "price", "return_url", "credit_grant")]
    return PreflightResponse(
        ready=not blocking,
        checks=checks,
        next_steps=steps,
        webhook_url=webhook_url,
        webhook_events=list(WEBHOOK_EVENTS),
    )


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
    base = _public_base(settings)
    price_id = _require_price_id(settings)

    # Fail fast with a clear message when the configured price cannot back a subscription.
    # Without this, a one-off / archived / wrong-mode price only surfaces as a vague 502 at click.
    try:
        price = stripe.Price.retrieve(price_id)
        recurring = getattr(price, "recurring", None)
        if not recurring:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=(
                    f"OMI_STRIPE_PRICE_ID ({price_id}) is a one-off price, not a "
                    "recurring subscription price. Create a monthly recurring price in Stripe and "
                    "set OMI_STRIPE_PRICE_ID to its price_… id."
                ),
            )
        if not bool(getattr(price, "active", False)):
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=(
                    f"OMI_STRIPE_PRICE_ID ({price_id}) is archived in Stripe. "
                    "Activate it or point the env var at an active recurring price."
                ),
            )
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        log.exception("stripe price retrieve failed for price=%s", price_id)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=(
                f"Could not load OMI_STRIPE_PRICE_ID ({price_id}) from Stripe: {_stripe_user_message(e)}. "
                "Confirm it is a price_… id from the SAME mode (test/live) as OMI_STRIPE_SECRET_KEY."
            ),
        ) from e

    with get_session() as session:
        user = session.get(User, current.id)
        if user is None:
            raise HTTPException(status_code=401, detail="Session invalid.")
        # Already subscribed → Customer Portal, not a second Checkout (avoids Stripe
        # "customer already has a subscription" friction and matches the button label).
        if user.subscription_status in PAID_STATUSES and user.stripe_customer_id:
            try:
                portal = stripe.billing_portal.Session.create(
                    customer=user.stripe_customer_id,
                    return_url=f"{base}/settings",
                )
            except Exception as e:  # noqa: BLE001
                log.exception("stripe portal session failed for user=%s", user.id)
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail=(
                        f"Could not open the billing portal: {_stripe_user_message(e)}. "
                        "Enable the Customer Portal in Stripe Dashboard → Settings → Billing."
                    ),
                ) from e
            if not portal.url:
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail="Stripe returned no portal URL. Check Customer Portal is enabled.",
                )
            return CheckoutResponse(url=portal.url)

        customer_id = _ensure_stripe_customer(stripe, user)
        # If Stripe already has a live subscription (local status can lag), send them to the
        # portal instead of opening a second Checkout that fails or double-bills.
        if _customer_has_live_subscription(stripe, customer_id):
            try:
                portal = stripe.billing_portal.Session.create(
                    customer=customer_id,
                    return_url=f"{base}/settings",
                )
            except Exception as e:  # noqa: BLE001
                log.exception("portal after live-sub check failed for user=%s", user.id)
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail=(
                        f"You already have a subscription, but the billing portal could not open: "
                        f"{_stripe_user_message(e)}. Enable Customer Portal in the Stripe dashboard."
                    ),
                ) from e
            if not getattr(portal, "url", None):
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail="Stripe returned no portal URL. Enable the Customer Portal.",
                )
            # Mirror live status locally so the UI shows Manage next time.
            if user.subscription_status not in PAID_STATUSES:
                user.subscription_status = "active"
            return CheckoutResponse(url=portal.url)

    # Build Checkout outside the DB session so a Stripe lag doesn't hold a connection.
    # success_url includes {CHECKOUT_SESSION_ID} so pure-API sync can claim the session immediately.
    success = f"{base}/settings?billing=success&session_id={{CHECKOUT_SESSION_ID}}"
    cancel = f"{base}/settings?billing=cancel"
    # 30s idempotency window absorbs double-clicks without blocking a later re-subscribe.
    checkout_idem = f"omi-checkout-{current.id}-{price_id}-{int(time.time()) // 30}"
    try:
        s = stripe.checkout.Session.create(
            mode="subscription",
            customer=customer_id,
            line_items=[{"price": price_id, "quantity": 1}],
            success_url=success,
            cancel_url=cancel,
            # link + card by default (see _payment_method_types / OMI_STRIPE_PAYMENT_METHOD_TYPES).
            # Link works while Cards are pending approval; card enables Apple Pay / Google Pay wallets.
            payment_method_types=_payment_method_types(settings),
            allow_promotion_codes=True,
            # Lets Checkout collect name/address when the Customer row is sparse — required when
            # Automatic Tax (or similar dashboard defaults) needs an address, and harmless otherwise.
            billing_address_collection="auto",
            customer_update={"address": "auto", "name": "auto"},
            client_reference_id=str(current.id),
            # Carried through to the subscription + invoices, so sync can resolve the user
            # even if the customer link is somehow missing.
            metadata={"omi_user_id": str(current.id)},
            subscription_data={"metadata": {"omi_user_id": str(current.id)}},
            idempotency_key=checkout_idem,
        )
    except Exception as e:  # noqa: BLE001
        msg = _stripe_user_message(e)
        log.exception("stripe checkout session create failed for user=%s: %s", current.id, msg)
        # Stale customer that retrieve() somehow accepted but Session rejected — one automatic retry.
        if "No such customer" in msg or "resource_missing" in msg.lower():
            with get_session() as session:
                user = session.get(User, current.id)
                if user is None:
                    raise HTTPException(status_code=401, detail="Session invalid.") from e
                user.stripe_customer_id = None
                customer_id = _ensure_stripe_customer(stripe, user, recreate=True)
            try:
                s = stripe.checkout.Session.create(
                    mode="subscription",
                    customer=customer_id,
                    line_items=[{"price": price_id, "quantity": 1}],
                    success_url=success,
                    cancel_url=cancel,
                    payment_method_types=_payment_method_types(settings),
                    allow_promotion_codes=True,
                    billing_address_collection="auto",
                    customer_update={"address": "auto", "name": "auto"},
                    client_reference_id=str(current.id),
                    metadata={"omi_user_id": str(current.id)},
                    subscription_data={"metadata": {"omi_user_id": str(current.id)}},
                )
            except Exception as e2:  # noqa: BLE001
                log.exception("stripe checkout retry failed for user=%s", current.id)
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail=f"Could not start Stripe checkout: {_stripe_user_message(e2)}",
                ) from e2
        else:
            hint = msg
            if "payment method" in msg.lower():
                hint = (
                    f"{msg} In Live mode enable Link and/or Cards under Dashboard → Settings → "
                    "Payment methods. Apple Pay needs Cards + a verified domain "
                    "(Settings → Payment method domains). Or set OMI_STRIPE_PAYMENT_METHOD_TYPES=link "
                    "if only Link is approved."
                )
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Could not start Stripe checkout: {hint}",
            ) from e

    if not getattr(s, "url", None):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Stripe created a session but returned no checkout URL. Check the Stripe dashboard logs.",
        )
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
    base = _public_base(settings)
    try:
        portal = stripe.billing_portal.Session.create(
            customer=customer_id,
            return_url=f"{base}/settings",
        )
    except Exception as e:  # noqa: BLE001
        log.exception("stripe portal session failed for user=%s", current.id)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=(
                f"Could not open the billing portal: {_stripe_user_message(e)}. "
                "Enable the Customer Portal in Stripe Dashboard → Settings → Billing → Customer portal."
            ),
        ) from e
    if not getattr(portal, "url", None):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Stripe returned no portal URL. Enable the Customer Portal in the Stripe dashboard.",
        )
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
