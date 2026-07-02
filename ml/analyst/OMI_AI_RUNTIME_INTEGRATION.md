# Omi — End-to-End AI Runtime Integration (every investigation reaches the endpoint)

> **Symptom.** Website operational, users authenticate, investigations complete, the Hugging Face
> Mistral endpoint is live — but it receives **zero requests** during investigations. The AI runtime
> was therefore never actually invoked; only the deterministic path ran.

This was traced by **executing the real runtime** against a local logging stand-in for the HF
endpoint (a mock that records every request and returns a Mistral-shaped, bundle-consistent
completion), with the analyst configured exactly as production (`OMI_ANALYST_ENABLED=true`,
`OMI_ANALYST_ENDPOINT_URL`, `OMI_ANALYST_ENDPOINT_API=messages`, `HF_TOKEN`, revision pinned).

## 1. Runtime execution diagram (as wired now)

```
[Run investigation] ─POST /v1/scan/link/start──────────────► scan_async worker
        (button)                                                   │ runs the detection pipeline
                                                                   ▼
                                            scan._persist_investigation()  ── on CREATE ──►
                                                                   │        analyst.maybe_autogenerate(slug, uid)   ★ NEW WIRE
                                                                   │            └─ background.submit(generate_and_persist)   (off the hot path)
                                                                   ▼
                                                   analyst.generate_and_persist()   (exactly-once: cache + in-flight guard)
                                                                   ▼
                                                   analyst.assess_payload()
                                                     ├─ Evidence Bundle (Binder, comment_section grain)
                                                     ├─ Prompt Registry → omi_analyst v1 (content-hash ph:…, source=registry)
                                                     ├─ Institutional Memory → prior_context
                                                     ├─ endpoint set? ──► QwenAnalystProvider(transport=_qwen_transport(model=Mistral))
                                                     │                       └─ RemoteReasoningProvider.complete()
                                                     │                            └─ HTTP POST ─────────────► HF endpoint (Mistral-7B-Instruct-v0.3)  ★ ONE REQUEST
                                                     ├─ mandatory Governor (PERMIT / REJECT)
                                                     └─ deterministic Floor (only on failure/REJECT)
                                                                   ▼
                                                   persist_assessment() → Investigation.payload_json[analyst_assessment_v1]
                                                                   ▼
[Investigation report] ◄─ AnalystPanel auto-loads on mount ─ POST /analyst → returns the cached, governed assessment
```

## 2. Root cause

**The investigation pipeline never invoked the analyst.** `assess_payload` (→ `RemoteReasoningProvider`
→ the HF endpoint) was reachable **only** through an explicit `POST /v1/investigations/{slug}/analyst`,
which the frontend called **solely on a manual "Generate assessment" click**. A normal investigation
(scan → view report) never issued that call, so the endpoint received nothing. Confirmed by
execution: `scan.py` / `scan_async.py` contained **zero** analyst references; a scan produced
**0** HF requests, and only a direct `/analyst` call produced one.

This is the **first decision** on the intended path that blocked `RemoteReasoningProvider`: it sits
**upstream of every AI stage** — the runtime never reached the Evidence Builder → Prompt Registry →
provider chain during an investigation at all. (Every downstream gate was already correct: with the
endpoint configured, `assess_payload` selects `QwenAnalystProvider` with the shared transport, and
`_call_model` fires the HTTP request — proven below.)

## 3. Files changed

| File | Change |
|---|---|
| `apps/api/app/routes/scan.py` | `_persist_investigation`: on a **new** investigation (create, not continuation-merge), call `analyst.maybe_autogenerate(slug, user_id)` after commit — the missing wire. |
| `apps/api/app/reasoning/analyst.py` | New `maybe_autogenerate()` (gated by `analyst_enabled`; schedules `generate_and_persist` on the background pool; never raises). `generate_and_persist()` gains an **in-flight guard** (with the durable cache = exactly-once model call). `_qwen_transport()` gains a `model` param so the request body names the served model (was `"tgi"`). Per-stage **INFO logging** at provider selection, the outbound model call (endpoint/api/model/latency/outcome), and the governed result. |
| `apps/web/app/(app)/investigations/[slug]/analyst-panel.tsx` | Auto-load the assessment on mount (`useEffect`), so the AI reading appears in the report automatically instead of requiring a click. |
| `apps/api/tests/test_analyst_autowire.py` | 7 tests: schedule-when-enabled, no-op-when-disabled, never-raises, create-schedules-once, continuation-does-not-reschedule, in-flight dedup, transport names the model. |

