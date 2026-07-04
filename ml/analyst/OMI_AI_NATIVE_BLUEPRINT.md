# OmiSphere — AI-Native Investigation Engine: Architecture Blueprint

> **Status: AUDIT ONLY. No code changed, nothing committed.** This is the engineering
> blueprint every future implementation increment follows. It documents the runtime as it
> *actually is* (verified against code), the desired AI-native end state, the exact places
> deterministic reasoning still decides, the exact place Mistral already reasons, the stages
> that must migrate, the dependency-ordered roadmap, the architectural conflicts that must be
> resolved first, and the safest migration order.

Verified against: `apps/api/app/orchestrator.py`, `app/detection/**`, `app/reasoning/**`,
`app/routes/**`, `ml/analyst/omi_analyst/**`, `apps/web/app/(app)/investigations/**`
(commit on branch `claude/stoic-edison-2ueecx`).

---

## 0. Executive summary (the one paragraph)

OmiSphere today is **deterministic-first with a single AI synthesis panel bolted on top**. The
deterministic engine *decides everything* — account authenticity, coordination, campaign
materialization, narrative inauthenticity, intent, cross-links, the overall verdict and summary.
Mistral runs **exactly once per investigation**, at the whole-investigation (`comment_section`)
grain, and it is constrained to **interpret** that evidence: by explicit *echo discipline* it may
generate prose/verdict-narrative but must copy the engine's `suspicion_probability` / `suspicion_tier`
verbatim. A **second, parallel AI surface** (Anthropic Haiku / template prose in
`app/reasoning/commentary.py`) still powers account and narrative "analysis." The desired end state
inverts this: deterministic systems become **sensors** (evidence collectors), and Mistral becomes
**the investigator** across seven stages, each consuming evidence and returning **structured JSON**
that the UI renders. The good news: the per-grain analyst capability (`assess_account`,
`assess_campaign`, `assess_narrative`, `summarize_investigation`) **already exists** in
`ml/analyst/omi_analyst/` — it is simply **not wired into production** and is **not yet fed real
per-stage evidence**. The migration is therefore mostly *evidence projection + wiring + live
validation*, not greenfield. Three hard conflicts gate it (numeric authority vs. echo discipline;
"HF is the runtime source" vs. the bundled-load reality; one-call-per-investigation vs. seven-stage
fan-out) and must be decided before any verdict authority moves.

---

## 1. Current runtime (verified)

### 1.1 Entry points (routes → engine)

| Route | Handler | Produces | AI? |
|---|---|---|---|
| `POST /v1/scan/*` (`routes/scan.py`) | `scan_comprehensive` → `scan_video_full` (`app/orchestrator.py`) | The full deterministic `Investigation.payload_json` | **Deterministic**; schedules the analyst via `maybe_autogenerate` (scan.py:1654) |
| `POST /v1/investigations/{slug}/analyst` (`routes/reasoning.py`) | `analyst.generate_and_persist` → `assess_payload` | Structured, Governor-validated assessment (cached on the row) | **Mistral** (the one real model path) |
| `POST /v1/investigations/{slug}/commentary` (`routes/reasoning.py`) | `synthesize_commentary` | Free-text paragraph | **Anthropic/template prose** (legacy on the investigation surface) |
| `POST /v1/accounts/{id}/analysis` (`routes/accounts.py:182`) | `synthesize_account_analysis` | Free-text account profile | **Anthropic/template prose** |
| `POST /v1/narratives/{id}/analysis` (`routes/narratives.py:133`) | `synthesize_narrative_analysis` | Free-text narrative assessment | **Anthropic/template prose** |

### 1.2 Current pipeline diagram

