# CLAUDE.md — OmiSphere working notes & session handoff

**Living document.** Update it in the same commit as the change it describes. It is the first thing a
new Claude Code session reads, and the only place that explains *why* several non-obvious things are
the way they are. If you change behaviour and don't update this file, the next session will
re-introduce a bug this one already paid for.

**Last updated:** 2026-08-04 · branch `claude/master-analyst-protocol-v1-1u8tyk`, restarted from
`main` after PR [#130](https://github.com/MCIF-TEST/omi/pull/130) merged · suite measured at
**1881 passed, 8 skipped, 1 failed** (5m58s), the failure pre-existing and listed below.
The 8 skips are the corpus-backed tests — see "The dataset corpus is not in git".

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
CLERK_SECRET_KEY= NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY=pk_test_Y2xlcmsuZXhhbXBsZS5jb20k npx next build
```

The build command deliberately runs with **`CLERK_SECRET_KEY` unset** — that must keep working (see
Clerk below). A malformed publishable key fails prerender with a confusing error, so use the
well-formed dummy above rather than something like `pk_test_x`.

---

## Known-failing tests (pre-existing, not yours)

Current measured state: **1572 passed, 8 skipped, 2 failed** (4m28s, 2026-07-28). Both failures reproduce on an
unchanged tree AND in isolation, so neither is pollution:

1. `tests/test_evaluation_benchmark.py::test_accuracy_gate_no_regression` — Brier 0.0321 against a
   0.032 gate.
2. `tests/test_investigation_prompt_builder.py::test_user_presents_the_investigation_context_evidence`
   — asserts the template's `evidence_instruction` appears in `pp.user`, but the comprehensive stage
   builder now renders a user message that ends after the evidence sections. Looks like the test
   trails a prompt-assembly change rather than a real regression; not yet diagnosed.

**A third failure is yours.** If you see mass failures instead, see the next section first.

**Count depends on collection order.** A run during the launch-readiness work reported *13* failures;
11 of those were order-dependent analyst tests that adding new test files shifted into a different
order, not regressions. A clean run in the default order gives the 2 above. If you see extra
failures, re-run the specific files in isolation before believing you caused them — and note that
this order sensitivity is itself a latent problem nobody has fixed yet.

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
- **`AuthFormGate` now gives up after 12s** and says the form could not load. A spinner with no
  terminal state is not a loading state, it is a silent failure, and this one cost a live hour.

Pinned by `apps/web/middleware.test.ts` (8 tests), which asserts the derived origin lands in every
directive that needs it. Note the key is inlined into the Edge bundle at BUILD time, so changing it
needs a rebuild of the web service, not a restart.

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

The join is on `external_id`, never the handle. Sorted worst first, which deliberately differs from
the on-screen order (that follows the batches so results can appear as they land).

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

### Billing

`compute_scan_credits = ceil(accounts / 50) × credits_per_batch[platform]`, minimum 1. **1 credit per
50 accounts, same rate for X and YouTube** (100 accounts = 2 credits). This was an explicit product
decision; don't "fix" the asymmetry back in.

**There are two separate free tiers, and neither one is derived from the other.** Confusing them is
the easy mistake, because both get called "the free scans":

| | Who | Amount | Where it lives |
|---|---|---|---|
| Pre-login demo | Any visitor, metered per IP | **1 scan**, ≤25 accounts | `DEMO_FREE_SCANS_PER_IP` + `DEMO_MAX_COMMENTERS`, hardcoded in `app/routes/scan_async.py` / `scan.py`, test-pinned |
| Signup trial | A new account | **1 credit**, then they pay | `OMI_FREE_TRIAL_CREDITS` in `render.yaml` (code default in `config.py` also 1) |

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

**The signup trial is 1 credit** (was 3, was 25). One credit covers up to 50 accounts, so a funnel
signup gets exactly one real scan of the post they arrived from, then they subscribe. Set in **four**
places and `test_deployed_credit_contract.py` fails on drift between the env pair:
`OMI_FREE_TRIAL_CREDITS` + `NEXT_PUBLIC_TRIAL_CREDITS` in `render.yaml`, `config.py`'s default, and
`plan.ts`'s default.

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

### The coordinated-events surface is removed from the product, not from the code

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

`/narratives` is a placeholder that says "Coming soon: narrative / campaign detector". It is
**admin-only and gated on the server** (`if (!user?.is_admin) notFound()`), because hiding the nav
link alone would leave the route answering to anyone who typed the URL. `adminOnly` on a nav item in
`sidebar.tsx` / `mobile-nav.tsx` is presentation only; the page is the access control.

One live reference remains on purpose: `campaign_reasoning` ("Campaign analysis") in
`analyst-panel.tsx` and `lib/api.ts`. That is a section of the **analyst's own response schema**, not
the campaigns feature. Removing it means a protocol change, a recompile, and a re-paste of the
OpenRouter preset.

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

## Outstanding — needs the user, not code

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
