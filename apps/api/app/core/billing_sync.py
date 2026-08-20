"""Reconcile a user's billing by ASKING STRIPE — the webhook-free path.

OmiSphere does not require a Stripe webhook. Instead of waiting to be told what happened, we read the
current truth from Stripe's API and make our records match: which subscription the customer has, what
state it is in, and which invoices they have actually paid. Every paid invoice we have not already
credited grants its credits, exactly once.

WHAT THIS BUYS, AND WHAT IT COSTS

* No webhook endpoint to register, no signing secret to rotate, nothing to break when a URL changes,
  and no public endpoint that grants credits. There is one less thing to get wrong.
* Stripe's API is the single source of truth, so a mistake here self-heals on the next sync. A missed
  webhook, by contrast, is lost for good unless someone replays it by hand.
* The cost is LATENCY, and only for renewals: credits appear the next time the user's account is
  reconciled rather than the instant Stripe charges the card. Reconciliation runs when they return
  from checkout (so a first purchase feels immediate), when they open billing, and — the one that
  actually matters — the moment a scan would otherwise be refused for lack of credits. A subscriber
  whose renewal just went through is therefore never turned away.

EXACTLY-ONCE IS UNCHANGED

Grants are keyed on the Stripe INVOICE id and claimed through a unique index, so syncing ten times a
minute grants nothing extra, and this remains true if the optional webhook is also enabled — both
paths compete for the same row and only one can win.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone

from app.core.config import Settings, get_settings
from app.storage.models import User

log = logging.getLogger("omi.billing.sync")

# How many of the customer's most recent invoices to examine. A monthly plan produces one per month,
# so this covers a long absence while staying a single cheap API call.
INVOICE_LOOKBACK = 12

# Per-user floor between automatic syncs. Explicit syncs (returning from checkout, a manual refresh,
# or a scan about to be refused) ignore it — those are the moments a stale answer is unacceptable.
AUTO_SYNC_MIN_INTERVAL_SECONDS = 300.0

# user_id -> monotonic timestamp of the last completed sync. Process-local on purpose: it is a
# rate-limit hint, not a correctness mechanism. A second instance simply syncs a little more often,
# which is harmless because the work is idempotent.
_last_sync: dict[int, float] = {}


def _stripe_or_none(settings: Settings):
    """The configured Stripe SDK, or None when billing isn't set up. Never raises — a deployment
    without Stripe must behave exactly like one with an unpaid user, not error."""
    if not settings.stripe_secret_key:
        return None
    try:
        import stripe  # type: ignore
    except ImportError:
        log.warning("stripe SDK not installed; billing reconciliation disabled")
        return None
    stripe.api_key = settings.stripe_secret_key
    return stripe


def _ts(value) -> datetime | None:
    return datetime.fromtimestamp(value, tz=timezone.utc) if isinstance(value, (int, float)) else None


def _period_end(sub: dict) -> datetime | None:
    """Renewal time for a subscription. Recent Stripe API versions moved ``current_period_end`` off
    the subscription and onto its items, so reading only the top level silently yields nothing."""
    raw = sub.get("current_period_end")
    if raw is None:
        items = ((sub.get("items") or {}).get("data") or [])
        if items and isinstance(items[0], dict):
            raw = items[0].get("current_period_end")
    return _ts(raw)


def _plain(obj) -> dict:
    """Stripe SDK object -> plain dict.

    In stripe>=8 a ``StripeObject`` is not a dict subclass and is not JSON-serializable, so anything
    that reaches the database or ``json.dumps`` must be converted first.
    """
    if isinstance(obj, dict):
        return dict(obj)
    for attr in ("to_dict_recursive", "_to_dict_recursive", "to_dict"):
        fn = getattr(type(obj), attr, None)
        if callable(fn):
            try:
                return dict(fn(obj))
            except Exception:  # noqa: BLE001
                pass
    return {k: getattr(obj, k) for k in dir(obj) if not k.startswith("_")}


def find_customer_id(stripe, user: User) -> str | None:
    """The Stripe customer for this user: the stored link, or a lookup by email.

    The email fallback exists so a payment made outside our own checkout — a Payment Link, or a
    customer created by hand in the dashboard — still finds its way to the right account instead of
    crediting nobody. Only an exact match on the address the user signed up with is accepted.
    """
    if user.stripe_customer_id:
        return user.stripe_customer_id
    from app.core.auth import _is_placeholder_email
    if not user.email or _is_placeholder_email(user.email):
        return None
    try:
        found = stripe.Customer.list(email=user.email, limit=1)
    except Exception:  # noqa: BLE001
        log.exception("stripe customer lookup by email failed for user=%s", user.id)
        return None
    data = getattr(found, "data", None) or []
    return data[0].id if data else None


def reconcile_billing(
    session,
    user: User,
    *,
    settings: Settings | None = None,
    force: bool = False,
    reason: str = "auto",
) -> dict:
    """Make this user's billing record match Stripe. Returns a small summary for logging/tests.

    Safe to call often: it is throttled unless ``force``, it never raises (a Stripe outage must not
    break a scan or a page load), and granting is idempotent per invoice.
    """
    settings = settings or get_settings()
    summary = {"synced": False, "granted": 0, "credits_added": 0, "status": user.subscription_status}

    stripe = _stripe_or_none(settings)
    if stripe is None:
        return summary

    now = time.monotonic()
    if not force:
        last = _last_sync.get(user.id)
        if last is not None and (now - last) < AUTO_SYNC_MIN_INTERVAL_SECONDS:
            return summary

    try:
        customer_id = find_customer_id(stripe, user)
        if customer_id is None:
            _last_sync[user.id] = now
            return summary
        if user.stripe_customer_id != customer_id:
            user.stripe_customer_id = customer_id     # repair/establish the link

        _sync_subscription(stripe, session, user)
        granted, added = _grant_unclaimed_invoices(stripe, session, user, settings)

        _last_sync[user.id] = now
        summary.update(
            synced=True, granted=granted, credits_added=added,
            status=user.subscription_status,
        )
        if granted:
            log.info(
                "billing sync (%s) granted %d credits to user=%s across %d invoice(s)",
                reason, added, user.id, granted,
            )
    except Exception:  # noqa: BLE001 — reconciliation is best-effort by contract
        log.exception("billing reconciliation failed for user=%s (reason=%s)", user.id, reason)

    return summary


def _sync_subscription(stripe, session, user: User) -> None:
    """Mirror the customer's most relevant subscription onto the user row."""
    subs = stripe.Subscription.list(customer=user.stripe_customer_id, status="all", limit=10)
    best = None
    for raw in (getattr(subs, "data", None) or []):
        sub = _plain(raw)
        # Prefer a live subscription; otherwise keep the most recent one so a cancelled account still
        # reports the right state.
        if sub.get("status") in ("active", "trialing", "past_due"):
            best = sub
            break
        if best is None or (sub.get("created") or 0) > (best.get("created") or 0):
            best = sub

    if best is None:
        # No subscription at all in Stripe. Don't invent one; only clear a stale 'active'.
        if user.subscription_status in ("active", "trialing", "past_due"):
            user.subscription_status = "canceled"
            user.subscription_renews_at = None
        return

    user.stripe_subscription_id = best.get("id")
    user.subscription_status = best.get("status")
    user.subscription_renews_at = _period_end(best)


