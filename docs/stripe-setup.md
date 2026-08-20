# Stripe setup: three plans plus credit packs (webhook + API backstop)

Everything you need to take the first real payment. Do it once in **test mode**, verify with a test
card, then repeat the same steps in **live mode** with live keys.

**Billing mode: webhook first, API reconciliation as the safety net.** Stripe pushes `invoice.paid`
to our webhook and credits land in seconds. Independently, the server also asks Stripe which
subscription exists and which invoices were actually paid, and grants any it hasn't already credited.

Keeping both is deliberate, and they cannot fight: **every grant claims the same per-invoice row**,
so whichever path arrives first grants and the other does nothing. The webhook makes it instant; the
reconciliation means a webhook you forgot to register, pointed at the wrong host, or whose secret you
rotated is an inconvenience rather than a customer who paid and got nothing.

Setup is seven env vars on the **API** service: `OMI_STRIPE_SECRET_KEY` (`sk_…`), one Price id
per plan (`OMI_STRIPE_PRICE_STARTER` / `_REPORTER` / `_RESEARCH`), one for the credit pack
(`OMI_STRIPE_PRICE_TOPUP`), `OMI_PUBLIC_BASE_URL` (your **web** URL), and
`OMI_STRIPE_WEBHOOK_SECRET` (`whsec_…`, from step 3).

**The Price on an invoice is what decides which plan was bought**, and therefore how many credits
are granted. That is why each tier needs its own Price id: a plan whose id is not configured does
not merely fail to sell, its renewal invoices resolve to no tier and grant **nothing**.
`GET /v1/billing/preflight` names any that are missing.

**Publishable keys (`pk_…` / `STRIPE_PUBLISHABLE_KEY`) are not used.** Checkout is Stripe-hosted;
no Stripe.js runs in the browser. A publishable key alone cannot make Subscribe work.

Two rules worth internalising before you start:

- **The price lives in Stripe, not in this repo.** The API never sends an amount — it sends a Price
  ID. That means no bug in our code can charge the wrong number, and changing the price is a
  dashboard edit, not a deploy.
- **Credits are keyed to the Stripe invoice id.** Reconciling ten times grants nothing extra; a
  renewal grants once, whenever it is first seen.

### When credits actually appear

| Trigger | Why |
|---|---|
| **Stripe sends `invoice.paid`** | The primary path. Credits land within seconds of the charge, including monthly renewals nobody is watching. |
| Returning from Checkout | The browser calls `POST /v1/billing/sync`. Completes the purchase even if the webhook is slow or missing. |
| Opening **Settings → Billing** | Throttled to once every 5 minutes per user. |
| **A scan that would otherwise be refused** | Forced, never throttled. A subscriber whose renewal just went through is never told to "subscribe". |

Only `invoice.paid` grants credits. A new subscription emits **both**
`customer.subscription.created` and `invoice.paid` — crediting on both would charge once and grant
twice, so the subscription events move status and renewal date only.

If you ever want to turn the webhook off, delete `OMI_STRIPE_WEBHOOK_SECRET`: the endpoint goes
inert (acks with 200, grants nothing) and reconciliation carries billing on its own. Renewals are
then credited the next time that user's account is reconciled rather than the instant they are
charged — which the scan path always does before refusing anyone.

---

## 1. Create the products and prices

You need **four** Prices: three recurring plans and one one-off credit pack.

Stripe Dashboard → **Product catalogue → Add product**, once per row.

| Product name | Price | Billing | Env var | Grants |
|---|---|---|---|---|
| `Omi Premium Starter` | `14.99` USD | **Monthly** (recurring) | `OMI_STRIPE_PRICE_STARTER` | 12 credits |
| `Omi Premium Reporter` | `79.00` USD | **Monthly** (recurring) | `OMI_STRIPE_PRICE_REPORTER` | 75 credits |
| `Omi Premium Research` | `249.00` USD | **Monthly** (recurring) | `OMI_STRIPE_PRICE_RESEARCH` | 250 credits |
| `Omi Credit Pack` | `25.00` USD | **One-off** (not recurring) | `OMI_STRIPE_PRICE_TOPUP` | 25 credits |

Save each one, open its price, and copy the id — it looks like `price_1QxxxxxxxxxxxxxxxxxxXXXX`.

> **The credit pack MUST be one-off, not recurring.** A recurring price here would silently sign
> customers up to a second monthly subscription when they meant to buy overage once. The checkout
> route uses `mode: payment` and will reject a recurring price.

