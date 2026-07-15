# OmiSphere AI Analyst — Program Log & Session Handoff

> **Living document.** This is the single source of continuity for the OmiSphere AI Analyst
> provider-independence program. Any Claude Code session can read this file and pick up exactly
> where the last one left off. **Whoever works on this program MUST update this file as part of
> every change** (new phase, new commit, new decision, new finding) — keep the *Status*, *Changelog*,
> and *Next step* sections current.

- **Last updated:** 2026-07-15 — after Phase 3A (evidence-semantics audit)
- **Working branch:** `claude/stoic-edison-2ueecx`
- **Pull request:** draft **PR #82** (`mcif-test/omi`), base `main` — covers Phases 0–2
- **Verify command:** `cd apps/api && python -m pytest tests/ -q`
- **Latest green suite:** **1318 passed, 1 warning** (the warning is a pre-existing Starlette/httpx deprecation, unrelated)

---

## 0. Quick start for a new session

1. `git checkout claude/stoic-edison-2ueecx && git pull`
2. Read this file top-to-bottom, then the **Next step** section.
3. Before changing anything, run the verify command and confirm the green baseline.
4. Respect the **Locked invariants** and **Working rules** sections below.
5. When you finish work, **update this file** (Status table, Changelog, Next step) and commit it with your change.

---

## 1. What this program is

Evolve OmiSphere's AI Analyst into a **provider-independent, evidence-owning** system:

- **Omi owns:** evidence collection, deterministic detectors/measurements, EvidenceRepository, Snapshot,
  InvestigationComposer, immutable InvestigationPackage, the analytical **doctrine / system instructions**,
  the canonical **ComprehensiveAssessment output contract**, validation/Governor, persistence, website.
- **The provider (OpenRouter, or Hugging Face today) is transport only** — it routes to a model that
  performs **exactly ONE comprehensive inference** and returns one canonical assessment.
- **One investigation = one primary model inference.** Six analytical domains are reasoning lenses
  *inside* that one inference, plus a Lead-Investigator synthesis.

### Production reasoning pipeline (current)
```
scan → EvidenceRepository.snapshot (es:) → InvestigationComposer.compose → InvestigationPackage (ipkg:)
     → investigation_render (alias + dedup + coverage budget) → build_comprehensive_investigation_prompt_package
     → pp.system (compiled Master Analyst Protocol) + pp.user (Investigation Package evidence)
     → run_stage_inference → _reasoning_transport (HF _qwen_transport | _openrouter_transport)  ← ONE inference
     → _adjudicate: canonical-schema validate → overlay Omi-owned fields from Floor → Governor
     → persist analyst_assessment_v1 → API → website (analyst-panel.tsx)
```

---

## 2. Phase status

| Phase | Title | Status | Commit |
|---|---|---|---|
| 0 | Provenance & instruction-content propagation proof | ✅ done | `19e8491` |
| 1 | ONE canonical ComprehensiveAssessment output contract | ✅ done | `9b17401` |
| 2 | OpenRouter preset-based ReasoningProvider (behind the seam) | ✅ done | `c6981ea` |
| 3A | Master Analyst Protocol evidence-semantics audit (read-only) | ✅ done | (this log) |
| 3B | Author & wire Master Analyst Protocol v1 | ⬜ **NOT STARTED** | — |
| later | Deploy OpenRouter preset + select model + production cutover | ⬜ not started | — |
| later | Model benchmarking (same package/instructions across models) | ⬜ not started | — |

---

## 3. Key files (the map)

**Reasoning / provider**
- `apps/api/app/reasoning/analyst.py` — `_assess_core` (the ONE production path), `_reasoning_transport`
  (provider dispatch), `_qwen_transport` (HF), `_openrouter_transport`, `reasoning_provider*`,
  `field_provenance()` (model vs Omi ownership), `investigation_trace` (forensics).
- `apps/api/app/reasoning/runtime.py` — `run_stage_inference` / `infer` / `_adjudicate` / `_canonical_candidate`
  (canonical validation + Floor overlay + Governor). Provider-agnostic adjudication.
- `apps/api/app/reasoning/model_providers/` — `base.py` (ReasoningProvider protocol + DTOs + typed errors),
  `remote.py` (HF, **untouched by Phase 2**), `openrouter.py` (Phase 2), `config.py`, `mock.py`.