**Not changed:** the Governor, OmiScore, the Orchestrator, the deterministic floor, the provider
abstraction, and the prompts — no new AI capability, no heuristic, no prompt redesign. The wire is
a **no-op unless `OMI_ANALYST_ENABLED` is set**, so the default deployment is byte-for-byte unchanged.

## 4. Before vs after runtime path

| | Before | After |
|---|---|---|
| Scan completes | investigation persisted; **analyst never called** | investigation persisted **→ analyst scheduled** (background, gated) |
| HF requests per investigation | **0** | **exactly 1** (cache + in-flight guard) |
| Reaching `RemoteReasoningProvider` | only on a manual button click | on every investigation (when enabled) |
| Report AI section | empty until the user clicks "Generate" | **auto-populated** with the governed, model-backed reading |
| Prompt source | (never reached) | Prompt Registry `omi_analyst v1` (`source=registry`, `ph:715d…`) |

## 5. Endpoint verification (executed)

One investigation, **no client-side `/analyst` call**, endpoint = the logging mock:

1. `POST /v1/scan/link/start` → **202** (scan runs).
2. HF request log after the scan alone: **exactly 1** —
   `POST /v1/chat/completions api=messages model=mistralai/Mistral-7B-Instruct-v0.3 auth=yes bytes=22102`.
3. Endpoint received the inference call (logged above).
4. Render/API log:
   `analyst.autogenerate: scheduled … (target=remote-model)` →
   `analyst.assess: REMOTE provider selected … model=mistralai/Mistral-7B-Instruct-v0.3 prompt=v1(ph:715d…) -> model call will be made` →
   `analyst.model_call: OK endpoint=127.0.0.1:9009 api=messages model=mistralai/Mistral-7B-Instruct-v0.3 chars=1887 latency_ms=3`.
5. Governor: the response was validated → `governor=permit`, `gov.provider=qwen-omi-analyst-v1`,
   `model_backed=True` (NOT the deterministic floor).
6. Report: the investigation's cached assessment returns `status=ready`,
   `provider=qwen-omi-analyst-v1`, headline present, prompt `source=registry` — and the
   AnalystPanel auto-renders it (Governor badge + evidence) with no manual click. Opening the report
   caused **no second HF request** (still 1 total — the in-flight/cache guard holds).

Gates: new wiring tests **7/7**; full backend suite green; `next build` + `tsc --noEmit` pass.

## 6. Remaining blockers (operator-side; not code)

1. **Set the analyst env on the live API service** (Render): `OMI_ANALYST_ENABLED=true`,
   `OMI_ANALYST_ENDPOINT_URL=<HF endpoint>`, `OMI_ANALYST_ENDPOINT_API=messages`, `HF_TOKEN=<read>`,
   `OMI_ANALYST_HF_REVISION=<sha>`, `OMI_ANALYST_MODEL_ID=mistralai/Mistral-7B-Instruct-v0.3`. Until
   the flag is on, the wire is a deliberate no-op (deterministic floor). Verify with
   `GET /v1/investigations/analyst/status` → `ready_for_live_qwen: true` and
   `endpoint_health()` → `model_matches: true` (prior sprint's instruments).
2. **Persistent database** (still the standing production blocker): sqlite on ephemeral disk loses
   investigations (and their cached assessments) on redeploy. Point `OMI_MEMORY_DATABASE_URL` /
   `OMI_DATABASE_URL` at persistent Postgres.
3. **Endpoint container must match `OMI_ANALYST_ENDPOINT_API`** (messages vs generate), else the
   Governor sees invalid output and the floor serves — verify via the smoke test after deploy.

---

*Integration only: the AI wiring was completed and instrumented; no scoring, detector, Governor,
prompt, or model behavior was added or changed. The endpoint is now reached by every enabled
investigation, exactly once, with the response governed and surfaced in the report.*