> **Keep the legacy `OMI_STRIPE_PRICE_ID` set.** It is the pre-tier single-plan price, and every
> current subscriber's renewal invoices carry it forever. The server maps it to Starter. Removing it
> would leave the only people already paying unable to name a tier on their next renewal, which
> fails closed to Free: a silent downgrade of exactly the customers you have.

> **The product names must match `PLAN_NAME` + the tier names in `apps/web/lib/plan.ts`.** The site
> names the plan, then Checkout shows whatever this field says, and a customer who sees two
> different names at the moment they hand over a card reasonably wonders what they are buying.
> Nothing in the repo can detect that drift. Renaming an existing product is safe: it does not
> change the price id, so no env var needs updating and no subscription is affected.

> **What each plan grants is in the repo, not in Stripe.** The amount charged is the Stripe Price;
> the credits and the monthly lookup ceiling are `app/core/plans.py`. The two are deliberately
> independent, and both are pinned against the website's copy by
> `tests/test_deployed_credit_contract.py`. One credit covers 20 analysed accounts.

## 2. Get your API keys

Dashboard → **Developers → API keys**

- **Secret key** → `OMI_STRIPE_SECRET_KEY` (`sk_test_…`, later `sk_live_…`)
- **Publishable key** → not required. Ignore it for Subscribe, or set
  `NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY` on the **web** service only if you add Stripe.js later.
  Never put a `pk_…` value in `OMI_STRIPE_SECRET_KEY`. A dashboard var named
  `STRIPE_PUBLISHABLE_KEY` alone will not enable billing.

Checkout is hosted by Stripe, so no card details and no Stripe.js touch our domain today.

## 3. Register the webhook

Dashboard → **Developers → Webhooks → Add endpoint**

**Endpoint URL:** `https://<your-API-host>/v1/billing/webhook`

> This is the **API** host, not `OMI_PUBLIC_BASE_URL` (that is the web app, where Stripe returns the
> *customer*). Pointing the webhook at the web host is the most common way this fails, and it fails
> silently — Stripe reports delivery to a service that has no such route.
>
> Don't type it from memory. `GET /v1/billing/preflight`, called **directly on the API host**, prints
> the exact URL and event list for your deployment.

**Events to send** — exactly these six:

| Event | What it does |
|---|---|
| `invoice.paid` | **Grants the credits.** The only event that moves the balance. |
| `invoice.payment_failed` | Marks the account `past_due` so the UI can prompt for a new card. |
| `customer.subscription.created` | Records status + renewal date. |
| `customer.subscription.updated` | Same, on plan change or renewal. |
| `customer.subscription.deleted` | Marks it cancelled. Credits already bought are kept. |
| `checkout.session.completed` | Binds the Stripe customer to the account. Grants nothing. |

Selecting fewer silently drops that behaviour; selecting more is harmless, as anything unrecognised
is recorded and acknowledged without action.

Then open the endpoint you just created, reveal the **Signing secret** (`whsec_…`), and set it as
`OMI_STRIPE_WEBHOOK_SECRET` on the API service. **Redeploy** — the secret is read at boot.

> Until that secret is set the endpoint is inert: it returns 200 and grants nothing, so Stripe won't
> retry for three days against a deployment that isn't ready. Billing still works via reconciliation
> in the meantime.

**Verify it:** use **Send test webhook** on the endpoint page, then call `/v1/billing/preflight`
again — `webhook_delivery` should report the event and its timestamp. If it still says nothing has
ever been received, the endpoint is registered against the wrong host or the other Stripe mode.

## 4. Turn on the Customer Portal

Dashboard → **Settings → Billing → Customer portal** → enable it, and allow customers to update
payment methods and cancel. Without this, "Manage subscription" fails when clicked.

**Then, in the same screen, turn on "Customers can switch plans" and add all three products to the
allowed list.** This is the step that makes upgrades and downgrades work, and it is easy to miss
because nothing in the app fails visibly without it — an existing subscriber clicking a different
plan simply lands in a portal that offers no way to switch.

Stripe's portal is used for plan changes deliberately: it prorates a mid-cycle switch correctly, and
re-implementing proration by hand is one of the more reliable ways to double-charge somebody. The
app only opens a fresh Checkout for customers who have **no** live subscription.

---

## 5. Render environment variables