- `apps/api/app/reasoning/prompts/master_protocol.py` — the repository-owned Master Analyst Protocol
  (compiled system == `pp.system`, hash == `system_prompt_sha`; what a preset must contain).
- `apps/api/app/reasoning/prompt/stage_builder.py` — `assemble_stage_system` (the 6-block system assembly),
  `build_prompt`.

**Instruction assets (compile into the Master Analyst Protocol)**
- `apps/api/app/reasoning/prompts/_assets/omi_analyst_v1.txt` — base identity + 10 absolute rules.
- `apps/api/app/reasoning/prompts/constitution.py` — 12 constitutional blocks.
- `apps/api/app/reasoning/prompts/framework.py` — specialist-council catalog (injected as JSON; **candidate to remove from the prompt** — see Phase 3A §7).
- `apps/api/app/reasoning/knowledge/` — knowledge library (top 12 entries).
- `apps/api/app/reasoning/prompts/comprehensive_investigation_template.py` — comprehensive task,
  **canonical schema** (`comprehensive_investigation_canonical_schema()`), schema-derived output contract.

**Evidence (what the model sees)**
- `apps/api/app/reasoning/evidence_bundles.py` — the 7 immutable bundles + every model-visible field dataclass.
- `apps/api/app/reasoning/investigation_render/render.py` — projects the package into the 9 model-facing sections.
- `apps/api/app/reasoning/investigation_composer.py` — InvestigationPackage + evidence_index (citable ids).
- `apps/api/app/reasoning/context/investigation.py` — InvestigationContext (upstream field semantics).
- `apps/api/app/detection/scoring.py` — `overall_probability`, `single_axis_capped`, convergence, `logit_delta`, `decorrelation_factor`.
- `apps/api/app/detection/coordination/aggregate.py` — `DISCRIMINATIVE_DETECTORS`, corroboration gate.
- `apps/api/app/intelligence/omiscore.py` — `omi_score` / `authenticity_score`.

**Output contract / validation**
- `ml/analyst/analyst_response_schema.json` — the wrapper schema the canonical schema derives from.
- `apps/api/app/governor/comprehensive.py` — `validate_comprehensive_model_output` (canonical parser),
  `validate_comprehensive_sections`.
- `apps/api/app/governor/governor.py` — the Governor.

**Frontend (do not change without explicit approval)**
- `apps/web/app/(app)/investigations/[slug]/analyst-panel.tsx` — consumes the wrapper + 6 `*_reasoning` sections.

**Tests (provenance / contract / provider)**
- `apps/api/tests/test_instruction_provenance.py` (Phase 0), `test_comprehensive_contract.py` (Phase 1),
  `test_openrouter_provider.py` (Phase 2), `test_one_inference_invariant.py`, `test_comprehensive_cutover.py`.

---

## 4. Phase detail (what shipped)

### Phase 0 — provenance (`19e8491`)
Executable proof that the compiled instruction TEXT reaches the provider request (not just a hash):
`tests/test_instruction_provenance.py` (asset content → `PromptPackage.system/.user` → `ReasoningRequest`
at the provider boundary; source-change → hash/id change; determinism). Added additive trace field
`investigation_trace.compiled_system_instruction_hash` (= `pp.manifest["system_prompt_sha"]`).

### Phase 1 — ONE canonical output contract (`9b17401`)
Resolved the contradiction where the wrapper schema required the model to fabricate Omi provenance while
forbidding the six reasoning domains. One canonical schema derived from `analyst_response_schema.json` with
the **6 domains as first-class REQUIRED properties**; the model-facing OUTPUT CONTRACT is **rendered
deterministically from the schema** (no drift). The runtime validates the model's full output against it and
**overlays Omi-owned fields from the Floor after validation** (`_canonical_candidate`). Missing/empty/malformed
domain → deterministic Floor (no repair inference). `tests/test_comprehensive_contract.py`.

### Phase 2 — OpenRouter provider (`c6981ea`)
OpenRouter added behind the existing `ReasoningProvider` seam (selection is configuration):
- Config: `OMI_ANALYST_PROVIDER` (default `huggingface`), `OMI_OPENROUTER_PRESET`, `OMI_OPENROUTER_MODEL`,
  `OMI_OPENROUTER_BASE_URL`, `OMI_OPENROUTER_STRUCTURED_OUTPUT`, `OMI_OPENROUTER_REFERER/TITLE`.
  **`OPENROUTER_API_KEY` is env-only, never a settings field, never persisted.**
