# Omi — Forensic Investigation Audit (endpoint untrusted until proven)

> **Mandate.** Treat the Hugging Face endpoint as untrusted. Instrument ONE investigation so it
> captures and logs: (1) the exact final prompt sent, (2) the prompt version/hash loaded from the HF
> package, (3) the model id the endpoint returned, (4) the raw Mistral response before any Governor
> processing, (5) the Governor verdict + exact rejection reason on fallback, and (6) whether the UI
> rendered the model response or the deterministic floor. Assume nothing works; produce evidence.

The audit runs the **real** production path (`assess_payload`) with a forensic **capture sidecar** —
not a reimplementation — so the evidence reflects genuine runtime behavior. It never alters the
request, response, or control flow (the sidecar is `None` on the hot path).

---

## What was built

- **`RemoteReasoningProvider.capture`** (opt-in dict): records the exact wire body, final
  system/user prompt, raw response body, served model id, and the raw text **before** thinking-strip
  / JSON-extract / Governor. Zero-impact when unset.
- **`assess_payload(..., capture=...)`** threads the sidecar through `_qwen_transport` and stamps the
  AI-package provenance (prompt version/hash) — the real path, instrumented.
- **`trace.audit_investigation()`** assembles the six items, each with a PROVEN / DISPROVEN /
  UNVERIFIED status and an overall `endpoint_trust_verdict`, and logs the trail to
  `omi.reasoning.audit`.
- **`POST /v1/investigations/{slug}/analyst/audit`** (admin) runs it on a real stored investigation.
- Tests: `tests/test_forensic_audit.py` (4) — trusted, untrusted-garbage, no-endpoint, route.

## Evidence — one real investigation (`inv_cc242b38`) against a Mistral-shaped endpoint

Verdict: **TRUSTED (model-backed, permitted, model id verified)** · total 365 ms · exactly one HF request.

| # | Stage | Status | Evidence captured |
|---|---|---|---|
| 1 | Final prompt sent | **PROVEN** | `POST http://…/v1/chat/completions` (api=`messages`); system = "You are OMI ANALYST, the reasoning layer of OmiSphere…"; user = "Analyze the following OmiSphere evidence for one comment_section. Produce a single JSON object…" |
| 2 | Prompt version/hash from HF package | **PROVEN** | `prompt_version=v1`, `prompt_hash=ph:715d4e26feb9d799f0f6bfc4a82629e9`, `package_hash=pkg:28d7576269becdeca82159bf` |
| 3 | Model id returned by endpoint | **PROVEN (matches expected)** | `served_model = mistralai/Mistral-7B-Instruct-v0.3` == expected |
| 4 | Raw model response (pre-Governor) | **PROVEN** | raw text captured verbatim: `{"analyst_version":"v1","prompt_version":"v1",…}`; attempts=1; latency 1.46 ms |
| 5 | Governor verdict + fallback reason | **PROVEN** | `verdict=permit`, `fallback_occurred=false`, `fallback_reason=null`, `trace_id=vt:81ab2959…` |
| 6 | Report renders model vs floor | **MODEL** | `provider=qwen-omi-analyst-v1`, `model_backed=true` — the persisted assessment the UI renders |

Render log trail (`omi.reasoning.audit`) mirrors the same, e.g.:
```
audit[sub_5ce9aab09311] 3_served_model_id = PROVEN (matches expected)
audit[sub_5ce9aab09311] served_model=mistralai/Mistral-7B-Instruct-v0.3 expected=…v0.3 | governor=permit provider=qwen-omi-analyst-v1 | prompt_hash=ph:715d…
```

## Disproving stages — the audit catches an untrusted endpoint (regression-tested)

The instrumentation is only useful if it can DISPROVE. Two adversarial cases, proven by
`test_forensic_audit.py`:

- **Wrong model + non-JSON garbage** (`{"model":"evil/wrong-model-13b","choices":[{"message":{"content":"I will not answer in JSON. Trust me."}}]}`):
  item 4 still captures the raw garbage verbatim; item 3 → **DISPROVEN (served=`evil/wrong-model-13b`)**;
  item 5 → `fallback_occurred=true`, `fallback_reason=model_output_not_schema_valid_json (…the judge
  fell back to the floor before the Governor)`; item 6 → **DETERMINISTIC_FLOOR** (`model_backed=false`);
  overall **NOT TRUSTED**. The product stays correct (a valid governed floor assessment ships).
- **No endpoint**: item 1 → **DISPROVEN (no model call)**, item 4 raw=`null`, item 5
  `fallback_reason=no_model_call (endpoint unset/unreachable) → deterministic floor`, item 6 FLOOR.

Both fallback causes are distinguished: a **Governor reject** of valid model output (`verdict=reject`
+ `rejected_codes`) vs. **invalid model output** that never reached the Governor (the judge
substituted the floor first).

## Honest scope

The live evidence above was produced against a **local Mistral-shaped stand-in** (the sandbox has no
egress to huggingface.co and no live endpoint URL). Every stage of the *runtime* is proven real —
the prompt assembly, the package hash, the served-model check, the raw-capture, the Governor, and the
render source. To certify the **live** endpoint, the operator runs the same one command against the
real deployment:

```
POST /v1/investigations/{slug}/analyst/audit   (admin)
```

and reads the six items + `endpoint_trust_verdict`. If item 3 is DISPROVEN or item 6 is
DETERMINISTIC_FLOOR, the endpoint is not (yet) trustworthy — with the exact captured prompt, raw
response, and reason to debug it.

## Files changed

`app/reasoning/model_providers/remote.py` (capture sidecar), `app/reasoning/analyst.py` (thread
capture + stamp package), `app/reasoning/trace.py` (`audit_investigation` + `_fallback_reason`;
`_trace_settings` now carries the model id + memory settings), `app/routes/reasoning.py`
(`/analyst/audit` admin route), `tests/test_forensic_audit.py` (4).

*Read-only forensic instrumentation. No change to detection, scoring, OmiScore, the Prompt Registry,
the Governor, or the deterministic floor.*
