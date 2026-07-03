# Omi — Investigation Runtime Architecture (audit, target, plan)

> **Runtime Architecture Refactor.** Establish the long-term production architecture: the AI
> investigation pipeline as the primary **reasoning/interpretation** layer, with the deterministic
> investigation engine as the **authoritative source of truth** for all measurable signals. The AI
> reasons *from* deterministic evidence; it never replaces detection, moves a score, or bypasses the
> Governor. This document is grounded in the current code, not historical intent.

---

## 1. Current runtime (as built)

```
User → POST /v1/scan/link/start → async worker (background pool)
  │
  ├─ DETERMINISTIC ENGINE  ── AUTHORITATIVE, source of truth ──────────────────────────────
  │    platform metadata → commenter/account scans → coordination detectors
  │    (temporal_semantic · fingerprint_cluster · age_cohort · style_match · co_engagement ·
  │     co_tag → aggregate_coordination, corroboration-gated) → narratives → campaigns →
  │    content intelligence → cross-links → convergence → OmiScore
  │      → persist Investigation.payload_json
  │
  └─ analyst.maybe_autogenerate()  [Sprint just prior] → background, exactly-once:
        assess_payload → Evidence Bundle (Binder) → Prompt Registry (in-app, omi_analyst v1,
          content-hashed) → Institutional Memory (prior_context) → RemoteReasoningProvider
          → HF Mistral-7B → structured JSON → MANDATORY Governor → deterministic Floor on reject
          → cache on the investigation row  (+ metrics block, this sprint)

REPORT renders TWO AI outputs:
   • AnalystPanel   → structured governed assessment    [model_providers → HF/Mistral]  (auto-loads)
   • CommentaryBlock → free-text narrative               [providers → Anthropic/template]  ← 2nd path

OFF THE USER PATH:
   • Shadow council (admin-only): runs BOTH councils (deterministic + AI) WITH the Context Builder,
     institutional-memory retrieval, and specialists — for evaluation/comparison only.
   • Specialist Framework (13 specialists) + Knowledge Library (33 entries): catalogued,
     content-hashed, published to HF — but INERT (not on the production path).
```

**Diagnosis.** The deterministic engine and the single governed inference are correctly placed and
now correctly wired (one investigation → one HF inference → Governor → report). Three things diverge
from the target: (a) a **second AI surface/provider** (commentary, Anthropic) sits beside the
governed analyst; (b) the **Context Builder + Specialist Framework** live only in the shadow/eval
path, not on the production inference they were designed for; (c) the **HF package** is a
drift-guarded published *mirror*, not the runtime source.

## 2. Proposed target runtime

```
User → investigation
  → Platform metadata
  → DETERMINISTIC ENGINE (unchanged, authoritative) — behavioral · graph · narrative · coordination
  → Evidence aggregation → ONE Evidence Bundle (Binder, immutable citable ids)
  → Institutional Memory retrieval (prior_context — background, never proof)
  → Context Builder            ← PROMOTED to production (structures evidence for the model)
  → Prompt Registry + Specialist Framework  ← resolved from the in-app registry that is the
                                               published, drift-guarded twin of the HF package
  → ONE prompt assembly
  → ONE HF Mistral inference (RemoteReasoningProvider)
  → structured JSON → MANDATORY Governor → (deterministic Floor on reject/outage)
  → persist → ONE report (single governed AI surface)
  Invariants preserved: deterministic Floor always-on · Governor never skipped · echo discipline ·
  exactly-one inference · full explainability · reproducible (content-hashed prompt + pinned model).
```

## 3. Subsystem placement (BEFORE / INSIDE / AFTER / REMOVE)

| Subsystem | Placement | Verdict |
|---|---|---|
| Platform metadata, commenter/account scans | BEFORE AI | keep |
| Coordination detectors + corroboration gate | BEFORE AI | keep — authoritative |
| Narrative / campaign / content intelligence | BEFORE AI | keep |
| OmiScore intelligence layer | BEFORE AI | keep (never touched by AI) |
| Evidence aggregation → Evidence Bundle | BEFORE AI | keep — the ONE bundle |
| Institutional Memory retrieval | BEFORE AI | keep (prior_context) |
| **Context Builder** | INSIDE AI | **promote** from shadow → production |
| Prompt Registry / Specialist Framework / Knowledge | INSIDE AI | keep in-app; HF = canonical mirror |
| Mistral inference (RemoteReasoningProvider) | INSIDE AI | keep — the ONE model call |
| Governor | AFTER AI | keep — mandatory, unchanged |
| Persist + report render | AFTER AI | keep |
| Deterministic Floor | AFTER AI | keep — always-on fallback |
| **Commentary (Anthropic) + `providers.py`** | REMOVE / CONSOLIDATE | **fork — needs a decision** |
| Shadow council | offline eval, off user path | keep as eval harness |