- `OpenRouterReasoningProvider`: **preset mode** (`model="@preset/<slug>"`, user-only message — the master
  prompt is NOT resent) and **direct mode** (system+user); native structured output via the **same** Phase-1
  canonical schema; usage(tokens+cost)+generation-id capture; one-inference retry (transient 5xx/429/connection
  only — never a post-generation timeout); API key in the `Authorization` header only.
- `master_protocol.py`: the compiled system instructions == `pp.system` (hash == `system_prompt_sha`) — the
  repository is the source of truth for the preset content; Omi records the version/hash it EXPECTS the preset
  to hold (it does not / cannot verify the remote preset).
- Forensic trace additions: `provider`, `requested_model`, `openrouter_preset`, `master_prompt_version/hash`,
  `canonical_schema_id`, `endpoint_cost_usd`. HF `remote.py` untouched; Floor unchanged; ONE inference preserved.

### Phase 3A — evidence-semantics audit (read-only, this log)
Produced the code-grounded specification to author Master Analyst Protocol v1. Highlights below (see the
full deliverable in the session transcript). No code/prompt/preset/production change.

---

## 5. Phase 3A findings (condensed — the spec for v1)

**What the model receives** (`pp.user`, from `render.py`): 9 sections as compact positional-row tables —
`investigation_summary, coordination_analysis, account_analysis, commenter_history, comment_analysis,
narrative_analysis, campaign_analysis, coverage, legend`. Accounts are `A#`, clusters `C#`, narratives `N#`.

**Citation grain (critical):** citable ids exist ONLY at the **account (`A#`), cluster (`C#`), narrative (`N#`)**
grain (resolve against `evidence_index ∪ alias legend`). There are **NO** citable ids for individual detector
signals/contributions (their `evidence` fields are free-text), individual comments (only near-duplicate groups),
or memory priors (by design). `eb:/ipkg:/es:` are manifest-only, not in `pp.user`. **v1 MUST teach: cite only
`A#/C#/N#`; name detectors in prose; never invent ids; never cite memory.**

**Ownership boundary** (`field_provenance()` + Phase 1): **model-generated** = analytical wrapper
(`verdict, coordination_label, confidence_band, confidence_rationale, headline, assessment, evidence_for,
evidence_against, uncertainty, what_would_change_this, limits_statement, supplemental_context,
legitimate_hypothesis`) + the 6 `*_reasoning` domains. **Omi-injected after validation** =
`suspicion_probability, suspicion_tier` (echoed), `corroboration` (engine), `subject, analyst_version,
prompt_version, schema_version, model_revision`, `governance`, `investigation_trace`.

**Key evidence semantics** (teach these; full table in transcript):
- `overall_probability` (0–1, calibrated engine suspicion — echo, never recompute), `tier` (its band).
- `coordination_adjusted_probability` — already coordination-derived; **do not re-add as coordination evidence**.
- `omi_score` (0–100 composite **index**, not a probability), `authenticity_score` (0–100, high=organic,
  ~inverse of overall_probability) — both derived from the same detectors → **not independent evidence**.
- `contributions`: `impact` (share of movement), `direction`, `logit_delta` (signed logit movement),
  `decorrelation_factor` (1=independent, <1=correlated → treat as ~one). Same signal — don't triple-count.
- `single_axis_capped` (one axis carried it → capped below HIGH), `discriminative_methods` ⊆
  `{fingerprint_cluster, co_engagement, co_tag}` (a maximal coordination read needs a discriminative lens or
  ≥2 independent detectors; a lone supporting/non-discriminative signal caps at MODERATE).
- `supplemental=True` signals (e.g. ai_writing) = **zero suspicion weight**, context only.
- Memory (`matched_prior_neighbors`, priors) = **background, never moves the score, not citable**.

**⚠ Under-defined in code (teach conservatively, pin later):** `spread_ratio`, `inauthenticity_score`
(narrative), `convergence_score`, memory `influence_class`/`epistemic_status` enums.

**Synthesis rule:** weight domains by evidence strength × corroboration (never average); raise confidence only
on *independent* cross-domain convergence; the corroboration gate binds `coordination_label`/`verdict`; echo
the engine number; state disagreement and lower confidence rather than pick the loudest; coverage/thin-data
lower `confidence_band`.