### API service (`omisphere-api`) — the only place secrets belong

| Variable | Example | Notes |
|---|---|---|
| `OMI_STRIPE_SECRET_KEY` | `sk_test_51Q…` | **Secret.** The only credential billing needs. |
| `OMI_STRIPE_PRICE_STARTER` | `price_1Q…` | $14.99/mo. Grants 12 credits. |
| `OMI_STRIPE_PRICE_REPORTER` | `price_1Q…` | $79/mo. Grants 75 credits + the signal breakdown, saved graphs and monitoring. |
| `OMI_STRIPE_PRICE_RESEARCH` | `price_1Q…` | $249/mo. Grants 250 credits + coordination detection and API access. |
| `OMI_STRIPE_PRICE_TOPUP` | `price_1Q…` | **One-off**, $25. Grants `OMI_TOPUP_PACK_CREDITS`. Unset means a customer who runs out has nothing to buy. |
| `OMI_STRIPE_PRICE_ID` | `price_1Q…` | The **legacy** single-plan price. Keep it: existing subscribers' renewals carry it and it resolves to Starter. |
| `OMI_TOPUP_PACK_CREDITS` | `25` | What one pack contains. Stripe sets what it costs; this sets what it holds. Keep them at $1/credit. |
| `OMI_STRIPE_WEBHOOK_SECRET` | `whsec_1Q…` | **Secret.** The signing secret from the endpoint in step 3 — not the API key, not the endpoint id. Unset = the webhook is inert and crediting falls back to reconciliation. |
| `OMI_PUBLIC_BASE_URL` | `https://omisphere.online` | The **web** URL. Stripe sends the customer back here after checkout — set it to the site people actually visit, not the API host, or they land on an API 404. |
| `OMI_FREE_TRIAL_CREDITS` | `5` | Credits a new signup starts with. |
| `OMI_SUBSCRIPTION_PRICE_DISPLAY` | `$14.99` | Fallback label only. `/v1/billing/status` reports the price of the tier the customer is actually on. |

> `OMI_MONTHLY_CREDIT_GRANT` **no longer exists.** What an invoice grants is a property of the tier
> its Price names. A single global grant could only ever have been right for one of three plans.

### Web service (`omisphere-web`)

| Variable | Example | Notes |
|---|---|---|
| `NEXT_PUBLIC_TRIAL_CREDITS` | `5` | Marketing copy only. Must match `OMI_FREE_TRIAL_CREDITS`. |
| `NEXT_PUBLIC_TOPUP_PACK_CREDITS` | `25` | Must match `OMI_TOPUP_PACK_CREDITS`. |

> Per-tier credits, prices and lookup ceilings are **not** env vars. They live in
> `apps/web/lib/plan.ts` and are checked against `app/core/plans.py` by
> `tests/test_deployed_credit_contract.py`. Nine more env vars nobody reconciles is the drift this
> repo has already been bitten by three times.

**Never put `OMI_STRIPE_SECRET_KEY` or `OMI_STRIPE_WEBHOOK_SECRET` on the web service.** Anything
prefixed `NEXT_PUBLIC_` is compiled into JavaScript that every visitor downloads; the two Stripe
secrets belong only on the API service, which is why neither has that prefix.

---

## 6. Verify before you trust it

**Run the preflight.** This is the fastest way to know whether your deployment can actually take a
payment. Sign in, then from the browser console on your site:

```js
await (await fetch('/api/v1/billing/preflight')).json()
```

> Called this way it reaches the API through the web app's `/api` proxy, so it cannot tell which host
> to register the webhook against and will say so rather than print a wrong one. To get the webhook
> URL, use the curl form below against the API host directly.

or with curl against the API host, passing your `__session` cookie:

```bash
curl -s https://<your-api-host>/v1/billing/preflight \
  -H "Cookie: __session=<your session cookie>" | python -m json.tool
```

It calls Stripe with your configured key and reports back:

