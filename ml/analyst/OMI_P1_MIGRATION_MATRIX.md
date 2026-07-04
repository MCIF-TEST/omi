# OmiSphere — P1 Investigation-Report Field Ownership & Migration Matrix

> **Status: AUDIT ONLY. No code changed, nothing committed, no migration performed.**
> This is the field-level ownership map for the investigation report UI and **the contract every
> future migration increment must honor**. For every field the report renders it records: the
> backend source, the file that computes it, the responsibility class, how it reaches the frontend,
> whether it should become AI-native under the approved architecture, and the dependencies gating
> that migration.

Verified against source on branch `claude/stoic-edison-2ueecx`:
`apps/web/app/(app)/investigations/[slug]/**`, `apps/web/app/(app)/investigate/**`,
`apps/web/components/shared/**`, `apps/api/app/routes/{investigations,reasoning,scan,intelligence}.py`,
`apps/api/app/orchestrator.py`, `app/detection/**`, `app/reasoning/**`,
`ml/analyst/omi_analyst/**`.

---

## 0. Responsibility classes (the legend for every row)

The brief lists five classes. The report actually has **seven distinct owners** — omitting the two
extra ones would make the contract wrong, so they are named explicitly:

| Class | Meaning | Where it originates |
|---|---|---|
| **DET-engine** | Deterministic backend computation | `app/detection/**`, `app/orchestrator.py`, `app/intelligence/**` |
| **DET-frontend** | Deterministic value **derived in TypeScript** from the payload (no backend field) | `synthesis.tsx` helpers |
| **Mistral** | Model-generated (the live HF analyst path) | `ml/analyst/omi_analyst` via `assess_payload` |
| **Governor** | Constitutional validation metadata | `app/governor/**` + `analyst.py::_attach_governance` |
| **Fallback** | Deterministic **floor** that impersonates the analyst schema when Mistral fails | `DeterministicAnalystProvider` |
| **Commentary** | Anthropic/template **prose** — the parallel AI surface | `reasoning/commentary.py` + `providers.py` |
| **Human** | Set manually by the analyst; authoritative by design | `routes/investigations.py` PATCH |

> Guardian §2 note: the **Human** verdict is not a defect to migrate — "the human analyst sets the
> final verdict" is a deliberate trust feature. The model provides a *recommended* verdict; the
> human's remains authoritative. It stays Human.

**How the three transports reach the browser (there are three, not one):**

1. `GET /v1/investigations/{slug}` → `InvestigationDetailResponse` → carries the **DET-engine**
   `payload` (`inv.payload_json`), the top-level scalars, the **Human** `verdict`/`notes`, and the
   stored **Commentary** columns. (`routes/investigations.py::_to_detail`.)
2. `POST /v1/investigations/{slug}/analyst` → `AnalystResponse` → the **Mistral / Governor /
   Fallback** assessment (cached under `payload_json["analyst_assessment_v1"]`; fetched by the panel,
   *not* read from `payload`). (`routes/reasoning.py`.)
3. `GET /v1/intelligence/account/{platform}/{id}` → `OmiScore` → the per-commenter **DET-engine**
   threat panel, fetched lazily per selected commenter. (`routes/intelligence.py`.)

---

## 1. Report surfaces (what renders where)

`investigations/[slug]/page.tsx` composes: the **header** (scalars) · **Human verdict widget** ·
**Omi Analyst panel** (Mistral) · **SavedInvestigationViewer** = `Synthesis` (verdict hero + trust
block + coordination) ‖ `CommenterList`/`CommenterDetail` ‖ `InsightsRail` (cross-links).
`commentary_text` is returned by the API but **no longer rendered on the investigation page**
(legacy — it is still rendered on the Account and Narrative pages).

---

## 2. THE MATRIX

### A · Report header + scalars — `page.tsx`

| Field | Class | Backend source / file | Reaches FE via | AI-native target | Dependencies |
|---|---|---|---|---|---|
| `overall_probability` | DET-engine | `orchestrator.py::_synthesize` (weighted combine) | GET `/{slug}` scalar + `payload` | **Stays sensor** (echoed by AI, moves only under C1-b) | P6 only |
| `overall_tier` | DET-engine | `orchestrator.py::_tier_for` | GET `/{slug}` scalar | Stays sensor | P6 only |
| `summary` | DET-engine | `orchestrator.py::_synthesize` (string builder) | GET `/{slug}` scalar | **AI-native** (model overall summary — stage 7) | P0→P5 |
| `batch_count`, `quota_used`, `created_at` | DET-engine | scan bookkeeping (`routes/scan.py`) | GET `/{slug}` scalar | Stays (operational metadata) | — |