**Prompt size:** compiled Master Analyst Protocol ≈ **24,161 chars ≈ ~6,040 tokens** (framework JSON is the
biggest block). Removing the council framework from the prompt (~1.5–2.5k tokens) funds the evidence-semantics
+ six-domain sections. Target ≲ 7–8k tokens; do NOT duplicate the JSON schema in prose (machine-owned).

**Verdict:** v1 CAN be written now, with two guardrails — (a) teach the 4 ⚠ fields conservatively; (b) teach
the entity-only citation grain. No production code must change first.

---

## 6. Phase 3B — recommended next step (NOT started)

Author Master Analyst Protocol v1 as stable doctrine and wire it, using the Phase 3A spec. Likely file changes:
- `prompts/_assets/omi_analyst_v1.txt` — rewrite Rule 10 (defer output to the canonical schema), broaden from
  account-grain "the subject" to investigation grain.
- `prompts/constitution.py` — Lead-Investigator identity in `_GLOBAL`; `_OUTPUT_FORMATTING` defers to schema;
  add an **Evidence Semantics** block (or new `prompts/evidence_semantics.py`) + the **citation-grain** rule.
- `prompts/comprehensive_investigation_template.py` — fold the six-domain method into `system_task`.
- `prompt/stage_builder.py` / `package_loader.py` — remove/reduce the council `framework` JSON in the compiled
  system (keep as internal metadata).
- Regenerate `ml/analyst/hf_repo/prompts/…` mirrors (drift guard).
- Tests: Phase-0 propagation asserts the new blocks reach the model + the compiled hash changes; the
  `master_protocol.py` hash test still guarantees preset == compiled system.
- **Zero** changes to: OpenRouter provider, canonical schema, Governor, Repository/Snapshot/Composer,
  persistence, frontend.

**Do not, without explicit user authorization:** create/edit the OpenRouter preset, select a production model,
switch production traffic, change Render/Supabase, or begin prompt tuning beyond authoring v1.

---

## 7. Locked invariants (never break silently)

- ONE Investigation Package → ONE compiled instruction set → ONE canonical output contract → **ONE primary
  model inference** → ONE ComprehensiveAssessment. No per-domain calls, no repair/synthesis inference, no hidden
  retry that bills a second generation.
- The repository is the source of truth for instructions; the OpenRouter preset is deployment, not truth.
- ONE canonical schema (Phase 1) serves the local validator, the model-facing contract, and OpenRouter native
  structured output. No second schema. Local canonical validation ALWAYS runs.
- Model generates analytical content only; Omi injects governance/provenance/subject/echo **after** validation.
- Evidence-not-verdicts; echo the engine number; corroboration gate; supplemental = zero weight; memory not
  citable; cite only `A#/C#/N#`.
- Invalid model output → deterministic Floor (existing policy), forensically observable, no repair inference.
- Provider selection is configuration; HF path stays default and byte-identical until an explicit cutover.

---

## 8. Working rules for this program (constraints)

- **Branch:** develop on `claude/stoic-edison-2ueecx`; commit with clear messages; push; keep draft PR #82 current.
  If the PR ever merges, restart the branch from latest `main` for follow-up work (do not stack on merged history).
- **Backend gate:** `cd apps/api && python -m pytest tests/ -q` must be green before commit; report the real count.
- **Frontend gate:** `cd apps/web && npm run typecheck` must pass before committing any web change.
- **Secrets:** production secrets were pasted in chat earlier and must be treated as compromised — **rotate them**
  (HF token, Supabase URL, session secret, Twitter/YouTube keys). Never write any secret value to a tracked file;
  read credentials from the environment only (`OPENROUTER_API_KEY`, `HF_TOKEN`, …).
- **Sandbox limits:** the Supabase DB and the HF endpoint are NOT reachable from this sandbox (proxy 403 / TCP
  timeout). Do not retry or circumvent policy denials; verify via tests, not live prod calls.
- **Do not modify** Render or Supabase configuration, or switch production traffic, without explicit authorization.
- **Keep this file updated** with every change (Status table, Changelog, Next step).

---

## 9. Changelog

- **2026-07-15** — Created this program log. Phases 0–2 complete and pushed (`19e8491`, `9b17401`, `c6981ea`);
  full suite 1318 passed. Phase 3A evidence-semantics audit complete (read-only). Next: Phase 3B (author Master
  Analyst Protocol v1) — awaiting authorization.
