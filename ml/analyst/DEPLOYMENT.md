# Omi Analyst — Deployment Runbook

> **Operator runbook.** Step-by-step activation of the live Qwen Analyst on a Hugging Face
> Inference Endpoint. This is the *how*; the *why/strategy* (lifecycle tags, serving economics,
> cost) lives in `huggingface_model_lifecycle.md` and is not repeated here. Deployment is
> **configuration, not code** — the code path is complete and verified. Nothing here touches the
> Governor, OmiScore, or the deterministic floor.

Repo: `Andrewexiga/omi-analyst-v1` (private) · Base: `Qwen/Qwen3-4B-Thinking-2507-FP8` · Runtime:
Render (`apps/api`) · Memory: Supabase (optional).

---

## 0. Preconditions

- HF package published to the repo: `HF_TOKEN=<write> python ml/analyst/register_hf_model.py --upload`
  (validate first with `--validate`). Publishes the card, config, base pointer, system prompt,
  schema, `prompt_manifest.json`, `prompt_catalog.json`.
- You have an HF **read** token for serving (separate from the write token).
- You know the immutable **revision sha** to pin (never `main`/`latest`).

## 1. Create the Inference Endpoint

1. HF → the repo → **Deploy → Inference Endpoints** → new **dedicated, private** endpoint.
2. Pin the **revision sha** (Advanced → Revision). Reproducibility + safe rollback depend on this.
3. Pick the serving container:
   - **Messages API (recommended)** — TGI / OpenAI-compatible `/v1/chat/completions`. The endpoint
     applies Qwen3's chat template server-side.
   - **Generate API** — raw TGI `/generate`.
4. Enable **scale-to-zero** to bound cost (the Analyst is off the request-critical path).
5. Copy the endpoint **URL** (the full route matching the API you chose).

## 2. Render environment variables

Set on the `apps/api` service, then deploy:

| Variable | Value | Notes |
|---|---|---|
| `OMI_ANALYST_ENABLED` | `true` | master switch (kill switch = set `false`) |
| `OMI_ANALYST_ENDPOINT_URL` | `<endpoint URL>` | must match the API route below |
| `OMI_ANALYST_ENDPOINT_API` | `messages` (recommended) or `generate` | must match the endpoint container |
| `HF_TOKEN` | `<read token>` | never printed; read from env only |
| `OMI_ANALYST_HF_REVISION` | `<commit sha>` | **pin**, never `main`/`latest` |
| `OMI_ANALYST_HF_REPO` | `Andrewexiga/omi-analyst-v1` | default already correct |
| `OMI_ANALYST_TIMEOUT_SECONDS` | `30` | optional |
| `OMI_ANALYST_MAX_RETRIES` | `2` | optional (capped-backoff) |

Durable institutional memory (optional — defaults to an empty in-memory store, which safely
no-ops):

| Variable | Value |
|---|---|
| `OMI_MEMORY_PERSISTENCE_ENABLED` | `true` |
| `OMI_MEMORY_DATABASE_URL` | `<Supabase Postgres URL>` |

## 3. Supabase configuration (only if enabling durable memory)

- Point `OMI_MEMORY_DATABASE_URL` at the Supabase Postgres instance (project `vqckxxfqgayvuurbvhhk`).
- Ensure memory migrations `0008`–`0010` are applied (`0011` index-dedup is optional cleanup).
- Memory is **context only** — a Supabase outage degrades to no-prior-context, never blocks a scan
  or moves a score.

## 4. Health verification

- **Endpoint reachability:** `GET /v1/investigations/analyst/integrity` → `endpoint_health.status`
  should be `reachable` (it is `not_configured` until the URL + token are set). Equivalent in code:
  `app.reasoning.trace.endpoint_health()`.
- **Readiness snapshot:** `app.reasoning.model_providers.provider_status()` →
  `ai_specialist_ready: true` once flag + endpoint + token are all present.

## 5. Smoke test (the green light)

Run one real investigation end-to-end through the live endpoint:

```python
from app.reasoning.trace import endpoint_smoke_test
endpoint_smoke_test()
```

**Expected when live:**
```
status = "qwen_backed"          # NOT "fallback_deterministic"
governor_verdict = "permit"
number_echoed = true
provider = "qwen-omi-analyst-v1"
endpoint_api = "messages"       # or "generate"
model_revision = "<your sha>"
prompt = { source: "registry", version: "v1", hash: "ph:…" }
```

If `status = "not_configured"` → env not set. If `status = "fallback_deterministic"` → the endpoint
was unreachable or returned invalid output (see Troubleshooting); the product is still correct (the
floor served a valid governed assessment), it just isn't Qwen-backed yet.

## 6. Expected logs & outputs

- **Logs (healthy):** no `AI specialist … fell back to deterministic` warnings; no
  `fabricated evidence_ref` / `ProviderProtocolError`. Latency logged per assessment.
- **Governed output (healthy):** each assessment carries a `governance` block with
  `provider = qwen-omi-analyst-v1`, `verdict = permit`, `model_revision = <sha>`,
  `prompt.source = registry`. The `suspicion_probability` equals the engine number (echoed).

## 7. Rollback (any one lever is sufficient, no redeploy needed for #1)

1. **Kill switch:** `OMI_ANALYST_ENABLED=false` → deterministic floor resumes immediately.
2. **Revision rollback:** re-pin `OMI_ANALYST_HF_REVISION` to the prior sha → restart.
3. **Schema/Governor guard (automatic):** any malformed or violating output is rejected and the
   floor is served — a bad revision cannot ship a malformed or ungoverned verdict.

Postgres/Supabase are never written by the Analyst layer, so no rollback can lose the system of
record.

## 8. Monitoring

- Watch the fallback-rate: a rising `provider = …->fallback:deterministic` share means the endpoint
  is flaky, slow, or emitting invalid JSON.
- Watch p95 latency vs `OMI_ANALYST_TIMEOUT_SECONDS`.
- Watch Governor `reject` rate on Qwen output (should be ~0; a spike means a prompt/model
  regression — roll back the revision).

## 9. Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `not_configured` | env not set / token missing | set the §2 vars; redeploy |
| `fallback_deterministic`, logs show timeout | endpoint cold / slow | raise timeout, keep the endpoint warm, or accept scale-to-zero cold starts |
| `fallback_deterministic`, `ProviderProtocolError` | model returned non-JSON | confirm `OMI_ANALYST_ENDPOINT_API` matches the container; check the prompt revision |
| `401/403` from endpoint | wrong/expired `HF_TOKEN` | rotate the read token |
| `messages` mode returns empty | endpoint is a raw `generate` container | switch `OMI_ANALYST_ENDPOINT_API=generate` or redeploy a chat container |
| Governor `reject` spike | prompt/model regression | roll back `OMI_ANALYST_HF_REVISION` |

## 10. Failure recovery

- The product is **always functional with the Analyst off or unreachable** — the deterministic
  floor is a complete, schema-valid, Governor-passed provider. There is no user-facing outage from
  an Analyst failure.
- To fully disable and investigate: `OMI_ANALYST_ENABLED=false`, then reproduce with
  `endpoint_smoke_test()` and `endpoint_health()` against the endpoint.

---

*Deployment is configuration only. No code change is required to activate the live Analyst; this
runbook and the verified code path are the deliverable.*