```
USER starts scan
      │
      ▼
Source (Twitter / YouTube)  ── app/integrations/{twitter,youtube}.py
      │  fetch profile, history, comments, engagers
      ▼
╔══════════════════════ DETERMINISTIC ENGINE (decides everything today) ══════════════════════╗
║  app/orchestrator.py :: scan_comprehensive / scan_video_full                                 ║
║   • per-commenter  → analyze_account (detectors) → scoring.aggregate → probability + TIER    ║
║   • memory prior   → fingerprint k-NN (app/memory)                                            ║
║   • thread scan    → analyze_comments                                                         ║
║   • coordination   → 6 detectors → aggregate_coordination → coordination_score + VERDICT      ║
║   • campaigns      → CampaignService.record_clusters (materialized, gated ≥0.5)               ║
║   • narratives     → NarrativeService.ingest (embeddings) → inauthenticity_score + label      ║
║   • cross-links    → _compute_cross_links   • matrix → _build_matrix                          ║
║   • SYNTHESIS      → _synthesize → overall_probability + overall_TIER + SUMMARY               ║
╚══════════════════════════════════════════════════════════════════════════════════════════════╝
      │  persists Investigation.payload_json   ── this IS the report content
      ▼
maybe_autogenerate(slug)  ── background, exactly-once (app/reasoning/analyst.py)
      │
      ▼
assess_payload(payload)                         ← ONE Mistral call, grain = comment_section
   ├─ load_ai_package()      (bundled prompts/knowledge/constitution, content-addressed)
   ├─ PromptBuilder.build_system(mode=registry|package)      ← prompt assembled from the package
   ├─ build_bundle(payload)  ← folds TOP-5 flagged commenters into descriptors, NO per-commenter call
   ├─ Orchestrator(judge=_AnalystJudge, floor=_AnalystFloor)
   │      └─ QwenAnalystProvider → RemoteReasoningProvider → HF endpoint (Mistral-7B)
   │             • on 503 / unreachable → DeterministicAnalystProvider (floor)
   │             • ECHO-GUARD: overwrites suspicion_probability/tier with the engine's numbers
   ├─ MANDATORY Governor (permit / reject → floor)
   └─ persist assessment on the row
      │
      ▼
WEBSITE  ── apps/web/investigations/[slug]/page.tsx
   • PRIMARY   : deterministic payload (VerdictWidget = human verdict + engine prob/tier;
                 SavedInvestigationViewer = commenters, clusters, matrix, synthesis)
   • SECONDARY : <AnalystPanel/> = the Mistral (or floor) structured assessment
   • Account page / Narrative page: Anthropic/template PROSE (separate surface)
```

### 1.3 The canonical AI package — where prompts actually live

`app/reasoning/package.py :: load_ai_package()` assembles the package from **bundled backend data**:
`app/reasoning/prompts/` (Prompt Registry: system + specialist prompts, Constitution, Specialist
Framework) and `app/reasoning/knowledge/` (Knowledge Library). It is content-addressed
(`package_hash = sha256(prompt_hash | framework_hash | knowledge_hash | constitution_hash)`), then
**published to HF `Andrewexiga/omi-analyst-v1` by a GitHub Action**. A drift guard proves the loaded
bundle is byte-identical to the published HF manifest.

> **Important reality check:** the runtime **loads the bundled copy, not HF, at request time**. HF is
> the *deployment mirror / distribution artifact*, not the runtime fetch source. This is deliberate
> (the always-on deterministic floor must not be coupled to HF availability). See Conflict C2.

---

## 2. Desired runtime (AI-native)

```
USER starts investigation
      │
      ▼
Source (Twitter/X, later YouTube, Reddit …)
      │
      ▼
╔══════════════════ DETERMINISTIC SYSTEMS = SENSORS (collect, never conclude) ══════════════════╗
║  metadata • behavioral evidence • comments • comment history • commenter profiles • network    ║
║  • graph relationships • coordination evidence • narrative evidence • fingerprints • temporal  ║
╚════════════════════════════════════════════════════════════════════════════════════════════════╝
      │
      ▼
EVIDENCE BUNDLE  (structured, PII-safe, per-stage projections)
      │
      ▼
PROMPT BUILDER  ── loads the AI package (system prompt + constitution + framework
      │             + specialist framework + knowledge library + schema + templates)
      │             and assembles: SYSTEM + CONSTITUTION + KNOWLEDGE + SPECIALIST + EVIDENCE
      ▼
INFERENCE ENDPOINT → MISTRAL performs ALL reasoning, per stage → STRUCTURED JSON
      │   (1) comment analysis      (2) commenter history      (3) account analysis
      │   (4) narrative analysis    (5) coordination reasoning
      │   (6) investigation synthesis   (7) overall summary
      ▼
GOVERNOR validation (mandatory) ──► deterministic floor on reject (safety net retained)
      ▼
WEBSITE renders the MODEL's structured output (not heuristic-generated conclusions)
```

