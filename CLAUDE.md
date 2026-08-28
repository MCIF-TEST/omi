# CLAUDE.md — OmiSphere working notes & session handoff

**Living document.** Update it in the same commit as the change it describes. It is the first thing a
new Claude Code session reads, and the only place that explains *why* several non-obvious things are
the way they are. If you change behaviour and don't update this file, the next session will
re-introduce a bug this one already paid for.

**Last updated:** 2026-08-25 · branch `claude/omisphere-social-integrity-ch9b9s`, built on `main`
after PR [#184](https://github.com/MCIF-TEST/omi/pull/184) merged. This session added the **cohort
coordination detector** (`app/campaigns/detector/`, `/narratives`, `/v1/admin/coordination`) — see
"The cohort coordination detector" below, and read its two rules before touching any threshold.
A second session then rebuilt scoring as a calibrated probability and added the planet-scale
tracking layer; read "The probability model" and "The planet-scale layer" below before touching a
likelihood ratio. A third session made the analyst explain its own failures and stop losing work to
them: read "Why a floor happens" below before changing a retry rule. A fourth session built the
**agent surface** (markdown negotiation, addressable `.md` pages, llms.txt, structured API errors,
per-request canonical links); read "The agent surface" below before touching anything that a machine
rather than a person reads, and note that `OMI_PUBLIC_BASE_URL` is now required to BUILD the web app.
The same session then built the **cross-investigation coordination system** (`app/narrative/cross/`,
`/v1/admin/cross-narratives`); read "Cross-investigation narratives" below, and its §1 in
`docs/cross-investigation-narratives.md`, before touching a threshold there. A fifth session then
went back to `app/netdetect/`: it was **not deterministic across processes** (a set of dataclasses
iterating in hash order set the null threshold), reposts and topics were reaching no feature, and the
detector was read-only so nothing accumulated and nothing could be dismissed. Read "The network
detector" below before touching a threshold or a set iteration there.

Suite measured at **2448
passed, 8 skipped, 2 failed** (13m05s, 2026-08-28), both failures pre-existing and listed below. The 8
skips are the corpus-backed tests — see "The dataset corpus is not in git".

> Several sessions work this repo in parallel (Claude Code sessions and Grok). Before starting, check
> whether `main` has moved: this branch's PR has merged once already, and a branch that is `0 ahead /
> N behind` means your work landed and you should restart from `origin/main` rather than build on it.

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
| `ml/` | Prompt mirrors + the offline training pipeline. Drift-guarded against `apps/api`. |
| `datasets/` | Training corpus — **not committed** (gitignored; see "The dataset corpus is not in git"). |
| `docs/` | Architecture, design system, ops. |

### Commands

```bash
# backend  (from apps/api)
python -m pytest -q                 # full suite, ~4½ min
python -m pyflakes app/             # catches undefined names — see "Bug class" below

# web  (from apps/web)
npx tsc --noEmit && npx next lint
CLERK_SECRET_KEY= NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY=pk_test_Y2xlcmsuZXhhbXBsZS5jb20k \
  OMI_PUBLIC_BASE_URL=https://omisphere.online npx next build
npx vitest run                      # web unit tests
```

`OMI_PUBLIC_BASE_URL` is required at BUILD time: it is baked into the canonical links, the
sitemap, llms.txt and the JSON-LD, and an absent one used to publish `localhost` URLs silently
(see "The agent surface" below). The build command deliberately runs with **`CLERK_SECRET_KEY` unset** — that must keep working (see
Clerk below). A malformed publishable key fails prerender with a confusing error, so use the
well-formed dummy above rather than something like `pk_test_x`.

---

## Known-failing tests (pre-existing, not yours)

Current measured state: **2448 passed, 8 skipped, 2 failed** (13m05s, 2026-08-28), both documented below:

1. `tests/test_investigation_prompt_builder.py::test_user_presents_the_investigation_context_evidence`
   — asserts the template's `evidence_instruction` appears in `pp.user`, but the comprehensive stage
   builder now renders a user message that ends after the evidence sections. Looks like the test
   trails a prompt-assembly change rather than a real regression; not yet diagnosed.

2. `tests/test_evaluation_benchmark.py::test_accuracy_gate_no_regression` — Brier 0.0321 against a
   0.032 gate. **Did NOT fire in the 2026-08-07 or 2026-08-15 runs**, having failed consistently
   before. Nothing in either session touched scoring, so treat it as order-dependent rather than
   fixed, and do not read its absence as a licence to tighten the gate.

**A second failure is yours.** If you see mass failures instead, see the next section first.

**Count depends on collection order.** A run during the launch-readiness work reported *13* failures;
11 of those were order-dependent analyst tests that adding new test files shifted into a different
order, not regressions. Item 2 above is the same effect. If you see extra failures, re-run the
specific files in isolation before believing you caused them — and note that this order sensitivity
is itself a latent problem nobody has fixed yet.

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

## Production boot fails closed (don't soften these)

`_validate_production_config` in `app/main.py` refuses the deploy rather than starting degraded. Two of
its checks exist because the insecure state used to be the *default*:

- **`OMI_REQUIRE_AUTH` must be true in production.** When false, `require_user()` does not reject — it
  *returns* `CurrentUser(id=0, is_admin=True, credits=999999)`. So a missing env var served every
  anonymous caller as an admin, with the admin routers, `/v1/metrics`, credit exemption and rate-limit
  exemption all included. It was previously unchecked, and worse: the session-secret check was gated on
  `if settings.require_auth`, so auth being off skipped its own validation.
- **`OMI_ENV` must be one of `_KNOWN_ENVS`.** Every production check is gated on `env == "production"`
  by exact string, so `prod`, `Production`, or an absent value silently bought CORS `*` plus a total
  skip of the storage / secret / API-key checks. An unrecognised value is now a boot error, and
  `OMI_ALLOW_DEGRADED_PRODUCTION` deliberately does **not** excuse it — a typo is not a degraded mode.

Pinned by `tests/test_production_config_fails_closed.py`. Note `test_production_config.py` previously
contained `test_session_secret_not_checked_when_auth_disabled`, which asserted the bypass was fine; it
now asserts the refusal.

## The archive list must never load `payload_json`

`Investigation.payload_json` holds the whole scan result (every commenter's scores, evidence, posts,
analyst sections) and the archive page requests **100 rows**. The list used to `select(Investigation)`
and read the blob per row just to resolve a platform string and a thumbnail, so one page load
deserialised megabytes per row — worst for the heaviest users, who are the best customers.

`platform` and `thumbnail_url` are now **columns**, denormalised at write time by
`repository._set_list_fields()` (free: the payload is already in memory there), and
`list_user_investigations` uses `load_only()`. The trap: with `load_only()` in place, *reading*
`inv.payload_json` in the summary builder lazy-loads the blob one row at a time — an N+1, strictly worse
than the original. So `routes/investigations._platform_of` / `_youtube_video_id` / `_thumbnail_of` are
deliberately payload-free and fall back to URL/`target_id` heuristics for pre-migration rows. Guarded by
`tests/test_investigation_list_does_not_load_payload.py`, which asserts against the **SQL actually
emitted**, not by inspection.

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

#### Both services must name the same Clerk instance, and nothing at runtime checks that

This was live on omisphere.online. The browser gets `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY` from the
**web** service and signs the user in; the API gets `CLERK_PUBLISHABLE_KEY` from the **API** service,
base64-decodes it (a key is `pk_(test|live)_<base64(frontend_api_host + '$')>`) and verifies every
session JWT against that issuer's JWKS. Two services, two copies, no reconciliation.

Switch one to the production keys and not the other and the result reads as a network fault and is
not one: sign-in succeeds, a valid JWT is minted by `clerk.omisphere.online`, and the API rejects it
because it still expects `sweet-finch-45.clerk.accounts.dev`. `verify_session_token` swallows the
mismatch and returns `None` (an unverifiable token is normally just an anonymous request), so there
is **no log line, no 5xx, no failed health check**. The only symptom is the user being told they are
signed in with no workspace.

Three things now hold it together:

- **`render.yaml` commits the key as a `value:` on both services, and they must be byte-identical.**
  A blueprint sync re-applies what is committed, so a dashboard edit that disagrees is temporary:
  fixing this in the Render dashboard alone gets silently undone on the next sync. The web service
  genuinely needs it at build time (the static prerender throws "Missing publishableKey"), which is
  why neither side is `sync: false`.
- **`_clerk_instance_problem` (`app/main.py`) refuses the boot** of a production deploy holding a
  `pk_test_` key, alongside the other fail-closed checks. `CLERK_ISSUER` overrides the key-derived
  issuer, so when it is set it is what gets checked. An **absent** key is deliberately not fatal:
  Clerk is optional here (the legacy cookie path still authenticates) and `render.yaml` always
  commits one, so failing on absence would add a way to brick a deploy without catching a bug.
- **`tests/test_clerk_instance_pairing.py`** (13 tests) asserts the two committed values match, that
  the API's is `pk_live_`, and that it decodes to the host `clerk_auth._issuer` will actually use.
  The decode assertion matters on its own: a typo in the base64 passes a `startswith` check and just
  points the API at a host that does not exist, failing every login with the same silent `None`.

**Changing the key needs a redeploy of both services, not a restart of one.** `_ISSUER` and
`_JWKS_CLIENT` are module globals cached for the life of the process.

#### The CSP has to name the production Clerk instance, and it is derived, not hardcoded

Second half of the same outage, and it hit immediately after the keys were fixed. A **development**
Clerk instance serves clerk-js and its Frontend API from `<slug>.clerk.accounts.dev`, which the
static wildcards in `middleware.ts` covered. A **production** instance serves both from the
customer's own subdomain, `clerk.omisphere.online`. A subdomain is a separate origin, so `'self'`
does not cover it and neither does `https://*.clerk.com`.

So the pk_live deploy had its Clerk script blocked outright, and the symptom named nothing: `useAuth()
.isLoaded` never turned true, so `AuthFormGate` held its spinner and `/sign-in` span forever with no
error on the page and nothing server-side at all. The only evidence was a CSP violation in the
browser console.

- **`clerkOrigins()` derives the origins from `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY`** and feeds
  `script-src` / `connect-src` / `img-src` / `frame-src` / `form-action`, so the policy follows the
  instance instead of having to be remembered on the day the keys change. It also adds
  `accounts.<domain>` (the Account Portal, which OAuth and email links hand off to) when the
  Frontend API is `clerk.<domain>`. A malformed key widens nothing: the decode is validated against a
  hostname pattern and discarded otherwise.
- **`atob` needs exact padding.** The live key's payload is 31 characters and needs ONE `=`; the
  obvious `atob(raw + '==')` throws and silently produced no origins at all. Python's `b64decode` on
  the API side is lenient about the extra padding, which is why the same line is correct there and
  wrong here.
- **The static dev hosts stay**, so a pk_test preview deploy keeps working.
- **`AuthFormGate` gives up after 12s** and says the form could not load. A spinner with no terminal
  state is not a loading state, it is a silent failure, and this one cost a live hour.

Pinned by `apps/web/middleware.test.ts` and `lib/clerk-origin.test.ts`, which assert the derived
origin lands in every directive that needs it. Note the key is inlined into the Edge bundle at BUILD
time, so changing it needs a rebuild of the web service, not a restart.

#### Three reasons the sign-in form does not load, and only one is the visitor's problem

`AuthFormGate`'s timeout used to say one thing for all of them: *check your network or extensions
blocking third-party scripts*. That advice is actively wrong for two of the three, and sends someone
to debug a machine that is working. It now distinguishes:

- **`blocked`** — a CSP violation naming the Clerk host. This is the cause with **no other evidence
  anywhere**: no server log, no failed health check, nothing on the page, only a line in the browser
  console. That is what made it cost an hour. `AuthFormGate` now listens for
  `securitypolicyviolation` and says so. The listener is registered on mount and clerk-js is fetched
  after hydration, so it is normally in place first; if a violation beats it, the generic message
  stands rather than a wrong claim.
- **`misconfigured`** — `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY` was empty at BUILD time, so the bundle
  has no instance to talk to. Reloading cannot help, so that branch does not offer the button.
- **`unreachable`** — everything is configured and the host did not answer.

**The production instance's host is a CNAME, so sign-in has a hard dependency on the DNS for
`omisphere.online`.** Observed 2026-08-15: a Namecheap resolver outage in the user's region made
`clerk.omisphere.online` fail to resolve, and the entire symptom was this notice. **Nothing
server-side can see it** — the API is healthy, the web service is healthy, and the failure is
between one visitor's resolver and a hostname we do not serve. So before debugging the app, check
that the host resolves (`dig clerk.omisphere.online`) and check the DNS provider's status page. The
notice now prints the host for exactly that reason, and no longer blames the reader's extensions
first.

The decode itself lives in `apps/web/lib/clerk-origin.ts`, shared by the middleware (which needs the
ORIGINS for the CSP) and the gate (which needs the HOST to name in the message). A malformed key
yields nothing rather than a string concatenated into a security directive.

#### Switching instances gives every user a new Clerk id, and the local row must re-point

A Clerk development instance and a production instance are **separate user pools**; nothing migrates
between them. So on the switch every existing user signs in with a Clerk id the database has never
seen, `_resolve_clerk_user`'s `clerk_user_id` lookup misses, and the account is found **by email**
instead, which is what carries their credits, investigations and subscription across.

That email link used to be written only `if not existing.clerk_user_id`, so a row still holding its
*development* id was never updated. It still resolved to the right account, but only through the
email path, meaning **every request** re-resolved the user through the Clerk Backend API, and the one
time that call failed (rotated secret, Clerk outage) `email` came back `None` and the create branch
below minted an **empty duplicate account** for someone with a subscription. It now re-points, which
is safe by construction: the lookup above already proved no row holds the new id, so the unique index
cannot collide.

Two more things on that path:

- **`is_admin` is granted from `OMI_SUPER_ADMIN_EMAILS` at CREATION only**, and this path skips
  creation. Without the re-grant the owner comes back from the switch as an ordinary customer: no
  `/disputes`, no `/narratives`, no signal breakdown on their own investigations.
- **The `sk_live_` `CLERK_SECRET_KEY` must be on the API service BEFORE anyone signs in.** Clerk
  session tokens carry no email, so the email that performs the link comes from the Backend API. With
  the wrong or missing secret the very first production sign-in creates a placeholder account instead
  of finding the real one.

Pinned by the last four tests in `tests/test_clerk_provisioning.py`.

### The analyst is batched, sequential, and progressive

For a selection larger than `analyst_batch_accounts` (**25**, in code and on the deployment),
`_generate_batched` in `apps/api/app/reasoning/analyst.py`:

1. splits the payload into ordered chunks of **`analyst_batch_accounts` (25)**, remainder last,
2. issues them **one at a time** (`analyst_batch_concurrency = 1`) — *not* in parallel,
3. persists the merged result the moment each batch lands,

so a 100-account investigation shows its first 25 accounts while 26–100 are still generating. The
route serves the merged-so-far entry with `status: "partial"`; `analyst-panel.tsx` renders it and
**resets its poll budget on every batch that arrives** (so `MAX_POLLS` means "10 minutes without
progress", not "10 minutes total"). Two indicators show progress: a strip above the results and a
trailing notice below them.

**The split is a fixed SIZE, and the remainder takes its own request.** 100 accounts is 4 calls of
25, 200 is 8 of 25, 92 is 25/25/25/17. `app/reasoning/batch_plan.py` owns the arithmetic
(`plan_batches`), and `apps/web/lib/analysis-progress.ts` mirrors it in `batchesFor`.

**The size is what bounds the request, and the request is what fails.** A revision in between divided
the selection into a fixed NUMBER of batches (4), which made the size grow with the selection
instead: a live 197-account scan became four calls of roughly 50 accounts and **every one came back
empty within about thirty seconds**. 25 per call is measured working on this deployment. A larger
scan must mean more requests, never a larger request. There is no batch-count setting any more.

**Progress is ONE record, not three counters.** `batching.batches` is a per-batch list
(`index` / `state` / `accounts`) written by `_merge_batch_parts`, and `RunPlan` in `batch_plan.py`
derives every number anyone wants from it. The three legacy keys remain for entries written before
the record existed:

| key | means | the bug when it was read as another |
|---|---|---|
| `done` | batches ATTEMPTED | the strip said "3 of 4 done" beside 25 accounts |
| `landed` | batches that PRODUCED accounts | a floored batch counted as landed, so the incomplete-coverage notice could never fire |
| `model_backed` | is the prose the model's | a mixed run rendered as a total failure |

They look interchangeable and they are not. Anything new reads `batching.batches`; the UI already
prefers it (`batchStates(..., record)`) and only falls back to inference for older entries.

Three landmines here, all previously live bugs:Three landmines here, all previously live bugs:

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

### The eight signals are scored by the MODEL, not the engine

Product direction (2026-07-29): per-signal scoring is back, but the **model** produces it. Every
account in `commenter_assessments` now carries `signals` (exactly eight) and `confidence` alongside
its `omi_score`. The detector still computes its own signals underneath and is still what
`OmiScore` is built from; nothing in the UI surfaces those any more.

```
temporal · semantic · ai_writing · profile · voice · engagement · account_maturity · history_authenticity
```

Six carry over from the old heuristics engine. **`memory` and `coordination` were deliberately
dropped** and `account_maturity` / `history_authenticity` put in their place: the model sees one
account's raw metadata and history, so a cross-scan fingerprint match and a cross-account
coordination read are things it cannot derive. Asking it to score them would have produced
confident fabrication in the two slots a customer is least able to check.

Four things here that must not be undone:

- **`score: null` is not `0`.** Null means the evidence that dimension needs was never collected
  (rhythm cannot be read off an account with no posting history). Zero means "this dimension looks
  like a real person". The schema is `["integer", "null"]` on purpose, `_normalise_signals` preserves
  the distinction, and the UI renders `n/a` over an empty track rather than a low-tier bar. Collapsing
  them turns "we could not tell" into an exoneration.
- **All eight, always, in canonical order.** `_normalise_signals` (`analyst.py`) drops unknown names,
  keeps the first of any duplicate, and materialises anything the model omitted as `score: None`. That
  is what lets `SignalBreakdown` render eight rows unconditionally instead of branching per account.
  An optional or short list would let the model quietly skip the dimensions it finds hardest, which
  are exactly the ones a reader wants explained.
- **The name list is declared twice, in two languages, and nothing at runtime reconciles them.**
  `COMPREHENSIVE_SIGNAL_NAMES` (Python) against `ACCOUNT_SIGNAL_KEYS` + `ACCOUNT_SIGNAL_META`
  (`apps/web/lib/api.ts`). Rename one side and the frontend's metadata lookup misses, the row is
  filtered out, and the account silently renders with seven dimensions and no error anywhere.
  `tests/test_signal_names_contract.py` fails on that drift, including order.
- **`confidence` is an integer and may not be null.** How much evidence arrived is always knowable,
  unlike an individual dimension's score.

**The coercion layer used to be a silent field shredder, and this cost a whole feature once.**
`coerce_comprehensive_model_output` (`app/governor/comprehensive.py`) rebuilds each per-account row
before the echo-join. It did that from a **hardcoded four-field allow-list**
(`ref` / `omi_score` / `suspicion_tier` / `assessment` + optional `citations`), so `signals` and
`confidence` arrived from the model and left deleted. Everything downstream worked perfectly on the
empty input: `_normalise_signals` dutifully materialised eight `None` rows and the UI rendered eight
`n/a`s for every account, with nothing failing anywhere to say so. It shipped green because the
tests covered the two ends (the schema declares the fields; `_normalise_signals` works in isolation)
and nothing asserted the middle.

The passthrough is now **driven by the item schema**, so a field added later cannot be lost by
anyone forgetting that line. Two rules follow:

- **Assert against the SERVED assessment, not an intermediate.** `test_commenter_assessments.py`
  now runs the full `assess_payload` path with a mocked transport for every signal case.
  `test_the_coercion_passes_through_every_declared_per_account_field` is the class-level guard.
- The **evidence-item** loop right above it still uses a hardcoded keep list
  (`signal`/`claim`/`evidence_refs` + `direction`/`impact`). That currently covers every property in
  its schema, so there is no bug today, but it is the same latent trap. Add a field to the evidence
  item schema and you must add it there too.

Verified behaviour on malformed model output (none of it floors the investigation, each account
degrades alone): 7 signals returned renders 8 with the last null; an unknown dimension name is
dropped and its slot left unscored; 900 clamps to 100; 42.7 rounds to 43; an explicit null survives
as null; `signals: "not-a-list"` gives eight nulls and leaves neighbouring accounts untouched.

`SignalBreakdown` (`components/shared/signal-breakdown.tsx`) is shared by the signed-in investigation
view and the pre-login demo, so the free scan shows the same eight. The demo falls back to the engine
list only when the analyst produced nothing, which is the documented degraded case (a model failure
still returns every deterministic score, and a free scan must not come back empty).

The **live model will not emit any of this until the recompiled protocol is pasted into the
OpenRouter preset** (`omi-master-v1`). Until then the schema accepts the old shape, every account
renders without a breakdown, and nothing errors.

### The breakdown is admin-only while it is unfinished

Product decision (2026-07-29): a customer sees each account's OMI score, tier and written read. The
eight-dimension scoring behind it is **admin-only** for now. `ADMIN_ONLY_ACCOUNT_FIELDS` in
`analyst.py` is the whole gate (`signals` + `confidence`); empty that set to ship the feature.

**Filtered on SERVE, never on persist**, and that is the load-bearing part. The signals stay in
`payload_json`, so the day the breakdown ships every investigation already generated has one and no
model output anyone paid for is discarded. Stripping at persist time would make the gate irreversible
for all history. It also stops a 150-account investigation shipping ~150 KB of JSON the page renders
nowhere.

`assessment_for_viewer()` returns a **copy**, including new row dicts. It is handed the live
`payload_json` object, so filtering in place would strip the signals from the row SQLAlchemy may flush
back: one customer page view would permanently delete the data, for admins too.

Applied at all four return sites in `routes/reasoning.py`, and hardcoded `is_admin=False` on the demo
(`scan_async._demo_assessment`) because that route is unauthenticated and `True` must not be reachable
there. `tests/test_signals_are_admin_only.py` includes a **source-level guard** that fails if any route
reads `entry["assessment"]` without passing it through the filter, since a fifth return path added
later would leak silently.

No frontend gate is needed: `SignalBreakdown` already renders nothing when `signals` is absent, which
is also how it handles investigations generated before per-signal scoring existed.

### Getting the results out: CSV and clipboard

`ExportResults` (`components/shared/export-results.tsx`) sits in the analyst card's header on
`/investigations/<slug>` and offers two buttons over the same table: **Copy table** (TSV to the
clipboard) and **CSV** (a downloaded file). `lib/investigation-export.ts` holds the pure half, pinned
by `lib/investigation-export.test.ts` (23 tests).

Five decisions in there:

- **The engine's account list is the spine, not the analyst's.** A batched run can finish having
  skipped accounts the model never returned, and the customer paid a credit for those. They export
  with their engine tier and a blank `omi_score`, which reads as "scanned, not assessed". An export
  built from `commenter_assessments` alone would be quietly smaller than the investigation.
- **The columns follow the data, never a second copy of the gate.** `confidence` and the eight
  `signal_*` columns appear only when the served rows carry them, which is the same thing as "only
  for an admin, until the breakdown ships". A hardcoded column list is the field-shredding trap
  `coerce_comprehensive_model_output` already paid for once.
- **The rows are projected on the SERVER** (`scannedAccountsFrom`, called in `page.tsx`).
  `inv.payload` is the whole stored scan and the page renders none of it; passing it to a client
  component would serialise megabytes into the HTML for a button most visits never press.
- **The CSV opens with a BOM.** Excel on Windows reads a BOM-less UTF-8 file as the local codepage
  and mangles every non-Latin handle, and this data has plenty.
- **CSV quotes, TSV flattens.** A pasted verdict containing a newline or a tab would explode into
  extra cells and rows in a spreadsheet, so the clipboard path collapses whitespace; the CSV keeps
  the text intact because RFC 4180 quoting can carry it.

The join is on `external_id`, never the handle. Sorted worst first, which every surface now agrees
on: see "Every list of accounts leads with the worst one" below.

### Every list of accounts leads with the worst one

The shared report, the markdown export, the CSV and the pre-login demo all sorted highest OMI score
first. The signed-in investigation page did not: it rendered in BATCH order, which is a consequence
of how a scan runs rather than a decision about what a reader wants. On a 100-account scan the
highest-scoring account sat wherever it happened to be selected, so the finding the customer opened
the page for was the one thing they had to scroll for.

`lib/rank-accounts.ts` is the rule, pure and pinned by `lib/rank-accounts.test.ts`. Two things in it
that a one-line inline sort gets wrong:

- **An unscored account sorts LAST, never as a zero.** A missing `omi_score` means the analyst never
  read that account (a floored batch, a row the model skipped), which is not the same claim as "this
  account looks like a real person". `(b.omi_score ?? 0) - (a.omi_score ?? 0)` would file an
  unassessed account among the most exonerated ones on the page. Same distinction as `score: null`
  on the eight signals.
- **Ties keep their existing order**, and it must stay a stable sort: the list re-renders every time
  a batch lands, and accounts on the same score shuffling between polls reads as instability.

It returns a copy. The panel holds that list in React state and `ExportResults` builds its own rows
from the same array, so sorting in place would reorder it underneath both.

### Score discipline: a high score has to be earned (constitution v9)

The analyst was too willing to hand out elevated and high scores. The fix is deliberately **not** a cap
on the numbers, which would just relocate the error. `_SCORE_DISCIPLINE` (`constitution.py`) makes a
high score expensive to reach:

- **Start from the base rate.** Most commenters are real. Every account starts low and moves up only as
  named cells force it.
- **The two errors are not equal.** Calling a real person bought is the expensive mistake, because the
  customer cannot check it and one bad high score discredits every other number on the page. On
  balanced evidence the lower score is *correct*, not merely cautious.
- **Ambient traits vs discriminative evidence.** Few followers, a new account, no bio, unverified,
  short or enthusiastic comments, emoji, agreement, fluent or formal prose, consistent posting hours, a
  plain handle: all ordinary among real people, all named individually, and they cap the account in the
  moderate band however many you stack. Fluent writing is called out explicitly, since treating it as a
  tell systematically misjudges people who write well and second-language speakers (who often write
  *more* formally, not less).
- **Convergence by band.** 50-74 needs two *independent* discriminative indicators; 75-100 needs several
  converging plus a statable reason the innocent explanation fails. Three restatements of one
  observation count once.
- **The alternative-explanation test** gates anything at 50 or above, and **thin evidence caps at 49**
  (an account whose history was never collected cannot be strongly accused on profile metadata alone).
- **No contagion**, and a **distribution self-check** as step (5) of the Dossier Loop: a mostly-high run
  is more often a calibration failure than a captured section.

Two things this also fixed: the worked example used to score A3 at 55 *explicitly because its wording
echoed another promotional account*, teaching exactly the contagion the protocol forbids (now a capped
moderate read that names what was not collected); and the constitution block count moved 15 → 16, which
is pinned in `test_ai_readiness.py`.

### Write so a stranger can verify you (constitution v10)

**The results get posted publicly, into Twitter comment sections, about named real accounts.** That is
the design constraint behind v10, and it should stay in mind for anything touching the analyst's prose:
a per-account sentence is not a dashboard readout, it is a published claim about a person who can read
it. A false positive is a harm to them and it discredits every other score in the same report.

`_CHECKABLE_CLAIMS`:

- **Compute, do not eyeball.** State the following-to-followers ratio as a figure, the age in days or
  years, the post count as a number. LLMs are unreliable at ratio and date arithmetic and will
  cheerfully describe an imbalance that is not there; forcing the computed number improves the
  reasoning *and* makes the claim auditable.
- **Quote, do not paraphrase.** Any claim about what an account wrote carries a short verbatim quote.
  "If you cannot quote it, you cannot claim it."
- **The hedge goes in the words, not only in the number.** A sentence gets screenshotted without the
  confidence score beside it, so thin evidence has to be admitted *in the sentence*.
- **Name what would overturn it** for anything at 50 or above. This is what makes it a finding rather
  than an accusation.
- **Never assert identity or intent**, and never imply knowledge of ownership, payment, networks, DMs,
  or other platforms. None of that is in the bundle.

`_CONFUSABLE_ACCOUNTS` names the legitimate shapes that resemble the tells, because a generic
instruction to be careful does not stop a model reading a small fan account as a farm: a business or
brand, a fan/hobby account, a news or aggregator feed, a real person who is new, a dormant account
that came back, a private person with a tiny footprint, someone writing in a second language or a
non-Latin script (**digits in a handle are auto-appended by platforms and are never a tell**), and an
account whose opinion is unpopular or which simply agrees with the post. Recognising one is framed as
a **correct finding**, not a failure to find something, so the model does not reach for a score.

Dossier Loop gained step **(3c) coherence**: the `omi_score` must be explainable by the eight
dimensions, and when the number is high and the dimensions are not, *the number is wrong*.

**The worked example was contradicting the schema.** It showed all eight signals for A1 and **none**
for A2 and A3, while the schema declares them required on every account. Models copy examples over
schemas, so that was an open invitation to skip the block. All three accounts now carry eight, and the
example teaches the semantics: A2 (82, high) has six elevated dimensions on different kinds of evidence
plus one honest `null` (four posts is too few to read a rhythm), while A3 (38, moderate) has five
`null`s and confidence 30, demonstrating that a null-heavy list must drag confidence down.

`BANNED_PHRASES` extended with certainty ("proves that", "undoubtedly"), identity and intent ("was
hired", "is operated by", "real identity"). **Note its reach:** the Governor's S9 lint sees only the
investigation-level `headline`/`assessment`/evidence claims, *not* `commenter_assessments[].assessment`,
and the comprehensive path runs `adjudication="schema_only"` so the Governor is not gating the model's
prose at all on the live route. **The protocol is the only real control today.** Extending enforcement
to per-account text is worth doing and is not done.

Pinned by `tests/test_score_discipline.py` (53 tests). Protocol recompiled to
**`map:ac15ee80f4237b3276877ed6`, 84,116 chars**, zero em dashes, all drift guards green. Pins moved:
constitution block count 16 → 18, `package_hash` → `pkg:eacb6bf1831418d1eb49d95d`.

**Cost note:** the protocol has grown 64,808 → 84,116 chars (roughly 21k input tokens) and is sent on
every batch, so a 150-account investigation pays it six times. Worth watching if OpenRouter spend
climbs, and worth resisting the urge to keep appending doctrine: past some length the model follows
each individual instruction *less* reliably, so additions should replace rather than accumulate.

### What actually goes on the OpenRouter wire

Worth knowing before anyone tries to "also send the prompt": **the local system prompt is never sent
to OpenRouter.** `OpenRouterReasoningProvider._request_body` builds `messages = [{"role": "user",
...}]` and nothing else. The dashboard preset `omi-master-v1` holds the compiled protocol, the
request carries only the evidence, and OpenRouter joins them.

That is correct and must stay: `compile_master_analyst_protocol().text` is byte-identical to
`pp.system` (test-pinned), so the preset content IS the local protocol. Sending both would put the
same ~20k tokens on every request twice, for nothing. The HF path still receives system+user.

The cost of that design is that **preset drift is undetectable**: paste an old protocol, or edit it
in the dashboard, and every scan silently runs on the wrong instructions. Omi records the hash it
EXPECTS (`master_prompt_hash` on the trace) but cannot read the remote preset to compare.

Because the preset owns the instructions, the operative task sits ~20k tokens behind the evidence by
the time the model reads it. So `_closing_directive` (`prompt/stage_builder.py`) appends a short tail
to the USER message, after the alias legend, restating only the constraints that fail in practice.
The load-bearing line names the exact aliases and the exact count: a model handed 25 accounts
sometimes returns 21, and without the expected set stated it cannot notice, whereas we could detect
the shortfall but not fix it. Keep the tail under ~900 chars (pinned): it rides on every request, so
unlike the preset it is a per-scan cost.

`docs/openrouter-wire-example.md` is a generated, readable dump of both halves plus the HTTP body.

### The analyst's prose is verified against the evidence, deterministically

`BANNED_PHRASES` never reached `commenter_assessments[].assessment`, and the comprehensive path runs
`adjudication="schema_only"`, so nothing at all inspected the sentences that actually get
screenshotted. The protocol was the only control, and asking a model nicely is not a control.

`app/reasoning/grounding.py` runs at the join in `_join_commenter_assessments`, which is the one place
holding BOTH the model's prose and the account's ground truth (`recent_activity`, `bio`,
`follower_count`, `following_count`, `account_created_at`, `history_size`). Every check is a
comparison between those two: no model call, no network, no guessing at what "sounds" wrong.

- **Quotes** are matched against what the account actually posted. This is the check worth having if
  you only have one: an invented quotation asserts a named person wrote words they never wrote, and
  the reader cannot tell. Truncated quotes match on the head, so honest shortening is not punished.
- **Figures** (followers, following, posts, age, ratio) are compared against the real metadata.
  `_CHECKABLE_CLAIMS` forced the number into the sentence to make the error auditable; this catches it.
- **Banned phrasing**, **boilerplate** (5-shingle Jaccard across the batch), **readability** (sentence
  length, a short jargon list) and **score coherence** (Dossier Loop 3c, previously unenforced).

**HARD violations withhold the paragraph**: it moves to `assessment_unverified`, `assessment` becomes
an honest notice, and confidence is capped at 40. SOFT violations never suppress anything.

Three things not to undo:

- **The replacement happens at JOIN, not at serve.** That is the opposite of the signal gate, and
  deliberately: that gate hides a finished feature and must stay reversible, while this removes a
  claim the evidence does not support, and there is no viewer who should be shown that. Nothing is
  deleted, so an operator can always see what the model said and why it was refused.
- **`NEVER_PUBLIC_ACCOUNT_FIELDS` is a separate set from `ADMIN_ONLY_ACCOUNT_FIELDS`.** A test caught
  this: folding `grounding` / `assessment_unverified` into the signal gate would mean emptying that
  set to ship the breakdown ALSO releases the refused paragraphs.
- **Quote detection keys on the speech verb, not just length.** Length alone cannot separate an
  excerpt from scare-quoting: "engagement farming" is 18 characters and quotes nobody, while
  `wrote "buy my course"` is a 3-word attributed claim that must be checked.

The protocol now tells the model the check exists, which is the strongest prompt lever available
(models comply far better when told output is machine-checked against a source), and adds a concrete
plain-English rule. Recompiled to **`map:ac15ee80f4237b3276877ed6`, 84,116 chars**. Pinned by
`tests/test_grounding.py` (33 tests).

#### A HARD check that over-fires deletes work the customer paid for

Reported 2026-08-05: assessments were being withheld on the live site. **Four checker bugs, and each
one was firing on a sentence the protocol actively ASKS the model to write.** A probe of realistic
prose flagged 3 of 5 paragraphs on the alias rule and 5 of 12 on figures. The direction of the error
matters: a false HARD is not a missing feature, it is the product refusing its own correct work and
showing a notice instead, and the customer already paid a credit for it.

- **Aliases inside QUOTATIONS.** `_ALIAS_RE` is `[AC]\d{1,3}`, which matches plenty of things real
  people write: "C4" (the broadcaster), "C19", "the A1" (the road), model and part numbers. Those
  arrive inside verbatim quotes of the account's own posts. An internal label only leaks in
  **narration**, so `check_alias_in_prose` now strips quoted spans before scanning. A label in the
  model's own words is still HARD.
- **Post counts are compared in ONE DIRECTION only.** The 75-100 mechanical gate *requires* subset
  counts ("near-identical text on two of its own posts", "six posts inside one hour"), and every one
  of those is legitimately smaller than the history. They were being compared against the total and
  withheld. A number below the history is consistent with the evidence; only a number **above** it
  describes posts that do not exist. This also closed a false negative, since `posted N times` was
  not matched at all.
- **A ratio stated the other way up is the same true fact.** `_CHECKABLE_CLAIMS` asks for
  following-to-followers, but a model writing "a followers-to-following ratio of 4.0" and labelling
  it correctly has stated a true figure. `_check_ratio` accepts either orientation and divides out a
  pair form ("a ratio of 300:1200"), which was previously read as the bare number 300.
- **A bare `N accounts` was read as a following count.** "one of 4 accounts in this batch" got
  compared against `following_count`. The alternative is deleted; the live contamination this check
  exists for ("following 1,281 people while only 505 follow back") names the verb and is still
  caught.

The prompt half ships with it, because a checker that only *tolerates* good output leaves the model
guessing at the forms that survive. `_CHECKABLE_CLAIMS` gained the mechanical rules: copy a quote
character for character out of ONE row (no merging two posts, no tidying spelling, no translating),
shorten with `...` and only the head is matched, state the two counts beside any ratio, say which
whole a subset count belongs to, and drop a figure you are unsure of rather than lose the paragraph
to it.

Pinned by the false-positive section of `tests/test_grounding.py`. **Every case there is a sentence
the protocol demands**, which is the standard for adding to it: if a HARD rule fires on prose the
constitution asks for, the rule is wrong, not the model. Recompiled to
**`map:feec389425014663a2b23cc3`, 101,754 chars**, zero em dashes, all drift guards green.
`package_hash` → `pkg:3e7f63fdd9456ddc1554ede4`. Constitution block count unchanged at 19.

### The protocol used to contradict itself about verdict length

Found while auditing for quality, and the most likely single cause of thin per-account reads. The
base prompt's Dossier Loop STEP 4 and the constitution's step (4) both said the per-account reason
was a **"1-3 sentence"** plain-English line. The output contract said **"4-7 sentences"** and the
schema sets `minLength: 200`. Told the short version twice and the long version once, a model writes
short, and three sentences cannot physically carry what the same protocol demands of them: a computed
figure, a verbatim quote, the innocent explanation, where the score landed, and what would overturn
it. All three sites now say 4 to 7.

The base prompt also called the loop a **"four-step worksheet"** after the constitution had grown it
with the (3c) coherence check and the (5) distribution check. A model told there are four steps stops
at four. It now states that the constitution governs where the two differ.

Both are pinned by `tests/test_score_discipline.py`, including an assertion that the stated length
can actually satisfy the schema floor it is paired with. **When editing one document, grep the
compiled protocol for the instruction rather than the file** — the same rule is stated in up to three
places and they drift silently.

A **FINAL PASS** checklist now closes the output contract, which is the last thing read before
generation: count the accounts against the legend, re-check every quote and figure against the rows,
spread, length, plain English. It deliberately points at the constitution's distribution check rather
than issuing a competing one.

### The repost recalibration, and the four places that contradicted it

Driven by ~250 real scored rows from four live investigation exports (2026-08-04). Of the ~90
accounts the model put at 50 or above, **roughly 75 rested on "posts mostly reposts" and nothing
else**: `4ucmikey` **86 high** (2011, 234/191), `Jillforhealth` **79 high** (2013, 155/283),
`willowpete` 66, `Trucker238` 66 (607/616), `marymporte` 64 (3066/3305), `malawattorney` 64. A
fifteen-year-old account with a balanced ratio that reposts politics all day is the most common real
human on the platform, and these verdicts get posted publicly about named people.

The model was not disobeying. `_SCORE_DISCIPLINE` already said ambient traits may never carry an
account past the moderate band; its ambient list simply **never named reposting, topical narrowness,
posting volume, or opinion strength**. The boundary was drawn in the wrong place. Four changes:

- **AMBIENT TRAITS now names them**, plus a rule of its own (`A MOSTLY-REPOST TIMELINE IS NOT A
  FINDING`) and a matching `THE HEAVY REPOSTER` entry in `_CONFUSABLE_ACCOUNTS`. It also names the
  phrasings the model reached for (`reads more like an amplifier than a personal timeline`, `a
  message relay`, `a broadcast feed`) as descriptions of ordinary use rather than evidence.
- **The 75-100 band is a MECHANICAL GATE, not a count.** At least one of five tells, written into the
  assessment as a quote or a figure: near-identical text on two of its own posts, scheduler-regular
  intervals, its own commercial pitch, a numbered campaign, a profile contradicting its own metadata.
  Repost share, narrowness, volume, tone, stance and follower ratio **can never BE the tell**. This
  keeps the genuinely correct high scores in the same data (`aiseomastery` 93 on hourly automated
  headlines, `horacio_names` 88 on five identical ad templates, `raidertbone` 88 on a numbered "Day
  41 … Day 16" sequence, `stonk_simian` 90 on pump pitches).
- **The thin-evidence cap became a graduated ceiling.** The old rule only covered a history that was
  never collected, so `FTrimby` scored 62 on 5 posts and `PromptKing32` 78 on 8, while two accounts
  in the identical state of nothing-collected came out **31 points apart** (`PedroJaniec` 3,
  `Jamison598294` 34). Now: zero posts = 10-20 with confidence ≤20, one post caps 39, 2-14 caps 49
  unless a tell is quotable from those very posts, 15+ normal bands.
- **The distribution check moved from a third to a QUARTER**, and now says explicitly that anything
  resting only on repost share, narrowness, volume or tone goes back below 50.

**Two of the defects were INSTRUCTED by the prompt.** The output contract literally asked for "why
you landed on THIS number rather than one 10 points higher or lower" (which became "I settled on 27
rather than 42" in ~90% of rows, sometimes arguing upward while scoring downward), and it permitted
"a short alias in parentheses" (which became "A17 is a 2009 account…" on essentially every verdict,
plus cross-account references like "near-identical to A23's reposts", the contagion the same protocol
forbids). Both instructions are gone.

**The alias permission was in FOUR places and the ambient/convergence doctrine in THREE**, which is
the drift this file has warned about twice. Do not fix one and stop: `constitution.py`
(`_SCORE_DISCIPLINE` **and** `_OUTPUT_FORMATTING`), `comprehensive_investigation_template.py`
(`COMPREHENSIVE_INVESTIGATION_SYSTEM_TASK` **and** the output contract), and
`_assets/omi_analyst_v1.txt`. The `system_task` copy was the worst: it still said "75-100 needs
several that converge", "cannot exceed 49 on profile metadata alone" (against the new 10-20 ceiling)
and "roughly a third", so half the recalibration was being contradicted a few thousand characters
later. **Grep the compiled protocol, never the file.**

Three checklists were also competing (base prompt "four audits", `system_task` "THE FOUR AUDITS",
contract "FINAL PASS"). FINAL PASS is last-read and authoritative; the other two are now a pointer
plus the two checks FINAL PASS does not make (the collapse audit, and use-the-cells-you-were-given).

**Two code fixes the prompt could not reach:**

- **The per-account tier is DERIVED from the score** in `_join_commenter_assessments`, not passed
  through. One export served score 28 as "low" on two accounts and "moderate" on two others, and 29
  as both, so the badge was not a function of the number beside it. `grounding.check_coherence`
  already *detected* this as a SOFT `tier_mismatch` and nothing acted on it. A disagreement is now
  logged (`analyst tier drift on %s`) and deliberately **not persisted**: a field here would go
  through the viewer gate and the export for no reader's benefit.
- **`check_alias_in_prose` is HARD** (`grounding.py`), so an internal label never reaches a reader,
  and **`check_style` is SOFT** for the score counterfactual and the "more like an X than a Y"
  construction. The severity split is deliberate and was a deviation from the plan, which proposed
  putting these in `BANNED_PHRASES`: that list is HARD-enforced and withholds the whole paragraph,
  and suppressing a factually correct assessment over a stylistic tic is a worse outcome than
  printing it. `_ALIAS_RE` is `[AC]\d{1,3}` and deliberately excludes `N` so "N95" is not flagged.

**Cross-account contamination was the most damaging class and is already caught deterministically.**
`swanson18982373` (really 505/600) was published as following "1,281 people while only 505 follow
back" and quoting "Climate scam" and "Fauci = evil fuck." All three belong to `X_is_Arbitrary` in the
same batch; `JohnWSavio` (created 2014-02-07) was described as "created on 2024-08-03", which is
`2vcGopld13`'s date. `check_figures`'s `_FOLLOWING_RE` **does** match that phrasing and returns HARD,
contrary to a note in the plan that said it did not, so the paragraph is withheld rather than
published. The protocol side adds an own-row sourcing rule to `_CHECKABLE_CLAIMS`.

`tests/fixtures/analyst_calibration_rows.json` + `tests/test_analyst_calibration.py` (22 tests) keep
the real accounts, grouped must-stay-high / must-come-down / must-be-capped, and pin the
deterministic half. **The model-facing half can only be verified by a live re-scan**: paste the
recompiled preset, re-scan one of these posts, and the elevated+ count should fall from ~90 to
roughly 15-20 while `aiseomastery` and `raidertbone` stay high.

Protocol recompiled to **`map:1b2d1dc15d37fc4ea0b9b20a`, 93,440 chars**, zero em dashes, all drift
guards green. `package_hash` → `pkg:6b56634700e134cdff2ea7ca`. Constitution block count unchanged at
18 (every change extended an existing block).

**Cost note:** 84,116 → 93,440 chars, about +2,300 input tokens per batch, so a 150-account
investigation pays it six times. The dedupe above gave back ~1.4k of the ~10.7k the new rules cost;
the rest is the rules themselves. At mini-class pricing that is fractions of a cent per
investigation, so the real reason to keep watching the number is that past some length a model
follows each individual instruction *less* reliably. Additions must keep replacing rather than
accumulating.

### The saved-graph redesign: an edge now says why it exists

`/graph` was inert, and the reasons were structural rather than cosmetic.

**Every edge collapsed to one float.** The route served
`strength=min(1.0, e.mean_cluster_score)`, a per-scan average that is not a probability of
anything, while the `CoordinationEdge` row already carried `log_lr_sum` (the accumulated log10
likelihood ratio, discounted for context correlation), `families_json`, `contexts_json` and
`observation_count`. All of it was discarded at the serialiser. A line drawn between two named
people that nobody can interrogate is asking to be trusted rather than read, which is the opposite
of what the rest of this product does.

`GraphCoordinationEdge` now carries the **calibrated posterior** (`_edge_posterior`, the same number
`app/campaigns/detector/probability.py` uses to decide a pair is coordinated at all, so the graph
and the detector agree by construction), the independent evidence **families**, how many **distinct
posts**, and first/last seen. `log_lr_sum` at 0 falls back to the old mean rather than collapsing to
the prior: that means "seen, but before we were accumulating", and blanking those would erase every
graph built before the tracking layer.

**The client hardcoded `community_id: 0` for every node**, so the whole community dimension of the
visualisation was dead, while `_louvain` sat unwired in `app/graph/algorithms.py`. `_communities`
now runs it over the graph's own edges. **Community 0 is reserved for the UNCONNECTED band** and
`community_count` deliberately excludes it, because counting it would report "1 community" for a
graph with no edges at all.

**Suggestions are the feature the old endpoint could not have.** Edges were only ever drawn between
accounts the user had already added, so a graph could only show its owner what they already knew.
`_suggestions` returns accounts OUTSIDE the graph that link into it, ranked by how many DIFFERENT
members they touch before raw strength: one strong edge can be a coincidence with a good story, and
an account tied to three separate members of a curated set is the shape of an operation. Gated at
`SUGGESTION_MIN_POSTERIOR` (0.80), because offering a lead the evidence does not support trains the
operator to add accounts on our say-so.

One query serves both: every edge touching any member, partitioned into both-inside (the graph's
edges) and one-inside (the leads). The old code ran a two-`IN` query over an unbounded member set;
`MAX_GRAPH_MEMBERS` (250) now bounds it and a capped response says `truncated` rather than quietly
showing a subset.

#### The score was being invented, and that is the part that mattered most

`tierToScore()` in the client rebuilt a number from the tier band (high -> 0.9, elevated -> 0.7,
moderate -> 0.45) and sized every node by it. **A tier is a band and a band cannot be un-rounded**:
50 and 74 are both "elevated" and are not the same account. `UserGraphMember.omi_score` now carries
the real value, `AddGraphMemberRequest` accepts it, and **null is not zero**: an unscored member
draws HOLLOW rather than small, because a confidently tiny node claims the account was measured and
came back clean.

#### The layout answers a question the data can support

`RadialGraph` picked a `focal` node and BFS'd hop rings around it. A saved graph is a set the
operator assembled and has no centre, and coordination edges are sparse by design, so in the common
case nearly every node fell into its `orphans` bucket.

`lib/graph-layout.ts` is pure and pinned by `lib/graph-layout.test.ts` (17 tests). Nodes group by
community, clusters pack by phyllotaxis and ring the canvas largest-first, and the unconnected band
gets its own labelled strip along the bottom, so **"nothing links these" reads as a finding rather
than as a drawing that failed**. Deterministic on purpose: no force simulation, because a node
moving between renders is a signal the data changed when it did not.

`RadialGraph` itself is untouched and still correct for the account-subgraph surface, where there IS
a focal account. `radial-graph-island.tsx` and `graph-explorer.tsx` in `app/(app)/graph/` are
currently imported by nothing; left in place rather than tidied, per the note about unimported code
in the campaigns section.

### The preset goes out as a copy page, every time

**Standing instruction from the owner (2026-08-19): every protocol change ships with a paste-ready
copy page.** `python scripts/make_preset_page.py` generates it from the compiled protocol; publish
the result as an Artifact.

**Always pass the EXISTING artifact url so it updates in place**, or the operator ends up with a
gallery of near-identical pages and no way to tell which one is current:

> https://claude.ai/code/artifact/d63016b6-d39e-4a7b-8878-8621876a20b9

Title (`Omi Master Analyst Protocol`) and favicon (📋) stay stable across versions for the same
reason. The hash, the character count and the date are on the page, so it identifies its own version
without the title having to.

Why a page rather than a link or an attachment, which is the part worth not re-litigating:

- **The repo is private**, so a raw GitHub URL asks the operator to be signed in, and the file is
  117k characters of unwrapped text in a browser tab either way.
- **A dashboard editor can truncate a paste this size silently.** That is the failure this is built
  around.
- **Omi CANNOT READ THE REMOTE PRESET BACK.** `master_prompt_hash` on the trace is computed locally
  from the repo, so it reports the new hash whether or not the paste ever happened. Checking it
  proves nothing, and this note exists because that advice was given once and was wrong.

So the page carries its own verification: a **marker string present in this version and no earlier
one**, which the operator searches for in the saved preset field. `VERSION_MARKERS` in the script is
that list, newest first, and a new version adds its distinctive heading to the TOP. It catches both
"pasted the wrong document" and "the editor cut it".

The script refuses to build from a compile that disagrees with the committed
`ml/analyst/omi_master_v1_preset.txt`, and asserts that the text a reader copies out of the textarea
is byte-identical to `compile_master_analyst_protocol()["text"]` after HTML escaping.

**Regenerating the protocol touches more than the protocol.** A prompt-source change invalidates
every committed mirror, and the drift guards fail loudly rather than silently, which is correct and
is also how a full suite went from 2 failures to 13. Run all of them:

```python
import app.reasoning.prompts.export as E
for w in [n for n in dir(E) if n.startswith("write_")]:
    getattr(E, w)()
```

That covers the catalog, knowledge, every template, the handbook, the behavioural handbook, the
manifest and the master preset. **Two more are NOT in that loop:** `ml/analyst/analyst_system_prompt_v1.md`
(the HF model-card mirror of the base prompt, checked by `trace.prompt_integrity`'s
`ml_doc_mirror_matches`, and regenerated by substituting the registry template into its
`## SYSTEM_PROMPT` fenced block), and the `package_hash` pinned in
`tests/test_investigation_summary_stage.py`, which moves by design on any prompt-asset edit.

### v14: the dimensions were the binding constraint all along, and one of them was half blind

v13 fixed the band rules and did not move the distribution, because the band rules were never what
was holding it. Measured across investigations 2 to 4 (~150 accounts, so ~1,200 dimension scores),
**exactly six dimension scores reached 50**. Five of the six belong to two accounts, and **exactly
one account has two**. Dossier Loop 3c permits a score of 50 only where two dimensions are
substantially elevated, so that one account (`ChadestGroyper`, 58) is also the only account in four
investigations scoring above 49. The match is the rule executing, not a coincidence.

**So the elevated-band list cannot lift anything on its own.** 3c gates on the dimensions, the
dimensions never move, and everything else is downstream. Four causes, all now fixed:

- **`substantially elevated` was defined nowhere.** The phrase appeared once in 112,000 characters,
  inside 3c, with no number attached: the model was asked to enforce a threshold it was never given.
  `USE THE WHOLE SCALE` in `_SIGNAL_DIMENSIONS` now states the bands (50-74 IS substantially
  elevated) and 3c points at it rather than restating it. 3c also runs **both ways** now: a score too
  LOW for its dimensions is the failure that actually happened, and it used to catch only the
  opposite.
- **`PROFILE` exemplified one direction of imbalance.** "such as following thousands while almost
  nobody follows back" was the only shape named, and models follow the example over the definition.
  Measured: the dimension fires at 45-65 on following-heavy accounts and sits at **10-22** on
  follower-heavy ones at far more extreme ratios. `Kingofcountry_2` (348 followers, follows 2, 36
  days old) scored 18; `gary_colwe88304` (1,249 / 8) scored 15. The definition now names the
  **ACQUIRED-AUDIENCE** shape beside the amplifier one and says they are equally elevated.
- **There was no worked example of an elevated account anywhere.** The four examples scored 12, 82,
  14, 22, and the only non-low one rests on leaked `as an AI language model` plus a repeated sentence
  plus a 390:1 ratio. The 50-74 band had no picture at all, so the only image of a raised score was
  the most extreme case available. A fifth account (`A5`, 61) now sits in the example, built on two
  NON-mechanical indicators, with `semantic` and `temporal` deliberately below 50 so it cannot be
  read as teaching the gate. Pinned by `test_the_example_teaches_the_elevated_band`.
- **`ai_writing` was 0 or 10 on essentially every row** when the rule said null. Zero claims the
  writing was examined and found human, which is an authorship claim style cannot support. Null is
  now stated as the default state rather than a permission.

**The worked example was demonstrating a sentence the constitution bans.** It closed on "Findings are
probabilistic; the human analyst sets the verdict", which `_FINISHED_VERDICT` forbids by name. That
is very likely why the v12 ban did not land: a rule competing with a demonstration of itself loses.
Gone, and pinned.

#### The rhythm tell was unreachable, and the fix is a measurement, not more prompt

Gate item (b) is the strongest per-account tell available and **it has never once been used**. The
protocol told the model to work the gaps out of the `created_at` column three separate times, in the
strongest wording in the document. Across ~400 accounts it wrote **eleven rhythm claims and not one
figure** ("the timeline shows human-like quiet periods", "not machine-regular"), and `signal_temporal`
never exceeded ~35. Worse, **every unmeasured claim ran exculpatory**: an impression nobody computed
was being used to hold scores down.

More prompt was not going to fix an instruction already stated three times and ignored. Computing 49
gaps for each of 25 accounts is arithmetic, and arithmetic is what the Evidence Compiler is for, so
`_timing_stats` now measures it and the row carries `post_gap_median_min`, `post_gap_stdev_min`,
`longest_daily_quiet_min` and `distinct_post_hours`. TEMPORAL and gate (b) both read those columns
instead of asking for the sum.

- **Computed is not judged.** These are descriptive statistics over timestamps already in the bundle,
  with no threshold and no opinion, exactly as `account_created_at` is a fact the model turns into an
  age. **The engine's own probability, tier and intent still reach the model nowhere**, which is the
  product rule and is separately pinned.
- **Nulls below ten timestamps**, which is the protocol's own floor for reading a rhythm. Reporting a
  median from four posts would manufacture the unearned confidence this replaces.
- Measured separation: a 62-minute scheduler gives stdev 0.0 across 20 hours of the clock; a real
  timeline gives stdev 311.6 with an 18-hour quiet stretch across 10 hours.

#### Two more rules that were being ignored, and the size budget

`NEVER CLOSE ON A REQUEST FOR MORE DATA` is still violated verbatim: `Bunnedette56021` closed on
"More posts would be needed to change the read", almost word for word one of the three banned
strings. The batch-level shape check cannot see scattered leaks (it needs a third of a batch), so
`check_closing_ask` reads one paragraph's last sentence. **SOFT**, and the load-bearing test is that
it does NOT fire on "Finding the same sentence on two of its own posts would overturn this", which
the protocol *requires* at 50 and above and which is shaped like a request for more data.

The 4-to-7-sentence floor was also being missed (two- and three-sentence verdicts shipped). It is now
stated as the four things a paragraph must CONTAIN, since the count was only ever a proxy for them.

**Paid for by deleting the base prompt's signal library**, which said "Do not run a competing
shortlist here" and then ran one: seven tells restating the mechanical gate item for item. That
duplication is the likeliest reason the 75+ gate came to be applied at the 50 boundary, since the
same list appeared twice with two different thresholds attached. Net growth is still +4,862 over v13,
and **the three ignored rules above are the argument for stopping**: rules already written down are
already not being followed, so v15 must cut before it adds.

Protocol recompiled to **`map:4b3ba3f45db2b994de5fc37f`, 116,971 chars**, zero em dashes, all drift
guards green, committed artifact regenerated at `ml/analyst/omi_master_v1_preset.txt`.

### The v13 recalibration: the gate migrated down and the product stopped finding anything

Driven by four live investigation exports (2026-08-19), roughly 400 scored accounts. **Exactly ONE
account cleared 50 and none reached 75.** Three of the four investigations have a maximum below 40.
The protocol's own stated expectation is "roughly one in ten" at 50 or above, so on that corpus it
should have been about 40. This is the mirror of the v10 defect (90 of 250 at 50+) and it is worse
for the product: a customer pays a credit and is told every account looks fine.

**The cause is the 75+ mechanical gate being applied at the 50 boundary**, and the model says so in
its own prose. `dickensian1776`, scored 44: *"If the account were found to have the identical
authored sentence posted on multiple separate days, the score would rise into elevated territory."*
Elevated is 50-74. That sentence, in variations, is on most rows in the corpus. Three structural
reasons, all fixed:

- **The gate outweighed the band rule about ten to one in words.** The gate is ~700 words with seven
  lettered sub-items; 50-74 was one clause inside a sentence that also defined 0-24 and 25-49.
- **The 50-74 band had no list of its own.** "Two independent discriminative indicators" pointed at
  nothing, so the only enumerated list of indicators in the block was the gate's.
- **Every tiebreaker pointed down** and the distribution check only ever fired when *too many*
  accounts were high. A run returning nothing above 49 triggered nothing at all.

What changed in `_SCORE_DISCIPLINE`:

- **`THE 50 TO 74 INDICATORS`**, the elevated band's own list, at comparable length to the gate:
  non-reciprocal follower acquisition, interchangeable engagement at volume, promotion as the
  dominant mode, an abrupt history, a profile that argues with itself. Two independent ones, and
  **none of them has to be mechanical** (stated in those words, because that is the failure).
- **The gate now scopes itself**: `THIS GATE GOVERNS 75 AND ABOVE. IT IS NOT THE TEST FOR 50`, and
  it names the exact tell of the failure ("if you find yourself writing that a repeated line *would
  raise this to elevated*, you have applied the wrong test").
- **`WHAT IS ACTUALLY DISCRIMINATIVE` was DELETED**, which is what paid for the addition. It was a
  near-restatement of the gate sitting a few hundred words below it, and that duplication is the most
  likely reason the model read the two thresholds as one. This is the pattern to keep: additions
  replace, they do not accumulate.
- **The distribution check runs in both directions.** `TOO FEW IS ALSO WRONG` re-reads accounts that
  already have a quoted indicator, and explicitly refuses to become a quota ("Do not invent an
  indicator to fill the quota"). A genuinely clean batch of 25 is still a real answer.
- **A zero-post carve-out that is arithmetic, not behaviour.** The ceiling was absolute ("always,
  whatever the follower counts look like"), which was right about behaviour and wrong about counts:
  `Kingofcountry_2` has 348 followers, follows 2, and is 36 days old, which is computed rather than
  inferred. Ceiling 49 instead of 20, confidence still capped at 35, and **never above 49 on profile
  numbers alone** so the original bug (two identical states scoring 30 points apart) cannot return.
- **A large audience is evidence in NEITHER direction**, phrased like the existing rule about account
  age. A live verdict used 18,742 followers to argue a LOW score ("the large audience weigh toward a
  genuine influencer"), which reasons backwards from the exact commodity being bought and sold.

**Deliberately NOT done: an engine-disagreement rule.** Eleven accounts have the engine at elevated
(up to 70) and the model at 13-18. It is tempting to have the model explain the gap, and it is not
possible: `_account_evidence` renders no engine field to the model ("Computed engine fields retained
on the object for OTHER features; NOT rendered to the model"), and showing them would inject exactly
the anchoring `NO CONTAGION` forbids. Product rule, from the owner: **the engine's only relationship
to the analyst is sending an evidence bundle.** Do not add one.

Protocol recompiled to **`map:e5794383e611a87fd9d1bf2f`, 112,109 chars**, zero em dashes, all drift
guards green. Constitution block count unchanged (every change extended an existing block). Pinned by
`tests/test_score_discipline.py`, which now asserts the gate and the band list are separately
reachable, and that the reader-facing rules still do not touch the score.

### Banning one sentence teaches substitution, so the rule is structural now

v12 banned *"collecting more posts would increase confidence"* as a closing sentence. The model
complied and immediately built a replacement: *"The one observation that would most change this read
is finding identical templated text repeated across its own posts"* now closes the majority of every
run, near word for word. That is worse than what it replaced, because it is a template on a product
whose central accusation is that other people use templates.

Two halves, and the deterministic one is the load-bearing part:

- **`_FINISHED_VERDICT`** gains `DO NOT REPLACE IT WITH A DIFFERENT STOCK CLOSER` and
  `THE RULE IS STRUCTURAL, NOT A WORD LIST`. The opener rule (which had been in the document since
  v12 and never landed) now names the exact failing sentence and tells the model its output is
  machine-checked, which is the strongest prompt lever available.
- **`check_boilerplate` compares opening and closing sentence SHAPES across a batch.** Whole-paragraph
  Jaccard could never see this: twenty-five verdicts share one skeleton while their middles differ
  enough to stay far under the threshold. `_sentence_shape` collapses digits to a marker and keys on
  the first eight words, so "created 2019-04-02 / 400 followers" and "created 2023-11-18 / 51
  followers" register as one template. Fires at 5/5 on the live pattern, silent on varied prose and
  on two-of-five convergence (`REPEATED_SENTENCE_SHARE` = 0.34).

**SOFT, and it must stay SOFT.** A repeated opener is a writing failure, not a false claim about a
person, and withholding a true paragraph over a stylistic tic is the trade `check_style` already
settled once.

### Cross-account contamination was reaching the page, in two forms nothing checked

Found in the same exports and reproduced against `check_figures` directly. `jamesthatcher_` is a 2023
account with 322 followers and 349 following. The product published:

> "A long-running account (2009) with 337 followers and 2,263 following and fifty sampled posts"

`2,263 following` and the 2009 year belong to `unique59`, four rows away in the same batch. Two holes,
both about the FORM the model writes a figure in rather than the check being absent:

- **`_FOLLOWING_RE` matched only the verb-first order.** `follows 2,263` was caught;
  **`2,263 following` was not matched at all** and number-first is what the model actually writes on
  most rows ("384 followers and 782 following", "103 followers vs 9 following"). The trailing
  `(?!\s*followers)` guard on the verb form stays, or `follows?` matches inside "followers".
- **No creation-date check existed in any form the model writes.** "N years old" was checked;
  `(created 2023-07-04)`, `A 2009 account` and `account (2009)` were not, and those are the forms the
  protocol's own opening-sentence rule produces. CLAUDE.md already recorded a live contamination on
  exactly this field (`JohnWSavio`) and it was still reachable.

`_check_created` holds a full date to the day and a bare year only to the year, deliberately: "a 2009
account" is a true statement about anything created in 2009, and demanding more would withhold honest
prose. A year is only read as a claim when it sits next to a creation word or the word "account", so
"the 2020 election" and a year inside a quoted post are left alone. One wrong date reports once, not
twice. Pinned by the contamination section of `tests/test_grounding.py`.

**The withhold rate is the other half of this and is NOT yet diagnosed.** About 36 of 400 verdicts
came back withheld, and in one investigation it is ~28 of ~130 (**21%**). That clustering says a
checker over-firing on a phrasing habit, not 28 hallucinations. Diagnosing it needs the withheld text
and codes from `assessment_unverified` / `grounding` in `payload_json`, which is why the field is
kept. Note the checker was simultaneously too strict on innocent prose and too loose on the one thing
that mattered.

### OMI_OPENROUTER_MODEL overrides the preset, so a dashboard model change does nothing

Same two-sided-contract class as the preset NAME and the Clerk keys, and it bit on 2026-08-19. The
model was changed on the OpenRouter preset; `render.yaml` still committed
`OMI_OPENROUTER_MODEL: 'openai/gpt-5-mini'`, so every request kept going out as
`openai/gpt-5-mini@preset/omi-master-v2` and **the change had no effect, with no error anywhere.**

Both model variables are now `''`:

- **`OMI_OPENROUTER_MODEL`** must stay empty while the preset names a model, so the dashboard is the
  single source. Empty is safe (`if self.model` is falsy, so the reference resolves to
  `@preset/<name>` alone) and is NOT the same as wrong: a bad slug answers 404 and floors **every**
  scan (`floor_reason.preset_or_model_not_found`). Set it again only if the preset goes back to
  "can be used with any model", where the preset alone does not resolve.
- **`OMI_OPENROUTER_EXPECTED_MODEL`** is emptied because it compares a committed string against what
  the gateway reports serving; leaving the old value would log a mismatch on every scan that is not a
  fault. **Fill it in with the exact slug** read off `GET /v1/investigations/analyst/preflight` after
  the deploy, and the proof-of-provenance check comes back on.

### The verdict rewrite (v12): the analysis was right, the writing sold it short

Driven by ~250 real scored rows across three live investigations. The scoring was defensible; the
PROSE made a working product read as one that found nothing. Five failures, all present in that
export, and none of them fixable by moving a score:

- **Clean accounts written as a run of negations.** "No templated repetition, no machine boilerplate,
  no repeated identical text, no pitch language" is four absences in a row and reads as though
  nothing was examined. `A CLEAN ACCOUNT IS A FINDING` requires the positive facts instead.
- **~60% of verdicts closed on "collecting more posts would increase confidence."** The last line is
  the one a reader remembers, and ending on the analysis being insufficient tells someone who just
  paid that they got nothing. Banned as a closing sentence; the hedge now goes INSIDE the sentence
  carrying the fact (`THE HEDGE GOES IN THE WORDS` was reworded to say where it goes).
- **~16% of accounts had NO posts collected and were described as fitting a benign explanation.**
  This is the one rule here that is about honesty rather than tone, and the score discipline cannot
  catch it because the score is correct and only the prose is false: an unexamined account was
  getting a clean bill of health. Now one or two sentences, no padding, and never "looks ordinary".
- **`evidence_against: None reported`** on a section of 100 ordinary people. The output contract's
  escape hatch ("empty ONLY if confidence_rationale states no exculpatory signal") had become the
  default, and `coerce_comprehensive_model_output` auto-appends that rationale, so nothing pushed
  back. Multi-year histories, balanced ratios and overnight quiet periods ARE collected exculpatory
  evidence, and on a clean section they are the substance of the report.
- **Every paragraph opening "This account (created X) has N followers and follows M."** The rule
  existed but was a sub-bullet of a sub-bullet inside `_CHECKABLE_CLAIMS`; promoted to its own rule.

**Two of these were INSTRUCTED, not invented.** The base prompt's TONE section literally said "End
the executive assessment with one sentence noting the findings are probabilistic and the human sets
the final verdict", which is why it appeared on every scan; and the output contract's evidence_against
clause is what taught the model that empty was acceptable. Grep the compiled protocol, never the file.

`_FINISHED_VERDICT` sits immediately after `_CHECKABLE_CLAIMS` on purpose: that block decides what a
sentence may ASSERT, this one decides how the finished paragraph READS, and they govern the same
text. **It moves no score and that is pinned** (`test_the_reader_facing_rules_do_not_touch_the_score`
asserts the base rate, the ambient-traits rule and the two-errors rule are all still there). The
scoring recalibration from v10/v11 is untouched.

Protocol recompiled to **`map:80d1363a513a6c358d827e56`, 105,765 chars**, zero em dashes, all drift
guards green. `package_hash` -> `pkg:7646d2a7524aacd8a2416a16`. Constitution block count 19 -> 20.

**Cost note, stated honestly:** 101,754 -> 105,765, about +1,000 input tokens per batch, and unlike
past passes this one did NOT pay for itself by deduplication. The only material available to cut was
score-discipline doctrine, and cutting that to fund a readability change would trade a false-positive
guard for nicer prose. The +3.9% stands. If the protocol keeps growing, the next pass must find its
budget inside `_SCORE_DISCIPLINE` (10.5k chars) and `_CONFUSABLE_ACCOUNTS` (4.3k), which overlap.

**Not yet verified against the live model.** The deterministic half is test-pinned; whether the prose
actually improves can only be seen by pasting the recompiled preset and re-scanning.

### The research pass (v11): what the literature says, and the hole it exposed

v10 was derived entirely from our own exports. It could tighten what we already believed and could
not tell us what the field has measured. This pass read the bot-detection literature and found three
things v10 could not have seen.

**The eight dimensions were defined NOWHERE.** `temporal · semantic · ai_writing · profile · voice ·
engagement · account_maturity · history_authenticity` appeared in the compiled protocol *only inside
the worked example*. No definition of any of them existed, while Dossier Loop 3c gates the omi_score
on how many are "substantially elevated". The model was scoring eight dimensions whose meaning it
inferred from their names. `_SIGNAL_DIMENSIONS` now defines each one: what evidence it reads, what
high means, when it must be null. Pinned by
`test_analyst_calibration.py::test_every_one_of_the_eight_dimensions_is_defined_and_not_merely_exemplified`,
which asserts each name appears *outside* the example JSON.

**`ai_writing` was a live score-inflation pathway.** The protocol said both that it is supplemental
and "never a reason to raise the OMI score", and that it is one of eight *required scored*
dimensions (the example gave it 40). Since 3c licenses 50+ on two elevated dimensions, an unreliable
one could be half the quorum. The engine already agreed it was worthless
(`evaluation/corpus.py:161` marks it `"supplemental": True`; `orchestrator/ai_modules.py:112` drops
`raises` findings citing a supplemental signal). Now: it scores above zero **only** for quotable
machine boilerplate (`as an AI language model`, a refusal template, a leaked prompt fragment),
everything else is `null`, and it **can never satisfy the 50+/75+ quorum**. That is stated in the
dimension definition *and* at 3c, because 3c is where the inflation happened.

**The bundle ships post timestamps and the protocol never said to read them.** `_account_evidence`
sends `recent_posts` as `(text, created_at)` pairs, up to 50. Gate tell (b) now carries a method:
compute the gaps, and state either a near-constant interval or the absence of a multi-hour daily
quiet period. The direction matters and is easy to get backwards: a circadian rhythm is a **human**
feature, so "posts at consistent times of day" stays ambient; the discriminative inverse is activity
in all 24 hours with no rest gap.

Also added, each traceable to published work:

- **The base rate is now stated, not implied.** 9-15% of active accounts are automated. Charged
  political threads measure 43-45%, but with a tool whose false positive rate on those very
  measurements runs 41-76%, so a charged section is the last place to relax the distribution check,
  not the first.
- **`WHAT THIS METHOD CANNOT SEE`**, the strongest anti-hallucination clause available because it is
  true: a competent operation is not reliably separable from a real person one account at a time, and
  the large networks that were exposed were caught by coordination, which this analysis does not do.
  So "no mechanical tell found" is the *expected* outcome, never a reason to promote an ambient trait
  to fill the gap. That pressure is exactly what invents tells.
- **Age is evidence in neither direction.** v10's "an old account with a balanced ratio is an
  ordinary person" fixed the false positives and would have become its own blind spot: aged accounts
  are bought and resold *because* age reads as trust. Continuity is the question, so new gate tell
  (f) is a datable break in the account's own history.
- **`THE ENGAGEMENT FARMER WHO IS A PERSON`.** The platform pays a revenue share on reply
  impressions, so high-volume replying and rage bait are now rational *human* behaviour.
- **`SOMEONE WRITING IN A SECOND LANGUAGE`** promoted from one clause in a list to its own confusable
  shape, carrying the measured 61% false-positive rate. It is the largest documented false-positive
  class in adjacent tooling and it was getting a single line.

**Deliberately NOT added.** Purchased-engagement research converges on *audience-level* measurements:
engagement that does not scale with follower count, sudden follower spikes, comment-to-follower
ratio. The single-account bundle cannot support any of them. Asking the model for a claim the
evidence cannot ground is how hallucinations get invited, so these stay out of the prompt. If they
are ever wanted, they need new evidence collection first, not new prompt text.

Protocol recompiled to **`map:5389ce7bc0376b7ef8f2668a`, 100,478 chars**, zero em dashes, all drift
guards green. `package_hash` → `pkg:9419a4dd71d9916953afec07`. Constitution block count **18 → 19**
(`signal_dimensions` is the only genuinely new block; everything else extended an existing one).

**Cost note:** 93,440 → 100,478, about +1,750 input tokens per batch. Roughly 3.4k of the ~10.4k the
new rules cost was paid back by deduplication: `_SCORE_INTEGRITY_RULES` was a fourth copy of the
Dossier Loop and its two gates, the base prompt's ABSOLUTE RULES 1/2/3/7 duplicated the OMI
CONSTITUTION block sitting directly beneath them, its signal library restated the
ambient/discriminative split, and `_OUTPUT_FORMATTING`'s plain-English bullet restated
`_CHECKABLE_CLAIMS`. Keep paying for additions this way.

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

### Rate limiting

Three layers, all env-tunable (`OMI_RATE_LIMIT_*`) so a traffic spike is absorbed without a deploy:

| Layer | Budget | Key | Where |
|---|---|---|---|
| Global | `rate_limit_global_max` (600) / 60s | **IP** | `GlobalRateLimitMiddleware` |
| Compile | `rate_limit_compile_max` (30) / 60s | **user** | `/v1/scan/link/commenters` |
| Scan start | `rate_limit_scan_max` (20) / 60s | **user** | `/v1/scan/link/score` |
| Auth | 10/60s login · 5/hr signup · 5/hr reset | IP | dedicated limiters |

**The global layer is keyed on IP and must stay that way.** Middleware runs *before* auth, so any user
identity there is an unverified claim an attacker could rotate to escape the limit. Per-user budgets
belong at the route level, where the auth dependency has already run (`rate_limit.enforce` +
`rate_limit.user_key`).

**Why 600 and not 120.** The old hardcoded 120/min was tight enough to break real customers: an open
investigation polls the analyst every **2.5s for up to 10 minutes** (`analyst-panel.tsx`,
`POLL_INTERVAL_MS`/`MAX_POLLS`) = ~24 req/min per user, before navigation or monitoring polls. Five
people behind one office/VPN/mobile-carrier NAT share one key and hit 120 exactly. Don't lower it
without redoing that arithmetic.

**Compile is the limiter that protects money.** `/v1/scan/link/commenters` requires auth but charges
**no credits** and calls the real X / YouTube API (X bills per post read), so credits cannot guard it —
there is nothing to spend. This limiter is the only ceiling; `test_compile_is_capped_per_user_and_stops
_upstream_calls` asserts refusal happens *before* the upstream fetch, so a 429 costs nothing.

Admins and local mode (id=0, `is_admin=True`) are exempt, matching how admins skip credit consumption.
Pinned by `test_admins_and_local_mode_are_exempt`.

**Scope limit, stated plainly:** every limiter is in-process, so each budget is **per instance** and
resets on deploy. One instance (what `render.yaml` provisions) behaves as configured; N instances give
N× the ceiling. Making them global needs Redis behind the same `hit()` interface. These are an abuse
guard, **not** a billing control — cost is guarded by credits, the demo's DB-backed per-IP
reservations, and the daily upstream budget below, all of which are correct across instances.

### The daily upstream budget: the only cost control on the free compile path

Compile requires auth, charges **no credits**, and calls an API that bills per read. The per-minute
limiter above is an abuse guard and was being asked to do a cost control's job, which it cannot: it
bounds a burst and not a day (30/min sustained is **~43,000 provider calls per user per day**), it is
per instance, it resets on deploy, and it **recorded nothing**, so no query anywhere could answer
"how much did today cost". The first signal would have been the invoice.

`app/core/upstream_budget.py` adds a DB-backed daily ceiling and, just as importantly, a ledger.
`upstream_usage` is one counter row per (scope, day, platform), read at `GET /v1/admin/usage` and
rendered at `/settings/spend`.

- **It counts provider calls, not requests.** One compile pages the provider several times;
  `Source.quota_used` is what bills. Counting requests would understate spend by roughly the page
  count, which is the whole quantity of interest.
- **Checked before the fetch, recorded after** — a refusal must cost nothing, the same property
  `test_compile_is_capped_per_user_and_stops_upstream_calls` pins for the limiter.
- **A failed fetch is still charged, and this is the subtle part.** The accounting callback fires
  from a `finally`, but the route used to raise straight out of the `with get_session()` block, which
  rolls the transaction back and takes the ledger row with it: money spent, nothing recorded. Both
  compile routes now **hold** the `HTTPException` in `fetch_error`, let the session commit, and raise
  after the block exits. Do not "simplify" that back into a direct raise. (Recording in a second,
  nested session instead would deadlock on SQLite.)
- **The paid scan path records but is NOT gated.** Credits are a real billing control there, and
  refusing a scan mid-flight would take the credit and return nothing. Recorded inside `_finish`'s
  terminal-transition guard, so the single caller that owns the outcome and the refund also owns the
  accounting: a worker finishing after the watchdog reaped it must not double-count. Recorded on
  **both** outcomes, because refunding a credit does not refund the upstream bill.
- **The demo records but is not gated either.** Every anonymous visitor shares one bucket, so a
  per-user budget there would shut the front page rather than stop an abuser; the demo has its own
  per-IP and global guards. It still reaches the deployment total, since a total that omits the
  highest-traffic surface is not a total.
- **Two scopes.** The per-user row enforces fairness; the `global` row answers "is the API budget on
  fire right now" and has no user to hang off. The global ceiling answers **503, not 429**, and says
  the fault is ours: it refuses paying customers who did nothing wrong. It is a circuit breaker to
  raise, not a business limit.
- **Recording never raises**, and a failure is reported to the error tracker. A ledger that can fail
  a scan is worse than a ledger with a gap, but a silent gap defeats the point.

Defaults: 1500 calls/user/day, 50,000/deployment/day, both env-tunable
(`OMI_UPSTREAM_DAILY_CALLS_PER_USER` / `_GLOBAL`, `0` disables) so a spike is absorbed without a
deploy. Sizing at ~$0.005/call: a 150-account investigation is ~300 calls plus ~30 to compile, and a
subscriber's 20 monthly credits buy ~1000 accounts, so a whole month of heavy legitimate use is
~2000-3000 calls. 1500 in one day caps a runaway at about $7.50 rather than $216.

Pinned by `tests/test_upstream_budget.py` (23 tests).

### The network detector (`app/netdetect/`): sets, not pairs

Built 2026-08-20 as a ground-up replacement for the pairwise approach, alongside the existing cohort
detector rather than instead of it. Design and the argument for it: `docs/network-detection.md`.

**It asks a different question.** Not "do accounts a and b share X" but "how improbable is it that
THESE k accounts share this much, in a corpus shaped like this one?" A set-level statistic is not
recoverable by fusing pairwise ones, which is why this is a new package rather than a new signal.

```
features -> corpus -> candidates -> set surprise -> refusals -> shuffled null -> findings
```

**Five things that must not be undone:**

- **The null is DEGREE-PRESERVING.** `shuffle.shuffle_corpus` uses double-edge swap so every account
  keeps its feature count and every feature keeps its account count. Only the association changes,
  and the association is what coordination IS. A shuffle that let degrees drift would make
  everything real look significant.
- **The search is corrected against the distribution of the MAXIMUM.** `build_null` re-runs the
  whole pipeline on K shuffles and keeps each run's best score. That is the answer to "I searched a
  huge space and took the winner", and it is the thing the old detector has no version of. **The
  callable passed to `build_null` must be the same `_search` used on real data**: a null built from
  a cheaper approximation corrects a different search while still looking like a correction.
- **Refusals run INSIDE `_search`, before the null.** Filtering survivors afterwards would compare
  them against a threshold built from a more permissive search, quietly weakening the correction.
- **It never reads an OMI score or tier.** Coordination and botness are orthogonal, and the old
  70+ filter was blind by construction to the operation worth catching: aged accounts, hand-written
  posts, each scoring 30 alone. `test_the_score_never_reads_an_accounts_own_suspicion_score` pins it.
- **In-group replies are excluded from the evidence, and a chatty group is refused outright.** Real
  communities talk to each other; operations broadcast. Counting in-group replies as coordination
  inverts the signal on exactly the population most at risk of being wrongly accused, and the fan
  community control fired until this was fixed.

**Family weights price in what the null cannot see.** The configuration null measures *statistical*
rarity; it cannot measure *behavioural innocence*. Ten reporters genuinely share a topic, a working
day and a newsroom tool. So `types.FAMILY_WEIGHT` weights `identity` and `network` at 1.0 (the
operator's own acts: provisioning a batch, converging on outside targets) and text / timing /
infrastructure at 0.40-0.55 (things a shared job or interest produces for free).

**A finding with no hard-family evidence is flagged, not published.** `needs_adjudication` carries
the reason. The professional-beat control lands here: statistically real, innocent, and unresolvable
by any threshold. Suppressing it would hide genuine operations using aged accounts; publishing it
would accuse a newsroom. A reader is the only thing that can make that call.

**A blunder worth remembering.** With K shuffles the smallest reportable p-value is 1/(K+1), so a
run asked for p<=0.05 with K=8 could never report anything whatever the data held, and the output
was indistinguishable from a clean corpus. `detect` now REFUSES that configuration.
`test_too_few_shuffles_refuses_instead_of_silently_finding_nothing` pins it.

**Measured dilution curve** (8-account operation planted in 60 organic accounts): caught and
publishable at discipline 0.0 to 0.5, invisible at 0.75 and above. That curve IS the honest product
claim. A disciplined operation emits no rare features and no statistics recover a signal that was
never sent.

Reachable at `POST /v1/admin/netdetect/{slug}`, admin-only, costs nothing (no provider call, no
model call, no credit).

#### It was not deterministic, and the falsification test was the only thing that noticed

The module's docstring promised "the same corpus always produces the same findings" and it was not
true, for reasons no amount of reading the seeded RNG would reveal. `shuffle_corpus` built its edge
list by walking `AccountProfile.features`, a **set of frozen dataclasses whose fields are strings**.
That set iterates in `hash(str)` order, which Python randomises per PROCESS, and the swap loop then
indexes into the list with a seeded RNG. So one seed produced a different shuffle in every
interpreter, and since every shuffle in the null is built that way, **the correction threshold was a
function of the interpreter rather than of the data.**

Measured on one corpus with one seed under three `PYTHONHASHSEED` values: thresholds of **8.505,
8.02 and 0.0**. A threshold of 0.0 accepts every candidate, which removes the search correction that
is the entire justification for this package. That is why `test_a_shuffled_corpus_yields_nothing`
failed roughly one run in five, and it read as ordinary flakiness.

Fixed by sorting on `Feature.token()` at the four places a set of features is walked into an ordered
structure: the shuffle's edge list, the `Corpus` build (which sets the insertion order of
`feature_accounts`, which sets the order of the candidate search), `score_candidate`'s union, and
the Louvain edge list in `candidates.py`. **Sorting a set before iterating it is not cosmetic
anywhere in this package**, and a `set` of dataclasses is the shape to look for.

`test_the_answer_does_not_depend_on_the_interpreters_hash_seed` runs the same corpus in three
subprocesses under three hash seeds and compares the findings. An in-process test cannot see this
class of bug: one process has one hash seed.

#### Two families that were carrying less than they could

- **Reposts are network evidence.** `_map_tweet` had been parsing `repost_of_id` and it reached no
  feature, so a ring whose entire behaviour is amplifying the same handful of posts emitted nothing
  in the family that would have caught it. `network_features(..., reposts=())` now emits
  `repost_of`, and `score_candidate` excludes an in-group repost target for the same reason it
  excludes an in-group reply: boosting each other is a community, not convergence on an outside
  target.
- **`narrative` was declared and never produced.** The family existed in `FAMILY_WEIGHT` with
  nothing emitting into it, so `MIN_FAMILIES` could never count it. `topic_features(topic_ids, *,
  exclude)` fills it from the cross-investigation topic assignments, which is the only place a topic
  id exists. **The topics the cohort was FOUND on are excluded**, exactly as the scanned post is:
  every member holds them by construction, so without the exclusion the cohort shares a perfect
  feature and reports as one enormous operation.

#### Findings are RECORDED now, and recording is not publishing

The detector was read-only, and that cost it twice: its findings evaporated when the page closed, so
the tracking layer that survives account rotation learned only from the older, weaker cohort
detector; and there was nothing for an operator to dismiss, so the one reservoir of ground truth
this system will ever accumulate stayed empty while the better detector ran.

`NetdetectFinding` + `app/netdetect/persist.py` + `GET /v1/admin/netdetect/findings/all` with
`dismiss` / `confirm`. **The original rule is untouched**: no share token is minted, no `Campaign`
row is written, nothing reaches a customer surface. A claim about a person being a decision somebody
took rather than a side effect of a page load is about PUBLICATION, and storing an internal lead is
a different act. `test_a_run_publishes_nothing` pins the difference.

**A SET FINDING IS NOT A PAIR FINDING, and the decomposition is where that could be quietly undone.**
This package's whole thesis is that a set-level statistic is not recoverable by fusing pairwise ones,
so `pair_evidence_from` does **not** distribute the set score across the pairs. It reads the
finding's own evidence list and gives each pair only the surprise of the features THAT PAIR actually
shares, spread across the pairs sharing each feature so one popular-within-the-group feature cannot
deposit its full weight onto all forty-five pairs it touches. The consequence is intended: a pair in
a high-scoring finding that shares one weak feature contributes almost nothing, because the set was
significant and that pair was not. Distributing the score would put a number in the accumulating
graph that no test produced, and it would look exactly like measured pairwise significance.

Four more rules:

- **Upsert on `(investigation_id, members_key)`.** An operator re-runs constantly while tuning, and
  a row per button press turns the queue into a log.
- **A dismissed row keeps its dismissal when the numbers are refreshed.** Somebody who has already
  said "this is a newsroom" must not be asked again on the next re-run, and silently reopening it
  would make the dismissal worthless as the training signal it is the only source of.
- **The same member set under two investigations is two findings.** Collapsing them would discard
  exactly the independent second sighting the tracking layer exists for. Accumulation is still keyed
  on the post, so a re-scan of one post cannot compound.
- **A judgement needs a non-blank reason.** `min_length=1` alone passes `"   "`, which then strips to
  nothing on the way into the column and records that somebody was unconvinced and nothing about
  why. A `field_validator` rejects it.

Accumulation is best-effort and wrapped: losing it degrades FUTURE findings, and must never turn a
completed run into an error for the operator looking at the results now. `record=false` on the run
route keeps the answer and skips the store, which is what an operator tuning thresholds wants.

Pinned by `tests/test_netdetect_persistence.py` (12) and `tests/test_netdetect_routes.py` (14).
`tests/test_coordination_admin_gate.py` covers the new routes against a REAL non-admin, because
every other test here runs in local mode where `require_user` returns `is_admin=True`.

#### The calibration report reads the reservoir back, and moves nothing

`app/netdetect/calibration.py` + `GET /v1/admin/netdetect/findings/calibration`. It replays each
tunable constant against every judged finding and answers one question: **if this threshold had been
set differently, which of the findings a person already judged would have changed?**

- **It reports and it never moves anything.** No constant in `app/netdetect` is read from the
  database and none may become so. A threshold that retunes itself on operator clicks can be steered
  by whoever clicks, with no review and no diff, and this one decides whether named real people are
  reported as running an operation together. A constant in code has a commit, a reviewer and a
  reason beside it; a constant in a row has a number. `test_the_source_never_reads_a_threshold_out_
  of_the_database` is a source-level guard on the writes.
- **It refuses to recommend while the reservoir is thin** (`MIN_JUDGEMENTS` 30, `MIN_PER_CLASS` 8).
  Four constants fitted against a dozen labels memorises the last dozen posts somebody happened to
  look at. The sweeps are still returned below the floor, because watching it fill is useful and an
  empty response would read as a broken endpoint.
- **A recommendation never trades away a confirmed finding.** The search is only over settings that
  keep every confirmed one and refuse more of the dismissed. Calling real people coordinated when
  they are not is the expensive error, and it is the one the reader cannot check.
- **Among ties, the LEAST strict value wins.** Extra strictness that refuses no additional dismissed
  finding buys nothing on the evidence in hand and costs recall on the findings nobody judged, which
  are most of them. Which end is least strict depends on the constant, so `stricter_direction` is
  carried rather than a sign being assumed.
- **`corrected_p` NULL is never counted as significant.** Reading "not compared against the shuffled
  search" as "passed it" would silently restore the search bias the null exists to remove.

The sweep is possible at all because the row carries `by_family_json` rather than only a score: hard
evidence, the family count and the top family's share all fall out of it, so a threshold can be
replayed against findings judged months ago **without re-running the detector**, whose corpus is not
kept and would risk being rebuilt differently.

**A dismissal labels the FINDING, not the accounts.** "These are reporters on one beat" says the
group is not an operation and says nothing about whether any member is automated. `AccountLabel` is
the other reservoir and it labels botness, which this package deliberately never reads. Averaging
them would be a category error.

Pinned by `tests/test_netdetect_calibration.py` (11).

#### A finding names bystanders, at a measured rate, and nothing said so

Found while verifying the persistence work. Every recall test asks whether the planted operation was
FOUND (`>= 4 of 8`); **nothing anywhere asked who else was in the finding**, which matters more here
because a finding names real people. Candidate generation is community detection and Louvain pulls
in boundary accounts.

Measured across a systematic grid (four background sizes x three seeds): recall **8/8 on all twelve**,
and **7 innocent accounts among 103 named members, about 6.8%**, with the worst finding at 3 of 11.
**Identical against the pre-persistence tree**, so this is not new. What changed is the consequence:
a swept-in account used to evaporate when the page closed and now lands in an operator's queue as a
member of an operation, with its pairs folded into the accumulating graph.

`test_a_finding_is_mostly_the_operation_and_the_rate_is_pinned` pins it as a **ceiling**, so a change
that makes contamination worse cannot land behind a recall test that still passes. **Keep the grid
systematic**: an earlier draft trimmed it to six configurations, the trim happened to keep most of
the contaminated ones, and it reported 12.7%, which would have baselined every future change against
the selection rather than the detector.

**The obvious fix is measured and does not work.** `pair_evidence_from` knows how much of the shared
evidence each member participates in, so publishing that as a per-member confidence (as the cohort
detector rightly does with its admitting posterior) is very tempting. On the measured corpus two
swept-in organic accounts **out-rank a genuine operation member**, so an operator shown that ranking
would clear the wrong accounts and doubt the right ones. A number beside a person's name is read as a
judgement about them, so publishing it would be worse than publishing nothing.
`test_attachment_weight_does_not_separate_the_bystanders_and_must_not_be_sold_as_if_it_did` is a
guard against building it, and states what would have to change for it to become buildable.

#### The fix: ask what each member ADDED, not how much it shares

`app/netdetect/attachment.py`. The failed statistic asked how much shared evidence a member
participates in. The one that works asks how much less improbable the set is **without** it: score
the set, then score the set minus one member, in the finding's own weighted log10 units.

**The sign comes out of the arithmetic rather than a threshold.** Removing a genuine member drops
the shared count `k` across many rare features, so the Poisson-binomial tail widens and the score
falls: a large positive delta. Removing a bystander leaves `k` alone on the features carrying the
finding while shrinking `n`, so the tail gets SMALLER and the score can rise: a delta at or below
zero. Measured, every bystander landed at or below zero and every operation member well above it.

Result on the systematic grid: **7 of 7 bystanders flagged, 0 of 96 genuine members flagged, 0
missed**, abstaining on the 4 findings where nobody is weakly attached.

Four rules, and three of them are about restraint:

- **The threshold is RELATIVE to the finding's own median, and that is a measurement.** Globally the
  populations overlap: the weakest genuine member scored **-0.134** and the strongest bystander
  **+0.116**, so any fixed cut misclassifies one of them. `WEAK_FRACTION` (0.25) compares a member
  against the typical member of its own finding, because the scale of a delta is set by how much
  evidence that particular finding rests on. Pinned by a test that fails if the two ever separate
  globally, since that would make a simpler rule viable.
- **It ABSTAINS below `MIN_MEDIAN_CONTRIBUTION` (0.5).** In a homogeneous group every member holds
  the same features, so removing any one barely moves the score and there is no weak member to
  find; a rule that went looking anyway would flag whichever account rounded lowest. The
  professional-beat control lands here and must: a real community IS everybody contributing alike.
  Measured, such findings ran medians of 0.04 to 0.18 while every contaminated one ran 1.57 to 3.92.
- **It REPORTS, it never drops a member.** Removing a flagged account would change the finding's
  membership, score and stored identity on a heuristic, and would silently delete a real
  participant whenever the heuristic got it the other way round. A flagged account stays in
  `members`.
- **`attachment_checked` is explicit, never inferred.** There are THREE states and the middle one is
  easy to lose: checked with weak members, checked with none (every member carries the finding), and
  not checked at all. The last two both present an empty list and are opposite statements about the
  people named. Same distinction as `score: null` against `0` on the analyst's eight signals, and it
  defaults False so rows written before the test existed read as "not checked" rather than as a
  clean bill of health.

**The old guard stays.** `test_attachment_weight_does_not_separate_the_bystanders_and_must_not_be_
sold_as_if_it_did` is still true and still passing: that statistic still fails. Two different
questions, one of which is answerable. `MEMBERSHIP_NOTE` on the response now describes the flag as a
pointer for review rather than a score, and says an empty list is not an all-clear.

Pinned by `tests/test_netdetect_attachment.py` (10).

**Not yet built:** the operation registry (persistent latent entities), the adjudication call, and
a per-member attachment test to stop a finding naming bystanders (see the contamination note above:
the rate is measured and pinned, the cause is understood, and the obvious fix is measured NOT to
work).

### Pre-launch lockdown: only admins can use the product

Live from 2026-08-20 for the Kickstarter campaign. `OMI_LOCKDOWN=true` means every signed-in user
who is not an admin is refused on product routes and sent to `/coming-soon`; the anonymous demo scan
is off; marketing pages, sign-up, sign-in and public `/r/<token>` reports stay open.

**The gate is on the API, and that is the whole point.** A redirect in `app/(app)/layout.tsx` stops
somebody browsing to the product. It does nothing about a signed-in non-admin calling
`POST /v1/scan/link/score` directly with the cookie their browser already holds, which is exactly the
person this exists to stop: the money is spent by the API, so the refusal lives there.
`app/core/lockdown.py` is enforced inside `require_user`, which every product route depends on.

- **`OPEN_PREFIXES` is an allowlist, not a blocklist**, so a route added later is refused by default.
  `/v1/auth` has to stay open or the web app cannot ask who you are in order to redirect you;
  `/v1/waitlist` is the only thing a visitor can do.
- **Anything unauthenticated never reaches `require_user`**, so shared reports keep working by
  construction. Deliberate: they cost nothing to serve and are the best proof the product works.
- **The demo needs its own refusal** (`_refuse_demo_while_locked`) precisely because it is
  unauthenticated. It is also the most expensive anonymous surface there is, running the real engine
  AND a real model call, so at campaign traffic it is a live bill with nobody able to convert.
- **The web learns the mode from the API**, on the user object (`UserOut.lockdown`), not from its own
  env var. One switch, so the two can never disagree about a signed-in visitor.
- **The landing page is the one exception** and mirrors it as `NEXT_PUBLIC_LOCKDOWN`, because
  `app/page.tsx` deliberately makes no API call (putting FastAPI in the critical path of the page
  traffic is bought for capped its throughput at the API's). Both values are committed side by side
  in `render.yaml` and `test_the_lockdown_switch_agrees_across_both_services` fails on drift.

**The code default is `False`.** A stale lockdown outliving its launch date is its own outage, and
whoever had to fix it would be hunting a bug rather than a leftover env var. `render.yaml` commits
`'true'` explicitly, and `app/main.py` logs the mode at WARNING on every boot so it is never a guess.

#### The waitlist, and the one email it sends

`WaitlistEntry` + `POST /v1/waitlist` (public, rate-limited) + `/v1/admin/waitlist` (list, CSV,
notify). Signup joins it too, on **both** the Clerk and legacy paths: somebody who goes straight to
sign-up during lockdown has, in effect, asked to be told when they can use the product, and without
that they would be silently left off the launch email.

- **The email is unique and normalised before insert**, so `Foo@Bar.com` and `foo@bar.com` are one
  person. Without it the launch blast mails them twice, which is the most obvious possible way to
  look amateur on the one day everybody is looking.
- **A duplicate join is a SUCCESS, not an error**, and the response is byte-identical either way, so
  the endpoint cannot be used to check whether a particular person signed up.
- **`notified_at` is stamped per address INSIDE the send loop**, not after the batch. A run that dies
  half way resumes instead of restarting, so re-running is always safe. The operator will re-run it.
- **No SMTP means nothing is sent AND nobody is marked notified.** The trap that avoids: marking the
  list done on a run that sent nothing, so the real blast later skips everybody.

**SMTP is not configured on this deployment.** `OMI_SMTP_HOST` and friends have to be set before the
blast will send anything; until then `/v1/admin/waitlist/notify` says so and the CSV export is the
fallback.

#### Opening the site

1. `OMI_LOCKDOWN` -> `false` (API) **and** `NEXT_PUBLIC_LOCKDOWN` -> `false` (web) in `render.yaml`.
2. Redeploy **both** services. The API's boot log confirms the mode.
3. `POST /v1/admin/waitlist/notify` as an admin, repeatedly until `remaining` is 0.

Nothing else has to change: the demo comes back, the landing page swaps the waitlist for the scan
form, and `/coming-soon` simply stops being reachable by redirect.

### Three plans, and the ceiling that makes them possible

Product decision (2026-08-20). `app/core/plans.py` is the catalog and the single place any question
about a plan is answered. Mirrored in `apps/web/lib/plan.ts`; `tests/test_deployed_credit_contract.py`
reads BOTH sources and fails on drift in name, price, credits or ceiling.

| tier | price | credits | accounts | lookup ceiling | adds |
|---|---|---|---|---|---|
| Starter | $14.99 | 12 | 240 | 640 | the core product |
| Reporter | $79 | 75 | 1,500 | 3,409 | signal breakdown, saved graphs, monitoring |
| Research | $249 | 250 | 5,000 | 10,869 | coordination detection, API access |

**1 credit = 20 accounts now, not 50, and the old rate was losing money.** At ~2 upstream calls per
account and ~$0.005-0.006 a call, 20 credits at 50 accounts each is ~1,000 accounts for $11-15 of
upstream against $14.26 of net revenue: a **6% gross margin on X**, negative on a metered API. The
number nobody had run was call volume x call price against revenue. `scan_batch_unit` is 20 and
`test_the_charged_rate_matches_the_rate_the_plans_are_priced_against` pins it to
`plans.ACCOUNTS_PER_CREDIT`.

**The ceiling is the actual fix, not the credit rate.** Credits bound how many accounts get SCORED.
Nothing bounded **compile**, which charges no credits and still calls a provider that bills. Its only
limit was `OMI_UPSTREAM_DAILY_CALLS_PER_USER` at 1500/day, which at $0.006 a call is **$270 a month
from one $14.99 subscriber** and needs no abuse to reach: somebody browsing many comment sections and
scanning a few. `enforce_period_budget` closes it, and four things about it are load-bearing:

- **Monthly and aligned to the customer's billing period**, so the meter resets when the credits do.
  A lookup allowance refilling on a different day from the credits is its own support load.
- **Derived from the tier**, never configured separately, so it cannot drift from what the plan was
  priced to afford. `test_a_tier_can_spend_every_credit_it_includes` fails if a ceiling ever drops
  below the scan cost of its own credits.
- **A scan is refused UP FRONT, with its projected cost**; a compile is simply declined. That
  asymmetry is the whole reason enforcement takes a `projected` argument: declining a compile costs
  the customer nothing, while a scan takes credits, so refusing one mid-flight means they paid for
  work that got cut off.
- **`calls_included == 0` means UNMETERED, never "exhausted".** Reading it the other way locks out
  admins, the accounts the exemption exists for. Same shape as `score: null` vs `0`.

**It is a meter, not a wall.** `POST /v1/billing/create-topup-session` sells credit packs at $1/credit
(~70% margin). A hard stop turns the most engaged customers into churn; selling them more turns the
same person into revenue, and it is what makes a bounded plan honest. The top-up is `mode: payment`,
never touches `plan_tier` or `subscription_status`, and never redirects to the Customer Portal (the
people who buy overage are exactly the people who already have a subscription).

**Margin is flat across the ladder, and that is deliberate.** Worst-case upstream share of list price
is 25.6% / 25.9% / 26.2%. Upstream cost here is purely variable and perfectly linear, so a per-unit
volume discount comes straight out of margin rather than out of fixed cost being spread; modelled
with normal SaaS discounting, Reporter and Research fell to 46% and 41%. The bigger tiers are worth
more because of FEATURES, whose marginal cost is zero. `test_margin_does_not_erode_as_the_tiers_grow`
is the guard.

#### The Stripe Price is what decides the tier

`_handle_invoice_paid` reads the Price off the invoice and looks it up in the catalog. Consequences:

- **A tier whose Price id is unset does not merely fail to sell: its renewals resolve to no tier and
  grant NOTHING.** `/v1/billing/preflight` names every missing one. An unrecognised Price grants
  nothing and reports `UnknownStripePrice` to the tracker rather than guessing at a default, because
  guessing would pay out a subscription tier for a one-off credit pack.
- **`invoice_price_ids` reads THREE shapes.** Stripe has moved this field twice
  (`lines.data[].pricing.price_details.price`, then `.price.id`, then `.plan.id`). Reading one shape
  yields an empty list on the others, which fails closed to Free — a silent downgrade of every
  paying customer on their next renewal.
- **`"manual"` is now a granting billing_reason**, because a `payment`-mode Checkout invoice carries
  it and without it a top-up takes the money and grants nothing. That widening is only safe BECAUSE
  the Price gates the grant: a hand-raised dashboard invoice for an unconfigured Price grants
  nothing. `test_a_manual_invoice_whose_price_we_do_not_know_grants_nothing` is what keeps it safe.
- **`OMI_STRIPE_PRICE_ID` (the legacy single-plan price) must stay set.** Every current subscriber's
  renewal invoices carry it forever; it maps to Starter. Dropping it downgrades exactly the customers
  you already have.
- **`OMI_MONTHLY_CREDIT_GRANT` is gone**, along with `settings.monthly_credit_grant`. One global
  grant could only be right for one of three plans, and leaving it as a fallback would let a
  misconfigured Price quietly pay out the wrong tier instead of surfacing the fault.
- **Plan CHANGES go through the Stripe Customer Portal**, which prorates correctly. The portal needs
  all three products added to its allowed list in the dashboard, and nothing in the app fails
  visibly without that: the subscriber just lands in a portal with no switch offered.

#### The three feature gates, and the one that is not an entitlement check

`require_feature(...)` (`core/auth.py`) is the dependency; `CurrentUser.features` carries the
entitlements so a hot path does not re-query. It answers **402, not 403** — "forbidden" reads as a
permissions bug and sends a customer to support, "payment required" is true and is answerable in one
click.

- **Signal breakdown** (Reporter). `assessment_for_viewer` now takes `features`. Still filtered on
  SERVE, never on persist, so a customer who upgrades today gets the breakdown on investigations
  they ran last month. `NEVER_PUBLIC_ACCOUNT_FIELDS` stays unreachable at any price: those are the
  reasons a paragraph was withheld, and showing them undoes the withholding.
- **Saved graphs and monitoring** (Reporter). Gated on **writes only**. A customer who downgrades
  keeps their graphs and watchlists and can still read them; making somebody's own saved work vanish
  on a plan change arrives as "the product lost my data", not as an upgrade prompt.
- **Coordination** (Research) is **NOT** a plain entitlement check, and this is the important one.
  A `Campaign` has no owner by design (one operation seen by two customers is one campaign), which
  is exactly why `/campaigns` and `/narratives` are admin-only: opening them to customers previously
  exposed other people's `context_id` values. `CampaignDetection` is different — it is one run over
  ONE investigation and carries that investigation's `user_id`. So `_coordination_scope` returns an
  **owner id, not a boolean**, and every query filters on it. A gate that only said "allowed" would
  let a caller reach an unfiltered query, which is precisely how the original exposure happened. A
  non-owner gets **404, not 403**: 403 would confirm that somebody else's scan found coordination
  there.

### Billing

`compute_scan_credits = ceil(accounts / scan_batch_unit) × credits_per_batch[platform]`, minimum 1.
**1 credit per 20 accounts, same rate on every platform** (100 accounts = 5 credits). It was 1 per 50
until 2026-08-20 and 50 was loss-making: see "Three plans, and the ceiling that makes them possible"
above for the arithmetic. The per-platform knobs stay because upstream prices can move independently;
they are equal today because measured per-account cost is within ~20% across X, Reddit and YouTube.

**There are two separate free tiers, and neither one is derived from the other.** Confusing them is
the easy mistake, because both get called "the free scans":

| | Who | Amount | Where it lives |
|---|---|---|---|
| Pre-login demo | Any visitor, metered per IP | **1 scan**, ≤25 accounts | `DEMO_FREE_SCANS_PER_IP` + `DEMO_MAX_COMMENTERS`, hardcoded in `app/routes/scan_async.py` / `scan.py`, test-pinned |
| Signup trial | A new account | **1 credit**, then they pay | `OMI_FREE_TRIAL_CREDITS` in `render.yaml` (code default in `config.py` also 1) |

The signup trial is **5** (2026-08-19, at the owner's request). It has been 25, then 5, then 3,
then 1, and is now 5 again. At the 1-credit-per-20-accounts rate that is up to **100 accounts** for a
new account before they pay. Don't move it without being asked.

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

### The scope statement, and where it has to appear

The product scores named accounts and the reports get posted publicly, so **what the number is NOT**
has to travel with it. Four surfaces, and the placement of each was a decision:

- **`ScopeNotice`** sits ABOVE the verdict on `/r/<token>`, so nobody reads a number before reading
  what it means. It is deliberately **not `no-print`**, unlike every other interactive block on that
  page: the exported PDF is the version that circulates as evidence, and a document making scored
  claims about people with no scope statement attached is the exact artifact this exists to prevent.
- **The markdown export** carries the same statement at the TOP, above the verdict. It used to have a
  one-line caveat at the very bottom, which is the part nobody reads and the first thing cropped from
  a screenshot. Break the lines on clause boundaries: a phrase split mid-sentence ("whether money /
  changed hands") is invisible to a reader scanning and to any test asserting on it.
- **The CSV export** carries it as `#`-prefixed lines at the BOTTOM, after a blank line, which is the
  one place in this product the statement does not lead. A preamble would push the header off row 1,
  and a CSV whose first row is not its header breaks sorting, filtering, and every tool that reads
  one. The clipboard copy carries no footer at all: its target is a spreadsheet cell range, not a
  document, and prose rows pasted into a sheet are noise rather than a notice.
- **`/accuracy`** is the full policy, linked from the report, the landing footer, the auth footer and
  the marketing nav. Written for the person who has just found themselves scored and is upset, which
  is the audience that matters most on that page.

The claim it makes, which must not be softened: these are probabilistic readings of public behaviour,
not findings of fact; not an allegation that anyone broke a law or a platform rule; no claim about who
operates an account, whether money changed hands, or anyone's intent. It names the confusable shapes
(businesses, fan accounts, news feeds, new users, second-language writers) as things that legitimately
resemble the patterns, and says a low score is not a certification either.

`tests/test_report_disputes.py` asserts the export leads with it and that the "Request a review"
promise on the page points at an endpoint that actually accepts a submission.

### Disputes: the recourse an accused account has

OmiSphere publishes scored claims about **named real people who never agreed to be analysed**, and the
results get posted into comment sections. A person who thinks a report is wrong about them needs a way
to say so, and the operator needs to withdraw a public claim fast. That is what `ReportDispute` and
`POST /r/<token>/dispute` are for. It is a legal artifact as much as a product one: "reviewed and acted
within a day" is a materially different position from "there was no way to reach us", and it is the
operational answer to a data-protection objection from someone whose data was collected indirectly.

Two rules pull against each other and both must hold:

- **Filing is anonymous and easy.** The person disputing is not a customer; making them sign up to the
  product accusing them would make the recourse theatre. The route is unauthenticated, sits under the
  public rate limiter, and asks for as little as possible.
- **Filing does NOT unpublish anything.** Otherwise anyone silences any report by claiming to be named
  in it. The takedown is a decision, not a side effect of a form submission.

They reconcile on the admin side: `POST /v1/admin/disputes/{id}` resolves and optionally revokes the
token in one call, and **it works on ANY report, not only the admin's own**. The owner-scoped
`DELETE /v1/investigations/{slug}/share` cannot serve here by construction: the person harmed is never
the owner, and waiting for the owner to act is not a takedown process. Revoking clears the token so
`/r/<token>` 404s immediately, including for links already posted publicly.

**The investigation itself is never deleted**, only the public claim. The customer keeps their work;
what is withdrawn is the thing that caused the harm.

Other decisions worth keeping: a dispute about an **already-unshared** report is still recorded (a 404
there reads as stonewalling at the worst moment); one open dispute per (token, subject) so a double
submit does not produce two queue entries; `ip_hash` is a hash and exists only for abuse triage.
Pinned by `tests/test_report_disputes.py` (13 tests).

### The shared-report funnel

A shared report (`/r/<token>`) is the highest-intent surface this product has: someone is reading an
analysis of a post they care about. Three CTAs carry them into signup, all saying **"Scan more comments
on this post"** and all `no-print` (the report doubles as an exportable document, and a signup pitch
inside a PDF someone is using as evidence undermines what made it credible):

| Placement | Where | Component |
|---|---|---|
| Strip | under the top bar, before any scrolling | `ScanMoreStrip` |
| Rail | sticky beside the article, `xl` and above only | `ScanMoreRail` |
| Footer | end of the report, where the reader is deciding | `ScanMoreFooter` |

Each links to `/sign-up?claim=<token>`. **The token is the whole point.** Drop it and signup still
converts but lands them on an empty dashboard with no idea which post they came from.

**The flow:** `/r/<token>` → `/sign-up?claim=<token>` → `/welcome?claim=<token>` → `POST
/v1/investigations/claim` → `/investigate?url=<source>&claimed=<slug>`.

The token has **two carriers** because Clerk runs multi-step sign-ups across its own sub-routes
(`/sign-up/continue`, email verification, an OAuth round trip) and a query param does not reliably
survive all of them: `fallbackRedirectUrl` is the happy path, and `RememberClaim` mirrors it into
**sessionStorage** (not localStorage: a stale token surviving for weeks would silently claim a report
during an unrelated future signup).

`POST /v1/investigations/claim` copies the shared investigation into the caller's archive. Four things
about it that must not change:

- **`share_token` is NOT copied.** It is unique and drives the `/r/<token>` lookup, so a second row
  holding it would either fail the insert or make the public report ambiguous for every visitor,
  breaking the very link that produced the signup. The copy is private until its owner shares it.
- **Idempotent per (user, token)** via the `claimed_from_token` column, because `ClaimHandoff` fires
  from a page load nobody can guarantee happens once (a refresh, React 18's double mount, a retried
  request) and `payload_json` is routinely megabytes. `claimed_from_token` is deliberately **not
  unique**: many people claiming one shared report is the entire point.
- **The original is untouched** and **no credits move**. Reading is free; scanning is what costs.
- **`/claim` is declared after `/{slug}`** and is safe only because `{slug}` is GET and PATCH while
  claim is POST. Adding `POST /v1/investigations/{slug}` later would shadow it silently;
  `test_claim_shared_investigation.py` asserts against that.

**The funnel argues with facts, never with pressure.** Three numbers, each real or absent:

- **`Investigation.commenters_available`** is how many commenters were COMPILED for the post, set at
  scan time from the candidate-list row count (free there, and the read path needs no join). Against
  the scanned count it produces the line the whole funnel rests on: *"checked 25 of the 312 accounts
  that commented, 287 have not been looked at."* NULL on rows written before it existed, and the CTAs
  fall back to a qualitative sentence rather than inventing a denominator. Copied on claim, or the
  claimer's own report forgets the gap.
- **`read_count`** is the deduped `public_report_view` count for the token, counted BEFORE the current
  request is logged so a first visitor is never told they are the second. Hidden below 25 reads,
  because a low number reads as "nobody cares". **The token lives inside `payload_json`, not in a
  column** (`EventLog` has none), so the query is a JSON path comparison; the first version compared a
  non-existent `EventLog.token` and would have silently returned `None` forever.
- **`_scanned_count`** prefers `commenter_count` and falls back to `len(commenters)`, because a
  payload with commenters but no count rendered "0 of 312", which reads as a broken product.

**The report lists EVERY account it scored, not just the flagged ones** (`_all_commenters`, rendered
as "Accounts scanned · N · M flagged"). A flagged-only list read as a hit list and hid the most
reassuring thing in the report, which is that most of the section came back clean; it also made the
product look like it flags everything, the opposite of what the score discipline is for. Sorted worst
first, so the findings still lead.

That list is deliberately **lighter** than `top_flagged`: no `reasons`, no `recent_activity`. Those are
per-account evidence blobs and carrying them for a whole 150-account section would multiply the public
response by data the table never renders. `_ALL_COMMENTERS_CAP` (250) sits above the operator scan cap
so it is unreachable in practice and exists only so a pathological payload cannot produce an unbounded
response. The page falls back to the flagged-only table for reports generated before the full list was
carried, and the **markdown export lists everyone too**: a page and an export that disagree about who
was scanned is worse than either alone.

**The shared report carries the analyst's per-account reads**, not just engine percentages: each row
shows the model's OMI score, its tier, and what it actually wrote. A summary of an investigation is not
the investigation, and without the prose a promoted link is just a percentage.

Those reads go through **`assessment_for_viewer(..., is_admin=False)`, hardcoded**, because `/r/` is
unauthenticated and the admin-only signal breakdown must not be reachable there. Hand-filtering the
fields would drift from the gate the rest of the app uses. Unresolved aliases are dropped: there is no
identity to attach a public claim to.

**`/r/<token>/json` used to dump `payload_json` raw**, and that blob carries the analyst cache with its
admin-only signals and internal provenance (trace ids, prompt hashes, token counts). So the gate was
one URL away from meaning nothing. `_public_payload()` strips the cache key; the filtered reads still
ride along on `investigation.account_reads`. Note this leak was NOT caught by the source-level guard in
`test_signals_are_admin_only.py`, which looks for `entry["assessment"]` and cannot see a route that
dumps the whole payload.

`account_reads` is built inside **`_investigation_to_dict`**, not per route. Adding it at one call site
is exactly what made the markdown export disagree with the page it exports, which a test caught.

**Nothing on this page may be estimated.** It is a report about fabricated engagement: one invented
number beside the real ones discredits all of them, and it only takes one screenshot. That rules out
fake scarcity, countdown timers, and invented view counts, and it is a business argument rather than a
stylistic one.

The **methodology note** on the public report described `memory` and `coordination` as two of the
eight long after they were replaced, so a sceptical reader checking the product's own description
found it wrong about itself. It now names the real eight and states the convergence rule.

`ClaimHandoff` never dead-ends: a revoked token (the owner unshared it between the click and the
signup) is the expected failure, so it offers the normal investigate flow rather than showing a new
customer an error page.

The arrival banner on `/investigate` is gated on `?claimed=`, and it matters: without it the
pre-filled URL and the already-scanned rows look arbitrary. Accounts the original report covered
already come back marked `scanned` by the compile step, so "scan more" is literally what the page
offers.

**The signup trial is 5 credits.** One credit covers up to 50 accounts, so a funnel signup can
scan up to 100 accounts before paying. Set in **four** places and
`test_deployed_credit_contract.py` fails on drift between the env pair: `OMI_FREE_TRIAL_CREDITS` +
`NEXT_PUBLIC_TRIAL_CREDITS` in `render.yaml`, `config.py`'s default, and `plan.ts`'s default.
(`.env.example` is a fifth, unchecked copy; it had been stale at 3 for two changes.)

**Anything the copy STATES about the trial must be derived from it, not written out.** `CREDIT_NOUN`
already existed because hardcoding "credits" became "1 free credits" in five places the moment the
trial was cut to one. Moving it back to 5 broke the next layer: the investigate page read "your 1
free credit covers up to 50 more", which became "your 5 free credits covers up to 50 more" — wrong
about the verb AND wrong about the number, since 5 credits is 5x whatever the rate is (250
accounts then, 100 now). `ACCOUNTS_PER_CREDIT`
and `TRIAL_ACCOUNTS` in `plan.ts` are the derived facts; use them.

Copy around that number goes through **`TRIAL_CREDITS_LABEL`** / **`CREDIT_NOUN`** (`lib/plan.ts`).
Hardcoding "credits" read fine at 3 and became "1 free credits" in five places the moment the trial
was cut, so don't write the noun out.

### The paid plan is called "Omi Premium Member"

`PLAN_NAME` in `apps/web/lib/plan.ts` is the single source, used by the pricing card, the landing
page's closing pitch, the settings billing card, the subscription status row (an active subscriber is
shown the membership name rather than the word "Active"), and the subscribe button ("Become an Omi
Premium Member · $13.99/mo").

Deliberately **not** an env var, unlike the credit and price figures. Those exist as env vars because
they can disagree with what the server actually charges and grants; a plan name cannot, so a second
copy in Render would be a liability rather than a safeguard.

**It does need to match the product name in the Stripe dashboard**, which is a dashboard change and
not a code one. The site names the plan, then Stripe Checkout shows whatever the product is called,
and a customer seeing two different names at the moment they hand over a card reasonably wonders what
they are buying. Nothing in the repo can detect that drift.

### Billing: Stripe ($13.99/mo, 20 credits), webhook + API backstop

Setup walkthrough: `docs/stripe-setup.md`. **Credits arrive by two independent routes, on purpose.**

1. **Webhook (primary).** Stripe pushes `invoice.paid` to `POST /v1/billing/webhook` and credits land
   in seconds. Inert until `OMI_STRIPE_WEBHOOK_SECRET` is set — an unverified webhook is an open door
   to anyone who wants to grant themselves credits, so no secret means it acks 200 and grants nothing.
2. **API reconciliation (backstop).** `app/core/billing_sync.py` reads the customer's subscription and
   paid invoices and grants any invoice not already credited. Runs on return from checkout
   (`POST /v1/billing/sync`, forced), on the billing page (throttled 5 min/user), and — the one that
   matters — inside `consume_credits` just before it would refuse a scan, so a subscriber whose
   renewal just landed is never told to subscribe. Never raises: a Stripe outage degrades to the
   normal 402, never a broken scan.

**Do not delete the backstop now that the webhook works.** A webhook can be registered against the
wrong host, killed by a rotated secret, or exhaust its retries during an outage; reconciliation is
what stops any of those becoming a customer who paid and got nothing. Running both is safe for
exactly one reason: **both claim the same per-invoice row**, so whichever arrives first grants and the
other loses the unique-index race. Pinned by
`tests/test_billing_webhook_primary.py::test_webhook_and_reconciliation_never_both_credit_the_same_invoice`.

`WEBHOOK_EVENTS` in `billing.py` is the single source of truth for what to tick in the Stripe
dashboard, and `test_webhook_events_match_the_dispatch_table` asserts it equals what `_dispatch`
actually handles. Add a handler without adding it there and the dashboard is never told to send that
event — the feature is dead on arrival, silently.

**The webhook URL is the API host, not `OMI_PUBLIC_BASE_URL`.** That variable is the *web* app, where
Stripe returns the customer. Registering the web host as the webhook endpoint is the most common way
this fails, and it fails quietly. `GET /v1/billing/preflight` prints the correct URL for the
deployment it runs on — but call it **directly on the API host**: through the web app's `/api` proxy
it sees the web host, detects that, and refuses to print a URL rather than printing a wrong one.

`GET /v1/billing/preflight` answers "can this deployment take a payment?" against the live Stripe
account: it validates the key, retrieves the price to confirm it is recurring and the right amount,
and checks the return URL. Point anyone debugging a "billing doesn't work" report at it first —
`OMI_STRIPE_SECRET_KEY` alone is NOT enough, and a missing `OMI_STRIPE_PRICE_ID` fails only at the
moment a customer clicks Subscribe.

Its three `webhook_*` checks are **deliberately non-blocking**: without a webhook, reconciliation
still credits every payment, so `ready` stays true and the checks report degraded-but-working.
`webhook_delivery` is the one that catches a webhook nobody tested — it reports the last real event
this deployment received, and excludes reconciliation's own `credit_grant:` rows from the same table
so it can never claim a healthy webhook on a server that has never received one.

**Checkout survives a payment method Stripe has not approved yet.** A new Stripe account commonly has
Link live while Cards are still in review, and asking for `payment_method_types=[link, card]` makes
Stripe reject the whole Session: the account can take money, our hardcoded list is what refuses it.
So a payment-method rejection retries once **without** `payment_method_types`, which makes Stripe
offer whatever the dashboard actually has enabled. `OMI_STRIPE_PAYMENT_METHOD_TYPES` (default
`link,card`) is still the explicit override. Pinned by
`tests/test_billing_checkout_payment_methods.py`, which also asserts the retry keeps the metadata:
a fallback that dropped `omi_user_id` would produce a paid invoice crediting nobody.

**The "not configured" state has two messages, chosen by `is_admin`.** It used to show every
customer `OMI_STRIPE_SECRET_KEY` and say "Card payments aren't switched on", which reads as a product
limitation rather than an unconfigured server, and confused the product owner into thinking Stripe
had blocked cards. Customers now get a plain apology; only admins see env-var names, on all three
branches (unconfigured, no-URL, 503).

Two pieces of middleware sit in front of the webhook and neither currently breaks it, but both are
worth knowing before you change them:

- **`BodySizeLimitMiddleware` (1 MiB) only counts bytes — it does not rewrite them**, which is why
  raw-body signature verification still works. If it ever buffered or re-emitted the body, every
  delivery would fail verification. Note the failure mode if a payload *did* exceed the cap: the body
  is truncated, the signature no longer matches, Stripe gets a 400 and retries into the same wall.
  Subscription invoices are nowhere near 1 MiB, so this is theoretical today.
- **The global rate limit (600/min per IP) applies to the webhook**, keyed on Stripe's sending IP. At
  this product's volume it will never be reached, and a 429 is safe because Stripe retries — but if
  you ever see delayed crediting during a burst, that is where to look first.

Four rules in `app/routes/billing.py` that must not be softened — each replaces a bug that cost or
would have cost real money:

- **Only `invoice.paid` grants credits.** A new subscription emits `customer.subscription.created`
  *and* `invoice.paid`; granting on both double-credits one charge. Subscription events move status
  and renewal date only.
- **Credits are ADDED, never "topped up to N".** The old code did `max(balance, grant)`, so a
  subscriber renewing with ≥20 credits paid the full price and received **nothing**.
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

Same select-then-scan shape as the signed-in app, X-only, capped at 25 repliers, **1 scan per IP**:

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

### Never look a candidate list up with `.scalar_one_or_none()`

Use **`_candidate_list_for(session, platform, content_id, uid)`** (`scan_async.py`). All four call
sites go through it — signed-in compile, signed-in score, demo compile, demo score.

`CandidateList` has `UniqueConstraint("user_id", "platform", "content_id")`, which *looks* like it
forbids a second row. **Two independent reasons it doesn't:**

1. **NULL owners.** SQL treats NULLs as **distinct** (Postgres, i.e. production, and SQLite), so the
   constraint is inert whenever `user_id IS NULL`. The anonymous demo bucket is entirely NULL-owned by
   design, and local mode (`OMI_REQUIRE_AUTH=false`, the id=0 user) maps its owner to NULL too.
2. **Databases predating the constraint.** `create_all` leaves existing tables alone, and the boot
   upgrade pass backfills columns and `table.indexes` only. A `UniqueConstraint` lives in
   `table.constraints`, so `_ensure_indexes` **cannot see it** and never adds it to a
   `candidate_lists` that already existed. On such a database duplicates are possible for **real user
   ids** as well, so this was never only a local-mode concern.

Either way two concurrent compiles of one post both see "no list yet" and both insert, and
`scalar_one_or_none()` then raised `MultipleResultsFound` out of the route as a **raw HTTP 500** —
permanently, since the rows persist, and for the whole anonymous bucket, since every visitor shares
it. This shipped and was live on the front page.

`_candidate_list_for()` prefers the duplicate that already holds cached commenters (settling on the
empty one would silently re-fetch upstream on every compile, paying for it each time), ties break on
lowest id so concurrent callers converge, and it best-effort deletes leftovers holding **zero**
candidates (deleting a populated one would cascade its candidates away). Existing poisoned rows heal on
next touch. Guarded by `tests/test_demo_duplicate_candidate_list.py` and
`tests/test_signed_in_duplicate_candidate_list.py`.

Not done, and worth doing properly one day: actually enforcing uniqueness. It needs a **partial**
unique index for the NULL case (`... WHERE user_id IS NULL`), and it must be preceded by a dedupe
migration or the index build fails on live data that already has duplicates.

---

## A bug class worth knowing

Python resolves a nested function's free variables against **module globals**, not the enclosing
function's local imports. A function-level `from x import y` does **not** make `y` visible to a
closure defined in a *different* function. This shipped once and disabled a whole feature silently,
because the background pool logs exceptions instead of raising them.

`python -m pyflakes app/` catches it in seconds. It currently reports **zero undefined names** —
keep it that way, and run it after touching anything that uses closures inside background work.

**The same trap has a second form, and pyflakes does NOT catch this one.** A function-level
`import os` makes `os` local to the *entire* function, including lines *above* the import — so an
earlier use raises `UnboundLocalError` at runtime while looking perfectly fine statically. This
happened in `_build_engine` (`app/storage/db.py`): a local `import os` added inside the Postgres
branch broke `os.makedirs` in the SQLite branch above it, and only a concurrency test caught it.
If a module already imports something at the top, use it; don't re-import it inside a function.

---

## Design system (don't drift)

**The binding rules live at the top of `app/globals.css`, not here.** That comment block is the
document; this section records what has bitten and why.

Near-black instrument ramp (`#010203` ground, `#0a0d12` panels), blue identity (`#3b82f6` /
`#5b9dff`), purple for the AI layer (`#8f7bf0` / `#5b3fd8`), tier colours green→amber→orange→red
(authentic→bot). **No glow, no gradient FILLS, no glassmorphism. Corners are 2 to 4px.** Archivo for
display (`.display` / `.display-hard` / `.display-hard-sm`), Inter for interface, JetBrains Mono for
data and evidence.

This section used to describe a deep-navy ramp and Inter as the display face, long after both had
changed. **A design note that describes the previous design is worse than none**: the next session
reads it, believes it, and builds to it.

**There is one display voice on both sides of the login boundary.** The pre-login page used to run a
second one (Space Grotesk, `.display-alt`) so it would read as "marketing"; the effect was that the
front page looked like a different product from the app a visitor was about to sign into. Space
Grotesk is no longer loaded at all (`app/layout.tsx`), so don't reach for `.display-alt` — the class
survives only as an Inter fallback so stray usage degrades instead of breaking. Headings at
`text-xl` and above take `.display-hard-sm` (Archivo 800); `.display` at those sizes is a 600 weight
and reads as a document heading rather than as signage.

### Instrument chrome: the vocabulary, and the one rule that matters

`@layer components` in `globals.css` carries the console vocabulary. Compose with it rather than
re-typing its parts, which is how four spellings of one label appeared in the first place.

| | |
|---|---|
| `.meta` (+ `.meta-hi`, `.meta-on`) | THE label voice. Mono, 10px, 0.18em, uppercase. Field labels, column heads, panel titles, status words. **Never a sentence**: past about five words the tracking stops being readable. |
| `.panel` / `.panel-head` / `.panel-body` | A framed readout. The header is a 34px bar, label hard left, meta hard right, hairline under, on its own ground. |
| `.tick-frame` (+ `.tick-frame-live`) | Corner registration ticks. |
| `.readout` / `.readout-v` | A label over a figure. Every number in this product should be presented this way. |
| `.led` (`-ok` `-warn` `-fail` `-work` `-off`) | Square status lamp. |
| `.rack-table`, `.rule-rack`, `.focus-hard` | Data table, capped hairline, square focus outline. |

`Card` gained `flush` (drops padding so a `CardHead` can touch the frame) and `ticks`. `CardHead` is
the panel header. Default `Card` padding is **18px**, down from 24: at 24 the gaps inside a panel
compete with the gaps between panels and a column of them reads as a feed of cards.

**The ticks are rationed on purpose**: the primary readout on a page, never every panel on it.
Today that is `ConsoleHeader`, the investigation case header, the account subject header, the
analyst panel, and the live progress panels. Ticks on everything is decoration, and the design
language's own rule is that decoration is not a purpose.

**`.tick-frame::after` must stay at `inset: 0`.** It was `-1px`, to sit ON the border. Every host
that wants ticks also wants `overflow-hidden` (a panel header has to be clipped to the frame's
corners), so the overlay was clipped away entirely — drawn, then thrown out, on exactly the panels it
had been rationed to. It rendered as nothing at all and looked like the class not working.

### `ConsoleHeader` replaced eight copies of one header

Eight workspace routes had each hand-rolled the same page-header slab and they had already drifted:
different paddings, different heading margins, three spellings of the right-hand readout, and
`/investigate` — the product's primary verb — with no slab at all. `components/shared/console-header.tsx`
is the one implementation.

**`SECTION_INDEX` is declared once, in that file, in the sidebar's own order.** A numeral that
corresponds to nothing is decoration pretending to be a filing system, which is worse than no
numeral, so pages take their number from the map rather than passing a literal.

### Colour bugs that were live, and the class they belong to

Every one of these was a value that had outlived the palette or the semantics around it. **When a
colour token is retired, grep for its literal**, because the drift never lives in the token file.

- **`rgba(217,164,74,…)`, a brass/amber left from a retired palette**, in four places. The worst was
  `Input`'s focus state: a **14px amber glow**, in the one design language that forbids glow by name,
  in the colour that means "elevated suspicion" everywhere else on the page. Also the whole
  `RadialGraph` field, and the posting heatmap's intensity ramp, so every cell of every account's
  calendar carried a warning tone before anyone had read it.
- **`bg-brand-gradient` used as chrome.** It is the suspicion ramp and the design language reserves
  it for surfaces where the scale IS the subject. It was painting the scroll-progress bar, so
  reading to the end of a report ran the bar red, and it was the fill of every card's suspicion
  meter, where a gradient along the LENGTH described the distance travelled rather than the reading.
- **A blue→purple diagonal** on the archive empty state, forbidden by name (blue is the identity,
  purple is the AI layer, a gradient between them says neither).
- **Two `drop-shadow(0 0 6px ${color}66)` filters** where `color` was `var(--tier-low)`. String
  concatenation onto a CSS variable produces `var(--tier-low)66`, which is not a colour, so the
  declaration was dropped and the glow never painted. Removed rather than repaired.

### Meters are square and graduated

`ProbabilityBar`, `SignalBreakdown`, `ConfidenceBand`, the detector cards and the history rows all
mark **25 / 50 / 75**, the real tier boundaries `ScoreScale` names. As unmarked stadium fills, 46 and
54 were eight pixels apart and looked identical, and they are a band apart. `ProbabilityBar` takes
`ungraduated` for the one quantity that is not on the 0-100 OMI scale (a detector's share of score
movement), because marking boundaries a quantity does not have is worse than marking none.

`ScoreRing` has a 20-mark graduation ring and a **butt cap**: a round cap adds half a stroke past
each end of the sweep, which on a 96px ring reads about two points high.

**`TierBadge` stays round.** It is the product's primary output and the tailwind config calls it out
as a status pill by name. Everything else that was a stadium chip is now square.

### `RadialGraph` was the most off-brand thing in the product

It rendered as a deep-space scene: a warm radial-gradient ground, two Gaussian blur filters, glossy
spheres with a specular bead, an animated focal ripple, and a private warm community palette that
ignored the `--cluster-N` values the design system defines for exactly that purpose. Four rules
broken at once, on the most analytical surface there is.

Now: flat ground, a measurement grid, labelled range rings, bearing ticks at the rim (not spokes
through the field, which cross every edge in the chart), a static focal reticle, square nodes with
the **tier as a ring stroke outside the body** so community and tier stay separately readable, and a
header stating node and edge counts.

### `Reveal` fails open, and it has to

The hidden state is `opacity-0`, so anything that stops the IntersectionObserver from firing leaves
content permanently invisible with nothing on the page to say so. The one thing wrapped in a
`Reveal` on this site is the **free scan form on the front page**, which is the entire pre-login
conversion path: the failure would cost every anonymous visitor and appear in no log.

It now shows immediately when `IntersectionObserver` is absent or its constructor throws, and a
4-second backstop reveals it regardless. Content below the fold is off-screen when that fires, so
the only thing lost is an animation nobody was positioned to watch. Same lesson as `AuthFormGate`'s
12-second timeout and the analyst's "check back in a moment": **a state with no terminal branch is
not a loading state, it is a silent failure.**

### The gateway name is never rendered, and a test enforces it

`lib/analyst-identity.ts` holds `ANALYST_NAME`, `analystProviderLabel()` and `scrubVendor()`. The
vendor name is not in our copy at all: it arrives inside VALUES the API writes
(`openrouter-omi-analyst-v1`, `ProviderError: openrouter HTTP 404`) and gets printed verbatim, so
render time is the only place to stop it.

`lib/analyst-identity.test.ts` scans every source file and fails on the literal, allowing exactly two
paths: `lib/analyst-identity.ts` itself, and **`app/(marketing)/privacy/page.tsx`, where naming the
real subprocessor is legally correct and must not be scrubbed.** The guard strips `//` comments and
`*` JSDoc continuations but not JSX block comments, so a `{/* … */}` that spells the vendor fails the
suite; word around it rather than loosening the guard.

The last leak closed was `/r/<token>`, which printed `Generated by {commentary.provider}` raw on the
**public** report, the surface most likely to be screenshotted and posted.

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

### The coordinated-events surface is removed from the product, not from the code
<!-- Superseded in part: /narratives is now the live admin coordination queue. See "The cohort
     coordination detector" below. The campaigns UI and /rc/ web route are still deleted. -->


Product decision (2026-07-28): the campaigns UI shipped clusters the engine had not earned the right
to call coordinated, so it is gone from the site pending a real detection algorithm.

**Deleted (web only):** `app/(app)/campaigns/*`, the public report route `app/(public)/rc/*`,
`lib/campaign-identity.ts`, `components/shared/how-to-read.tsx` (its only caller was the campaign
detail page), the featured China/Russia cases and `CaseCard` on the landing page, the campaign types
in `lib/api.ts`, and the nav entries.

**Deliberately KEPT:** the entire backend. `app/campaigns/`, `app/routes/campaigns.py`, the
coordination detectors, the Campaign models, `featured_campaigns.json` and their tests all still run
and are still green. That is the foundation the future algorithm builds on, so do not "tidy it up"
because nothing in the UI imports it. `/rc/<token>` is still a live **API** route, which is why
`tests/test_featured_campaigns.py` passes unchanged.

`/narratives` is no longer a placeholder: it is the **coordination queue** for the cohort detector
(see below), labelled "Coordination" in both navs. It remains **admin-only and gated on the server**
(`if (!user?.is_admin) notFound()`, plus `force-dynamic`), because hiding the nav link alone would
leave the route answering to anyone who typed the URL. `adminOnly` on a nav item in `sidebar.tsx` /
`mobile-nav.tsx` is presentation only; the page is the access control.

One live reference remains on purpose: `campaign_reasoning` ("Campaign analysis") in
`analyst-panel.tsx` and `lib/api.ts`. That is a section of the **analyst's own response schema**, not
the campaigns feature. Removing it means a protocol change, a recompile, and a re-paste of the
OpenRouter preset.

### The cohort coordination detector: what it is and the two rules holding it up

`app/campaigns/detector/` answers the question a per-account score cannot: **are these accounts
running together?** It takes the accounts an investigation scored at **70 or above**, clusters them
on evidence those accounts produced themselves, and writes corroborated groups into the existing
`Campaign` tables. Deterministic: no model call, no network, no provider quota, pinned by
`tests/test_campaign_detector_uses_no_model.py` at the **import graph**, because a "no model" rule
that is only true by inspection stops being true the first time someone adds a convenient import.

It is **admin-only**, at `/narratives`, served by `/v1/admin/coordination`. The thresholds are
reasoned, not fitted against a labelled corpus, so a finding is an operator's lead. Nothing reaches
the customer app, the public report, or the exports.

**This is a new algorithm, not the six detectors in `app/detection/coordination/`.** Those still run
on every scan and are untouched. `app/campaigns/verdict_coordination.py` also still exists and is
still unwired; it was not adopted because its every measurement is *relative to the batch*, and the
70+ filter is precisely what removes the batch.

#### Rule 1: filtering to 70+ destroys the background, so the evidence must be ABSOLUTE

Measuring agreement relative to peers is what stops a detector reporting "the 80-scorers use
similar words, therefore a campaign". A cohort filtered to 70+ has no such background: every member
already looks bad, which is the *definition* of the cohort. So each signal is improbable in itself,
not relative to a peer group.

Where a null is genuinely needed it comes from the **full batch and the full thread**, which the
filter never touched, while only cohort members are ever named. Two signals need one:

- **`burst_lockstep`** tests co-arrival against the post's own arrival rate. Without that null it is
  the single worst false-positive generator available: on a viral post 200 comments land per minute
  and any four accounts share a minute. `tests/test_campaign_detector_signals.py` runs the same four
  accounts in the same window against a viral thread (refuses) and a quiet one (p < 1e-4). Those two
  tests *are* the thesis; if you break one, the detector is wrong.
- **`provisioning_window`** tests creation clustering against the batch's empirical distribution,
  because platform growth is not uniform and a theoretical prior fires on every signup wave.

**A cluster must never be counted in its own background.** It inflates the distribution it is being
tested against and hides itself. This bit twice during development, in two different coordinates:
`stats.local_rate` takes an `exclude` range (the same burst went from p=1.4e-4, missed, to p=2.3e-7,
caught) and `stats.window_mass` does the same for creation dates. `window_mass` also floors at the
uniform rate because an empirical count has **no resolution** below the spacing of the data: with
300 creation dates over ten years, a 200-second window is empty for every window that does not
contain the cluster, and zero mass reads as untestable rather than significant.

#### Rule 2: corroboration is AND, and it counts FAMILIES

The seven signals sit in five families of independent evidence:

```
text (verbatim_echo, bio_echo) · timing (burst_lockstep) · network (co_target)
infrastructure (client_signature) · identity (provisioning_window, handle_template)
```

Fusion takes the **strongest edge within a family** and combines **across** families. Two methods
reading the same material are one kind of evidence seen twice: `verbatim_echo` + `bio_echo` both say
"these accounts emitted the same string", and counting method names would let one copy-paste
observation clear a gate meant to need independent confirmation.

Fusion is now **arithmetic, not heuristic**: likelihood ratios multiply only when the evidence is
conditionally independent given the hypothesis, and the family map *is* that independence
assumption written down. See "The probability model" below.

Three more guards, each replacing a specific way this goes wrong:

- **Edges, not clusters.** `CampaignService.merge_clusters` unions any two clusters sharing one
  account, so per-detector clusters let one account fuse two unrelated groups into a fake
  mega-campaign. Findings come out member-disjoint and `record_clusters` is called **once per
  finding**.
- **Two independent links to join a group** (`MIN_LINKS_INTO_GROUP`). This replaced a density
  ratio, which was a proxy for the same thing. If one account posts a script that four unrelated
  people each copy, every spoke links to the hub at high probability while the spokes share
  nothing; admitting all five would report "these five are running together" on evidence that only
  ever said "each of these four echoed that one". **The rule triggers from the third member, not
  the fourth** — requiring it only from the fourth let a three-account star through, which is the
  smallest thing it exists to refuse.
- **Every edge carries an `artifact`** and `pair_evidence` drops any that does not. The
  deterministic form of "if you cannot quote it, you cannot claim it".

`test_the_same_input_always_gives_the_same_answer` pins determinism: these are published claims
about named accounts, and a verdict that changes between runs is not a verdict.

#### The probability model: `detector/probability.py`

The output is a **calibrated posterior**, not a score. `posterior_odds = prior_odds × Π LR_family`.

**The prior is stated**: P(two accounts in one 70+ cohort are coordinated) ≈ 0.033, derived from the
documented base rates (9-15% of active accounts automated; an operation of ~5 inside a ~15-account
cohort, present in ~35% of investigations). From there, clearing 0.95 needs **LR ≥ 551**, and that
number is the entire discipline.

**Two signals get their denominator for free.** `LR = P(E|coordinated) / P(E|independent)`, and
`burst_lockstep` and `provisioning_window` already compute a p-value that *is* the denominator. The
null models built for a different reason turn out to be exactly what Bayes wants underneath, so
those two ratios are data-derived per observation rather than estimated once.

**The old hardcoded gate is gone because the numbers do its job.** With honest ratios, no single
family at any strength can clear the bar, and any two independent families can. `SUPPORTING_CEILING`
and `EVIDENCE_EPS` were deleted, not ported. Every one of those refusals is pinned in
`tests/test_coordination_probability.py`; if a ratio drifts, whichever refusal it breaks says so.

**Both measured-null signals are capped per method, and the reason is not tidiness.** A p-value
answers "how surprising is this under MY null", and each of these nulls has a confound it cannot
see. `burst_lockstep` (cap 2.30) correctly refuses a viral post but cannot see an **external
referral spike**: a post linked from a Discord or a subreddit makes real strangers arrive together,
and that burst is precisely the deviation the null flags. `provisioning_window` (cap 2.00) rests on
an empirical CDF over a few hundred creation dates that already needs a uniform floor for lack of
resolution. The caps are where the unmodelled confound is priced in.

**Membership is gated per account.** An account joins only when *its own* posterior link to the
group is ≥ 0.95, and a group's headline number is its **weakest** member's, not its mean: a group is
only as defensible as the least defensible person named in it, and that person is the one harmed if
it is wrong. Every member carries its own admitting probability into the UI so a reviewer can
challenge one name without dismissing the finding.

**Nothing claims certainty.** Total log10 LR is capped at 4.0, so the reportable ceiling is ~0.997.
Five estimates multiplied do not make a fact.

#### Two passes, one core, one stored result

Pass 1 fires when the scan is saved, on the **deterministic engine probability**, so a coordination
read exists even when the analyst floors (a documented recurring failure). Pass 2 fires from
`generate_and_persist`'s `finally` and re-cuts on the **customer-visible OMI score**.

Both are literally the same function (`run.detect_for_investigation`, differing only in `prefer`),
and pass 2 **replaces** pass 1's `campaign_detection_v1` block rather than sitting beside it. That is
the whole anti-divergence design: there is one scoring core and one stored answer, so the two passes
cannot present competing verdicts about the same accounts. Scheduled on `background.submit`, **not**
`submit_slow` — the slow pool exists because an analyst run holds a worker for minutes, and this is
seconds of pure CPU.

`campaign_detections` is a denormalised index row so the admin queue can list and filter **without
loading `payload_json`**. Same trap the archive list already paid for, and worse here because these
are the heaviest payloads in the product. Uniqueness is an `Index(..., unique=True)` and not a
`UniqueConstraint`, because the boot-time upgrade pass backfills `table.indexes` and cannot see
`table.constraints`.

#### The planet-scale layer: `app/campaigns/tracking/`

Three things a per-investigation detector cannot do, and the reason the layer exists.

**It accumulates.** Every pair's evidence is folded into `CoordinationEdge` (extended with
`log_lr_sum` / `families_json` / `contexts_json` / `platforms_json`), including pairs that did
**not** clear the bar. That is the point: a pair at 0.86 today is below the threshold and still
worth remembering, because the same pair on an unrelated post next month is what takes it over.
Discarding sub-threshold evidence would mean the system could only ever learn from what it had
already decided. Measured: one sighting 0.857 (refused, zero campaign rows), two sightings 0.988.

Repeat sightings are **discounted by half** and capped at 5 contexts, because two observations of
one pair are not independent (both accounts follow the same topics). And only a **distinct post**
counts: `contexts_json` is a set, so re-scanning or a continuation batch cannot compound, which
would otherwise let anyone strengthen a finding by pressing rescan. `last_shared_parent` could not
serve here because it is overwritten, so one post scanned twice looked identical to two posts.

**It survives account rotation.** A serious operation burns its accounts between runs, so
`_match_or_create`'s member overlap finds nothing and forks a new campaign with a fresh random key
— the system reports a first sighting of something it has seen three times. `tracking/signature.py`
sketches the operation's **behaviour** (script shingles, handle skeletons, creation-month buckets,
client strings, link domains) and **never account ids**, banded into `operation_signature_bands` for
indexed lookup. Match order is now: member overlap, then signature collision verified at similarity
≥ 0.40, then create. Measured: same operation with zero shared accounts, similarity 1.000 and 32/32
bands colliding; a different operation, 0.031 and 0/32.

**The hash family matters.** `verdict_coordination._minhash` derives permutations by XOR with a
constant, which is not a universal family: the permutations are correlated, so the banding
arithmetic does not hold. At one-investigation scale nobody noticed; at deployment scale, where band
collisions decide what gets compared at all, it would produce a match rate nothing predicts. The
tracking layer uses independently salted BLAKE2b (as `detector/textsim._hash64` already does).

**Cross-platform is one rule.** A cross-platform edge may only be created by a **platform-neutral**
family: text, network, timing. `client_signature` reads an X-only field, and handle conventions
differ per platform so a shared skeleton across two would be evidence about the platforms rather
than the accounts. Enforced once in `run._drop_illegal_cross_platform`, not inside seven signals
that would each have to remember it.

Two more fixes that landed here:

- **`handle_template` fired on ordinary one-word handles.** Letter runs are capped at 9 in the
  skeleton, so `marchingfern`, `quietwaterbird` and `brightpennylane` all reduce to `L9` and were
  reported as sharing a template. A template needs more than one part; a bare single-word skeleton
  is now refused alongside the auto-append shape.
- **A large campaign swallowed every new cluster.** `jaccard >= 0.30 OR shared >= 3` is fine while
  campaigns are small and absurd once one is large: three shared accounts linked a 5-account cluster
  to a 500-account campaign at j = 0.006. Above `LARGE_CAMPAIGN_MEMBERS` the Jaccard floor is
  required.

#### What the calibration harness can and cannot tell you

`python -m app.evaluation.coordination_probability` reports Brier, a reliability curve, and
precision/recall per threshold over the committed scenarios. **Read the caveat it prints.** On the
9 clean scenarios the detector is silent 9/9, which is the number that decides shippability and is
genuinely meaningful. But those scenarios were built for the older per-scan detectors and carry no
comment timestamps, no posting clients and no engagement targets, so four of seven signals cannot
fire and **recall is not measurable from this corpus at all**. The harness says "no calls" rather
than "precision 1.000" for exactly that reason: a metric that passes because it never looked is the
same failure `/analyst/status` had before the preflight was written.

The ratios are reasoned, not fitted, and stamped with `LR_VERSION`. ~200 labelled accounts can
falsify a badly wrong ratio; they cannot fit seven. `AccountLabel` and the dismissals on
`campaign_detections` are the reservoirs a real fit will eventually come from.

#### Evidence that used to be thrown away

Four things were collected on every scan, used in-process, and dropped before persistence. All are
now carried, and none costs an extra fetch:

- **`CommenterScanResult.thread_comments`** — the account's comments *on the scanned post*, with
  real timestamps. `recent_activity` is the account's own timeline, which is a different thing:
  co-timing is only evidence when both accounts were commenting on the same thing.
- **`FullVideoScanResult.thread_arrivals`** — epoch seconds for every comment under the post from
  **every** author, scanned or not. Numbers only, no text, no author. This is `burst_lockstep`'s
  null, and it must stay complete: measured over scanned accounts alone the rate is under-stated,
  which over-states significance. `BatchBackground.arrivals_complete` is False for payloads written
  before this existed, and **`burst_lockstep` abstains entirely** rather than measuring a subset.
- **`source_client` / `reply_to_id` / `repost_of_id`** on each activity sample, and `source_client` +
  `reply_to_id` on X reply items. `_map_tweet` had already parsed all of them and
  `fetch_tweet_engagers` was building a four-key dict that discarded two.

**`_merge_payloads` was deleting the analyst assessment, and had been all along.** It started from
`merged = dict(new)`, so any top-level key present only in the stored payload was dropped, and a
fresh scan result never carries `analyst_assessment_v1`. So a continuation batch silently destroyed
the written analysis a customer had already paid for. Pre-existing, unrelated to this feature, found
because the detection block lives in the same place and would have died the same way. Pinned by
`test_a_continuation_batch_does_not_delete_the_analyst_assessment`.

#### `campaign_pack` method lists must stay SPLIT

`_silent_methods` reports every method a campaign did not fire, so `KNOWN_METHODS` is now
`ENGINE_METHODS + COHORT_METHODS` and the function picks the family the campaign actually ran under.
Merging them would make every existing engine campaign render seven extra "did not fire" lines for
detectors that did not exist when it was recorded, which is a false statement about the evidence:
never attempted is not the same as attempted and found nothing.

`aggregate.DISCRIMINATIVE_DETECTORS` itself is **not** modified. It feeds `elevate.py` on the live
per-scan path, so adding names would change per-member score elevation inside every running scan.
`campaign_pack.ALL_DISCRIMINATIVE` is the union, used for reporting only.

#### What it cannot see, stated on the page

It catches operations that reuse copy, arrive in lockstep, share a non-standard publishing tool,
converge on unpopular targets, or were provisioned together. It will **not** catch a well-run
operation using aged accounts with individually written posts on ordinary clients: five of the seven
signals go quiet. So an empty result means no mechanical tell was found, **not** that the accounts
are unrelated, and the `/narratives` page says so rather than leaving it in a docstring.

`tests/test_campaign_detector_precision.py` is the load-bearing suite and its controls come first:
professionals covering one beat (the shape that once scored unrelated journalists at 1.0), a fan
community, second-language writers, a viral thread, and accounts sharing only a handle shape. Every
one is built to score 70+ across the board, because that is the state the filter guarantees.

**The dismissals are the only ground truth this will ever accumulate.** Every constant is reasoned;
`POST /v1/admin/coordination/{slug}/dismiss` records a labelled negative so a future calibration has
something to fit against.

### Campaigns are GATED, not scoped, because they have no owner

`Campaign` has no `user_id` and that is deliberate: one operation seen by two customers on two
different posts is **one** campaign, and that cross-customer accumulation is the whole point. The
cost is that these routes cannot be "scoped to your own data" — there is no such thing here — so the
library is **admin-gated** instead, matching `/narratives` and `/disputes`.

This replaced a live cross-tenant exposure. `require_user` with no admin check meant any signed-in
customer could enumerate every campaign in the deployment **with each one's `share_token`** (a
capability URL), read `observations[].context_id` (the id of the post **another customer scanned**),
mint a permanent public `/rc/<token>` report for any campaign including one assembled from other
customers' scans, and revoke anyone else's. **The existing campaign tests could not catch any of it:
they run in local mode, where `require_user` returns `is_admin=True`.** Any test that needs to prove
an authorisation rule must set `OMI_REQUIRE_AUTH=true` and sign up a real user.

**`/v1/narratives/*` had the same hole and it is now closed.** A `Narrative` also has no owner: it
is assembled from content ingested across every customer's scans. The routes were `require_user`
only, so any signed-in customer could read narrative clusters, their top accounts and their sample
texts, all built from other customers' investigations, by calling the endpoints directly. The
`/narratives` *page* had always gated on `is_admin` server-side, which is exactly what made it look
fine. Gated by `narratives._require_admin` and pinned by `tests/test_coordination_admin_gate.py`,
which signs up a real non-admin and also proves an admin still gets through (a suite of 403s with no
positive case cannot tell a gate from a broken router).

- **`include_provenance` on `_campaign_detail` defaults to False.** A route added later that forgets
  to pass it leaks nothing; one that forgot to *strip* would. `context_id` is gone from the public
  `/rc/` report, the featured path, and the export pack **even for an admin** — the pack is a file
  that leaves the app to be forwarded, which is exactly when provenance must not ride along. Admins
  do still see it on the detail route, because the post an observation came from is the first thing
  an investigator needs.
- **The `feat_` examples stay open** to any signed-in user. Curated from public disclosure archives,
  owned by nobody, and the product's front door.
- **Share/unshare are the gates that mattered most.** Publishing a claim about named real people is
  the operator's decision, never a customer's on the operator's behalf.

Pinned by `tests/test_campaign_tenancy.py` (11 tests; 8 fail against the pre-fix route file, checked
by stashing it). The privacy policy now describes the cross-investigation record explicitly.

The detection algorithm that will feed this is designed and implemented in
`app/campaigns/verdict_coordination.py`, documented in `docs/campaign-detection.md`, and **not yet
wired to any route**. It clusters accounts from omi scores + analyst verdicts alone. Two things in
it that a future session will otherwise re-break: a score-band-stratified permutation test
degenerates when a cluster fills its own band (every draw is the cluster, p lands near 0.5, and a
correct detection is thrown away), so `p_value=None` means "could not test" and must never be read
as "not significant"; and a DBSCAN blob larger than 40% of the batch is the batch, not a cohort.

### The analyst is called the Omi Analyst, and the gateway is never named

Product rule (2026-08-18): **no rendered string in `apps/web` names the model gateway.** The product
has one analyst and it is the Omi Analyst; the gateway it happens to run on is our implementation
detail, and naming it tells a customer that the thing they pay for is somebody else's.

The vendor name was never in the copy. It arrives inside **values** the backend writes and the UI
prints verbatim, which is why the fix is a render-time function rather than a review rule:

- `investigation_trace.provider` is `openrouter-omi-analyst-v1`, or
  `openrouter->fallback:deterministic-analyst-v1` on a floored run.
- `endpoint_error` is `ProviderError: openrouter HTTP 404`, `openrouter unreachable`, and similar.

`lib/analyst-identity.ts` is the only place that matters. `analystProviderLabel()` returns Omi's own
vocabulary and keeps the one distinction an operator needs (`Omi Analyst (model)` against
`Omi Analyst (deterministic floor)`); `scrubVendor()` replaces the name inside a free-text
diagnostic while keeping the rest, because the rest is exactly what someone debugging needs. Both
are applied in `VerificationPanel` and `AiUnavailableDiagnostics`, which are `?verify=1` surfaces
and were the only leaks: the customer-facing copy was already clean.

Pinned by `lib/analyst-identity.test.ts`, which includes a **source-level guard** that walks every
`.ts`/`.tsx` file and fails on the name in a rendered string. Two deliberate exemptions:

- **`app/(marketing)/privacy/page.tsx`** names it as a **subprocessor**. That is a legal disclosure,
  not branding: a privacy policy has to say who processes user data, and removing it would be a
  data-protection problem rather than a win.
- `openrouter_preset` as a FIELD name on the API type. The rendered label is "Protocol preset" and
  the rendered value is the preset id, so nothing vendor-named reaches the page.

Not covered, and a separate question: `requested_model` / `served_model` still render the model slug
(`openai/gpt-5-mini@preset/...`) in the verify panel. That is a different vendor and it feeds
`served_model_verified`, the check that catches a silent model swap, so it was left alone.

### No em dashes, and no decorative badges

Two house rules, both enforced by the product owner's explicit decision (2026-07-28):

- **No em dashes (`—`) or en dashes (`–`) anywhere in `apps/web`, in the prompt sources, or in the
  compiled protocol.** Use a comma, colon, semicolon, parentheses, or two sentences. A hyphen inside
  a compound word or a numeric range (`0-100`, `25-50%`) is correct and stays. The rule reaches the
  analyst too: the constitution's PUNCTUATION bullet forbids them in generated prose, because the
  model's assessments render directly on the site and would otherwise reintroduce them on every scan.
  Never "fix" a dash by deleting the character: `link — we compile` becomes `linkwe compile`. Rewrite
  the punctuation.
  Two traps found doing this the first time: em dashes are also used as **"no value" placeholders** in
  tables (`?? '—'`), which must become `'-'` and not a comma; and **paired** dashes around an
  appositive must become paired commas, not a full stop that leaves a fragment.
- **`components/ui/badge.tsx` is deleted.** The 9 decorative status chips are now plain
  `font-mono text-2xs uppercase` spans that keep the semantic colour and drop the pill.
  **`TierBadge` is NOT a badge in this sense and stays** — it carries the LOW/MODERATE/ELEVATED/HIGH
  result, which is the product's primary output, not decoration.

Motion follows the `emil-design-eng` skill: transform/opacity only, custom easing
`cubic-bezier(0.23, 1, 0.32, 1)`, <300ms for UI, `scale(0.95)` never `scale(0)`, always
reduced-motion guarded.

Copy goes through `stop-slop`. The relevant skills are `stop-slop`, `ui-ux-pro-max`,
`emil-design-eng`, `human-crafted-design-auditor`.

---

## Cross-investigation narratives: one question asked across every customer's scans

Built 2026-08-25 from `docs/cross-investigation-narratives.md`. Read §1 of that document before
touching anything in `app/narrative/cross/`, because the whole system is built to measure ONE
difference and measuring it wrong is an expensive way to rediscover what a single user was curious
about.

**The signal is cross-customer independence, and it is the one thing no customer and no competitor
can reproduce.** Each customer sees their own handful of investigations; OmiSphere sees every
customer's in one database. One customer scanning twelve posts about a subject is one person's
curiosity. Three unrelated customers landing there in a week is evidence about the world.

```
extract -> assign topics -> roll up per day -> score one (topic) + score two (cohort)
```

Admin-only, at `/v1/admin/cross-narratives`, gated for the same reason `/campaigns` and
`/narratives` are: a finding is assembled from many customers' scans and belongs to none of them.
Pinned in `tests/test_coordination_admin_gate.py`, which signs up a REAL non-admin, because every
other test in this repo runs in local mode where `require_user` returns `is_admin=True`.

**OFF by default** (`OMI_ENABLE_CROSS_NARRATIVES`), and that is correctness rather than caution: see
the embedder note below.

### The two live defects it was blocked on, both now fixed

- **`ingest_batch` wrote the SCAN time**, so every temporal statistic over narrative membership was
  measuring our own scanner and every member of one scan was a perfect burst by construction.
  `posted_at` is a NEW column rather than a redefinition, because existing rows genuinely hold scan
  times. NULL means "we do not know" and every statistic SKIPS such a row.
- **Production fell back to `HashingEmbedder`**, whose own docstring says it will not catch
  paraphrases, so "same topic" meant "same words" and two accounts pushing one narrative in
  different phrasing never clustered. That is precisely the case the feature exists to catch.

### Switching embedders forks the topic space, silently

`cosine` returns 0.0 on a width mismatch rather than raising, and clustering compares new vectors
against stored centroids. So a batch embedded by a different embedder matches nothing, spawns a
duplicate of every topic it touches, and **reports success**. Three things prevent it:

- **`ApiEmbedder` raises `EmbeddingUnavailable` and never degrades.** Every caller SKIPS the batch.
  That is recoverable, because the text is still in the utterance store; a forked space is not.
- **`Embedder.space` names the space** (`api:<model>:<dims>`), not just the width. Two different
  1536-dimension models are different languages.
- **`CrossTopic.embedding_space` / `Narrative.embedding_space`** record which space a centroid was
  built in, and assignment only ever compares like with like, so a model change starts a new
  generation of topics instead of corrupting the old one. **Changing the model is therefore not
  free**: old topics stop accumulating. Pick one and leave it.

**The vendor NAME is required before the embedder will build at all** (`OMI_NARRATIVE_EMBEDDING_
PROVIDER`). That is the name the privacy policy has to disclose, because this sends other people's
public posts off our servers and those people are not our users. Enforcing the order in code makes
it a configuration error rather than a disclosure gap nobody notices.

### The utterance store

One append-only row per comment, extracted from `payload_json` which already holds all of it. A blob
cannot be queried and it is the heaviest column in the product; the archive list already paid for
reading it per row.

- **`user_id` is used ONLY to count DISTINCT customers.** It never reaches an admin view as "who
  scanned what": the value is in the independence, not the identity, and a test asserts the serialised
  queue response contains no user id at all.
- **Idempotency is a unique index on a content-derived `dedupe_key`, not an `if`.** The backfill is
  driven by a loop that dies on every deploy and by an operator who will run it twice. The key
  deliberately EXCLUDES the investigation, so the same comment reached through two customers' scans
  of one post is one comment rather than two.
- **`tier` is frozen at extraction.** The tier-mix test asks what the population looked like AT THE
  TIME; reading a later score would rewrite history on every rescan.
- **Retention drops the TEXT at 90 days and keeps the row**, so the rolling counts that drive
  detection survive while what we hold of other people's content stays bounded.

### Score one: is the topic anomalous?

Three components, **multiplied, each required**: volume against the topic's OWN trailing baseline,
tier mix against the corpus base rate, and cross-customer independence.

**The tier-mix test is the one that carries the argument, and it is why the score is a product.**
Customers scan what they suspect, so a news story that makes a subject topical spikes volume AND
pulls several customers to it with nothing manufactured. That confound is real and does not improve
with scale. A story everyone is discussing recruits a REPRESENTATIVE sample of accounts; a subject
being pushed recruits a BIASED one. Averaging would let a volume spike carry a topic whose accounts
look completely ordinary, which is every viral news story.
`test_a_viral_news_story_does_not_score_because_its_accounts_are_ordinary` is the load-bearing test.

Two arithmetic rules that are easy to get wrong:

- **The binomial baseline excludes the topic under test and is measured outside the window under
  test.** A cluster counted in its own background inflates the distribution it is compared against
  and hides itself. This codebase has now paid for that in three separate coordinates.
- **Distinct counts are computed over the WHOLE WINDOW, never summed from the daily rows.** Summing
  per-day distincts counts an account active on three days three times, and two customers who
  scanned on different days would report as one, understating the only component nothing else can
  compute.

**Untestable topics are returned carrying their refusals, not filtered out.** Silently dropping one
is indistinguishable from finding nothing, which is how the netdetect shuffle budget managed to be
broken invisibly.

### Score two: is the cohort a formation?

Every account on the topic in the window, across all investigations, through `app/netdetect`. An
operation spread thinly over eight posts scanned by three customers is invisible in each of those
scans and obvious in the union.

- **The posts the topic was found on are excluded from the evidence.** Every member engaged them by
  construction; without the exclusion the cohort shares a perfect feature and reports as one
  enormous operation. Worse here than in a single scan, because it would manufacture a link between
  every pair of posts.
- **An account seen in several investigations contributes its MOST COMPLETE block, not its newest.**
  Those blocks differ mainly in how much history each scan fetched, and the thinner copy yields
  fewer features, which reads as innocence the account has not earned.
- **Nothing here reads a suspicion score**, proved behaviourally: the same cohort scored all-low and
  all-high produces identical findings.

**THE TWO SCORES ARE NEVER MULTIPLIED.** Collapsing them hides the two most interesting cases: a
topic that is anomalous but whose accounts are unrelated (organic outrage), and a tight formation on
a topic that is not spiking at all, which is what a patient operation looks like.

### The pass, and the dismissals

`run.run_one_pass` walks all four stages, each bounded and each **resumable rather than
restartable**: the loop dies on every deploy, assignment EMBEDS so redoing work is spend, and
skipping it is a silent gap no score would report. A Postgres advisory lock (a different key from
the monitoring loop's) keeps N instances from running N passes, which here would be N times the
embedding bill.

`CrossFinding` is one row per `(topic, window_end)`, so a re-run updates rather than stacks. **A
dismissed row is updated with new numbers but keeps its dismissal**: an operator who has already
said "this is a news story" must not be asked again every fifteen minutes.

**The dismissals are the only ground truth this system will ever accumulate**, which is why the
reason is required and why a dismissed row is never deleted. Every threshold here is reasoned, not
fitted; no labelled corpus of worked topics exists and none can be bought.

### What it cannot claim

**"Anomalous relative to our own corpus", never "anomalous on the platform."** The corpus is what
customers chose to scan, which is not a sample of anything. `_SCOPE_NOTE` says so on the queue
response itself rather than leaving it in a docstring.

### Not yet done

The daily digest (decision 3) is not built: **SMTP is not configured on this deployment**, so it
would be an inert feature, and the queue is the surface that matters. When it is built it must say
SMTP is unconfigured rather than silently sending nothing, the same rule the waitlist blast follows.
There is no web page yet either; `/v1/admin/cross-narratives` is the whole surface.

---

## The agent surface: what a machine gets instead of the page

Added 2026-08-25 against an external readiness audit that scored the site 65/100 for agent
readability. Everything here is read only by machines, which is the property that makes it dangerous
to maintain: a mistake in any of it is invisible in the browser, in TypeScript, in the build, and in
every log.

**`apps/web/lib/agent-content.ts` is the single source, and that is the whole design.** Five surfaces
have to agree about which pages are public and what each one says: the sitemap, the negotiated
markdown, the addressable `.md` files, the llms.txt index and the 404 recovery list. Nothing at
runtime reconciles them. A page added to one and forgotten in the others fails silently, so they are
all derived from `AGENT_PAGES` and pinned by `lib/agent-content.test.ts`.

The markdown is **written by hand, not scraped from the JSX**. Deriving it from our own components
would produce navigation chrome, button labels and accessibility text that mean nothing out of
context. An agent asking for markdown wants the page's CLAIMS.

### `Vary: Accept` cannot be set on the HTML variant, so the fix is a second address

The audit's specific finding was that a negotiated URL served HTML with no `Accept` in its `Vary`
header, which lets a shared cache hand the stored HTML to an agent that asked for markdown.

**Half of that is unfixable from inside this repo.** Next 14's app router calls
`res.setHeader('vary', ...)` during render (`base-server.js: setVaryHeader`), a bare overwrite with
its own RSC values, and it runs AFTER both middleware headers and `next.config` `headers()` have
been applied (`router-server.js` writes `resHeaders` before invoking the render). So the markdown
response, which middleware returns directly and which therefore never reaches that code, carries
`Vary: Accept, Accept-Encoding` correctly, and the HTML variant carries Next's. The line setting it
is left in middleware because it is correct and becomes effective the day the framework stops
clobbering it.

**`markdownPath()` is the answer that does not depend on a header.** Every page also has its own
address (`/index.md`, `/pricing.md`, ...), served by `markdownDocument()` in middleware before
negotiation runs. One document, one URL, no variants, so a cache cannot confuse anything. It carries
`Vary: Accept-Encoding` and NOT `Accept`: naming a header it does not vary on would tell a cache to
store one copy per distinct Accept string. `<link rel="alternate" type="text/markdown">`, llms.txt
and the 404 body all point at it, so an agent never has to negotiate to get markdown.

`prefersMarkdown` (`lib/accept-markdown.ts`) is q-value aware and **treats a tie as HTML**. The
direction of the error is what matters: serving HTML to an agent costs one wasted parse, while
serving markdown to a browser downloads a text file instead of the site, for every human visitor.
`*/*` must never win, and browsers put it in every Accept header they send.

### The root layout builds metadata per request, and a page that sets `alternates` undoes it

`generateMetadata()` in `app/layout.tsx` reads `x-pathname` (set by middleware) to produce the
canonical link and the markdown alternate for the page being rendered. Two traps, both found live:

- **`canonical` was hardcoded to `/`.** Every page that did not set its own therefore told search
  engines it was a duplicate of the home page, which is the most effective way there is to keep a
  site out of an index, and it was doing it to the marketing pages a brand query depends on.
- **A page's own `alternates` REPLACES the layout's whole object.** `/developers` set
  `alternates: { canonical: '/developers' }` and silently lost its markdown link, on the one page
  whose entire job is machine discoverability. No page may set `alternates` any more;
  `lib/page-metadata.test.ts` walks every `page.tsx` and fails on it.
- **The title template appends the brand**, so a page naming it too rendered
  `Pricing. OMISPHERE . OMISPHERE`. Same test.

### `OMI_PUBLIC_BASE_URL` now fails the BUILD when absent

It was passed as the value INTO `required()` with a localhost default, so the check never saw an
empty string. A deploy missing the variable published a sitemap, a set of canonical links, an
llms.txt and a JSON-LD graph all pointing at `http://localhost:3000`. Nothing failed, nothing
logged, and the site simply would not be indexed. It is baked in at BUILD time, so the local build
command needs it:

```bash
CLERK_SECRET_KEY= NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY=pk_test_Y2xlcmsuZXhhbXBsZS5jb20k \
  OMI_PUBLIC_BASE_URL=https://omisphere.online npx next build
```

### Content has to be readable with scripting off

`Reveal`'s resting state is `opacity-0` and only an effect clears it, so with JavaScript disabled
the free scan form, the entire pre-login conversion path, was in the document and invisible. Every
text-extracting check passed on it, which is exactly why it survived. The hidden state now carries
`reveal-pending` and the root layout ships a `<noscript>` rule overriding it. Both halves are
useless alone, so `lib/no-script-content.test.ts` asserts they stay together.

### The API speaks a structured error, beside `detail` and never instead of it

`app/core/errors.py` adds `{"error": {code, message, hint, docs, status, fields?}}` while keeping
`detail` at the top level unchanged, because the web app reads it in a dozen places. The codes are
**derived from the status**, not invented per route: a code only some routes set is worse than none,
because a client cannot rely on it. `CodedHTTPException` is for the cases where the status is
genuinely ambiguous, 402 covering both "out of credits" and "wrong plan" being the motivating one.

**Both exception classes are registered.** Routes raise FastAPI's `HTTPException`; the ROUTER raises
Starlette's when nothing matched, and that unmatched-route 404 is the first thing an agent probing
the API hits. Registering only the FastAPI class leaves it answering a bare `{"detail": "Not
Found"}`. Pinned by `tests/test_agent_error_envelope.py`.

### `/openapi.json` and `/docs` exist on the web origin now

They were named on `/developers` and linked from llms.txt while 404ing: the discoverability work was
advertising documents nobody could fetch. `app/openapi.json/route.ts` proxies the spec from the API
service and rewrites `servers` to the browser-visible origin (FastAPI describes itself relative to
an internal hostname no client can reach); `/docs` redirects into the API's own reference rather
than rendering a build-time copy of it. `robots.ts` had to gain explicit `Allow` entries for
`/api/openapi.json` and `/api/docs`, since `/api/` is disallowed wholesale.

### The JSON-LD offers are derived from the plan catalog

`lib/structured-data.ts` is pure and quotes `PLAN_TIERS` rather than repeating the prices. The prices
are already declared in two languages with a test reconciling them; a third copy would be the one
nothing checks, and it is the copy search engines quote back to people.

---

## Operator blindness: the two things nobody could see

### Error tracking is one env var away, and the SDK is already installed

`app/core/observability.py` was written to be opt-in and inert, and `app/main.py` already called
`init_error_tracking()` from the lifespan. What was missing was the part that made any of it reachable:
**`sentry-sdk` was not a dependency**, so setting `SENTRY_DSN` in the Render dashboard would have
logged one warning and done nothing. It is now a **core** dependency, not an extra, for the inverse of
the httpx reasoning: the module costs nothing when unconfigured, whereas shipping without the package
means turning error tracking on needs an env var *plus* a build-command edit *plus* a redeploy, at the
exact moment someone is trying to see a production fire.

`SENTRY_DSN` is declared `sync: false` on the API service in `render.yaml`. Paste a DSN, redeploy, done.
Any Sentry-compatible ingest works, self-hosted included, so this commits to no vendor.

Guarantees pinned by `tests/test_error_tracking.py` (18 tests), each because monitoring that can break
the thing it monitors is a downgrade: no DSN is a total no-op; a blank/whitespace DSN counts as unset
(that is Render's shape for "not filled in yet"); a bad DSN, a missing package, or an SDK that raises
all degrade to a log line; `send_default_pii` is off and `max_request_body_size="never"`, because this
service handles other people's social media data and a scan payload attached to a crash report would
be a data-protection incident of our own making; and **tracing is off unless `SENTRY_TRACES_SAMPLE_RATE`
is set**, so enabling error tracking cannot silently enable a spend.

**The background pool is the reason this matters more than it looks.** `background._wrap` absorbs every
exception by design, so a failed analyst run or scan job has *no user-visible signature at all* — the
work simply never finishes. That is exactly how the `NameError` in the analyst's persist closure
survived long enough to mean no investigation over 25 accounts ever produced an assessment. `_wrap` and
`_submit_to` now call `capture_exception` alongside the existing `logger.exception`, and the test
asserts the **exception object** reaches the sink, not that a log line was written: the log line already
existed and is precisely what was not enough. `capture_exception` is imported at **module scope** in
`background.py` for the reason in "A bug class worth knowing" — this module runs other people's
closures, and a function-level import would not be visible inside one.

The request path needs no wiring: there are no global exception handlers, so Starlette re-raises and
sentry-sdk's FastAPI integration captures. The web app is **not** wired (that needs `@sentry/nextjs`,
`instrumentation.ts` and a source-map upload step); a Next 500 is still log-only.

### The dispute queue now has a UI

`POST /r/<token>/dispute` and the admin routes shipped without an interface, so the only way to read
the queue was curl. That is not a takedown process. The operational value of the whole feature is being
able to say "reviewed and acted within a day" instead of "there was no way to reach us", and a queue
nobody looks at cannot deliver that.

`/disputes` (`app/(app)/disputes/`) lists the queue, filters by status, and resolves with a note.
Three things about it:

- **Admin-gated on the SERVER** (`if (!user?.is_admin) notFound()`), plus `force-dynamic` so a cached
  render cannot serve one user's gate result to another. The page reads complainants' contact details
  and its resolve action can unpublish **any** report in the system, so the hidden nav link is
  presentation, exactly as with `/narratives`.
- **The takedown takes two clicks.** Revoking clears the share token, so `/r/<token>` 404s for every
  link already posted publicly and re-sharing mints a different one. That is the right outcome when we
  got someone wrong and the wrong one to reach by a stray click. "Uphold, leave published" is a separate
  button, because agreeing with a complainant and withdrawing a public claim are different decisions.
- Resolving removes the row from a filtered view it no longer belongs in, so "Open" reads as work
  remaining rather than a log.

Pinned by four source-level tests at the end of `tests/test_report_disputes.py` (the server gate, the
`adminOnly` flag in **both** navs, and the confirm step), in the same spirit as the signal gate's guard:
TypeScript will not tell anyone if the server check is dropped.

---

### A floored assessment is invisible by construction, and the copy lied about it

Reported 2026-08-05: *every* investigation showed "The AI analysis for this investigation isn't ready
yet. It runs automatically. Please check back in a moment or scan again shortly."

**That message is not a loading state.** It renders when the run has FINISHED and FAILED. The model
was unreachable or its output was rejected, the deterministic Floor was persisted as the assessment,
and `isModelBacked()` is false. The route already holds the loading screen through one automatic
regeneration (`claim_floor_autorefresh`, exactly once per slug) and only then serves the Floor as
`status: "ready"`. So "just keep it loading" was already the behaviour, and extending it forever
would poll every 2.5s against a run that can never succeed while deleting the only signal that the
analyst is down. Same lesson as the sign-in spinner: **a spinner with no terminal state is not a
loading state, it is a silent failure.**

Two fixes, and a third thing that still needs the operator.

**The alert.** `persist_assessment` now calls `_report_floor` when `entry_is_model_backed` is false:
an ERROR log carrying the trace's classified `fallback_reason`, plus `capture_exception` with a typed
`AnalystFellBackToFloor`. This is the load-bearing point and it is worth stating plainly: **a Floor
result is a *successful* code path.** Nothing raises, so `background._wrap`'s reporting never fires,
so the tracker never hears about it, so the only symptom in the entire system is a sentence on a page
a human has to happen to read. That is exactly how this ran on every scan unnoticed. The alert fires
BEFORE the write, so a persist failure cannot also swallow it, and it is wrapped so a broken tracker
can never fail a scan. Pinned by `tests/test_analyst_floor_alerting.py` (7 tests), including the
inverse: a model-backed assessment must report nothing, because an alert that fires on success is an
alert people turn off.

**The copy.** `AiUnavailable` promised a result that was never coming and offered no recovery except
re-running the whole scan, which costs a credit. It now says the written analysis could not be
produced, names the cause in customer-safe words, states that **every account score below is real and
unaffected** (only the analyst prose is missing, which the old wording hid), and carries a Retry
button on the existing `run(true)` / `?refresh=true` path. `lib/analyst-failure.ts` holds the pure
mapping from `fallback_reason` to a sentence, pinned by `lib/analyst-failure.test.ts`; it returns
`null` rather than guessing, because a confident wrong explanation about someone's own scan is worse
than admitting only that it failed.

**The four causes are already classified** by `_fallback_reason` (`reasoning/trace.py:451`) and any
investigation prints its own with `?verify=1`. `no_model_call` means the credential or provider is
wrong; `model_output_not_schema_valid_json` means the preset is truncated or the response was cut
off (worth checking `OMI_ANALYST_COMPLETION_CEILING_TOKENS`, currently 150000, against the served
model's real output ceiling, since a `max_tokens` above what the model allows is rejected outright);
`governor_reject` means the S1-S9 lint refused valid output. Admins can get the raw capture from
`POST /v1/investigations/<slug>/analyst/audit`.

### Why a floor happens: the field was always null, and three fixes behind it

Reported 2026-08-15, same symptom as above and a different bug: the notice was appearing and naming
no cause. The alert above was built and then fed by nothing.

**`fallback_reason` was ALWAYS `None` on the live path.** `analyst.py` set it from
`inference.fallback_from`, which `runtime.py` only ever populates on the `judge_then_floor` branch,
and the comprehensive path runs `adjudication="schema_only"`. So three separate surfaces degraded at
once, all silently: `_report_floor` logged `reason="unclassified"`, `capture_exception` carried that
same empty reason to Sentry, and `lib/analyst-failure.ts` matched nothing and fell through to its
generic sentence. One disconnected wire, three symptoms, and no test could see it because
`test_analyst_floor_alerting.py` **hand-builds its trace dicts** — it proves the alert fires given a
reason and says nothing about whether production ever supplies one.

Everything needed to classify was already being captured and simply never read: `response_status`,
`endpoint_error`, `finish_reason`, `canonical_validation_errors`.

`app/reasoning/floor_reason.py` is the fix and is pure. **Its vocabulary is the probe's on purpose**
(`bad_api_key` / `no_credit` / `preset_or_model_not_found` / `rate_limited` / `unreachable`), so
`/v1/investigations/analyst/preflight` and a floored scan describe one fault identically instead of
an operator having to learn two dialects. Order matters in two places: truncation is checked BEFORE
the schema errors, because a cut-off reply also fails validation and reporting the schema errors
sends someone hunting a prompt bug that is really a token budget; and a 5xx (`gateway_error`) is
split from a 4xx (`http_error`) because only one of them is worth trying again.

The load-bearing test is the **end-to-end** one in `tests/test_analyst_floor_classification.py`: it
drives the real `assess_payload` path with a failing transport and asserts the persisted trace names
its cause. A test that constructs the trace itself cannot catch this class of bug, which is exactly
how it shipped.

#### Retry once, and only where a retry can change the answer

Almost nothing retried: a failed batch was `parts[i] = None` forever, so one bad draw cost the
customer that batch permanently and the only recovery was them noticing and pressing Retry.
`_generate_batched._run` now retries **once**, and the gate is `floor_reason.is_retryable`. The
exclusions are the interesting half, and each is a decision about spending real money:

- **A dead credential, an exhausted balance, a missing preset and a never-made call are never
  retried.** The second call fails identically, so a retry is pure spend in front of a failure the
  operator needs to see.
- **A timeout is never retried**, even though it looks transient: the generation may already have
  billed on their side. This matches `openrouter._fetch`'s own policy and softening it here would
  quietly double the cost of a slow model.
- **`governor_reject` is never retried.** Re-inferring to get a different draw past our own quality
  gate is the wrong instinct.
- **A run-level circuit breaker** stops retrying after two unfixable floors, so a 12-batch scan
  against a broken config cannot double its generations before giving up.
- **Truncation retries with 1.5x the budget.** Retrying it unchanged would truncate again at the
  same cap, which is precisely why the in-transport retry declines it. The multiplier is passed only
  when it is an escalation, so the ordinary call stays byte-identical and every existing test double
  still works.

#### A floored wrapper must not take the per-account reads with it

`validate_comprehensive_model_output` is all-or-nothing, so a reply whose twenty per-account
paragraphs were perfect and whose synthesis wrapper was missing one field was discarded whole. The
serve gate emptied `commenter_assessments` on any non-model-backed result, and the same gate hid a
**mixed batched run**: one floored batch out of four makes the merged entry non-model-backed, so a
finished scan carrying 75 real per-account reads rendered as a total failure. That is the more
misleading of the two options, not the safer one, and it is the likeliest thing the user actually
saw.

`_salvaged_account_reads` keeps the rows; the wrapper still floors. Nothing pretends the run
succeeded: `model_backed` stays False, so the operator alert fires and the self-heal path still
works. The new `investigation_trace.account_reads_salvaged` answers the different question the
customer's page needs, and `AssessmentView` renders `AiUnavailable summaryOnly` plus the reads.

Three rules:

- **Salvaged rows are not taken on trust.** They go through the same `_join_commenter_assessments`,
  so the tier is derived from the score and `grounding` still withholds an invented quote or a
  contradicted figure.
- **A Governor rejection is never salvaged.** That is our own policy layer refusing the output, not
  a shape mismatch. It cannot fire on today's `schema_only` path; the guard is there so that changing
  the adjudication mode cannot quietly turn salvage into a bypass.
- **Rows resolving to no account are refused.** A read of nobody is not a read.

#### A broken config now announces itself at boot

None of the above helps against a revoked key or a renamed preset: the retry is correctly refused,
the salvage finds nothing, and the deployment floors every scan in silence. `boot_preflight.py` fires
the real probe once on `background.submit` and turns that into an ERROR log plus a typed
`AnalystPreflightFailed` in the tracker, with the operator remedy attached.

Five properties, because monitoring that can break the thing it monitors is a downgrade: it never
blocks boot, never fails boot, never raises, no-ops without `OPENROUTER_API_KEY`, and no-ops when the
analyst is switched off. Cost is one `max_tokens: 1` call per deploy. `_PROBE_REMEDIES` is imported
lazily from the route package, because a route importing a reasoning module is the normal direction
and doing it the other way at import time would couple boot to the whole router graph.

#### The reason list is declared twice, in two languages

`floor_reason.ALL_REASONS` (Python) against `FAILURE_SENTENCES` (`apps/web/lib/analyst-failure.ts`).
Add a reason on one side without a sentence on the other and it renders as the generic line,
silently, for exactly the fault nobody has seen before. Same drift class as the signal-name contract,
so `test_every_reason_has_a_customer_sentence_in_the_web_app` reads the TypeScript source and fails
on it. `null` is allowed only for `deterministic_floor`, which genuinely means "we cannot tell".

Two rules the customer wording follows, both learned from copy that was live: **never say "credit"
about anything but the customer's own credits** (this product sells credits, so "the analysis service
is out of credit" reads as "you are out of credit" and sends someone to the billing page over a fault
of ours), and **name whose fault it is**, so nobody re-runs a scan that will fail identically.

### The analyst's output budget is 50,000 tokens, and the FLOOR is what sets it

Product decision (2026-08-18). Batches are a fixed 25 accounts, so the linear formula asks for
`base + 450x25 = 23,250`, and a live run was observed spending **12,970 of 23,250**. Truncation here
is not a graceful degradation: the reply fails schema validation, the wrapper floors, and before the
salvage path existed it took every per-account read in the batch with it. The margin is the point.

**Ceiling and floor are BOTH 50,000, so the budget is flat.** `completion_budget` is
`min(ceiling, max(floor, base + per*n))`, and with the two equal the linear formula between them is
unreachable: every request asks for exactly 50k whatever its size. That is the point — batches are a
fixed 25 accounts, so a per-size budget was arithmetic nobody could act on, and a 17-account
remainder is not quietly given a third less room than the 25s beside it.

The ceiling it replaces was **150,000**, set temporarily on 2026-07-22 to observe true per-scan
output cost with no truncation. That measurement is in (12,970 for 25 accounts) and the number had
never been checked against a real model. Set in `completion.py`, `config.py` and `render.yaml`
(`OMI_ANALYST_COMPLETION_CEILING_TOKENS` + `_FLOOR_TOKENS`).

**One guard goes quiet, and it is worth knowing.** The truncation retry multiplies the budget by 1.5
to give a cut-off reply more room; with ceiling == floor that clamps straight back to 50k, so the
escalation is a no-op. At ~2,000 output tokens per account against a measured ~519, truncation is not
the binding risk. If it ever becomes one, raise the ceiling ABOVE the floor rather than raising both.
The DOWNWARD retry below is unaffected, because the multiplier is applied after the clamp rather than
through it.

**A cap is not a spend.** OpenRouter bills tokens generated, so a run that finishes early costs
exactly what it produced. What this does buy is a real risk, and it needed a guard.

#### `output_budget_too_large`, the one 4xx that is worth retrying

`max_tokens` above the served model's own ceiling is **rejected outright**. `http_error` is
deliberately NOT retryable (a 4xx means the request was wrong and the next one would be wrong the
same way), so that rejection would floor **every scan on the deployment, permanently**, until a human
noticed. And nothing in this codebase can pre-empt it: the model is named by an env var
(`OMI_OPENROUTER_MODEL`, today `openai/gpt-5-mini`) and resolved by the gateway, so the number cannot
be checked against the model from here.

So the rejection is recognised instead. `floor_reason.OUTPUT_BUDGET_TOO_LARGE` matches a narrow set
of hints (`max_tokens`, `max_completion_tokens`, `max_output_tokens`, `maximum context length`,
`exceeds the maximum`) on a 4xx, and is the **only reason retried DOWNWARD**:

| reason | multiplier | why |
|---|---|---|
| `truncated_output` | **1.5** | the reply did not fit; ask for more room |
| `output_budget_too_large` | **0.5** | the provider refused the ask; ask for less |
| everything else | 1.0 | the budget was not the problem |

`budget_multiplier_for()` owns that table so the rule lives beside the reasons it keys on, and
`_generate_batched._run` reads it rather than testing for truncation by name.

**Keep the hint list narrow.** It carves a retryable case out of `http_error`, whose entire
justification is that an ordinary bad request would be refused identically; widening the hints makes
ordinary bad requests billable twice. Status is still checked before the error string, so a 401 whose
body happens to mention tokens is still a dead credential. Pinned by
`tests/test_output_budget_headroom.py`.

**Four tests moved deliberately, and the reason is the same in each.** They described a budget that
GREW with the investigation, from when a single inference carried a whole scan and the ceiling sat far
above anything real. Neither holds now: work is split into fixed 25-account batches and the budget is
flat, so assertions about growth across sizes that all clamp to one number were asserting a behaviour
the product no longer has. `test_commenter_capacity_matches_ceiling` in particular asserted
`cap > 150` and is now tied to `batch_plan.BATCH_SIZE`, because capacity is only ever asked about ONE
REQUEST and a request is one batch.

### The liveness window must not depend on an env var being right

Same report, and this is the half that explains a reset seen MID-run rather than after one.

`batch_heartbeat_stale_sec()` is `max(BATCH_HEARTBEAT_STALE_SEC, analyst_timeout + 300)`, and it
decides whether another worker may conclude a run has crashed and start a duplicate.
`Settings.analyst_timeout_seconds` **defaults to 500**, so a service where
`OMI_ANALYST_TIMEOUT_SECONDS` is not actually applied computed `max(420, 800) = 800s`. A batch has
been measured on this deployment at **857s**. A perfectly healthy batch could therefore outlive the
window by a minute, mid-run, and the duplicate republished "1 of 4" over what the customer was
reading and billed a second full run to do it.

`render.yaml` commits `1800`, but a Render dashboard value can disagree with what is committed (see
the billing and Clerk notes for the same class), and **a duplicate billable run is not a failure mode
worth leaving to configuration**. The floor is now **1800**, and the asymmetry is the whole argument:

- declaring a live run dead too EARLY costs a second full generation and a visible reset;
- declaring a crashed run dead too LATE costs a delayed self-heal on a run that produced nothing,
  with the Retry button right there.

Pinned by `test_the_floor_alone_outlives_the_slowest_batch_this_deployment_has_measured`, which
asserts against the measured 857s with the env var **absent**.

Worth knowing: the route's live-run guard is `(... inflight or lease_is_live) and not refresh`, so
`refresh=True` bypasses it — but `generate_and_persist` claims the durable lease itself and returns
early when someone else holds it, regardless of `refresh`. That second line of defence is what keeps
the bypass from being a bug today; do not remove it on the grounds that the route already checks.

### An interrupted run RESUMES, it does not start over

Reported 2026-08-18: a scan finished **2 of 4 batches, stopped, and the elapsed clock kept running**.

`_generate_batched` held every landed batch in a local `parts` list and nothing else. The merged view
was persisted, but the per-batch pieces the merge is built FROM were not, so a run that died
mid-flight (a redeploy — `background.shutdown` cancels in-flight work after a 5s grace — a container
restart, an OOM) left the investigation with results it could not continue from. The route's
interrupted-run branch then resubmitted the whole generation, `parts` started as `[None] * total`
again, and batches 1 and 2 were re-sent to OpenRouter to produce answers already in the database.
The customer paid twice and waited through work that was finished.

`BATCH_PARTS_KEY` (`analyst_batch_parts_v1` in `payload_json`) checkpoints each batch as it lands.
A new run seeds `parts` from it and skips those model calls, so it picks up at the first batch with
no result. Four rules:

- **`_chunk_signature` gates the reuse**, and it is the load-bearing part. It fingerprints which
  accounts are in which batch, in order, so a different selection, a different batch size or a
  re-ordered list all refuse to resume. A batch-3 result stapled onto a run whose batch 3 holds
  different accounts would publish real model prose against the wrong handles, which is the single
  worst thing this product can do.
- **A floored batch is never resumed as done.** An empty part is re-run, because treating it as
  finished would make an interruption permanently lose whichever batch it happened to interrupt.
- **Cleared when the run ends.** It duplicates every landed batch's per-account prose and
  `payload_json` is already the heaviest column in the product, so the cost is only ever paid by a
  run actually in flight.
- **It must never reach a public response.** It holds the RAW per-batch assessments, i.e. exactly
  what the viewer gate filters, one batch at a time. `_public_payload` now strips both internal keys,
  resolved BY NAME from the analyst module so a rename cannot silently stop the stripping.

Pinned by `tests/test_analyst_batch_resume.py`.

**Recovery still needs the page open.** `maybe_autogenerate` fires at scan time and the
interrupted-run branch fires on a POST from the investigation page; there is **no sweeper** for
analyst runs (unlike `reap_stale_scan_jobs` for scan jobs). So a run killed by a restart while
nobody has the tab open stays stopped until someone opens it. Closing that needs a scheduler, which
is the same missing piece as OMI-13.

**A live-looking clock is not evidence that anything is happening.** The panel keeps polling and the
elapsed timer keeps ticking against a dead run, which is what the report above actually describes.
The clock cannot tell a slow batch from a dead run; time since the last LANDING can, so
`BatchProgressStrip` now says so after `STALL_NOTICE_SEC` (15 min, above the measured 857s worst
batch) and offers a restart. It also states that nothing is lost by waiting, which is true now that
a restarted run continues from where the last one stopped.

### A salvaged batch was buying itself a second full run

Reported 2026-08-18 from a live 100-account scan, with screenshots. The customer read the
per-account verdicts, then watched the panel reset to **"1 of 4"** and analyse the whole
investigation again. The chain, and every link of it was working as designed:

1. batch 1's synthesis wrapper fails validation;
2. `_salvaged_account_reads` keeps its 25 per-account rows, which is the substance they paid for;
3. `_merge_batch_parts` marks the MERGED entry `model_backed=False` on the strength of that one part;
4. `routes/reasoning.py`'s floor self-heal keys on exactly that flag;
5. it sets `refresh=True`, **which also bypasses the live-run guard** (`... and not refresh`);
6. a second full run of every batch is submitted.

**Nothing outside the OpenRouter bill would ever have shown this.** The customer's only symptom was
the UI apparently restarting, and the analyst's own alerting stays quiet because a Floor is a
*successful* code path.

`entry_warrants_auto_regeneration()` is the fix and the distinction it draws is the point:

| | asks | used by |
|---|---|---|
| `entry_is_model_backed` | is the SYNTHESIS WRAPPER the model's? | the serve gate |
| `entry_warrants_auto_regeneration` | would a full billable re-run buy anything? | the self-heal |

They come apart on the salvage path and **must stay apart**. Making `entry_is_model_backed` true for
a salvaged entry would publish Floor prose as the model's; making the self-heal fire on it spends the
customer's money to improve a paragraph they did not ask us to improve. A regeneration is warranted
only when there are no per-account reads at all — nothing of the model's to lose. `AiUnavailable
summaryOnly` already tells the reader the summary is missing, and the Retry button is still there:
the choice stays theirs. Pinned by `tests/test_analyst_no_unrequested_regeneration.py`.

### The coverage box was denying the reasoning printed beneath it

Same report. Three lines of one box, sitting directly above twenty-five model-written paragraphs:

```
PARTIAL AI COVERAGE · 25 OF 25 COMMENTERS ASSESSED
AI reasoning was not produced (deterministic Floor); completeness not applicable.
~25 commenters remaining.
25/25 analyzed · 12,970/23,250 out tokens · stop: stop
```

Every clause came from `verify_completion` and no two of them agreed. The cause is that **salvage was
being reported as a Floor**: `model_backed` is False on that path, so the Floor branch fired even
though every account genuinely had the model's own read. `verify_completion` now takes
`salvaged_reads` and reports `summary_not_certified` instead, which names the half that is actually
missing. `complete` stays False — the entry as a whole is not certified and the operator surfaces key
on that — so only the SENTENCE changed.

**`_merge_batch_parts` was also inheriting batch one's `reason` and `estimated_remaining`.** `base` is
the first completed batch's payload, so a four-batch run whose first batch was clean and whose third
floored rendered *"Complete, every commenter received AI reasoning"* inside a box whose own heading
said coverage was partial. The counts were merged and the sentence explaining them was not. Both are
now computed for the merge. Pinned by `tests/test_completion_under_salvage.py`.

### One fact, six vocabularies

The same live page stated its progress six times, in six different wordings, and two of them
disagreed:

| where | what it said |
|---|---|
| panel header | `100 accounts, every one this scan scored` |
| progress strip | `SCORING IN BATCHES · 1 OF 4` · `25 ACCOUNTS · 5M 08S` · a track · `Waiting on batch 2 of 4` · a paragraph |
| above the list | `25 accounts scored so far, listed below…` |
| coverage box | `PARTIAL AI COVERAGE · 25 OF 25` (see above) |
| list heading | `PER-ACCOUNT ASSESSMENTS · 25` |
| below the list | `3 BATCHES TO GO` · `25 analyzed` · the SAME track again · another paragraph |

**The strip is the one authoritative progress statement.** Everything else was cut back to what only
it can say:

- the strip keeps its line, its track and its "waiting on batch N", and lost its explanatory
  paragraph;
- the sentence above the list is gone entirely — the strip renders directly above it;
- the coverage box **does not render while the run is working** (`running` prop). Mid-run, "partial
  coverage" is not a finding, it is "not finished yet";
- the trailing notice is one line, and says the only thing knowable at that position: the list has
  ended and is not the whole answer. It no longer repeats the track;
- the header count now says `Export covers all N scanned accounts`, because it describes the EXPORT,
  not the run, and sat a few pixels from a live progress count with no way to tell them apart.

### The completion box was written for us, and a customer reads it

Reported 2026-08-19 looking at a live scan: *"it shouldn't say the token budget, this is a consumer
app not just for me."* The line was `12,592/50,000 out tokens · stop: stop`, sitting under the
coverage heading on the page a customer reads about their own investigation.

**Tokens are the worst of it, because they invite a question that has no good answer.** This product
sells credits at one per 20 accounts. Nobody is charged for tokens, and printing a token budget
beside their results is the only thing on the page that suggests otherwise. `CompletionStats` now
shows coverage always (an incomplete investigation must never be hidden from the person who paid for
it) and puts the token figures and `stop:` behind `verificationEnabled()`, which is exactly the
operator surface they belong on: to somebody debugging a truncation that line is the whole diagnosis.

**The sentences beside it were the same defect.** Every `reason` string in `verify_completion` is
rendered into that box, and they were written in our vocabulary: "deterministic Floor", "output-token
ceiling", "a single inference", "schema / Governor / JSON completeness", "citable", "the upstream
evidence budget". Each names our infrastructure and answers no question the reader has. All are
rewritten in plain English. **`incomplete_kind` is untouched** and is the machine-readable half that
code and operators key on.

Two tests in `tests/test_completion_under_salvage.py` hold it: one walks every branch and fails on
operator vocabulary, and one asserts each branch still says something (a guard that only forbids
words passes happily on an empty string). Two existing tests keyed on the old jargon and now assert
the branch's STRUCTURE instead, which is the behaviour; the wording is copy and may change again.

### 103 of 100: an account written up twice is two verdicts about one person

Reported 2026-08-19 from a live 100-account scan. The page read **PER-ACCOUNT ASSESSMENTS · 103**
beside **PARTIAL AI COVERAGE · 103 OF 100 COMMENTERS ASSESSED**.

`assessed_commenters` counts rows that RESOLVED to a real account, so 103 of 100 never meant three
strangers had been invented. It meant three of the hundred were each written up **twice**, and both
paragraphs rendered. That is the specific harm this product exists not to cause: these are scored
claims about named real people, they get posted publicly, and two independently reached verdicts
about one person are free to disagree about the score, the tier and the evidence. A reader cannot
tell which one we stand behind, and neither can we.

`_dedupe_account_reads` keeps the FIRST row per account at the join and drops the rest. First is not
arbitrary: the output contract asks for the accounts in legend order, so the first mention is the
model's intended sweep and the later one is the slip.

**The key is the account, never the alias, and getting that wrong deletes most of a run.**
`build_alias_legend` numbers `A1..An` within ONE package and every batch builds its own, so `A1`
means a different person in each of four batches. Deduplicating on the alias would silently discard
three quarters of a 100-account scan. The join keys on the resolved `author_ref`; a row that
resolved to nobody has no identity, so it falls back to its alias and is only ever compared against
rows in its own batch. Two unresolved rows are never collapsed together: "we could not tell who this
is" is not evidence that two of them are the same account.

`_merge_batch_parts` dedupes again **across** batches, and there the only valid key is `external_id`
(the identity that survives the join). A cross-batch duplicate means the selection carried the same
account twice and chunking dealt it to two requests.

**`completion.assessed_commenters` is now counted from the MERGED rows**, not summed from each
batch's own figure. Each batch computes its count before the merge exists, so a row the merge drops
was still being counted by the batch that produced it, and the box claimed coverage for a paragraph
that is not on the page. Pinned by `tests/test_duplicate_account_reads.py` (8 tests), including the
regression an alias-keyed fix would introduce.

### The strip could not say which batch was on the wire, or that it was on its second try

Reported 2026-08-19: *"it's been running the fourth batch for about ten minutes, and it took the
other ones fairly quickly."* The run was behaving correctly. The page simply had no way to say what
it was doing, for two separate reasons that compound.

**Every incomplete batch was recorded as `pending`.** `batchStates` prefers the server's
`batching.batches` record over its own reconstruction whenever the record exists, and only the
reconstruction ever produced `running`. So the day the record shipped, the strip's *"Waiting on
batch N of M"* line became **unreachable on every modern entry** — dead code hiding behind a truthy
guard, with nothing failing anywhere to say so. `_merge_batch_parts` now takes the set of requests
actually open (`inflight`) and marks those `running`. It is passed rather than inferred because "the
first index without a result" is wrong twice: a batch that floored to `None` is finished and failed,
and a concurrent run holds several open at once.

**Progress was only ever written when a batch LANDED**, so the whole duration of a batch — which is
all of the time anyone spends waiting — was described by a record written before it started.
`_run` now persists once when the request opens as well. That costs one extra write per batch and
buys two things: the strip can name the batch on the wire for the entire time it is on the wire, and
the lease heartbeat is re-stamped mid-run rather than only between batches (the gap between two
heartbeats used to be one entire model call, which is the whole reason the stale window had to be
floored at 1800s).

**A retried batch looked identical to a slow one.** One batch can honestly occupy a very long time:
a per-request timeout of 1800s, up to two in-transport retries, then `_run`'s own whole re-attempt.
Nothing recorded that a second call had been made, so ten minutes on batch 4 was indistinguishable
from ten minutes on batch 4. Each batch record now carries `attempt`, and `_run` publishes the
increment **before** the second call rather than after it — announcing a retry once it is over is
announcing it too late to be of use to somebody watching. The strip adds `· attempt 2` and one
sentence saying it is an extra request rather than a restart, because a number going up next to a
progress bar otherwise reads as the scan starting over, which is the thing this page has already
been wrong about twice.

Three rules the tests pin:

- **The count is calls actually made.** A batch refused a retry (a dead credential, an exhausted
  balance) reports `attempt: 1`, and a resumed batch that cost this run no call at all reports 1 too.
  Reporting 2 would tell an operator money was spent that was not.
- **A missing `attempt` is read as 1, never as unknown.** Entries written before the field existed
  are the ordinary case, not a mystery.
- **A retry of the FIRST batch is invisible, and that is honest.** Nothing can be published before
  any batch lands, because there is no merge to write; the page has no batching record to render at
  that point either.

Pinned by the attempt-record section of `tests/test_analyst_batch_retry.py`, and by
`test_the_batch_on_the_wire_is_named_while_it_is_on_the_wire` in `tests/test_analyst_batching.py`.

**Two writes per batch now, not one, and two tests in that file pin the arithmetic.**
`test_batches_run_one_at_a_time_and_persist_as_they_land` and
`test_a_fully_successful_run_is_not_persisted_twice` both encoded one write per batch. Their intent
is unchanged and still asserted: a batch's results are written before the next batch is sent, and
nothing is written after the last landing (exactly one write is marked `complete`, and it is the
last one). Note `done` counts batches attempted AND FINISHED, so the open-of-request write repeats
the previous number rather than claiming the in-flight batch; what that write adds is the `running`
marker.

### One failed batch used to freeze the whole run

Live symptom on a 100-account scan: batch 1 landed, batch 2 floored, and the UI sat on
`1 OF 4 DONE` while batches 3 and 4 were still generating. It read as a hung scan.

`_landed` persisted progress only when the longest *completed prefix* grew. A failed batch leaves
`parts[i] = None` forever, so the prefix could never advance past it: the counter froze, **and**
batches 3 and 4 kept their finished accounts unpersisted until the entire run ended minutes later.
Work that was already done was being withheld.

The prefix was never needed for ordering. `_merge_batch_parts` walks `parts` by index and merges every
completed one, so accounts always come out in batch order however the batches finish; a gap left by a
failed or slow batch simply fills in when it lands. Progress is now persisted after **every** batch.

**`batching.done` counts batches ATTEMPTED, not batches that succeeded.** It drives the progress
readout and the client's poll-budget reset (`analyst-panel.tsx` resets `polls` when `done` grows), and
counting successes meant a run containing any failure could never show itself finishing and a failed
batch looked like no progress at all, which is what spent the poll budget. How many batches actually
produced accounts is visible in the accounts themselves. Two tests pinned the old meaning and were
updated deliberately.

A test caught a regression in the first version of this fix: the final merge still re-persisted with
the *success* count, so the readout ran 1, 2, 3, 4 and then dropped back to 3, which reads as the scan
losing work it had already shown. Pinned by
`test_a_failed_middle_batch_does_not_freeze_progress_or_withhold_later_batches`.

### Two runs used to fight over one investigation, and progress ran backwards

Reported 2026-08-05: the panel reached **"3 of 4"** and then dropped to **"1 of 4" with 0 accounts
scored**. Two batched runs were writing to the same row.

**`_autogen_inflight` is a per-process set.** `is_generation_inflight()` therefore answers only for
the worker that happens to serve the request. With more than one worker, or after a restart, a
healthy run in flight is *invisible*, and a partial entry (`batching.complete == False`) looks
exactly like the interrupted run the route is supposed to heal. So the second worker cleared `entry`,
submitted a duplicate generation, and that duplicate's first `_persist_progress(1)` republished 25
accounts over the 75 the customer was reading.

Two independent fixes, because either alone leaves a hole:

- **A durable heartbeat.** `batching` now carries `run_id` and `heartbeat`, written on every progress
  persist, and `batched_run_looks_alive()` reads them. That is cross-process evidence that somebody
  is still working, which the in-flight set cannot provide. Used in `generate_and_persist` (serve the
  partial instead of regenerating) and in the route's partial branch. The window is **derived from
  `analyst_timeout_seconds`** (`batch_heartbeat_stale_sec()`, timeout + 300s, floored at 420s), and
  that derivation is load-bearing: **the heartbeat is written when a batch LANDS, so one whole model
  call sits between two writes.** A fixed 420 was a bet that no batch would ever take seven minutes,
  and it lost. A measured 25-account batch took **857s**, so for 437 of those seconds a perfectly
  healthy run looked dead, another worker concluded it had crashed, and the duplicate republished
  "1 of 4" over the "3 of 4" the customer was reading, billing a second run to do it. Raising
  `OMI_ANALYST_TIMEOUT_SECONDS` now moves the window automatically instead of silently re-opening
  that. An **absent** heartbeat counts as not-alive, so entries written before the field existed
  still self-heal.
- **The lease is re-stamped as the run works.** Its heartbeat used to be written ONCE, at claim
  time, so liveness was measured from when a run STARTED rather than from when it last did
  anything: a four-batch scan at ~857s a batch runs close to an hour and outlived any fixed window,
  so the lease expired mid-flight and another worker was free to claim it. Widening the window only
  postpones that. `touch_generation_lease` is called on every progress persist, and it refuses to
  re-stamp a lease it does not own (which would hide a genuinely dead run behind a heartbeat from a
  process that is not doing the work).
- **The floor self-heal claim is DURABLE**, stored as `FLOOR_HEAL_KEY` on the investigation. It was
  a process-local set, so N web workers each granted their own automatic regeneration of the same
  floored scan and a restart granted another. An automatic regeneration is a full billable run
  nobody asked for, and the only place that would ever have shown up is the OpenRouter bill. The
  in-process set stays in front of it to keep a 2.5s poll loop off the database.
- **Progress never goes backwards.** `_entry_is_ahead()` makes `_persist_progress` defer to a stored
  entry that belongs to a *different*, *still-live* run with *more* accounts. Deliberately narrow:
  our own `run_id`, a stale entry, a finished entry and a behind entry all fall through to
  the normal write, so a single run is completely unaffected and a crashed run stays replaceable. The
  guard **defers, it does not disable** the run: once the second run draws level it publishes again.

The `cached_assessment(inv)` read inside `_persist_progress` is wrapped in `try/except` on purpose.
It is advisory, and a guard that cannot read the current entry must fall through to the write:
losing the guard costs a cosmetic regression, losing the write costs results a customer paid for.

**Two holes remained after the first attempt, and the user hit them the same day:**

- **The FINAL write was exempt from the guard** (`if not run_finished and ...`), which made this
  permanent rather than cosmetic. A duplicate run finishing with one batch published 25 accounts over
  the leader's 75 **and set `complete: true`**, so the entry stopped being regenerable and the
  customer was left with a quarter of what they paid for, forever. The guard now covers both writes;
  a deferring run simply ends, and the leader marks the row complete itself.
- **`refresh=True` never read the entry at all** (`cached = None if refresh else ...`), so every
  forced regeneration started a duplicate: both the route's one-shot floor auto-heal and the UI's
  Retry button pass it. The liveness check now runs BEFORE the refresh branch. A refresh exists to
  heal a dead or floored result, not to race a live one.

`analyst-panel.tsx` also keeps a `maxScoredRef` and ignores a poll carrying fewer accounts than the
last one. That is defence in depth, not the fix: the cost is asymmetric, since showing fewer accounts
reads as the product losing paid-for work while ignoring one stale poll costs nothing (the next poll
corrects it 2.5s later). Both refs reset at the top of `run()`, so Retry and a slug change start clean.

Pinned by eleven tests at the end of `tests/test_analyst_batching.py`.

#### Missing coverage is not the same thing as floored, and conflating them restarted finished scans

Reported 2026-08-06: the results appeared, then the panel started batching again from the top. Not a
duplicate run this time, a **self-inflicted full regeneration**.

`_merge_batch_parts` used to set `all_model_backed = False` whenever a finished run had landed fewer
batches than it attempted. That is precisely the signal `routes/reasoning.py`'s floor self-heal keys
on, so a run that landed 3 of 4 batches was read as the deterministic Floor the instant it finished:
`claim_floor_autorefresh` fired, `refresh=True` was submitted, and the whole scan ran again from
batch 1. It billed a second full run, and `_floor_autorefreshed` is a per-process set, so N workers
give N regenerations and a restart resets the one-shot.

**`model_backed` answers "is the prose in this entry the model's?"** For three real batches that is
yes. Coverage is a different fact and now has its own field:

- **`batching.landed`** is how many batches actually produced accounts. `done` cannot serve: it
  counts batches ATTEMPTED so the readout moves when one fails rather than freezing, which makes
  `done == total` on every finished run. `IncompleteCoverageNotice` was gated on `done < total` and
  had therefore been silently unreachable since `done` changed meaning; it now reads `landed`.
- **A wholly floored run still self-heals**, because a floored batch returns an assessment carrying
  `model_backed: False` and the per-part check catches it. Pinned by
  `test_a_run_where_every_batch_floored_is_still_not_model_backed`.

`landed` is optional in `lib/api.ts`: entries written before it existed have no value and the UI
falls back rather than claiming coverage it cannot know. Note that the exact-equality
assertions on `merged["batching"]` had to go through `_batching_core()`, since a heartbeat is a
wall-clock timestamp and asserting on the whole dict is asserting on the current time.

### The preset name is a two-sided contract and nothing at runtime reconciles it

The OpenRouter preset was renamed `omi-master-v1` -> `omi-master-v2` in the dashboard.
`OMI_OPENROUTER_PRESET` in `render.yaml` still said `omi-master-v1`, so every request asked for
`@preset/omi-master-v1`, OpenRouter answered 404, and **every scan served the deterministic Floor**
with no written analysis. Same shape as the Clerk instance pairing: two systems, two copies of one
name, no reconciliation, and a failure that reads as "the AI is broken" rather than "a string is
stale".

`GET /v1/investigations/analyst/preflight` reports this as `preset_or_model_not_found` and names the
model reference it tried, which is the whole diagnosis in one line.

A second, separate problem was visible in the same dashboard view: the preset had **no model
configured** ("can be used with any model"), while `render.yaml` deliberately left
`OMI_OPENROUTER_MODEL` unset *because the preset was supposed to choose the model*. A preset with no
model and no override does not resolve to anything. `OMI_OPENROUTER_MODEL` is now pinned to
`openai/gpt-5-mini`, which layers onto the preset as `openai/gpt-5-mini@preset/omi-master-v2`. If a
model is ever pinned ON the preset, unset the env var again so the dashboard stays the single source.

**Renaming a preset is a deploy, not a dashboard edit.** The name lives in `render.yaml` as a
committed `value:`, so a blueprint sync re-applies it and a dashboard-only fix is temporary.

### The analyst floored on EVERY scan because a validator lived outside the deployed package

This is the one that actually broke the product, and it is a packaging bug wearing a validation bug's
clothes.

`app/governor/comprehensive.py` did `from omi_analyst.schema_validate import validate_analyst_response`.
That package lives in **`ml/analyst/`**, and `apps/api/pyproject.toml` packages only `app*`. So:

1. the import raised `ModuleNotFoundError`;
2. `validate_comprehensive_model_output` appended `"canonical validator unavailable: ..."`;
3. a non-empty error list **is** a validation failure, so `runtime.py::_canonical_candidate` returned
   `None` for **every** model response, whatever the model said;
4. the deterministic Floor was persisted, on every investigation;
5. nothing raised, so `background._wrap` reported nothing and the tracker never heard about it.

**How it ever worked.** `analyst.py::_impl()` appends `ml/analyst` to `sys.path` as a side effect
before importing the legacy HF implementation. When that ran first, the later validator import
succeeded. So canonical validation of every investigation was riding on an unrelated legacy function
having been called first, and on `ml/` being present on the deployed filesystem. Neither is guaranteed.

**The fix is ownership, not leniency.** The validator is vendored to
`app/governor/canonical_validate.py`. Failing closed when it is unreachable is correct and unchanged;
what was wrong was reaching across a packaging boundary to find it. The `ml/` copy stays for the
offline pipeline (it must not import from the API), and a test asserts the two agree so they cannot
drift.

The vendored copy drops ml/'s repo-relative `SCHEMA_PATH` default, which could not resolve in a
packaged deploy anyway. Every API caller passes the canonical schema explicitly, and a missing schema
now returns an error rather than silently validating against the wrong document.

**Why the suite could not catch it.** Every one of these tests ran green with the validator
unavailable, because nothing asserted that validation was actually happening.
`tests/test_canonical_validator_is_owned_by_the_api.py` closes exactly that: it asserts a good object
validates with **zero** errors (not merely "no crash"), that a bad one is still rejected, that the
shipped worked example passes our own validator, and a source-level guard against re-adding the
cross-boundary import. A test that passes whether or not the validator loads cannot protect it.

### `/analyst/status` is config-only, and that is how every scan floored unnoticed

`analyst.runtime_status` checks that `OPENROUTER_API_KEY` is **present** and a preset name is set,
then reports `ready_for_live_model: true`. It never calls anything. So a revoked key, a renamed or
truncated preset, and an exhausted balance all read as ready and then fail on **every** scan, each one
silently persisting the deterministic Floor. `render.yaml` used to point the go-live check at exactly
that endpoint.

`GET /v1/investigations/analyst/preflight` closes it, the same way `/v1/billing/preflight` closed the
identical hole for Stripe: **the key being set is not the same as the key working.** It makes one
`max_tokens: 1` call through the real credential and the real model reference, classifies the refusal
(`bad_api_key` / `no_credit` / `preset_or_model_not_found` / `rate_limited` / `unreachable`), and
returns the operator action for it. It also prints `config_only_status` beside its own answer, because
the gap between the two IS the diagnosis.

Three things not to undo:

- **`OpenRouterReasoningProvider.probe()` never raises and never returns the key.** It is rendered
  straight to an operator and gets pasted into chats and issues. Pinned by
  `test_the_probe_never_returns_the_api_key`.
- **The `gateway_reachable` check is appended on every OpenRouter path, success or failure.** An
  earlier draft only appended it when the probe ran, so a preflight that could not perform its live
  check reported `ready: true` for precisely the reason `/analyst/status` already did. A test caught
  it. A preflight that passes because it failed to look is worse than no preflight.
- **Do not use `build_remote_provider()` here.** Despite the name it builds the **Hugging Face**
  provider and returns `None` without an HF endpoint, so the probe silently never ran. The preflight
  constructs the same `OpenRouterReasoningProvider` the analyst does, from the same settings, or it
  proves nothing about the path that actually runs.

`_PROBE_REMEDIES` is keyed on the probe's reasons and `test_every_probe_reason_has_an_operator_remedy`
fails when a new reason arrives without one, so a failure can never render as a bare error with no
next step.

## Outstanding — needs the user, not code

0. **Measure the coordination detector on real scans.** Every threshold in
   `app/campaigns/detector/` is reasoned, not fitted: no labelled corpus of verdict-only campaigns
   exists. The controls in `test_campaign_detector_precision.py` are synthetic, so they prove the
   *shape* of the guard and not its calibration. Run a dozen real investigations, open
   `/narratives`, and dismiss the false positives; those dismissals are the only ground truth that
   will ever accumulate, and a later pass can fit against them. Watch specifically for
   `verbatim_echo` firing on platform-templated text (auto-generated "I just earned a badge" posts)
   and for `co_target` on small niches where everyone genuinely engages the same handful of posts.

   **The same is now true of `app/netdetect/`, and it has somewhere to put the answers.** Run
   `POST /v1/admin/netdetect/{slug}` on real investigations, read
   `GET /v1/admin/netdetect/findings/all`, and dismiss or confirm each one with a reason.
   `GET /v1/admin/netdetect/findings/calibration` replays every threshold against those judgements
   and refuses to recommend anything until there are 30 with 8 of each class, so the first thirty
   are the whole cost of calibrating it. Watch specifically for a finding that names an account you
   can tell is an ordinary bystander: that is the measured ~7% contamination and the judgement to
   record is a dismissal with that reason, since it is the one class no threshold currently
   separates.
1. **Register the Stripe webhook** and set `OMI_STRIPE_WEBHOOK_SECRET` on the API service, then
   redeploy. URL is `https://<API-host>/v1/billing/webhook` (**not** the web host) and the six events
   are listed in `docs/stripe-setup.md` §3 — or read them off `/v1/billing/preflight`, called directly
   on the API host. Until then billing works, just not instantly: reconciliation carries it.
2. **Clerk dashboard:** Configure → User & authentication → Email, phone, username → **Username OFF,
   Phone Optional.** Otherwise sign-up dead-ends on `/sign-up/continue`. This is config, not code.
   Also set the **`sk_live_` `CLERK_SECRET_KEY` on BOTH Render services** (it is `sync: false`, so it
   is dashboard-owned and was never committed) and confirm the committed `pk_live_` in `render.yaml`
   equals the production publishable key in the Clerk dashboard. See the Clerk instance-pairing note
   above for why a mismatch is invisible.
3. **Rotate the secrets** pasted into chat in an earlier session (`CLERK_SECRET_KEY`,
   `OMI_DATABASE_URL`, `OMI_TWITTER_API_KEY`, `OMI_YOUTUBE_API_KEY`, `OPENROUTER_API_KEY`,
   `OMI_SESSION_SECRET`). Never commit them.

### Launch-readiness findings still open

Closed 14 of 20 in `fbbd096`; these 7 were left because each needs a decision, money, or a
measurement that cannot be taken from a sandbox. Recorded here because a commit message is not
somewhere anyone looks:

| | Why it is still open |
|---|---|
| OMI-04 dependency pinning | A lockfile generated in this sandbox may not match the production interpreter. |
| OMI-09 infra sizing | Postgres 256MB + starter plans. Spends your money. |
| OMI-10 browser → API directly | Touches the auth cookie flow; wants its own change and real verification. |
| OMI-11 Redis | For rate limits / cache / metrics. Needs a service provisioned. |
| OMI-13 durable job queue | Same, plus an architecture change. |
| OMI-16 analyst token ceiling | The right number comes from your production `output_tokens`. |
| OMI-20 analytics | A vendor choice — and your privacy policy promises no third-party analytics. |

Also partial: **OMI-07** — the landing page no longer awaits `/v1/auth/me`, but it is still
per-request because the root layout reads `headers()` for the CSP nonce. Trading a nonce CSP for CDN
caching is a judgement call nobody has made.

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

## The dataset corpus is not in git, and must not go back

`datasets/` (~862 MB) was committed with its archives in **Git LFS**. The account's LFS budget was
exceeded, and because `git clone` must smudge LFS pointers to check out the working tree, the failure
was **total**: GitHub refused to serve the objects, the clone died mid-checkout, and Render could not
deploy at all. Not a slow build — no build.

```
batch response: This repository exceeded its LFS budget.
error: external filter 'git-lfs filter-process' failed
fatal: ... smudge filter lfs failed
==> Unable to clone https://github.com/MCIF-TEST/omi
```

The corpus is offline training/eval data. **The API never reads it at runtime** — it boots fine
without it and `discover()` returns an empty set rather than raising, which is what made removal
safe. It is now `.gitignore`d, and the LFS tracking patterns are deleted from `.gitattributes` rather
than merely unused: left in place, committing any new `.zip`/`.gz`/`.tar` would silently re-enter LFS,
hit the same exhausted budget, and take deploys down again with an error pointing at git rather than
at this decision.

Two consequences worth knowing:

- **Deleting at HEAD fixes the clone, not the quota.** The LFS objects still exist in history, so the
  budget stays consumed until the history is rewritten (`git filter-repo`) or a data pack is bought.
  Clones work because nothing at HEAD needs smudging any more.
- **Nothing was lost.** Every file remains in git history and is recoverable
  (`git show <pre-removal-sha>:datasets/...`). Keep a local copy under `datasets/` to run the `ml/`
  pipeline; the tests that read real corpus files skip themselves when it is absent
  (`_needs_corpus` in `test_dataset_governance.py` / `test_phase1_free_wins.py`).

If large files are ever needed again, put them in object storage or the Hugging Face datasets the
`ml/` pipeline already syncs to — not in this repo.

## Environment notes

- `cryptography` is broken **in this sandbox only** (`_cffi_backend` missing). `clerk_auth.py` imports
  `jwt` lazily so the app still boots locally; verify RS256 work in a clean venv, not here.
- Outbound HTTPS goes through an agent proxy (`/root/.ccr/README.md`). Never disable TLS verification.
- No `gh` CLI — use the `mcp__github__*` tools.
