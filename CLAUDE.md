# CLAUDE.md — OmiSphere working notes & session handoff

**Living document.** Update it in the same commit as the change it describes. It is the first thing a
new Claude Code session reads, and the only place that explains *why* several non-obvious things are
the way they are. If you change behaviour and don't update this file, the next session will
re-introduce a bug this one already paid for.

**Last updated:** 2026-07-25 · branch `claude/master-analyst-protocol-v1-1u8tyk` · PR
[#130](https://github.com/MCIF-TEST/omi/pull/130) (draft) · suite **1513 passed, 1 known-failing**

> `HANDOFF.md` at the repo root is a **stale one-off** from a different branch (2026-05-29). Ignore
> it; this file supersedes it.

---

## What this is

OmiSphere detects bought / bot / coordinated accounts in the comment section of a social post. Paste
an X or YouTube link → the app compiles the commenters (free) → you select who to analyse → the
engine scores each account and the **Omi Analyst** (an OpenRouter model) writes a per-account read.

This is a **real product launch**, funded by a $20K loan. Treat cost, abuse limits, and correctness
as production concerns, not exercises. Wasted OpenRouter spend is real money.

| | |
|---|---|
| `apps/api` | FastAPI + SQLAlchemy. Python ≥3.11. The engine, the analyst, all routes. |
| `apps/web` | Next.js 14 App Router + Tailwind. Clerk auth. |
| `ml/`, `datasets/` | Prompt mirrors + training data. Drift-guarded against `apps/api`. |
| `docs/` | Architecture, design system, ops. |

### Commands

```bash
# backend  (from apps/api)
python -m pytest -q                 # full suite, ~4½ min
python -m pyflakes app/             # catches undefined names — see "Bug class" below

# web  (from apps/web)
npx tsc --noEmit && npx next lint
CLERK_SECRET_KEY= NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY=pk_test_Y2xlcmsuZXhhbXBsZS5jb20k npx next build
```

The build command deliberately runs with **`CLERK_SECRET_KEY` unset** — that must keep working (see
Clerk below). A malformed publishable key fails prerender with a confusing error, so use the
well-formed dummy above rather than something like `pk_test_x`.

---

## Known-failing tests (pre-existing, not yours)

Current measured state: **1521 passed, 2 failed** (~4m20s). Both failures reproduce on an unchanged
tree AND in isolation, so neither is pollution:

1. `tests/test_evaluation_benchmark.py::test_accuracy_gate_no_regression` — Brier 0.0321 against a
   0.032 gate.
2. `tests/test_investigation_prompt_builder.py::test_user_presents_the_investigation_context_evidence`
   — asserts the template's `evidence_instruction` appears in `pp.user`, but the comprehensive stage
   builder now renders a user message that ends after the evidence sections. Looks like the test
   trails a prompt-assembly change rather than a real regression; not yet diagnosed.

**A third failure is yours.** If you see mass failures instead, see the next section first.

### If the suite is suddenly red everywhere, it is probably not you

Rate limits are in-process and cumulative, and `app.main` exposes a module-level `app = create_app()`
that most test files import and **share**. `GlobalRateLimitMiddleware` builds its own limiter (120
requests / 60s) as an instance attribute on that shared middleware, keyed on the client IP — which
under `TestClient` is the constant `"testclient"`. So it used to count every request the entire
session made and then answer ~everything after the 120th with 429.

That presented as **118 failures/errors across ~25 unrelated files**, every one of which passed in
isolation, because the damage was indirect: a fixture's signup came back 429, its user row never
existed, and the test died later on `NoResultFound` — reading as a database or billing bug. Fixtures
that cleared `SIGNUP_LIMITER`/`LOGIN_LIMITER` were clearing the wrong objects; those are module
singletons, and the guilty limiter belonged to the middleware instance.

`tests/conftest.py` now resets **all** limiters around every test via
`app.core.rate_limit.reset_all_limiters_for_tests()`, which walks a `WeakSet` of every limiter ever
constructed so per-app-instance ones are reachable. Don't remove that fixture, and if you add a new
limiter it is registered automatically by `SlidingWindowLimiter.__init__`.

Related smell worth knowing: files that build their own app with `create_app()` were immune to all of
this; files doing `from app.main import app` were the victims. That shared-app import is also why
in-process state leaks between test files in general.

---

## Decisions that must not be undone

### Clerk runs entirely client-side

There is **no `clerkMiddleware`**, and **nothing on the server calls Clerk's `auth()`**. Next strips
secrets from the Edge runtime, so any server-side Clerk usage breaks the Render build or throws
*"auth() was called but Clerk can't detect usage of clerkMiddleware()"* at runtime. Instead:

- `components/shared/clerk-provider.tsx` is a `'use client'` provider.
- The server authenticates by forwarding the `__session` cookie to FastAPI, which verifies the JWT
  against Clerk's JWKS (RS256 — no secret needed). See `apps/api/app/core/clerk_auth.py`.
- `lib/api-server.ts` must never import from `@clerk/nextjs/server`.
- Use `useAuth()` on the client, never `<SignedIn>`/`<SignedOut>` (they call server `auth()`).

`pyjwt[crypto]` is a **required** dependency in `apps/api/pyproject.toml`. Without it
`verify_session_token` silently returns `None` and every login bounces back to the landing page.

### The analyst is batched, sequential, and progressive

For a selection larger than `analyst_batch_accounts` (25), `_generate_batched` in
`apps/api/app/reasoning/analyst.py`:

1. splits the payload into ordered ≤25-account chunks,
2. issues them **one at a time** (`analyst_batch_concurrency = 1`) — *not* in parallel,
3. persists the merged result the moment each batch lands,

so a 100-account investigation shows its first 25 accounts while 26–100 are still generating. The
route serves the merged-so-far entry with `status: "partial"`; `analyst-panel.tsx` renders it and
**resets its poll budget on every batch that arrives** (so `MAX_POLLS` means "10 minutes without
progress", not "10 minutes total"). Two indicators show progress: a strip above the results and a
trailing notice below them.

Three landmines here, all previously live bugs:

- **`get_session` must stay a module-level import in `analyst.py`.** It was imported inside
  `generate_and_persist`, which made it a local there; the nested persist closure resolved the name
  against module globals, found nothing, and raised `NameError` on the first persist — swallowed by
  the background pool. Net effect: *no investigation over 25 accounts ever produced an assessment*.
  Guarded by `test_get_session_is_importable_at_module_scope`.
- **`batching.complete` means "the run is over", not "every batch succeeded."** If a finished run
  stays incomplete, the route treats it as interrupted and resubmits a **full billable regeneration
  on every poll, forever**. `_merge_batch_parts(..., run_finished=True)` on the final merge is what
  prevents that.
- **Analyst work runs on `background.submit_slow`**, a pool of its own. It holds a worker for the
  whole run, and on the shared pool it starved the *scan* jobs.

### Evidence completeness — what the model is allowed to see

The analyst's verdict is only as good as the evidence assembled *before* the coverage budgeter
(120k tokens for a full investigation, with a disclosed omission manifest) ever runs. Anything cut
upstream of it is cut silently and is not in the manifest. Four such cuts existed, and together they
meant the model was judging accounts on almost nothing:

- **`CommenterScanResult` carries the raw profile metadata** — `follower_count`, `following_count`,
  `account_created_at`, `bio`, `verified`, `history_size`. `_account_evidence` reads exactly these
  keys; the schema didn't have them, so every account reached the model with `None` for all of them.
  Populate via `_profile_fields(record.profile)` at every construction site.
- **History goes to every tier.** `_activity_payload` used to return `[]` for LOW-tier accounts.
  "Reads like a real person" is what exonerates the ~80% of commenters who are genuine, and the
  empty list was indistinguishable from "this account has never posted". An empty list must now mean
  *only* that.
- **The caps track what we fetch.** `ACTIVITY_SAMPLE_LIMIT` (50) ≥ `scan_max_history_per_commenter`,
  and `_MAX_PER_ACCOUNT_SAMPLES` is 50 (was **4**). Post text is cut at 600 to match what the
  evidence layer renders. A tighter cut here is wasted API quota — fetched and then discarded.
- **A cache hit reuses the score, not the evidence.** `scan_refetch_evidence_for_cached` (default
  on) still pulls profile + history for cached accounts. With a 7-day TTL the recurring accounts are
  precisely the repeat offenders the fingerprint memory exists to catch, and they were arriving with
  an empty post list. Turning it off saves upstream calls on repeat accounts and makes their verdicts
  materially worse.

`bio` distinguishes `""` (the account has no bio — a real tell) from `None` (the platform never told
us). Don't collapse them.

### Mobile: the page is a column, never a canvas

Four rules in `globals.css` hold the phone layout together. They look like small CSS details and are
not:

- **`overflow-x: clip` on `html, body`** (with an `overflow-x: hidden` fallback for Safari < 16).
  `clip` rather than `hidden` on purpose — `hidden` creates a scroll container and breaks the sticky
  topbar. One overflowing child used to make the whole document pan sideways, which reads as a broken
  app: the sticky header stops short of the scrolled edge and content slides out from under the
  viewport. Anything genuinely wider than the screen (the posting heatmap, a wide table) scrolls
  inside its **own** `overflow-x-auto` container.
- **Form controls are 16px on touch screens** (`@media (max-width: 767px), (pointer: coarse)`). iOS
  Safari zooms the entire page when you focus a control under 16px and never zooms back out — that
  single tap is what leaves the app magnified and pannable. Do **not** "fix" this by disabling
  pinch-zoom; people who need to magnify must still be able to.
- **`touch-action: manipulation`** on interactive elements — removes Safari's ~300ms double-tap-zoom
  wait, which otherwise makes every button feel dead.
- **`.section-label` wraps** (`max-width: 100%`, `flex-wrap: wrap`). It is `inline-flex`, so it would
  not shrink below its content and spilled out of narrow columns to paint over its neighbours.

Layout rule that caused the worst of it: **never put a `shrink-0` action cluster beside a
`flex-1 min-w-0` text column without stacking on mobile.** The text column collapses to near-zero —
the investigation title rendered two characters per line ("Ba" / "I…") and its URL as "htt…". Stack
with `flex-col … sm:flex-row`.

Verified with Playwright at 360/375/390/430px: no sideways pan, account button on-screen, no
overlap, title at ~80% of viewport width, inputs computed at 16px.

### Scan watchdog scales with scan size

`reap_stale_scan_jobs` judges each job against `scan_job_budget_seconds(job.max_commenters,
settings)` — floor 300s, +12s/account, ceiling 1800s — not a flat number. A flat 300s budget against
a 100-account cap meant large scans were reaped **while still healthy**: refunded and reported failed
after their upstream calls were paid for, and the worker persists the investigation *before* it
reports success, so it could happen to a scan whose results were already saved. If a worker finishes
after being reaped it logs an error naming the investigation and account count — that means the
per-account allowance needs raising.

### Billing

`compute_scan_credits = ceil(accounts / 50) × credits_per_batch[platform]`, minimum 1. **1 credit per
50 accounts, same rate for X and YouTube** (100 accounts = 2 credits). This was an explicit product
decision; don't "fix" the asymmetry back in.

**There are two separate free tiers, and neither one is derived from the other.** Confusing them is
the easy mistake, because both get called "the free scans":

| | Who | Amount | Where it lives |
|---|---|---|---|
| Pre-login demo | Any visitor, metered per IP | **2 scans**, ≤25 accounts each | `DEMO_FREE_SCANS_PER_IP` + `DEMO_MAX_COMMENTERS`, hardcoded in `app/routes/scan_async.py` / `scan.py`, test-pinned |
| Signup trial | A new account | **3 credits**, then they pay | `OMI_FREE_TRIAL_CREDITS` in `render.yaml` (code default in `config.py` also 3) |

The signup trial was **25**, then 5, now **3** — an explicit product decision (2026-07). At the
1-credit-per-50-accounts rate with `OMI_SCAN_MAX_COMMENTERS=150`, 3 credits is one full 150-account
investigation *or* three small ≤50-account ones. Don't raise it back without being asked.

Two traps around this value:

- **It is set twice and nothing at runtime reconciles them.** The API grants
  `OMI_FREE_TRIAL_CREDITS`; the web service separately prints `NEXT_PUBLIC_TRIAL_CREDITS`, which Next
  inlines into the landing/pricing/sign-up copy at build time. Edit one and the site simply lies to
  customers. `tests/test_deployed_credit_contract.py` now fails on that drift (same check for the
  `*_MONTHLY_*` pair). Everything in the web app reads `lib/plan.ts`, so there is no third copy.
- **The Render dashboard can hold a different value than `render.yaml`.** A blueprint sync re-applies
  what is committed, so `render.yaml` is the source of truth and a hand-edited dashboard value is
  temporary. If the live grant disagrees with the repo, the repo wins on the next deploy.

The per-IP abuse guard (a signup from an IP that already claimed a trial gets 0) runs on **both** the
Clerk path (`app/core/auth.py`) and the legacy path (`app/routes/auth.py`). The 5/hour/IP signup rate
limit only guards legacy `POST /v1/auth/signup`; Clerk signups never touch it.

### Billing — Stripe ($9.99/mo → 20 credits), webhook-free

Setup walkthrough: `docs/stripe-setup.md`. **No webhook is configured.** `app/core/billing_sync.py`
reconciles against Stripe's API — it reads the customer's subscription and paid invoices and grants
any invoice not already credited. It runs on return from checkout (`POST /v1/billing/sync`, forced),
on the billing page (throttled 5 min/user), and — the one that matters — inside `consume_credits`
just before it would refuse a scan, so a subscriber whose renewal just landed is never told to
subscribe. It never raises: a Stripe outage degrades to the normal 402, never a broken scan.

The webhook endpoint still exists and is **inert without `OMI_STRIPE_WEBHOOK_SECRET`**. Enabling it
is safe — both paths claim the same per-invoice row, so only one can grant.

`GET /v1/billing/preflight` answers "can this deployment take a payment?" against the live Stripe
account: it validates the key, retrieves the price to confirm it is recurring and the right amount,
and checks the return URL. Point anyone debugging a "billing doesn't work" report at it first —
`OMI_STRIPE_SECRET_KEY` alone is NOT enough, and a missing `OMI_STRIPE_PRICE_ID` fails only at the
moment a customer clicks Subscribe.

Four rules in `app/routes/billing.py` that must not be softened — each replaces a bug that cost or
would have cost real money:

- **Only `invoice.paid` grants credits.** A new subscription emits `customer.subscription.created`
  *and* `invoice.paid`; granting on both double-credits one charge. Subscription events move status
  and renewal date only.
- **Credits are ADDED, never "topped up to N".** The old code did `max(balance, grant)`, so a
  subscriber renewing with ≥20 credits paid $9.99 and received **nothing**.
- **Exactly-once is a unique index, not an `if`.** Each grant claims a `grant:<invoice_id>` row in
  `billing_events` inside a SAVEPOINT. Event-id idempotency alone is insufficient — two *different*
  events can describe one payment.
- **Claim and work commit in ONE transaction.** Recording the event before running the handler meant
  a handler failure was retried by Stripe, skipped as a duplicate, and the customer got nothing.

Also: the webhook verifies with the SDK but then reads `json.loads(payload)`. In stripe ≥8 a
`StripeObject` is **not** a dict subclass and is not JSON-serializable — persisting one into
`payload_json` raised `TypeError` and 500'd *every real webhook* while passing any test that
hand-builds dicts. Don't put SDK objects in the DB.

The charged amount lives in the Stripe Price, never in this repo — the server sends a price id, so
no code bug can charge the wrong number. `OMI_PUBLIC_BASE_URL` must be the **web** host: it is where
Stripe returns the customer after payment.

### Free pre-login scan

Same select-then-scan shape as the signed-in app, X-only, capped at 25 repliers, **2 scans per IP**:

- `POST /v1/scan/demo/commenters` — compile (free, no auth)
- `POST /v1/scan/demo/score` — analyse the selection, runs the **real** engine + a real OpenRouter
  call, returns the assessment inline on `analyst_assessment`

The demo runs its analyst call **inline** because an anonymous scan has no saved investigation to
generate against in the background and poll. It's affordable because the free tier is exactly one
batch. Bounded by `demo_analyst_timeout_seconds` (120s) rather than the 500s a background run gets,
since a browser is waiting. Best-effort: a model failure still returns every deterministic score.

The 2-per-IP limit uses **reservations**: a row is written *before* the minutes-long scan and
confirmed or released after. Counting only finished scans left a time-of-check/time-of-use hole —
three tabs at once meant three free scans. Reservations expire after 20 minutes so a crash can't lock
a visitor out.

**Never look the anonymous candidate list up with `.scalar_one_or_none()`.** Use
`_demo_candidate_list()`. Anonymous compiles share one bucket (`CandidateList.user_id IS NULL`) so two
visitors on a post reuse one X fetch. `CandidateList` has
`UniqueConstraint("user_id", "platform", "content_id")`, which *looks* like it forbids a second row —
it does not: `user_id` is nullable and SQL treats NULLs as **distinct** (Postgres, i.e. production,
and SQLite). The constraint is silently inert for exactly these rows, so two concurrent compiles both
see "no list yet" and both insert. `scalar_one_or_none()` then raised `MultipleResultsFound` straight
out of the route as a **raw HTTP 500 on the front page** — permanently, since the rows persist, and
for every visitor, since the bucket is global. This shipped and was live.

`_demo_candidate_list()` picks the duplicate that already holds cached repliers (settling on the empty
one would silently re-fetch from X on every compile, paying for it each time), ties break on lowest id
so concurrent callers converge, and it best-effort deletes leftovers that hold **zero** candidates
(deleting a populated one would cascade its candidates away). Guarded by
`tests/test_demo_duplicate_candidate_list.py`.

Still open, deliberately out of scope for that fix: the signed-in compile/score paths
(`scan_async.py` ~L293 and ~L743) have the identical shape and are exposed the same way **whenever
`uid is None`**, which is local mode (`OMI_REQUIRE_AUTH=false`, the id=0 user). Production users have
real ids, so the constraint genuinely holds there and prod is unaffected.

---

## A bug class worth knowing

Python resolves a nested function's free variables against **module globals**, not the enclosing
function's local imports. A function-level `from x import y` does **not** make `y` visible to a
closure defined in a *different* function. This shipped once and disabled a whole feature silently,
because the background pool logs exceptions instead of raising them.

`python -m pyflakes app/` catches it in seconds. It currently reports **zero undefined names** —
keep it that way, and run it after touching anything that uses closures inside background work.

---

## Design system (don't drift)

Deep navy (`#09111f` / `#0e1728` / `#131e31`), blue identity (`#3b82f6` / `#5b9dff`), purple for the
AI layer (`#8f7bf0` / `#5b3fd8`), tier colours green→amber→orange→red (authentic→bot). **No glow, no
gradients, no glassmorphism.** Inter for interface (`.display`), JetBrains Mono for data/evidence.

**There is one display voice now: `.display` (Inter), on both sides of the login boundary.** The
pre-login page used to run a second voice (Space Grotesk, `.display-alt`) so it would read as
"marketing"; the effect was that the front page looked like a different product from the app a
visitor was about to sign into. Space Grotesk is no longer loaded at all (`app/layout.tsx`), so don't
reach for `.display-alt` — the class survives only as an Inter fallback so stray usage degrades
instead of breaking.

The landing page (`app/landing-page.tsx`) is deliberately built from the **signed-in app's** grammar,
not a marketing kit: the page-header slab from `/investigations` (rounded-2xl `bg-bg-elev`, top accent
hairline, blurred orbs, `.section-label` eyebrow, `.display` heading), figures in mono/tabular
(`.stat-value`), the real `Card` / `Button` / `Badge` / `TierBadge` primitives, and blue-compiles /
purple-analyses. `app/demo-scan-form.tsx` tracks `investigate/commenter-select.tsx` the same way
(same input material, HUD header, selection pip, action bar). If you restyle one, restyle both.

Two traps that bit here, both verified with Playwright at 360/375/390/430px:

- **`.section-label` is `inline-flex` + `flex-wrap: wrap` and already draws its own blue tick.** Give
  it a long label *and* a leading icon and the tick+icon orphan onto their own line on a phone. Keep
  the label short; hang status on a `Badge` beside it, which wraps as one piece.
- **No `overflow-hidden` on a page root that holds a sticky header** — it creates a scroll container
  and the header stops tracking the scrolled edge. Horizontal containment belongs to
  `overflow-x: clip` on `html, body` in `globals.css` (see the mobile section above).

Motion follows the `emil-design-eng` skill: transform/opacity only, custom easing
`cubic-bezier(0.23, 1, 0.32, 1)`, <300ms for UI, `scale(0.95)` never `scale(0)`, always
reduced-motion guarded.

Copy goes through `stop-slop`. The relevant skills are `stop-slop`, `ui-ux-pro-max`,
`emil-design-eng`, `human-crafted-design-auditor`.

---

## Outstanding — needs the user, not code

1. **Redeploy the API service.** Picks up `pyjwt[crypto]` (logins), the `get_session` fix (>25-account
   investigations produce an assessment at all), and the scan watchdog. Nothing else on this branch
   matters until this happens.
2. **Clerk dashboard:** Configure → User & authentication → Email, phone, username → **Username OFF,
   Phone Optional.** Otherwise sign-up dead-ends on `/sign-up/continue`. This is config, not code.
3. **Rotate the secrets** pasted into chat earlier in this session (`CLERK_SECRET_KEY`,
   `OMI_DATABASE_URL`, `OMI_TWITTER_API_KEY`, `OMI_YOUTUBE_API_KEY`, `OPENROUTER_API_KEY`,
   `OMI_SESSION_SECRET`). Never commit them.

### Unverified / worth measuring

- The watchdog's **12s/account** allowance is a reasoned estimate, not measured against the live X
  API. The post-reap error log exists to tell you if it's too tight.
- One flaky run of `test_compile_is_refused_once_the_budget_is_spent` was observed and could not be
  reproduced in seven subsequent runs. Its setup now asserts explicitly, so a recurrence will point
  at the real cause instead of the symptom.
- `scan_refetch_evidence_for_cached` costs upstream API calls on repeat accounts (the cache no
  longer saves the fetch, only the scoring). It is on because evidence completeness was the explicit
  goal; watch quota and flip it if that bites.
- Prompt/protocol quality with the widened evidence has not been observed against the live model —
  the model now receives far more per account than it ever has, and the preset may want revisiting
  once you can see real outputs.

---

## Environment notes

- `cryptography` is broken **in this sandbox only** (`_cffi_backend` missing). `clerk_auth.py` imports
  `jwt` lazily so the app still boots locally; verify RS256 work in a clean venv, not here.
- Outbound HTTPS goes through an agent proxy (`/root/.ccr/README.md`). Never disable TLS verification.
- No `gh` CLI — use the `mcp__github__*` tools.