Doctrine: *deterministic = sensors, Mistral = investigator.* Deterministic systems collect
structured evidence and stop deciding authenticity / coordination / commenter legitimacy /
narrative manipulation / campaign probability / behavioral reasoning. The Governor and the
deterministic floor are **preserved** as the safety spine.

---

## 3. Where deterministic reasoning still *decides* (must become a sensor)

Every row below is a **conclusion** the engine makes today that the desired architecture assigns to
Mistral. "Sensor-safe part" = the measurement that legitimately stays deterministic (the evidence).

| # | Decision made deterministically | Code | Sensor-safe part to keep |
|---|---|---|---|
| D1 | Account authenticity (probability + tier) | `detection/scoring.py::aggregate`, `_tier_for` | the detector sub-signals + evidence strings |
| D2 | Suspected intent | `scoring.py::_infer_intent` | the signals that imply intent |
| D3 | Coordination verdict + score | `detection/coordination/aggregate.py::aggregate_coordination` | the 6 detector findings + cluster memberships |
| D4 | Campaign materialization (is-a-campaign, gated ≥0.5) | `orchestrator.py` Phase 5.5 → `campaigns/service.py` | the cluster members + methods + texts |
| D5 | Narrative inauthenticity + coordination_label | `narrative/service.py`, `narrative/coordination.py` | message clusters, member/author counts, spread ratio |
| D6 | Cross-links + convergence | `orchestrator.py::_compute_cross_links` | the raw link facts (shared videos, style distance…) |
| D7 | Coordination matrix (account × detector) | `orchestrator.py::_build_matrix` | the detector-flag matrix (evidence) |
| D8 | **Overall verdict + summary** | `orchestrator.py::_synthesize` | the per-source numbers being combined |
| D9 | OmiScore | `intelligence/omiscore.py` | stays deterministic (an index, not a verdict) |
| D10 | Memory prior | `memory/prior.py` (k-NN) | stays deterministic (context, never proof) |
| D11 | Account / narrative **prose** (2nd AI surface) | `reasoning/commentary.py` + `reasoning/providers.py` (Anthropic/template) | the digest inputs only — the *prose itself* should move to the Mistral structured path |

> Note the doctrine line (Guardian §2 "evidence, not verdicts"): D9/D10 are *evidence*, not
> verdicts, and correctly stay deterministic. D1–D8 are the verdicts to migrate. D11 is a duplicate
> AI architecture to **collapse into** the Mistral path, not a deterministic decision.

---

## 4. Where Mistral already reasons

**One place, verified:** `app/reasoning/analyst.py :: assess_payload` → constitutional council
`Orchestrator` → `_AnalystJudge` → `QwenAnalystProvider` → `RemoteReasoningProvider` → HF Mistral-7B,
with a **mandatory Governor** and an always-on **deterministic floor** (`_AnalystFloor`).

- **Grain:** `comment_section` (the whole investigation), **one model call per investigation**
  (exactly-once via `_autogen_inflight` + on-row cache).
- **Model-generated fields** (`_MODEL_GENERATED_FIELDS`): `verdict`, `confidence_band`,
  `confidence_rationale`, `headline`, `assessment`, `evidence_for`, `evidence_against`,
  `uncertainty`, `what_would_change_this`, `limits_statement`, `coordination_label`,
  `legitimate_hypothesis`, `supplemental_context`.
