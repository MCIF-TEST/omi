# Stripe setup — $9.99/month for 20 credits

Everything you need to take the first real payment. Do it once in **test mode**, verify with a test
card, then repeat the same steps in **live mode** with live keys.

**There is no webhook to set up.** OmiSphere reconciles against Stripe's API: rather than waiting to
be told what happened, the server asks Stripe which subscription exists and which invoices were
actually paid, then grants credits for any paid invoice it hasn't already credited. Setup is three
env vars and a price.

Two rules worth internalising before you start:

- **The price lives in Stripe, not in this repo.** The API never sends an amount — it sends a Price
  ID. That means no bug in our code can charge the wrong number, and changing the price is a
  dashboard edit, not a deploy.
- **Credits are keyed to the Stripe invoice id.** Reconciling ten times grants nothing extra; a
  renewal grants once, whenever it is first seen.

### When credits actually appear

Reconciliation runs at the moments where being stale would be visible:

| Trigger | Why |
|---|---|
| Returning from Checkout | The browser calls `POST /v1/billing/sync`, which is what completes a purchase. Credits land in a second or two. |
| Opening **Settings → Billing** | Throttled to once every 5 minutes per user. |
| **A scan that would otherwise be refused** | Forced, never throttled. A subscriber whose renewal just went through is never told to "subscribe". |

The trade-off, stated plainly: a monthly renewal is credited the next time that user's account is
reconciled, not the instant Stripe charges the card. In practice they notice when they come back to
use it, and the scan path syncs before it ever refuses them. In exchange there is no public endpoint
that grants credits, no signing secret to rotate, and nothing to silently lose — a missed webhook is
gone for good, whereas a missed sync self-heals on the next one.

> Prefer instant crediting later? `POST /v1/billing/webhook` still exists and is inert until you set
> `OMI_STRIPE_WEBHOOK_SECRET`. Enabling it changes nothing about the above — both paths compete for
> the same per-invoice row, so only one can ever grant.

---

## 1. Create the product and price

Stripe Dashboard → **Product catalogue → Add product**

| Field | Value |
|---|---|
| Name | `OmiSphere Monthly` |
| Description | `20 analysis credits per month` |
| Price | `9.99` **USD** |
| Billing period | **Monthly** (recurring) |

Save, then open the price and copy its id — it looks like `price_1QxxxxxxxxxxxxxxxxxxXXXX`.
That is `OMI_STRIPE_PRICE_ID`.

> One credit covers up to 50 analysed accounts, so 20 credits ≈ 1,000 accounts a month. If you ever
> want to change what a subscription is worth, change `OMI_MONTHLY_CREDIT_GRANT` — the amount charged
> is the Stripe Price, and the two are deliberately independent.

## 2. Get your API keys

Dashboard → **Developers → API keys**

- **Secret key** → `OMI_STRIPE_SECRET_KEY` (`sk_test_…`, later `sk_live_…`)

There is no publishable key to set: checkout is hosted by Stripe, so no card details and no Stripe
JS ever touch the browser on our domain.

## 3. (Skipped — no webhook needed)

Nothing to do here. Billing reads from Stripe's API, so there is no endpoint to register, no signing
secret, and no public URL that grants credits.

## 4. Turn on the Customer Portal

Dashboard → **Settings → Billing → Customer portal** → enable it, and allow customers to update
payment methods and cancel. Without this, "Manage subscription" fails when clicked.

---

## 5. Render environment variables

### API service (`omisphere-api`) — the only place secrets belong

| Variable | Example | Notes |
|---|---|---|
| `OMI_STRIPE_SECRET_KEY` | `sk_test_51Q…` | **Secret.** The only credential billing needs. |
| `OMI_STRIPE_PRICE_ID` | `price_1Q…` | Not secret, but must match the price you want to charge. |
| `OMI_STRIPE_WEBHOOK_SECRET` | *(leave unset)* | Only if you later want instant crediting. Unset = the webhook endpoint is inert. |
| `OMI_PUBLIC_BASE_URL` | `https://omisphere-web.onrender.com` | The **web** URL. Stripe sends the customer back here after checkout — set it to the site people actually visit, not the API host, or they land on an API 404. |
| `OMI_MONTHLY_CREDIT_GRANT` | `20` | Credits added per paid invoice. |
| `OMI_FREE_TRIAL_CREDITS` | `3` | Credits a new signup starts with. |
| `OMI_SUBSCRIPTION_PRICE_DISPLAY` | `$9.99` | Display only. Keep it in step with the Stripe price. |

### Web service (`omisphere-web`)

| Variable | Example | Notes |
|---|---|---|
| `NEXT_PUBLIC_MONTHLY_CREDITS` | `20` | Marketing copy only. Must match `OMI_MONTHLY_CREDIT_GRANT`. |
| `NEXT_PUBLIC_TRIAL_CREDITS` | `3` | Must match `OMI_FREE_TRIAL_CREDITS`. |

**Never put `OMI_STRIPE_SECRET_KEY` or `OMI_STRIPE_WEBHOOK_SECRET` on the web service.** Anything
prefixed `NEXT_PUBLIC_` is compiled into JavaScript that every visitor downloads; the two Stripe
secrets belong only on the API service, which is why neither has that prefix.

---

## 6. Verify before you trust it

**Health check.** The API logs a startup line — confirm it says billing is on:

```
Stripe billing: on
```

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
3. Complete one real £/$9.99 purchase yourself and confirm the credits land, then refund it from the
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