## 4. Duplication / obsolescence found

1. **Two provider abstractions, two AI surfaces.** `app.reasoning.model_providers`
   (RemoteReasoningProvider → HF/Mistral, governed) vs `app.reasoning.providers` (LLMProvider →
   Anthropic/template, free-text commentary + account/narrative analysis). The report shows both.
   Target: one governed surface; retire the second path (fork).
2. **Context Builder + Specialist Framework are shadow/inert.** Built and hashed, but the production
   inference uses the ml/ projection + the single OMI ANALYST judge. Target: promote onto the live path.
3. **HF package is a mirror, not the runtime source** (by deliberate GitHub-source-of-truth design).
   The charter asks for HF "canonical" — see the fork in §6.

## 5. Implemented this sprint (safe, additive, no decision required)

Delivering the charter's **measurement** mandate without destabilizing the runtime I just spent
three sprints stabilizing:

- **Per-investigation metrics** (`assess_payload` → `assessment.metrics`): `total_reasoning_ms`,
  `model_ms`, `governor_and_assembly_ms`, `memory_store_ms`, `memory_durable`, `model_backed`,
  `est_completion_tokens` + `est_completion_cost_usd` (clearly labeled char/4 estimate; authoritative
  token usage is endpoint-side — Phase 2), and the content-hashed `prompt_version`/`prompt_hash`.
- **Cache effectiveness** (`analyst.runtime_metrics()`): process-lifetime `generated` vs
  `served_from_cache` + `hit_rate`, surfaced on `GET /v1/investigations/analyst/integrity`.
- **Config**: `OMI_ANALYST_COST_PER_1K_TOKENS_USD` (0.0 → cost reported null, no guess).
- Tokens/latency/governor overhead also emitted to the Render log per assessment.
- Tests: `tests/test_runtime_metrics.py` (5). Metrics never alter the assessment, the Governor, or
  the floor (asserted).

This is instrumentation only — zero change to detection, scoring, OmiScore, the Governor, the
Prompt Registry, or the model call.

## 6. Open architectural forks (need an explicit decision before I refactor a live runtime)

I did **not** execute these — they are destructive and/or conflict with a standing invariant, so
they need your call (I attempted to ask; the picker failed on a container restart). My recommendation
is first each time.

1. **HF role.** *Recommended: keep GitHub as source-of-truth with HF as the canonical, CI
   drift-guarded published mirror* (the app resolves prompts/framework from the in-repo registry that
   is published to — and verified byte-identical against — the HF package). The alternative,
   *loading the Prompt Registry from HF at runtime*, makes HF a hard per-investigation dependency
   (an HF outage would degrade every investigation) and **cannot be built or verified in this
   environment** (egress to huggingface.co is blocked). If you want it, I'd implement a **fetch-at-boot
   with the in-repo registry as the always-on fallback** — never a per-request HF fetch.
2. **Reasoning depth.** *Recommended: promote the Context Builder + Specialist Framework to shape the
   ONE production prompt* (matches the target flow, preserves one inference). Alternatives: keep the
   single judge (minimal), or activate all 13 specialists per investigation (many calls / huge prompt
   — conflicts with "one inference"; not recommended).
3. **Commentary.** *Recommended: consolidate to the one governed analyst and retire the separate
   Anthropic commentary path* (one report, one AI surface, removes the second provider abstraction).
   Destructive — it removes a shipped feature; hence the decision gate.

## 7. Remaining improvements before production maturity

- **Persistent database** (still the #1 blocker): sqlite on Render's ephemeral disk loses users +
  investigations (and cached assessments) on every redeploy. Move `OMI_DATABASE_URL` to Postgres.
- **Authoritative token/cost**: capture the endpoint's `usage` object in RemoteReasoningProvider and
  thread it into `metrics` (replaces the char/4 estimate).
- **Live-endpoint verification**: run the end-to-end proof against the real HF endpoint (not
  possible from this sandbox — egress blocked; operator-run with the env set).
- Execute the §6 forks once decided, then re-verify one-investigation-one-inference end-to-end.

---

*This sprint: audit + target design + safe instrumentation only. Deterministic evidence generation,
the mandatory Governor, explainability, and reproducibility are all preserved. The structural
refactors in §6 await an explicit decision.*