- **Echoed from the engine, never model-authored** (`_DETERMINISTIC_ECHOED_FIELDS` + the
  `QwenAnalystProvider` echo-guard): `suspicion_probability`, `suspicion_tier`.
- **Flag-gated OFF by default** (`analyst_enabled=False`); requires `OMI_ANALYST_ENDPOINT_URL` +
  `HF_TOKEN`; degrades to the deterministic floor when the endpoint is unreachable (currently a 503
  cold-start situation).
- **Prompt assembly:** `PromptBuilder.build_system(mode=registry|package)`. `registry` (default) =
  base prompt only (byte-identical to legacy). `package` = base + Constitution + Knowledge Library
  (built, but gated behind a live-endpoint control-FPR check before it can become default).

**Latent capability (already implemented, NOT wired):** `ml/analyst/omi_analyst/analyst.py` exposes
`assess_account`, `assess_campaign`, `assess_narrative`, `summarize_investigation`, each with its own
Evidence Bundle projection (`project_*_bundle`) and schema-valid output. Production never calls these
— it only calls `assess()` on a folded `comment_section` bundle. **This is the single biggest lever
in the migration: the per-stage investigator mostly exists; it needs evidence + wiring + validation.**

---

## 5. Investigation stages that must migrate to Mistral

| Stage | Today | Target evidence source (sensor) | ml/ capability status |
|---|---|---|---|
| 1. Comment analysis | none (raw comments never reach the model) | thread comments, per-comment features | **missing** — new grain + bundle + specialist |
| 2. Commenter history analysis | deterministic per-account scoring | commenter post history, temporal, fingerprint | **missing** grain; `project_account_bundle` is close |
| 3. Account analysis | deterministic (D1) + Anthropic prose (D11) | account detectors, memory neighbors, trend | **exists** `assess_account` (unwired) |
| 4. Narrative analysis | deterministic (D5) + Anthropic prose (D11) | narrative message clusters, spread, authorship | **exists** `assess_narrative` (unwired) |
| 5. Coordination reasoning | deterministic (D3/D4) | 6-detector findings, clusters, campaign members | **exists** `assess_campaign` (unwired) |
| 6. Investigation synthesis | deterministic (D8) + the ONE Mistral call | the per-stage model assessments (components) | **partial** `summarize_investigation` folds descriptors, not real sub-assessments |
| 7. Overall summary | deterministic (`_synthesize` summary) | same as synthesis | rolled into (6) |

Each target stage must "consume evidence and return structured JSON" (per the brief) and the UI must
render that JSON.

---

## 6. Architectural conflicts (resolve BEFORE building)

**C1 — Numeric authority vs. echo discipline (the central tension).**
The desired doctrine says deterministic systems must *not* decide account authenticity, coordination,
or campaign probability. But today's entire trust model (Guardian §2 "evidence, not verdicts", §3
precision discipline / corroboration gate / control-FPR) is enforced **on the deterministic number**,
and the model is *forbidden* from moving it (echo-guard). Moving the number itself to the model
removes the deterministic guarantee and makes the platform's precision frontier depend on model
behavior. **Decision required:** does Mistral (a) author qualitative verdicts while the engine keeps
authoring the numbers (keeps echo discipline, safest), or (b) author the numbers too — in which case
the corroboration gate + FPR guarantees must be re-established *inside the Governor* around a
non-deterministic core, with the deterministic floor retained as fallback. This is the riskiest move
and belongs **last**.

**C2 — "HF is the runtime source" vs. bundled-load reality.**
The brief states the runtime source is the HF repository and the Prompt Builder loads the AI package
from HF. The code deliberately does the opposite: it loads a **bundled copy** and only *publishes* to
HF (drift-guarded), so the always-on floor never depends on HF uptime. **Decision required:** keep
the bundled-load design (recommended — availability) and treat "HF is canonical" as *provenance*
(the drift guard already proves parity), OR add an explicit runtime HF-fetch mode with a bundled
fallback. Do not silently assume a per-request HF fetch exists — it does not.

