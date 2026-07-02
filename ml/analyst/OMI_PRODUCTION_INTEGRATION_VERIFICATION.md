# Omi — Production Integration Verification

> **Mandate.** Assume the integration is **not** working until every stage of the production
> pipeline is proven with evidence. Verify each arrow from the website to the Mistral endpoint and
> back. If something cannot be verified, treat it as broken. No "probably." Verdict is **READY** or
> **NOT READY** — no middle ground.

This report separates what is **proven by executable evidence** from what is **structurally verified
but not live-provable from the engineering sandbox** (no live Render URL, no HF endpoint URL, no
`HF_TOKEN`, and egress to `huggingface.co` is blocked here). Per the mandate's own rule, anything not
provable is treated as **not certified** — so the production verdict is **NOT READY from here**, and
this report hands the operator the exact, now-existing instruments to flip it to READY in minutes.

---

## A. Method & honest scope

| Layer | Can I prove it *here*? | How |
|---|---|---|
| Frontend code (website → API call) | **Yes** | source audit + contract test |
| Backend execution path (route → Governor → floor) | **Yes** | source audit + full suite |
| Provider transport (both serving APIs) | **Yes** | mocked-endpoint tests (Mistral + Qwen shapes) |
| Model-independence of the constitutional stack | **Yes** | byte-identical hashes/eval across model ids |
| **Live** Render service running the deployed code | **No** | no live URL from sandbox |
| **Live** HF endpoint reachable + auth + serving Mistral | **No** (instrument built) | egress blocked; operator runs the probe |
| **Live** end-to-end latencies | **No** (instrument built) | requires the live endpoint |

The valuable, previously-unaudited surface this sprint **did** prove: the **website actually calls
the production analyst endpoint** — and, in doing so, uncovered two real defects in the live-path
diagnostics, now fixed.

---

## B. Website → Render API arrow — **VERIFIED WIRED**

Traced every hop of `apps/web`:

1. **The panel is mounted, not orphaned.** `app/(app)/investigations/[slug]/page.tsx:11,104` imports
   and renders `<AnalystPanel slug={inv.slug} />` inside the live investigation page.
2. **It issues the POST.** `analyst-panel.tsx:37-41` → `apiClient('/v1/investigations/${slug}/analyst')`,
   `method: POST`, with `?refresh=true` on regenerate.
3. **The three server states are all handled** (`analyst-panel.tsx:49-76`):
   - `503` → `ApiError.status === 503` → **disabled** state (graceful "not enabled" copy).
   - `202` "generating" → **poll** every 2 s, capped at 10 polls, then a surfaced "taking longer"
     message; the background job still backfills the cache for the next click.
   - `200` "ready" → renders the assessment (verdict, evidence-for/against, uncertainty, Governor
     badge, latency).
   - any other error → surfaced in a visible error box.
