# OMISPHERE — Operations

Production checklist + day-2 runbook. Keep this file current.

---

## Deployment topology

```
Render
├── omisphere-web      Next.js  · port $PORT  · 1 instance
├── omisphere-api      FastAPI  · port $PORT  · 1 instance
└── omisphere-postgres Postgres · managed     · starter ($7/mo)

Stripe (external)
Supabase Postgres (alternative DB host — currently Render-managed)
Anthropic (optional, for LLM commentary)
YouTube Data API v3
```

---

## First deploy (from scratch)

1. Push repo to GitHub.
2. Render → New → Blueprint → connect repo → Apply.
3. After the first build (will fail until env vars are set), fill in
   the Environment tab on `omisphere-api`:

   | Key | Source |
   |---|---|
   | `OMI_YOUTUBE_API_KEY` | console.cloud.google.com (Data API v3) |
   | `OMI_STRIPE_SECRET_KEY` | dashboard.stripe.com (test then live) |
   | `OMI_STRIPE_PRICE_ID` | Created in Stripe — $9.99/mo recurring |
   | `OMI_STRIPE_WEBHOOK_SECRET` | After registering webhook below |
   | `OMI_SESSION_SECRET` | `python -c "import secrets; print(secrets.token_urlsafe(64))"` |
   | `OMI_PUBLIC_BASE_URL` | `https://omisphere-api.onrender.com` until custom domain lands |
   | `OMI_ENABLE_MONITORING` | `true` (so background anomaly + watchlist passes run) |
   | `OMI_ANTHROPIC_API_KEY` | Optional — enables Claude analyst commentary |

4. On `omisphere-web` set:
   | Key | Value |
   |---|---|
   | `OMI_PUBLIC_BASE_URL` | The public URL once the custom domain is live |

5. Register the Stripe webhook:
   - dashboard.stripe.com → Webhooks → Add endpoint
   - URL: `https://omisphere-api.onrender.com/v1/billing/webhook`
   - Events: `customer.subscription.{created,updated,deleted}` + `invoice.paid`
   - Copy the signing secret → paste into `OMI_STRIPE_WEBHOOK_SECRET` → redeploy.

---

## Health + observability

- `GET /health` — DB-touching liveness probe (used by Render).
- `GET /v1/status` — engine state. Cached 5s.
- `GET /v1/metrics` — **admin-only**. Totals + per-route latency p50/p95
  + lifetime YouTube quota + lifetime LLM tokens + cache stats.

To promote a user to admin, run a one-off SQL on the Postgres DB:

```sql
UPDATE users SET is_admin = 1 WHERE email = 'you@example.com';
```

Render gives you a `psql` shell from the database page.

---

## Logging

Production env auto-emits JSON-line logs. Filter by `request_id` to
trace a single user action across services. Set `OMI_LOG_LEVEL=DEBUG`
temporarily for verbose tracing; revert after.

---

## Common operations

### Rotate the YouTube API key

1. console.cloud.google.com → Credentials → regenerate
2. Update `OMI_YOUTUBE_API_KEY` in Render env → save (auto-redeploys)
3. The old key stops working immediately; in-flight scans fail with 503.

### Cancel a problem user's subscription

1. dashboard.stripe.com → Customers → find them → Cancel subscription
2. Stripe fires `customer.subscription.deleted` → our webhook updates the
   user's `subscription_status='canceled'`
3. They keep existing credits until they're used.

### Refund

Stripe dashboard → payment → Refund. Doesn't auto-credit the user; if
they should keep their credits, leave them; if they shouldn't, set them
to 0 in the DB:
```sql
UPDATE users SET credits_remaining = 0 WHERE email = 'their@email';
```

### Scale up (when traffic justifies)

1. Bump API plan from `starter` to `standard` in Render.
2. When you hit a single-instance ceiling:
   - **Swap in Redis** — replace `TTLCache` calls with a Redis-backed
     cache (`app/core/cache.py` interface unchanged).
   - **Move scheduler to Dramatiq** — same interface as
     `app.core.background.submit`; existing call sites unchanged.
   - **Increase Postgres tier.**

### Restore from a bad deploy

Render rollback button on the service page → pick the prior known-good
deploy. Postgres is unaffected. If a migration broke things, restore
DB from automatic snapshot (Render daily, 7-day retention on starter).

---

## YouTube quota

- Free tier: 10,000 units / day
- Roughly: 1 comprehensive scan ≈ 100 units. So ~90 scans/day max.
- Apply for an extended quota at:
  console.cloud.google.com → APIs & Services → YouTube Data API → Quotas
- Approval requires demonstrating: usage type, expected volume,
  user-facing app description. Reasonable apps with clear use cases
  usually get 10–100× quota.

---

## Cost ceilings

Sanity caps to set in Render env if you need them:

- `OMI_SCAN_MAX_COMMENTERS` — default 150. Lower if quota spirals.
- `OMI_WATCHLIST_MAX_PER_TICK` — default 5. Lower if scheduler eats quota.
- `OMI_REASONING_MAX_TOKENS` — default 320. Lower if Anthropic bill spikes.

Watch `/v1/metrics` `cost.youtube_quota_lifetime` and
`cost.reasoning_tokens_lifetime` trend over time.

---

## Backup strategy

- Render Postgres: daily snapshot, 7-day retention (starter plan). Pay
  to bump retention. For long-term archive run a weekly `pg_dump` to
  S3 / R2 via a Render cron job (Phase 9.5).
- User data is the only irreplaceable thing — investigations,
  fingerprints, watchlists. Scan-source data can be re-fetched from
  YouTube; lose it freely.

---

## Incident response (compressed playbook)

| Symptom | First check |
|---|---|
| 5xx spike | `/v1/metrics` → which route's p95 spiked? logs → `request_id` of one failing request |
| Scans stuck | YouTube quota exhausted? `/v1/status` → `youtube_configured` → quota dashboard |
| Stripe webhooks failing | dashboard.stripe.com → Webhooks → recent deliveries; check signature mismatch |
| Auth not persisting | `OMI_SESSION_SECRET` changed? cookies invalid after rotation. Force-redeploy reverts |
| Monitoring loop silent | `OMI_ENABLE_MONITORING=true`? logs for `monitoring loop started` line |