**C3 — One call per investigation vs. seven-stage fan-out.**
Today's cost/latency budget is one HF call per investigation (`_autogen_inflight`). Seven stages,
some fanning out per-commenter and per-cluster, multiply calls, latency, token spend, rate limits,
and cold-start 503 exposure. **Decision required:** a fan-out + batching + per-stage caching strategy
(and a concurrency model) before per-stage reasoning goes live.

**C4 — Two parallel AI architectures.**
The Mistral/council structured path and the Anthropic/template prose path (`commentary.py`) coexist;
account + narrative "analysis" still run on the prose path. (The Phase-B doc claimed the commentary
surface was retired — it is not; `accounts.py` and `narratives.py` still call it.) The single-surface
goal requires **collapsing the prose surfaces into the Mistral structured path**, not maintaining
both.

**C5 — Evidence the model never receives.**
`build_bundle` folds only the top-5 flagged commenters into compact descriptors with **no
per-commenter evidence** and never passes raw comments, per-commenter history, profiles, or graph
edges. The desired per-stage evidence (comment history, commenter profiles, network/graph, temporal,
fingerprints) is **collected but not projected** to the model. Evidence projection is the true
prerequisite for every stage — you cannot have the model reason over evidence it never sees.

**C6 — Endpoint reliability becomes a hard dependency.**
Today the model is *optional* (endpoint unset / 503 → deterministic floor, and the product still
works). Making Mistral the **primary** investigator makes endpoint availability load-bearing. The
current live endpoint returns **HTTP 503** (cold-start / scale-to-zero) and falls back. Reliability
(min-replica / keep-warm / a dependable inference path) must be solved before "primary," and the
floor must remain the fallback.

**C7 — Data-grain mismatch (Guardian §1).**
Narratives = *message* clusters; Campaigns = *account* clusters; Coordination persists as pairwise
edges + a scalar. The Mistral stages must respect these grains (a narrative assessment ≠ an account
assessment ≠ a campaign assessment) — the `project_*_bundle` split already encodes this and must be
honored, not flattened.

---

## 7. Migration roadmap (dependency-ordered)

Each phase: **precondition → change → validation gate.** Nothing is a "redesign" here — this is the
sequence, not an instruction to build now.

**Phase 0 — Unblock & decide (must be first).**
- P0.1 **Endpoint reliability** — resolve the 503 (keep-warm / min-replica / reliable inference).
  Gate: `analyst/audit` shows `model_backed=true` consistently.
- P0.2 **Forensic capture live** — HF REQUEST/RESPONSE on every call *(shipped)*.
- P0.3 **Decide C1, C2, C3** — written architectural decisions (authority model, package source,
  fan-out budget). Gate: signed-off decisions recorded.

**Phase 1 — Evidence layer (make deterministic a sensor; additive, no verdict moves).**
- P1.1 Define per-stage **Evidence Bundles** (comment, commenter-history, account, narrative,
  coordination) — PII-safe, structured, content-addressed. Extend the existing `project_*_bundle`.
- P1.2 **Evidence-collection completeness** — ensure the collectors persist what each stage needs
  (comments = Content DB; history/fingerprints = memory; graph = GraphStore; campaigns; narratives).
  Map and fill gaps (resolves C5). Gate: each bundle validates + is reproducible; no verdict yet.

**Phase 2 — Per-stage model reasoning in SHADOW (non-authoritative).**
- P2.1 Wire `assess_account`, `assess_narrative`, `assess_campaign` (already in `ml/`) into a shadow
  path that stores output without rendering it authoritative (reuse `app/reasoning/shadow`).
- P2.2 Add the two missing grains — **comment analysis** + **commenter history** (new bundle +
  specialist prompt + schema).
  Gate: per-stage **control-FPR ≤ deterministic baseline** on the Gold Corpus; Governor permit-rate
  healthy (Guardian §3).