4. **The transport reaches Render.** `lib/api.ts:57` does `fetch('/api'+path)`;
   `next.config.mjs:22-29` rewrites `/api/:path*` → `${API_ORIGIN}/:path*`; `API_ORIGIN` resolves
   `OMI_API_ORIGIN` (bare `host:port` → `http://…` for Render's internal mesh).
5. **The auth gate does not eat API calls.** `middleware.ts:36` matcher **excludes** `api/`, so the
   rewrite is a clean passthrough (a real silent-break risk that is correctly avoided).
6. **Invalid-JSON / gateway-timeout is surfaced, not swallowed.** `_parse` (`lib/api.ts:19-45`)
   turns a truncated 2xx body into an explicit `ApiError` instead of leaving the UI blank.
7. **Contract integrity.** Backend `AnalystResponse` (`app/schemas.py:651-665`) matches the web
   `AnalystResponse` (`lib/api.ts:685-693`) field-for-field
   (`slug/enabled/status/cached/assessment/provider/generated_at`) — now guarded by
   `test_analyst_response_contract_matches_the_website_panel`.

**Verdict for this arrow: proven connected.**

---

## C. Backend execution path — **VERIFIED**

`POST /{slug}/analyst` (`app/routes/reasoning.py:87-141`): 503 when disabled → 404 when missing →
200 cached (`analyst.cached_assessment`) → else `background.submit(analyst.generate_and_persist,…)`
+ 202. All three referenced functions exist and are wired
(`analyst.py:439 cached_assessment`, `465 generate_and_persist`, `492 _platform_of`).
`assess_payload` (`analyst.py:268`) runs through the **one** `Orchestrator` (judge = OMI ANALYST,
floor = deterministic), the **mandatory** `Governor`, and the always-on floor; prompt comes from the
Prompt Registry; institutional memory is injected as `prior_context` (background, never proof). A
`governance` block (verdict, trace id, provider, model_revision, prompt, latency) is attached to
every assessment.

---

## D. HF endpoint + **is it actually Mistral?** — instrument built, live proof = operator

Before this sprint, **nothing verified the served model** — `system_health.active_model` only echoed
*config*. New capability (additive, off the hot path, never raises):

- `RemoteReasoningProvider.probe_served_model()` — reads the served model from the chat completion's
  top-level `model` field (`messages` API) or the TGI `/info` route (`generate` API).
- `endpoint_health` / `endpoint_smoke_test` / `system_health` / `trace_investigation` now surface
  `served_model`, `expected_model` (`mistralai/Mistral-7B-Instruct-v0.3`), and `model_matches`.

**Operator's one-shot proof (run on Render with the live endpoint):**
```python
from app.reasoning.trace import endpoint_health, endpoint_smoke_test
endpoint_health()      # → status=reachable, served_model=…, model_matches=true
endpoint_smoke_test()  # → model_backed=true, governor_verdict=permit, number_echoed=true,
                       #   served_model=mistralai/Mistral-7B-Instruct-v0.3, model_matches=true
```
`model_matches: true` is the evidence the endpoint is Mistral — **not merely up, and not a different
model**. `model_matches: false` now emits `model_mismatch_detail` naming the wrong served model.

The HF package declares Mistral consistently (README `base_model`, `analyst_config.json`,
`BASE_MODEL.md`, `hf_repo_manifest.toml`; `thinking.enabled=false`; no `Qwen` runtime references),
proven by `test_hf_package_declares_mistral_consistently`.

---

## E. Defects found → **STOPPED and fixed**

**E1 — Health probe used the wrong wire contract (false "unreachable").**
`endpoint_health()` built its probe provider with the *default* `generate` API regardless of
`OMI_ANALYST_ENDPOINT_API`. Against the **recommended** `messages` (chat) endpoint for Mistral it
sent a `/generate`-shaped body to a chat route → rejection → a **healthy endpoint reported
`unreachable`**, corrupting `/integrity` and `system_health`. *Fix:* honor `analyst_endpoint_api`
and pass the model. *Proof:* `test_endpoint_health_probes_a_messages_endpoint_with_the_chat_contract`
(a chat-only mock; asserts `reachable` + every probe used the chat contract).

**E2 — No served-model verification (can't prove it's Mistral).** *Fix:* `probe_served_model` + the
`served_model`/`model_matches` surfacing above. *Proof:* six tests incl. Mistral-match, wrong-model
flag, `/info` path, not-configured, and failure-without-raise.

Both are additive/corrective — **no frozen architecture touched** (Governor, OmiScore, Orchestrator,
provider abstraction, prompt/framework hashes all unchanged; `complete()` hot path byte-identical).

---

## F. Silent-failure modes & how each is now detectable

| Stage | Silent-failure mode | Detection |
|---|---|---|
| Website → API | rewrite/env misconfig, auth gate eats `/api` | audited: rewrite present, `api/` excluded; contract test |
| Endpoint reachability | chat endpoint pinged with generate body | **E1 fixed** — probes with configured API |
| Endpoint identity | endpoint serving the wrong model | **E2 fixed** — `model_matches` + `model_mismatch_detail` |
| Model output | non-JSON / moved number / fabricated ref | `Governor` REJECT → deterministic floor (valid governed output) |
| Provider down | HF outage / timeout | typed `ProviderTimeout`/`ProviderError` → floor; `fallback:` in provider string |
| UI | blank panel on truncated response | `_parse` raises surfaced `ApiError` |

Product safety invariant confirmed: **the analyst being off or unreachable never blocks a scan or
moves a score** — the floor is a complete, schema-valid, Governor-passed provider.

---

## G. Latency instrumentation

`trace_investigation` emits an ordered per-stage trace with `duration_ms` (evidence bundle, memory
retrieval, context builder, prompt registry, model, judge, Governor, final) plus `total_duration_ms`
and `flag_state.endpoint_identity`. `endpoint_health`/`endpoint_smoke_test` report `latency_ms`.
Absolute wall-clock numbers require the live endpoint (operator-run); the harness to capture them is
in place and tested.

---

## H. Verdict

**Code path & website wiring: READY** — proven by source audit + **1115** passing backend tests
(11 new), including the previously-unaudited frontend arrow and the two defect fixes.

**Production (live Render + HF endpoint): NOT READY *as certified from here*** — and, per the
mandate ("if it cannot be verified, treat it as broken"), it must not be called READY on `probably`.
The live external stages are **unreachable from the engineering sandbox**, so they are explicitly
**not certified**. This is not a code gap; it is an evidence gap that only the operator can close.

**Exact steps to flip to READY (operator, on Render with the live endpoint):**
1. Set the §2 env (`OMI_ANALYST_ENABLED=true`, `OMI_ANALYST_ENDPOINT_URL`, `OMI_ANALYST_ENDPOINT_API`,
   `HF_TOKEN`, `OMI_ANALYST_HF_REVISION`, `OMI_ANALYST_MODEL_ID`).
2. `endpoint_health()` → `status=reachable`, `model_matches=true`.
3. `endpoint_smoke_test()` → `model_backed=true`, `governor_verdict=permit`, `number_echoed=true`,
   `model_matches=true`.
4. One real investigation via the website → the panel renders a `permit` assessment with a
   non-fallback provider.

When steps 2–4 return the values above, production is **READY** — with evidence, not assumption.

---

*Additive/corrective only. No change to OmiSphere scoring, detectors, OmiScore, the Governor, the
Orchestrator, or the provider abstraction. GitHub remains the single source of truth; the HF package
continues to publish solely through the existing GitHub Actions workflow.*
