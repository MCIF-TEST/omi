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

## Receiving updates (local dev)

As of v1.0.0 OMISPHERE is on GitHub at
`https://github.com/MCIF-TEST/OMISPHERE`. Zips are retired. To pull
the latest fixes onto your local machine:

```cmd
cd C:\Users\omisp\Downloads\omisphere
git fetch origin
git pull origin main
```

If `pyproject.toml` changed (API deps):

```cmd
cd apps\api
py -m pip install -e .[youtube]
```

If `package.json` changed (Web deps):

```cmd
cd ..\web
npm install
```

Then relaunch via `scripts\start_omisphere.bat`.

If you ever get a "merge conflict" because you edited a file locally
that also changed upstream, the simplest recovery is:

```cmd
git stash             # set your local edits aside
git pull origin main  # take the upstream version
git stash pop         # try to re-apply your edits; resolve conflicts in your editor
```

CI runs on every push to `main` and on every pull request — the
GitHub badge on the repo's README shows green/red. If it goes red,
the build is broken; don't pull onto a working install until it
flips green again.

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

---

## Email alert delivery (SMTP)

Watchlist alerts can be delivered via email, webhook, or both. Webhooks
work without any config; email requires SMTP credentials set on the API
service.

### Configuring SMTP

Any standard SMTP provider works. Set these env vars on the API service
(via Render dashboard or `apps/api/.env` for local):

```
OMI_SMTP_HOST=smtp.resend.com
OMI_SMTP_PORT=587
OMI_SMTP_USER=resend
OMI_SMTP_PASSWORD=re_xxxxx          # the API key from your provider
OMI_SMTP_FROM=alerts@yourdomain.com
OMI_SMTP_USE_TLS=true               # STARTTLS on 587; some providers prefer port 465
```

Recommended providers (any will work — same SMTP creds shape):

| Provider | Host | Port | Notes |
|---|---|---|---|
| Resend | `smtp.resend.com` | 587 | Cheapest. Use `resend` as the user; password is the API key. |
| AWS SES | `email-smtp.<region>.amazonaws.com` | 587 | Generate SMTP creds in SES console; default region is us-east-1. |
| Postmark | `smtp.postmarkapp.com` | 587 | Server token as both user and password. |

### Verifying delivery

After setting the env vars and redeploying, sign in as an admin and call:

```bash
curl -X POST https://api.yourdomain.com/v1/monitoring/test-alert \
     -b "omi_session=<your-cookie>"
```

The response reports the delivery status of every channel the admin has
enabled in settings:

```json
{
  "user_email": "you@example.com",
  "email": {
    "requested": true,
    "delivered": true,
    "error": null,
    "smtp_host": "smtp.resend.com"
  },
  "webhook": { "requested": false },
  "smtp_configured": true
}
```

If `delivered: false`, the `error` field carries the specific reason
(`smtp_not_configured`, `SMTPAuthenticationError: ...`, etc.). Common
failures:

- `smtp_not_configured` — `OMI_SMTP_HOST` is empty. Re-check env vars and
  redeploy.
- `SMTPAuthenticationError` — wrong user or password. Resend uses the
  literal user `resend`; SES requires SES-generated creds, not your
  AWS access key.
- `gaierror` — DNS / hostname wrong. Typo in `OMI_SMTP_HOST`.

### Boot-time confirmation

On every startup the API logs an `Optional features:` line that
includes the live SMTP state:

```
Optional features: YouTube ingestion: on | Anthropic LLM: off |
  SMTP email alerts: on (smtp.resend.com) |
  Stripe billing: on | Background monitoring: on
```

If you expect SMTP to be on but the log says `off — webhook delivery
still works`, the env var didn't reach the API service. Re-check the
Render dashboard.

---

## Schema migrations (Alembic, advisory)

For Phase 1 deploys the boot flow uses ``Base.metadata.create_all`` plus
an ad-hoc ``_INCREMENTAL_COLUMNS`` hook in ``app/storage/db.py``. That's
fine for the additive changes we've made so far but it doesn't handle
column type changes, drops, renames, or foreign-key changes safely.

Alembic is wired up under ``apps/api/alembic/`` for operators who want
proper migrations. Today it's advisory — the boot flow still calls
``create_all`` for backward compatibility — but new schema work should
land as an Alembic migration alongside the model change so the history
is real, not implicit.

### Adopting Alembic on an existing deploy

A one-time step to tell Alembic the existing schema is at the latest
revision (so it doesn't try to recreate every table):

```bash
cd apps/api
OMI_DATABASE_URL="<the prod URL>" alembic stamp head
```

After that, every future deploy can apply pending migrations with:

```bash
OMI_DATABASE_URL="<the prod URL>" alembic upgrade head
```

We don't run this automatically in the Render boot flow yet — wire it
into the build / pre-deploy step when you're ready.

### Authoring a new migration

When you change a model in ``app/storage/models.py``:

```bash
cd apps/api
OMI_DATABASE_URL="sqlite:///./data/scratch.db" \
  alembic revision --autogenerate -m "describe the change"
```

Review the generated file under ``alembic/versions/`` — autogenerate is
not infallible (it can miss enum changes, index renames, type widenings).
Trim or extend manually, then commit. Run ``alembic upgrade head`` to
apply locally and confirm it works.

### Inspection

```bash
# Where is this DB currently at?
alembic current

# What revisions exist?
alembic history --verbose

# What would the next upgrade do, as SQL, without running it?
alembic upgrade head --sql
```

### When the create_all hook and Alembic disagree

The migrations under ``alembic/versions/`` are written to be idempotent
on tables that ``create_all`` may already have built. Specifically: every
``op.create_table`` is guarded by a presence check (see
``0002_account_labels.py``). This means new deploys can use either
mechanism without conflicts. Once an operation arrives that can't be
expressed safely both ways (e.g. dropping a column), we'll flip the
boot flow to ``alembic upgrade head`` and retire ``_INCREMENTAL_COLUMNS``.
