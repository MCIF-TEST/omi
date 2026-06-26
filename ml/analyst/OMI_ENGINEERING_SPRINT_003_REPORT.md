# OMI_ENGINEERING_SPRINT_003 — AI Runtime Activation (report)

> **Engineering sprint.** The live Qwen endpoint is externally blocked (no GPU endpoint,
> no Render dashboard from this environment), so per the directive's IF-BLOCKED clause:
> **everything except the external dependency is implemented, tested, and left
> immediately activatable.** The mandatory Governor gate (deterministic, GPU-free) is the
> centerpiece — every live assessment is now Governor-validated with a Floor fallback.

## A. GitHub commits

One commit on `claude/stoic-edison-2ueecx`. Backend additive + minimal-surface edits to
the analyst seam; the frozen detection engine + scoring are untouched.

## B. Implemented & runtime-verified (no live endpoint needed)

| Capability | Where | Verified by |
|---|---|---|
| **Mandatory Governor gate on the live path** | `app/reasoning/analyst.py::_govern` | every `/analyst` assessment is bound (`app.evidence.Binder`) + validated (`app.governor.Governor`); PERMIT → ship, REJECT → deterministic Floor (re-validated) |
| **Governance reporting** (provider · verdict · latency · model revision · trace id) | `_govern` → `assessment["governance"]` → wrapper + UI | tests + the analyst panel renders it |
| **Inference health check / diagnostics** | `runtime_status()` + `GET /v1/investigations/analyst/status` | reports which links are configured/ready; **no secrets** (token presence is a bool) |
| **Timeout + retries + graceful fallback** | `QwenAnalystProvider` (config timeout, capped-backoff retries) | mocked-transport tests: retries N+1 times then falls back to the Floor |
| **Provider / latency / revision reporting** | governance block + `runtime_status` | tests assert presence + values |
| **Frontend exercises it** | `analyst-panel.tsx` | typecheck + build green; panel shows the assessment + "Governor permit" line |
| **Graceful degradation** | off-by-default; Floor backs every path; `_govern` never raises | full suite green with the feature off |

**Verified vs assumed (the live AI links):**

```
Render ─⚠️─ HF_TOKEN ─⚠️─ Hugging Face ─⚠️─ omi-analyst-v1 ─❌─ Qwen ─❌─ Inference ─✅─ Backend ─✅─ Governor ─✅─ Frontend ─✅─ UI
  operator env        operator env       repo exists        no live endpoint        all code-ready + tested (deterministic + fallback)
```
✅ implemented + tested · ⚠️ config-ready, operator must apply · ❌ blocked (no GPU endpoint). **The Backend→Governor→UI half is live and verified; the Render→Qwen→Inference half is code-complete and waiting on the endpoint.**

## C. Test results

- Backend: `pytest tests/ -q` → **787 passed** (was 780; **+7**), 0 regressions.
  - new `tests/test_analyst_runtime.py` (7): governance-on-permit, reject→Floor fallback,
    `runtime_status` (disabled + enabled), the status endpoint, Qwen retry-then-none, Qwen
    generate-falls-back.
- ml/ analyst impl: `pytest ml/analyst/test_omi_analyst.py -q` → **25 passed** (provider
  change is backward-compatible).
- Web: **typecheck** clean · **vitest** 23 passed · **production build** OK (26 pages).

## D. AI activation status & remaining blockers

**Status: code-complete, activation-ready, blocked only on external infrastructure.**
The Render blueprint already declares the env keys (Sprint 001); the Governor + Floor +
provider + diagnostics are implemented and tested. **Blockers:**
1. **No HF Inference Endpoint** serving the model (GPU) — the only true blocker.
2. **Render env not live-applied** (operator/dashboard action).
3. **No GPU/dashboard access from this environment** to perform (1)–(2).

### Exact operator actions to activate (then it's live)
1. **Deploy an HF Inference Endpoint** (GPU) for the base model
   `Qwen/Qwen3-4B-Thinking-2507-FP8` (V1 is base + prompt — `omi-analyst-v1` carries the
   card + `base_model` pointer, **no fine-tuned weights**, so serve the base model; the
   provider supplies the system prompt). Copy the endpoint URL.
2. On the **`omisphere-api`** Render service, set:
   `HF_TOKEN=<read token>`, `OMI_ANALYST_ENDPOINT_URL=<endpoint url>`,
   `OMI_ANALYST_ENABLED=true` (optional: `OMI_ANALYST_HF_REVISION`,
   `OMI_ANALYST_TIMEOUT_SECONDS`). The keys already exist in the **root** `render.yaml`
   (confirm the Render Blueprint points at the root file, not a stale copy).
3. **Verify:** `GET /v1/investigations/analyst/status` → `ready_for_live_qwen: true`;
   then `POST /v1/investigations/{slug}/analyst` → 202 → poll → 200 with
   `governance.provider` showing the Qwen path; the UI renders the assessment + Governor
   line.
4. **Rollback (instant):** set `OMI_ANALYST_ENABLED=false` (or clear
   `OMI_ANALYST_ENDPOINT_URL`) → reverts to the deterministic Floor; Governor + Floor stay.

## E. Recommendation for Sprint 004

Two parallel tracks:
- **Operator (out-of-band):** perform C-steps 1–2 to light up live Qwen; a short
  follow-up verifies the live link (the code + diagnostics are ready).
- **Engineering (GPU-free, in our control) — Sprint 004 = Orchestrator control-plane
  skeleton:** stand up the deterministic Reasoning Orchestrator (blackboard +
  `ReasoningContract` interfaces + Budget Controller, with the Floor as the only
  "module"), so the Analyst Council can be added module-by-module behind the
  already-live Governor gate. Persisting the `ValidationTrace` to a durable audit store is
  a natural adjacent task.

---

*Working software over documentation. No engine / scoring / OmiScore change; the analyst
stays off by default; the Governor is mandatory and the deterministic Floor backs every
path; best-effort writes stay SAVEPOINT-isolated. Gates green at commit time (787 backend
+ 25 ml + web typecheck/vitest/build). GitHub remains the source of truth; Hugging Face
remains the source of AI assets.*