def _grant_unclaimed_invoices(stripe, session, user: User, settings: Settings) -> tuple[int, int]:
    """Grant credits for every PAID invoice we have not already credited. Returns (invoices, credits)."""
    from app.routes.billing import (
        GRANTING_BILLING_REASONS,
        _grant_credits_once,
        resolve_invoice_purchase,
    )

    invoices = stripe.Invoice.list(
        customer=user.stripe_customer_id, status="paid", limit=INVOICE_LOOKBACK,
    )
    granted = 0
    added = 0
    # Whether a SUBSCRIPTION invoice was seen. Deliberately not `granted`: a top-up grants credits
    # without being a subscription, and flipping status to active off a credit pack would tell a
    # lapsed customer they have a live plan.
    subscribed = False
    # Oldest first, so a long gap replays in the order the customer actually paid.
    for raw in reversed(getattr(invoices, "data", None) or []):
        inv = _plain(raw)
        if inv.get("billing_reason") not in GRANTING_BILLING_REASONS:
            continue
        if (inv.get("amount_paid") or 0) <= 0:
            continue                                   # fully discounted / proration-only
        invoice_id = inv.get("id")
        if not invoice_id:
            continue
        # WHAT the invoice bought is resolved by the same function the webhook uses. The two paths
        # race for the same grant row on purpose, and if they read one invoice differently then
        # whichever arrived first would silently decide the customer's plan.
        purchase = resolve_invoice_purchase(inv, settings)
        if purchase is None:
            log.error(
                "invoice %s is paid but matches no configured Stripe Price; granting nothing",
                invoice_id,
            )
            continue

        kind, tier = purchase
        amount = settings.topup_pack_credits if kind == "topup" else tier.monthly_credits
        if _grant_credits_once(
            session, user, key=str(invoice_id),
            amount=amount, reason=f"api_sync:{kind if kind == 'topup' else tier.slug}",
        ):
            granted += 1
            added += amount

        # A top-up is not a subscription and must not imply one. Only a tier invoice sets the plan.
        if kind == "tier" and user.plan_tier != tier.slug:
            log.info("user=%s plan %s -> %s (sync, invoice %s)",
                     user.id, user.plan_tier, tier.slug, invoice_id)
            user.plan_tier = tier.slug
            subscribed = True

    if subscribed and user.subscription_status not in ("active", "trialing"):
        user.subscription_status = "active"
    return granted, added


def reset_sync_throttle_for_tests() -> None:
    _last_sync.clear()