### B · Human verdict block — `verdict-widget.tsx`

| Field | Class | Backend source / file | Reaches FE via | AI-native target | Dependencies |
|---|---|---|---|---|---|
| `verdict` (analyst verdict) | **Human** | `routes/investigations.py` PATCH → `Investigation.verdict` | GET `/{slug}`; written via PATCH | **Stays Human** (AI gives a *recommended* verdict in panel C; human's is authoritative) | — |
| `notes` (private) | **Human** | PATCH → `Investigation.notes` | GET `/{slug}` | Stays Human | — |

### C · Omi Analyst panel — `analyst-panel.tsx` (the one live model surface)

Fetched via `POST /{slug}/analyst`. When Mistral is unreachable (currently a 503), **every field
below is produced by the deterministic Floor instead** — same schema, `provider` shows `→ fallback`.

| Field | Class | Backend source / file | Reaches FE via | AI-native target | Dependencies |
|---|---|---|---|---|---|
| `verdict` (recommended) | Mistral / Fallback | `ml/analyst/omi_analyst/providers.py::QwenAnalystProvider` (floor: `DeterministicAnalystProvider::_verdict`) | POST `/{slug}/analyst` | **Already AI** — promote to primary | P0.1, P4 |
| `headline` | Mistral / Fallback | same | same | Already AI — promote | P0.1, P4 |
| `assessment` | Mistral / Fallback | same | same | Already AI — promote | P0.1, P4 |
| `evidence_for` / `evidence_against` | Mistral / Fallback | same | same | Already AI — promote | P0.1, P4 |
| `confidence_band` / `confidence_rationale` | Mistral / Fallback | same | same | Already AI | P0.1, P4 |
| `uncertainty` / `what_would_change_this` | Mistral / Fallback | same | same | Already AI | P0.1, P4 |
| `coordination_label` / `legitimate_hypothesis` / `supplemental_context` | Mistral / Fallback | same | same | Already AI | P0.1, P4 |
| `limits_statement` | Mistral / Fallback | same | same | Already AI | P0.1 |
| `suspicion_probability` / `suspicion_tier` | **DET-engine (echoed)** | echo-guard in `QwenAnalystProvider.generate`; contract `_DETERMINISTIC_ECHOED_FIELDS` | POST `/{slug}/analyst` | **Stays sensor unless C1-b chosen** | P6 |
| `governance.{verdict,provider,latency_ms,trace_id,violation_codes,model_revision}` | **Governor** | `governor/governor.py` + `analyst.py::_attach_governance` | POST `/{slug}/analyst` | **Stays Governor** (validates AI output) | — |
| `provider = "…->fallback:…"` | **Fallback** | `QwenAnalystProvider.generate` degrade path | POST `/{slug}/analyst` | **Stays Fallback** (safety floor retained) | — |

### D · Verdict hero + trust block — `synthesis.tsx`

| Field | Class | Backend source / file | Reaches FE via | AI-native target | Dependencies |
|---|---|---|---|---|---|
| ScoreRing value, tier badge | DET-engine | `overall_probability` / `overall_tier` (as A) | `payload` | Stays sensor | P6 |
| Hero `summary` | DET-engine | `_synthesize` | `payload` | **AI-native** (stage 7) | P0→P5 |
| **`confidence` (overall)** | **DET-frontend** | `synthesis.tsx::_overallConfidence` (mean of detector confidences) | derived in TS from `payload` | AI may re-express; number stays sensor | P1, P4 |
| **`result_state`** (coordination_found / organic / insufficient / incomplete) | **DET-frontend** | `synthesis.tsx::_resultState` | derived in TS | **AI-native** (model states the read) | P1, P4 |
| **`corroborated` badge** | **DET-frontend** | `synthesis.tsx` + `lib/api.ts::isCorroborated` | derived in TS from cluster methods | Interpretation → AI; the gate stays deterministic | P1, P4 |
| **`evidence_for` / `evidence_against`** (trust lists) | **DET-frontend** | `synthesis.tsx::_evidenceFor/_evidenceAgainst` (assembles cluster evidence, cross-links, reasons, weak_signals) | derived in TS | **AI-native** (this is exactly the model's job) | P1, P2, P4 |
| sampling disclosure | DET-frontend (static) | `synthesis.tsx` (commenter count) | derived in TS | Stays (honest caveat) | — |
| Stat strip: convergence, sources, commenters, fresh/cached | DET-engine | `cross_links`, `inputs_provided`, `video.*` | `payload` | Stays sensor | — |

### E · Coordination summary + rings — `synthesis.tsx`

| Field | Class | Backend source / file | Reaches FE via | AI-native target | Dependencies |
|---|---|---|---|---|---|
| `video.coordination_score` / `coordination_tier` | DET-engine | `detection/coordination/aggregate.py::aggregate_coordination` | `payload` | Stays sensor (the number); **reasoning → AI** (stage 5) | P1, P2 |
| `clusters[].{method,members,score,evidence,metadata}` | DET-engine | 6 detectors in `detection/coordination/**`; orchestrator Phase 3 | `payload` | **Stays sensor** (evidence); interpretation → AI | P1 |
| `thread_scan.{overall_probability,tier}` | DET-engine | `detection/engine.py::analyze_comments` | `payload` | Stays sensor; **comment analysis → AI** (stage 1) | P1, P2 |
| `tier_distribution` | DET-engine | `routes/scan.py:468` | `payload` | Stays sensor | — |
| `high_suspicion_handles` | DET-engine | `routes/scan.py:469` | `payload` | Stays sensor | — |

### F · Commenter list + detail — `commenter-list.tsx`, `commenter-detail.tsx`

| Field | Class | Backend source / file | Reaches FE via | AI-native target | Dependencies |
|---|---|---|---|---|---|
| `overall_probability` / `tier` / `confidence` (per commenter) | DET-engine | `detection/scoring.py::aggregate`, `_tier_for` | `payload.video.commenters[]` | Stays sensor | P6 |
| `coordination_adjusted_probability` | DET-engine | `orchestrator.py:571` (`apply_coordination`/`elevate.py`) | `payload` | Stays sensor | P6 |
| `signals[].{name,probability,confidence,evidence,supplemental}` | DET-engine | `detection/engine.py` + individual detectors | `payload` | **Stays sensor** (the raw evidence) | P1 |
| `contributions[].{name,impact,direction,headline}` | DET-engine | `detection/scoring.py` (`DetectorContribution`) | `payload` | Stays sensor | — |
| `intent_label` | DET-engine | `detection/scoring.py::_infer_intent` | `payload` | **AI-native** (account reasoning — stage 3) | P1, P2 |
| `reasons` | DET-engine | `detection/scoring.py::_extract_reasons` | `payload` | **AI-native** (stage 3) | P1, P2 |
| `coordination_evidence` | DET-engine | `orchestrator.py:572` (`build_coordination_signal`) | `payload` | Stays sensor | P1 |
| `weak_signals` | DET-engine | detectors / scoring | `payload` | Stays sensor (caveat) | — |
| `score_adjustments` | DET-engine | `scoring.py:235` + `coordination/elevate.py:200` | `payload` | Stays sensor (calibration narration) | — |
| `recent_activity[]` (comment history) | DET-engine (collector) | `routes/scan.py:203` `_activity_payload`; on-demand deep scan | `payload` + on-demand account scan | **Stays sensor** (evidence); **commenter-history *analysis* → AI** (stage 2) | P1, P2 |
| `matched_prior_neighbors` | DET-engine | `memory/prior.py::compute_memory_signal` (k-NN) | `payload` | Stays sensor (memory = context) | — |
| **OmiScore panel** (`ThreatBreakdown`) | DET-engine | `intelligence/omiscore.py` → `routes/intelligence.py` | separate GET `/v1/intelligence/account/{platform}/{id}` | Stays sensor (composed index) | — |

### G · Cross-links rail — `insights-rail.tsx`

| Field | Class | Backend source / file | Reaches FE via | AI-native target | Dependencies |
|---|---|---|---|---|---|
| `cross_links[].{kind,severity,summary,evidence,related_entities,metadata}` | DET-engine | `orchestrator.py::_compute_cross_links` | `payload.cross_links` | **Stays sensor** (link facts); the *narrative* over them → AI synthesis (stage 6) | P1, P5 |
| `focus_account.{handle,tier,summary,intent_label,reasons,confidence,from_cache,history_size}` | DET-engine | `orchestrator.py::scan_comprehensive` (focus block) | `payload.focus_account` | numbers stay sensor; `summary`/`intent`/`reasons` → **AI** (stage 3) | P1, P2 |

### H · Commentary (parallel AI surface — legacy on this page)

| Field | Class | Backend source / file | Reaches FE via | AI-native target | Dependencies |
|---|---|---|---|---|---|
| `commentary_text` / `commentary_provider` | **Commentary** | `reasoning/commentary.py::synthesize_commentary` → `providers.py` (Anthropic Haiku / template) | GET `/{slug}` (row column); **not rendered on the investigation page**; Account/Narrative pages render their own via `synthesize_account_analysis` / `synthesize_narrative_analysis` | **Collapse into the Mistral structured path — retire prose** (C4) | P2, P3 |

---

## 3. Migration verdict rollup

| AI-native target | Fields | Notes |
|---|---|---|
| **Already AI (deepen / promote to primary)** | all of panel **C** except the echoed pair | live model path; needs endpoint reliability + FPR gate |
| **Migrate to AI-native** | `summary`, `result_state`, trust-block `evidence_for/against`, `intent_label`, `reasons`, `coordination_label` reasoning, thread/comment analysis, narrative analysis, coordination reasoning, cross-link synthesis, `focus_account.summary/intent/reasons` | today DET-engine or DET-frontend |
| **Collapse & retire** | `commentary_*` (+ Account/Narrative prose) | replace with the Mistral structured assessments |
| **Stays sensor (evidence, never verdict)** | all probabilities/tiers/confidences, `signals`, `contributions`, `clusters`, `coordination_score`, `recent_activity`, `cross_links` facts, `matched_prior_neighbors`, OmiScore, `tier_distribution`, `high_suspicion_handles` | the numbers the AI echoes and reasons *from* |
| **Stays Governor / Fallback** | `governance.*`, the floor path | safety spine — preserved |
| **Stays Human** | `verdict`, `notes` | human sets the final verdict by design |

## 4. Dependencies (mapped to the approved P0–P6 roadmap)

Every migratable field inherits the same gate chain from `OMI_AI_NATIVE_BLUEPRINT.md`:

- **P0.1** endpoint reliability (503 fix) — gates *anything* becoming primary (panel C, all promotions).
- **P0.3** decisions **C1** (numeric authority), **C2** (package source), **C3** (fan-out budget).
- **P1** the per-stage **Evidence Bundle** for that field's grain must exist and be fed real evidence
  (resolves C5) — gates every "migrate to AI-native" row. Grains: comment (stage 1), commenter-history
  (stage 2), account (stage 3), narrative (stage 4), coordination/campaign (stage 5).
- **P2** run that stage in **shadow**; **control-FPR ≤ deterministic baseline** on the Gold Corpus —
  gates authority for any interpretive field.
- **P3** collapse the **Commentary** surface — gates the `commentary_*` retirement.
- **P4** promote the stage to **primary** in the UI (render model output; keep the sensor numbers beside it).
- **P5** model-native **synthesis + report restructure** — gates `summary`, cross-link synthesis, overall read.
- **P6** move **numeric authority** (the echoed `suspicion_probability`/`suspicion_tier`, `overall_*`) —
  last, only if C1-b is chosen, with the corroboration gate re-enforced inside the Governor.

**Cross-cutting on every promotion:** Governor mandatory · deterministic Floor retained ·
control-FPR non-regression.

---

## 5. Contract invariants (bind all future migration work)

1. A field marked **Stays sensor** must never be authored by the model without an explicit C1-b
   decision + P6; the AI **echoes and reasons from** it.
2. A field's UI transport must not silently change grain: panel C stays on `POST /{slug}/analyst`;
   `payload` fields stay on `GET /{slug}`; OmiScore stays on its own endpoint.
3. Retiring **Commentary** requires the replacing Mistral grain to have passed its P2 FPR gate first.
4. The **Human** verdict is never overwritten by the model; the model's verdict is *recommended* only.
5. The **Governor** and **Fallback** are preserved for every migrated field — no field becomes
   model-primary without the floor behind it.
6. `DET-frontend` fields (confidence, result_state, corroborated, trust-block evidence) migrate by
   moving the *derivation* into the model's structured output — the current TS derivation is the
   interim, not a second source of truth to keep in parallel.