```json
{
  "ready": true,
  "webhook_url": "https://<your-api-host>/v1/billing/webhook",
  "webhook_events": ["invoice.paid", "invoice.payment_failed", "…"],
  "checks": [
    {"name": "secret_key",        "ok": true,  "detail": "Set (test mode key)."},
    {"name": "stripe_reachable",  "ok": true,  "detail": "Authenticated with Stripe account acct_1Q…"},
    {"name": "price",             "ok": true,  "detail": "13.99 USD per month — this is what a customer is charged."},
    {"name": "return_url",        "ok": true,  "detail": "Customers return to https://…/settings after paying."},
    {"name": "credit_grant",      "ok": true,  "detail": "20 credits granted per paid invoice."},
    {"name": "webhook_url",       "ok": true,  "detail": "Register this endpoint in Stripe: https://…/v1/billing/webhook"},
    {"name": "webhook_secret",    "ok": true,  "detail": "Set — signatures are verified and the webhook credits on invoice.paid."},
    {"name": "webhook_delivery",  "ok": true,  "detail": "Last event invoice.paid at 2026-07-28T… · 3 in the last 24h."},
    {"name": "crediting",         "ok": true,  "detail": "Webhook (instant) with API reconciliation as the backstop."}
  ],
  "next_steps": []
}
```

`ready: false` means **no customer can pay yet**, and `next_steps` says exactly what to set. It never
returns your secret key or signing secret. It catches the failures that otherwise only appear when a
real customer tries to check out:

- the secret key set but `OMI_STRIPE_PRICE_ID` missing — checkout 503s
- a price that is one-off rather than recurring — subscription checkout fails
- a price from the *other* Stripe mode (test price + live key, or vice versa)
- an archived price
- `OMI_PUBLIC_BASE_URL` left on localhost — paying customers redirect into nowhere

The three `webhook_*` checks are reported but **deliberately not blocking**: with no webhook,
reconciliation still credits every payment correctly, so the deployment is degraded rather than
broken. Read them as "is instant crediting live?", not "can I take money?".

`webhook_delivery` is the one that catches a webhook nobody has tested. Config can look perfect and
delivery still fail — wrong host, a firewall, an endpoint registered in the other Stripe mode — and
this is the only check that proves Stripe has actually reached this deployment. Grant markers written
by reconciliation are excluded from it, so it cannot report a healthy webhook on a server that has
never received one.

**Health check.** The API also logs a startup line — confirm it says billing is on:

```
Stripe billing: on
```

If it says `off (free tier only)`, the API has **not** picked up your keys: either they aren't set on
the API service, or the service hasn't been redeployed since you added them.

**Test the card path.** In test mode, subscribe with Stripe's test card:

- Card `4242 4242 4242 4242`, any future expiry, any CVC, any postcode.
- Decline path: `4000 0000 0000 0002`.
- Requires-authentication path: `4000 0025 0000 3155`.

After a successful test payment you should see, in order:

1. Stripe returns you to `/settings?billing=success`.
2. The page says "Payment received — adding your credits…" and then settles.
3. Credits increase by **20**.
4. Dashboard → the customer shows a paid invoice.

**If credits don't appear**, hit the sync directly and read what it says:

```bash
curl -X POST https://<your-api-host>/v1/billing/sync \
  -H "Cookie: __session=<your session cookie>"
# -> {"synced":true,"granted":1,"credits_added":20,"credits_remaining":20,...}
```

`synced: false` means Stripe wasn't reachable or the account has no Stripe customer;
`granted: 0` with `synced: true` means Stripe reports no paid invoice that isn't already credited.

---

## 7. Going live

1. Flip the dashboard to **live mode** and repeat steps 1 and 4 — live mode has its **own** product
   and its own Customer Portal setting.
2. Replace `OMI_STRIPE_SECRET_KEY` and `OMI_STRIPE_PRICE_ID` on the API service with the live values.
3. Complete one real $13.99 purchase yourself and confirm the credits land, then refund it from the
   dashboard. It is the only way to know the live path works end to end.
4. Stripe requires a statement descriptor and business details before it will accept live payments —
   Settings → Business.

---

## How the money path behaves

Worth knowing when something looks odd:

- **Credits are added, never reset.** Renewing with 12 credits banked leaves you with 32. An earlier
  version topped balances *up to* 20, so a subscriber holding 20+ credits paid and received nothing.
- **One invoice grants exactly once.** The grant is keyed on the Stripe invoice id and enforced by a
  unique index, so redeliveries, retries, and two different events describing the same payment can't
  double-credit.
- **Nothing is lost.** Stripe is the source of truth, so a sync that fails simply runs again and
  catches up — including replaying every invoice missed during a long absence.
- **Cancelling keeps your credits.** They were paid for.
- **A payment made outside our checkout still finds its owner.** If the stored customer link is
  missing, reconciliation looks the customer up by the account's email and repairs the link.
