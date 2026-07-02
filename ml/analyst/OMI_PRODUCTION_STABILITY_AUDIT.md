# Omi — Production Stability Audit (Runtime User-Journey Verification)

> **Mandate.** Assume the deployment is not production-ready. Treat the application as broken.
> Boot the real stack, drive the complete user journey in a real browser, reproduce every runtime
> error from logs / browser console / API responses, fix blockers, and repeat the full journey
> until it is clean: **Website → Login → Dashboard → Investigation → AI Analysis → Report.**

Unlike the previous sprint (source-level integration verification), this audit **executed the
product**: a production `next build` + `next start` frontend against a `uvicorn` backend booted in
production-like mode (`OMI_REQUIRE_AUTH=true`, analyst enabled), driven end-to-end with a real
Chromium browser (Playwright), capturing every console error, page error, failed request, and
4xx/5xx response, while watching the server logs.

---

## A. What ran (evidence base)

| Layer | How it ran |
|---|---|
| Frontend | `npm run build` (production compile — **passed, exit 0**) → `next start` on :3000 |
| Backend | `uvicorn app.main:app` on :8000, `OMI_REQUIRE_AUTH=true`, `OMI_ANALYST_ENABLED=true`, fresh sqlite DB (31 tables auto-created, featured campaigns seeded) |
| Browser | Headless Chromium via Playwright; console/pageerror/requestfailed/≥400-response capture; full-page screenshots per stage |
| Platform data | The sandbox has **no YouTube/Twitter credentials**, so the suite's `FakeYouTubeClient` (15 commenters) was injected through the API's own public test seam (`set_client_factory_for_tests`) **in the server process — zero product-code changes**. Everything downstream of the transport (scoring, coordination, persistence, credits, UI) is the real pipeline. |
| AI analysis | `OMI_ANALYST_ENABLED=true` with no HF endpoint → the **deterministic floor** serves the governed assessment (the designed always-on path). The live-endpoint leg was separately certified in `OMI_PRODUCTION_INTEGRATION_VERIFICATION.md`. |

## B. The journey — final run, all stages green

Every step below is from the last full run (`run4`, fresh DB), screenshot-backed:

| # | Stage | Result | Evidence |
|---|---|---|---|
| 1 | Landing page renders | **PASS** | title `OMISPHERE — Social Authenticity Intelligence`; no page errors |
| 2 | Auth gate: `/dashboard` logged-out | **PASS** | redirect → `/login?next=%2Fdashboard` (middleware) |
| 3 | Signup → dashboard | **PASS** | `POST /v1/auth/signup` → 200; lands on `/dashboard`; renders (19 KB body, no error boundary) |
| 4 | Investigation scan from the UI | **PASS** | `POST /v1/scan/link/start` → **202** (async job contract); job polled; permalink appears; slug `inv_eb7c0e33` |
| 5 | Investigations list | **PASS** | saved scan listed at `/investigations` |
| 6 | Investigation detail | **PASS** | hero + three-pane viewer render (152 KB body), 15 commenters, no error boundary |
| 7 | **AI analysis** | **PASS** | "Generate assessment" → 202 → poll → assessment renders with **Governor permit** badge; provider `deterministic-analyst-v1`; ValidationTrace `vt:049d8643…`; latency 0.86 ms; verdict `inconclusive` (evidence-bounded, tier `high`) |
| 8 | Share link minted | **PASS** | `POST /v1/investigations/{slug}/share` → 200, token `rpt_…` |
| 9 | **Public report, logged out** | **PASS** | `/r/{token}` renders in a fresh anonymous browser context (22 KB body) |
| 10 | Logout → gate → login | **PASS** | logout 200; `/dashboard` re-gated to `/login`; `POST /v1/auth/login` → 200 → dashboard |

**Across the entire journey: zero 4xx/5xx responses (other than deliberate negative probes), zero
unhandled page errors, zero 500s in the API log.**

Negative-path probes (deliberate):
- Scan without platform credentials (before injection): `POST /v1/scan/link/start` → **503**, error
  **surfaced in the UI** (no crash, no charge — the route builds the platform source before billing).
- Duplicate-email signup → **409**, surfaced in the form.
- Wrong-password login → **401** `"Email or password is incorrect."` (non-enumerating), surfaced.

## C. Issue checklist (found → root cause → fix → verification)

**Product-code defects found: 0.** Every blocker encountered was in the audit harness or
environment, and two prior-sprint product fixes are what made the AI stage certifiable. Full
honesty ledger:

| # | Issue | Root cause | Fix | Verified by |
|---|---|---|---|---|
| 1 | First seeding attempt produced `investigation_slug=None` (looked like a silent persistence failure) | **Not a product bug** — audit script called `_run_comprehensive` directly, which by design does not persist; persistence lives in `scan_link` / the async job worker (`scan_async.py`), i.e. the layer the UI actually calls | Re-architected the audit to drive the **real UI path** (`/investigate` → `POST /v1/scan/link/start` → background job) with the fake client injected in-process | Journey run4 step 4–6: scan persisted, listed, rendered |
| 2 | Driver flagged `scan_job_started` FAIL on status 202 | Audit-driver assertion expected 200; the async-start contract is **202 Accepted** | Corrected the driver expectation | run4 step 4 PASS |
| 3 | Driver crash navigating to `public_url` (`/r/rpt_…`) | `ShareResponse.public_url` is **deliberately relative** (`reports.py:71`); the UI composes the absolute link from its own `PUBLIC_BASE_URL`. Driver assumed absolute | Driver absolutizes; documented the contract note below | run4 steps 8–9 PASS |
| 4 | Signup 409 on re-run | Stale audit DB (harness `rm` ran in the wrong cwd) — and the 409 itself is correct duplicate-email behavior | Reset the right DB file; kept 409 as a verified negative path | run4 step 3 PASS + negative probe |
| 5 | 14 browser console errors on every page | External font CDNs (`rsms.me/inter`, `fonts.googleapis.com`) are blocked by sandbox egress; the app falls back to system fonts and renders fully | None required (graceful degradation works). **Production observation:** the UI has a runtime dependency on two third-party CDNs; self-hosting the fonts would remove the only recurring console noise and the CDN availability dependency | All pages rendered and functioned with fallback fonts |
| 6 | AI stage previously unprovable-healthy (prior sprint, fixed at `e6787e1`) | `endpoint_health()` probed chat endpoints with the `generate` wire contract → false `unreachable`; and no served-model verification existed | Fixed + `probe_served_model()` added (previous sprint, this branch) | 11 tests in `test_integration_verification.py`; this journey exercised the analyst route/panel end-to-end |

Contract note (not a defect): API consumers of `POST /{slug}/share` receive a **relative**
`public_url` (`/r/<token>`); the web UI never uses it (it builds the absolute URL client-side).
Integrators must prepend their deployment origin.

## D. Silent-failure surfaces checked

- **API log for the full journey:** no `Traceback`, no `500 Internal Server Error`, no
  `fell back to deterministic` warnings, no fabricated-evidence/Governor-reject logs.
- **Browser:** no unhandled `pageerror` on any of the 10 stages; the only console entries are the
  external-font fetches (§C-5).
- **Aborted RSC prefetches** (`?_rsc=` → `ERR_ABORTED`) observed during navigation are normal
  Next.js prefetch cancellation, not failures.
- **Credits:** scan charged the trial-credit account and out-of-credit/mis-config paths refund
  before billing (verified in code path + 503-before-charge probe).

## E. Sandbox constraints (stated plainly)

- **Platform transport was faked** (no YouTube credentials in this environment). The fake is the
  test suite's own client injected via the API's public test seam at boot; every other layer —
  routes, job pool, scoring, coordination, persistence, credits, auth, UI — was the real thing.
  A production deploy with a real `OMI_YOUTUBE_API_KEY` swaps only that transport.
- **AI analysis ran on the deterministic floor** (no HF endpoint URL/token here; egress to
  huggingface.co is blocked). The floor is the designed availability guarantee — Governor-validated,
  schema-valid, sub-millisecond. The live Mistral-endpoint leg has its own operator checklist in
  `OMI_PRODUCTION_INTEGRATION_VERIFICATION.md` (§H) and now carries served-model verification.
- Fonts: see §C-5.

## F. Gates

- Full backend suite: **1115 passed** (unchanged code, re-run this sprint).
- Frontend: production `next build` **passed**; `npm run typecheck` **passed**.
- No product source was modified by this audit (drivers/harness live outside the repo; this report
  is the sprint's repo artifact).

## G. Verdict

**The login → authentication → dashboard → investigation → AI analysis → report pipeline is
runtime-clean in this environment.** Ten of ten journey stages pass in a real browser against the
production build with auth enforced, with zero server errors and zero unhandled client errors; the
negative paths (no credentials, duplicate signup, wrong password, logged-out gating) all degrade
gracefully and visibly. The two production-certification gaps that remain are the same two external
legs already documented: a real platform API key, and the live HF endpoint checks — both
operator-side configuration with ready-made verification instruments, not code work.

---

*Audit only: no product code changed. Harness artifacts (Playwright journey drivers, fake-platform
boot wrapper, screenshots, console/network captures) ran from the session scratchpad.*
