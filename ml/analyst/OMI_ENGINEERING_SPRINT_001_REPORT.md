# OMI_ENGINEERING_SPRINT_001 — Runtime Foundation (report)

> **Engineering sprint, not a design doc.** Working code committed; gates green. This
> records what was *implemented and verified* vs what *remains assumed/blocked*. Sprint
> goal: establish + verify the AI runtime foundation (Browser→…→Qwen→UI).

## A. Working implementation (committed)

| # | Change | Files |
|---|---|---|
| 1 | **One canonical `render.yaml`** — deleted the stale duplicate that auto-deployed from an abandoned session branch; folded its SMTP vars into root | `render.yaml`, **deleted** `infrastructure/render.yaml`, `docs/architecture.md` |
| 2 | **Analyst runtime env wired into the blueprint** — `OMI_ANALYST_ENABLED` (off), `OMI_ANALYST_ENDPOINT_URL`, `OMI_ANALYST_HF_REVISION`, `HF_TOKEN` (sync:false) + enable instructions | `render.yaml` |
| 3 | **Inference-pipeline fallback test** — Qwen endpoint unreachable → deterministic Floor, schema-valid, echo preserved | `apps/api/tests/test_reasoning_analyst.py` (+1 test) |
| 4 | **Frontend analyst UI** — the first consumer of the `/analyst` endpoint: POST → 202-poll → 200 render (verdict/tier/confidence, evidence for/against, uncertainty, what-would-change), 503-disabled handled gracefully | `apps/web/.../analyst-panel.tsx` (new), `lib/api.ts` (types), `.../page.tsx` (mount) |

**Gates:** backend `pytest tests/ -q` → **755 passed** (was 754). Web **typecheck** clean ·
**vitest** 23 passed · **production build** OK (26 pages, incl. `/investigations/[slug]`).

## B. Verification report — verified vs assumed (assumptions eliminated where possible)

| Component | Status | How |
|---|---|---|
| Repo hygiene / single render config | ✅ **VERIFIED** | duplicate removed (`git rm`); root is now the complete superset; doc updated |
| Analyst endpoint exists + gated (503 off) | ✅ **VERIFIED** | route `routes/reasoning.py:87`; `test_route_503_when_disabled` |
| Inference pipeline — fallback to Floor | ✅ **VERIFIED** | new `test_qwen_endpoint_unreachable_falls_back_to_deterministic` (green) |
| Error handling — never raises | ✅ **VERIFIED** | `test_assess_payload_never_raises_on_garbage` |
| Frontend exercises the endpoint | ✅ **VERIFIED** | new panel; typecheck/build/vitest green; endpoint now has a consumer |
| End-to-end **deterministic** path (Browser→…→Floor→UI) | ✅ **VERIFIED (build/type)** | the path is complete + type-safe + builds; the deterministic Floor backs it with the flag on and no endpoint |
| HF auth + `omi-analyst-v1` repo + `base_model` pointer | ✅ **VERIFIED** | live HF API (Phase 0), authenticated `Andrewexiga` |
| Render **live** env applied + Blueprint = root | ⚠️ **ASSUMPTION** | no dashboard access; config is correct in-repo, operator must apply |
| **Qwen live inference** (HF Inference Endpoint) | ❌ **BLOCKED** | no endpoint deployed; 4.4B FP8 needs a GPU endpoint; code path verified, live inference not |
| Live browser click-through vs a running deploy | ⚠️ **ASSUMPTION** | no running Render service reachable from this env |

## C. Runtime diagram (verified links)

```
Browser ─✅─ Frontend ─✅─ Backend ─✅─ /analyst route ─✅─ Analyst (deterministic Floor) ─✅─ UI
                                          │
                                          └─ Qwen path:
                                             Render env ─⚠️─ HF_TOKEN ─⚠️─ Hugging Face ─❌─ Qwen Inference Endpoint
                                             provider code ✅ · graceful fallback ✅ · LIVE inference ❌ (no endpoint)

   ✅ verified   ⚠️ config-ready, not live-applied (operator)   ❌ blocked (external infra: no GPU endpoint)
```

**The deterministic half of the sprint path is fully wired and verified.** The single
unverified link is **live Qwen inference**, blocked only on a deployed HF Inference
Endpoint + the Render env being applied — both operator/infra actions, not code.

## D. Remaining blockers

1. **No HF Inference Endpoint** serving `Andrewexiga/omi-analyst-v1` (GPU). *The* blocker
   for live Qwen inference. The model repo carries the card + `base_model` pointer but no
   weights (V1 by design); serving needs a deployed endpoint.
2. **Render env not live-applied:** operator must set `HF_TOKEN` + `OMI_ANALYST_ENDPOINT_URL`,
   flip `OMI_ANALYST_ENABLED=true`, and confirm the Render Blueprint points at the **root**
   `render.yaml`.
3. **No dashboard/GPU access from this environment** to perform or verify (1)–(2).

None block further engineering — the deterministic foundation is buildable now, and the
graceful fallback means the product is correct with the Qwen link still dark.

## E. Next engineering sprint recommendation

**Sprint 002 — Deterministic Foundation (Program Phase 3).** Build the Binder + normalized
**Evidence Bundle** → content-addressing/version-binding → the **Governor** (fold in
`schema_validate.py`) → audit ledger → harden the **Floor**. Rationale: it is **fully in
our control, GPU-free, unit-testable**, and is the critical-path foundation everything else
rides on — exactly the "deterministic before AI" order. Run the **HF Inference Endpoint +
Render env activation** (blockers D1–D2) as a **parallel operator task**; when it lands,
a short follow-up verifies the live Qwen link end-to-end.

---

*Working software over documentation. No engine/scoring/OmiScore change; the analyst stays
off by default with the deterministic Floor backing every assessment; best-effort writes
stay SAVEPOINT-isolated. Gates green at commit time.*