**Phase 3 — Collapse the parallel Anthropic prose surface (resolves C4).**
- P3.1 Replace `synthesize_account_analysis` / `synthesize_narrative_analysis` with the Mistral
  structured assessments (account / narrative grains) rendered in the UI; retire those prose paths.
  Gate: UI renders model structured output for account + narrative; prose surface removed; suite green.

**Phase 4 — Promote qualitative stages to PRIMARY (per stage, gated).**
- P4.1 Flip `analyst_prompt_assembly=package` (already built) once live FPR passes.
- P4.2 Render the model's structured assessment as the **primary** per-stage content (engine numbers
  shown as evidence beside it). Gate: live A/B, control-FPR non-regression, Governor mandatory.

**Phase 5 — Model-native synthesis + report restructure.**
- P5.1 `summarize_investigation` consumes the **per-stage model assessments** (real components), not
  folded descriptors → true cross-stage synthesis.
- P5.2 Report restructure (Behavioral / Coordination / Narrative / Authenticity / Alternative-
  Explanations sections from model fields — the Phase-B "next increment").
  Gate: end-to-end model-primary report; deterministic floor still present.

**Phase 6 — (Optional, LAST) move numeric authority (resolves C1 option b).**
- P6.1 Only if chosen: let the model author the numbers, with the corroboration gate + FPR guarantees
  re-established **inside the Governor** and the deterministic floor retained. Gate: extensive live
  validation; control-FPR provably non-regressed.

---

## 8. Dependency graph (what must precede each migration)

```
P0.1 endpoint reliability ─┐
P0.3 decisions (C1/C2/C3) ─┼─► P1 evidence bundles ─► P2 per-stage SHADOW ─┬─► P3 collapse prose
P0.2 forensic capture ─────┘        (resolves C5)      (FPR gate)          │
                                                                            └─► P4 promote qualitative
                                                                                        │
                                                                                        ▼
                                                                            P5 synthesis + report
                                                                                        │
                                                                                        ▼
                                                                            P6 numeric authority (last)

CROSS-CUTTING GATES on every promotion:  Governor (mandatory)  •  deterministic Floor (retained)
                                         •  control-FPR non-regression on the Gold Corpus
```

Hard edges: **no stage reasons before its evidence bundle exists (P1)**; **no stage is authoritative
before its shadow FPR passes (P2)**; **nothing is "primary" before the endpoint is reliable (P0.1)**;
**numeric authority (P6) is last** because it removes the deterministic guarantee that everything else
still leans on.

---

## 9. Safest migration order (one line)

**Fix the endpoint → build per-stage evidence bundles (turn deterministic into sensors) → run each
Mistral stage in shadow → validate control-FPR ≤ baseline → collapse the Anthropic prose surface →
promote qualitative stages to primary → model-native synthesis + report → (optionally, last) move the
numbers, with the Governor enforcing the corroboration gate and the deterministic floor retained.**
Never move a verdict before its evidence exists, its FPR is measured, and the floor still catches
failures.

---

## 10. What already exists in our favor (de-risks the build)

- The **per-grain investigator** (`assess_account/campaign/narrative/summarize_investigation`) and its
  **Evidence Bundle projections** are implemented in `ml/analyst/omi_analyst/` — unwired, not absent.
- The **Governor** (mandatory) and **deterministic floor** are already the spine of `assess_payload`.
- The **Prompt Builder** already assembles from the package (registry/package modes) and is
  content-addressed; `package` mode is built and waiting on a live FPR gate.
- The **AI package** is canonical + drift-guarded against HF; `package_hash` gives one-field
  reproducibility.
- The **forensic audit** endpoint (`/analyst/audit`) + **live forensic capture** already prove each
  runtime stage — the instrument to validate every promotion is shipped.
- The **shadow council** (`app/reasoning/shadow`) already exists as the non-authoritative comparison
  harness for Phase 2.

*The AI-native runtime is ~60% latent in the codebase; the migration is evidence-projection + wiring
+ live validation + governance, not a rewrite. The deterministic engine is not deleted — it is
demoted from judge to sensor, and kept as the floor.*
