# Stripe setup — $9.99/month for 20 credits

Everything you need to take the first real payment. Do it once in **test mode**, verify with a test
card, then repeat the same steps in **live mode** with live keys.

Two rules worth internalising before you start:

- **The price lives in Stripe, not in this repo.** The API never sends an amount — it sends a Price
  ID. That means no bug in our code can charge the wrong number, and changing the price is a
  dashboard edit, not a deploy.
- **`OMI_STRIPE_WEBHOOK_SECRET` is the only thing stopping a stranger crediting themselves.** The
  webhook URL is public. Without the signing secret set, the endpoint refuses to act on anything.

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

## 3. Create the webhook

Dashboard → **Developers → Webhooks → Add endpoint**

- **Endpoint URL:** `https://<your-api-host>/v1/billing/webhook`
  (the **API** service, not the web one — e.g. `https://omisphere-api.onrender.com/v1/billing/webhook`)
- **Events to send** — exactly these five:

  | Event | What it does |
  |---|---|
  | `invoice.paid` | **Grants the 20 credits.** The only event that adds credits. |
  | `invoice.payment_failed` | Marks the account `past_due` so the UI asks for a new card. |
  | `customer.subscription.created` | Records status + renewal date. |
  | `customer.subscription.updated` | Keeps status + renewal date current. |
  | `customer.subscription.deleted` | Marks `canceled`. Credits already paid for are kept. |

  Optionally add `checkout.session.completed` — it isn't required, but it re-links a customer to a
  user if that link is ever missing.

After creating it, click **Reveal** on the signing secret (`whsec_…`) → `OMI_STRIPE_WEBHOOK_SECRET`.

> The signing secret is **per endpoint**. Your test-mode and live-mode endpoints have different
> secrets, and so does the Stripe CLI. Using the wrong one makes every webhook 400.

## 4. Turn on the Customer Portal

Dashboard → **Settings → Billing → Customer portal** → enable it, and allow customers to update
payment methods and cancel. Without this, "Manage subscription" fails when clicked.

---

## 5. Render environment variables

### API service (`omisphere-api`) — the only place secrets belong

| Variable | Example | Notes |
|---|---|---|
| `OMI_STRIPE_SECRET_KEY` | `sk_test_51Q…` | **Secret.** |
| `OMI_STRIPE_WEBHOOK_SECRET` | `whsec_…` | **Secret.** From the endpoint you created in step 3. |
| `OMI_STRIPE_PRICE_ID` | `price_1Q…` | Not secret, but must match the price you want to charge. |
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
4. Dashboard → Webhooks → your endpoint shows `invoice.paid` with a **200**.

**Test webhooks locally** without deploying:

```bash
stripe login
stripe listen --forward-to localhost:8000/v1/billing/webhook
# use the whsec_… it prints as OMI_STRIPE_WEBHOOK_SECRET locally
stripe trigger invoice.paid
```

---

## 7. Going live

1. Flip the dashboard to **live mode** and repeat steps 1, 3 and 4 — live mode has its **own**
   product, its own webhook endpoint, and its own signing secret.
2. Replace `OMI_STRIPE_SECRET_KEY`, `OMI_STRIPE_WEBHOOK_SECRET` and `OMI_STRIPE_PRICE_ID` on the API
   service with the live values.
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
- **A failed webhook is retried, not swallowed.** The event is only marked processed in the same
  transaction as the work, so if the handler fails, Stripe's retry genuinely re-runs it.
- **Cancelling keeps your credits.** They were paid for.
- **A payment we can't match to a user grants nothing and logs an error** naming the customer id —
  search the API logs for `could not be matched to a user` if someone reports a missing top-up.
