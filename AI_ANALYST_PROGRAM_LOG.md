# OmiSphere AI Analyst — Program Log & Session Handoff

> **READ THIS FIRST.** This is the single source of continuity for the OmiSphere AI Analyst
> provider-independence program. A brand-new Claude Code session should be able to resume **flawlessly
> from this file alone**. **Whoever works on this program MUST update this file as part of every change**
> (new phase, new commit, new decision, new finding) — keep *Status*, *Changelog*, and *Next step* current,
> and commit the update alongside the work.

| | |
|---|---|
| **Last updated** | 2026-07-17 — **Phases 3B, 4A, 5A, 5B, 5C, 5D, 5E complete**: Master Analyst Protocol v1, canonical-response UI integration, OpenRouter readiness layer, cutover verification, dev-only verification mode, production infrastructure cutover (render.yaml/.env.example), and transport-level verification logging |
| **Repo** | `mcif-test/omi` (FastAPI `apps/api` + Next.js `apps/web` + `ml/analyst/` package) |
| **Working branch** | `claude/master-analyst-protocol-v1-1u8tyk` (the live branch; already contains Phases 0–2 — the earlier `claude/stoic-edison-2ueecx` work was folded in via a "PR #83" merge) |
| **Current HEAD** | the Phase 5B commit on the working branch (advances with this change) |
| **Pull request** | draft **PR #84**, base `main`, head `claude/master-analyst-protocol-v1-1u8tyk` — covers Phases 1–2 + 3B + 4A + 5A + 5B (+ this log); `main` itself still holds only Phase 0 |
| **Verify command** | `cd apps/api && python -m pytest tests/ -q` (backend) · `cd apps/web && npm run typecheck && npm run test` (frontend) |
| **Latest green suite** | backend **1348 passed, 1 warning** (pre-existing Starlette/httpx deprecation — unrelated, ignore); frontend typecheck clean + 23 tests |
| **Master Analyst Protocol (production doctrine)** | compiled `pp.system` == `compile_master_analyst_protocol().text`; **hash `map:5226c1bd2259be9caa5260fe`**; version `map/prompt:v1+constitution:v4+framework:v1+template:citmpl-v4`; 35,699 chars; 14 constitution blocks. Instructs COMPLETE per-account coverage: one CONCISE `commenter_assessments` item for EVERY account alias (no sampling). Paste-ready artifact: **`ml/analyst/omi_master_v1_preset.txt`** (+ `.json` manifest), drift-guarded byte-identical to the compiled text. **Operator must re-paste the regenerated preset into the OpenRouter dashboard for the new output contract to take effect.** |
| **Next step** | **Operator: OpenRouter production cutover** — create preset `omi-master-v1` + set Render env (see **§13 checklist**). Token budget resolved (`max_new_tokens=16000`). Then optional **Phase 4B** (AI experience integration). Code is cutover-ready; deployment is not authorized to execute from here. |

---

## 0. First actions for a new session (do these in order)

1. `git checkout claude/master-analyst-protocol-v1-1u8tyk && git pull` — this branch already contains Phases 0–2 + 3B. (The log used to name `claude/stoic-edison-2ueecx`; that work was folded into this branch.)
2. Read this whole file. It contains the full Phase 3A spec (§8) and the Phase 3B delivery record (§9).
3. `cd apps/api && python -m pytest tests/ -q` — confirm the green baseline (**1319 passed**). Full suite ≈ 3.5–4.5 min.
4. Do **not** start implementing until the user issues the next phase authorization (see §1). Phase 3B is **done**; the next step (deploy the OpenRouter preset + select a model + production cutover) is **not authorized to build** yet.
5. When you make any change: keep the backend suite green, commit to the branch, push, keep the draft PR current, and **update this file** (§Status, §Changelog, §Next step).

---

## Why this matters — the north star

**OmiSphere is a coordination-intelligence platform.** It detects **coordinated inauthentic behavior —
campaigns, influence operations, artificial amplification — NOT merely "suspicious accounts."** A deterministic
engine (detectors + scoring + coordination aggregation + OmiScore) *measures* the evidence. The **AI Analyst is
the reasoning layer** that *interprets* that evidence into an explainable recommendation a human analyst can act
on, cite, or overturn.

**Main goal of this program:** a trustworthy, **provider-independent** AI Analyst where **Omi owns the
intelligence doctrine and the model is replaceable.** One investigation → one comprehensive model inference →
one validated, evidence-grounded **ComprehensiveAssessment** the website renders. The near-term destination is
to deploy a stable **Master Analyst Protocol** through an **OpenRouter preset** and be able to swap/benchmark
models **without changing** Omi's evidence, doctrine, output contract, Governor, persistence, or frontend.

**Core trust principle (non-negotiable): evidence, not verdicts.** Surface observations, probabilities,
confidence, evidence-for / evidence-against, and uncertainty — **never** a persisted "this IS a bot / IS a
campaign." The **precision frontier is sacred**: legitimate coordination (newsrooms, on-message officials, fan
communities, benign automation) must never be read as hostile. The UI must never show a strong conclusion
without visible supporting evidence. This principle predates and outranks any single phase.

## The arc so far (history & trajectory)

This program sits on top of a large prior body of work (see `ml/analyst/OMI_*.md` and the completed task list):
the **single-inference AI-native architecture** was designed, built, and certified before Phase 0 —
`EvidenceRepository → Snapshot → InvestigationComposer → immutable InvestigationPackage → coverage-budgeted
render → ONE comprehensive inference → Governor + deterministic Floor → persisted analyst_assessment_v1 →
website (6 domain panels)`. The six-domain comprehensive response, the forensic trace, aliasing/dedup/coverage
budgeting, and the website cutover all shipped earlier.

Then **production reality** intervened: real investigations kept falling to the deterministic Floor. Root causes
were found and fixed — a schema-prefilter ordering bug and a messages-API URL bug (PR #81, since merged to
`main`) — and the trace was made self-diagnosing (`endpoint_error`, `response_status`).

The **strategic pivot** that defines the current work: make the model **replaceable** via **OpenRouter as the
primary gateway**, with Omi owning the instructions/doctrine/output contract. That produced the phase sequence:
**Phase 0** (prove the compiled instruction text actually reaches the model) → **Phase 1** (ONE canonical output
contract — which also fixed the real bug that was forcing every response to the Floor) → **Phase 2** (OpenRouter
provider + preset seam) → **Phase 3A** (evidence-semantics audit) → **Phase 3B** (write Master Analyst Protocol
v1) → **later** (deploy the preset, pick a model, production cutover, model benchmarking, eventually fine-tuning
once doctrine + output contract + a labeled corpus are stable).

**Where this is heading after 3B:** the human deploys the preset (system prompt = the compiled Master Analyst
Protocol) and picks a model; then a controlled production cutover (flip `OMI_ANALYST_PROVIDER=openrouter`); then
benchmarking the *same* Investigation Package + instructions + output contract across models (comparing evidence
grounding, false-positive behavior, six-domain completeness, schema compliance, citation correctness, latency,
tokens, and **per-investigation cost** — `endpoint_cost_usd` already makes cost measurable); then possibly
fine-tuning. **None of that is authorized yet** — it is the map, not the next step.

## How we work (method & quality bar)

- **Audit before building.** Every phase begins by reading the *actual* code and reporting findings grounded in
  `file:line`. **Never invent semantics** — if the code doesn't define a field's meaning, say
  "SEMANTICS NOT SUFFICIENTLY DEFINED IN CURRENT CODE." That honesty is a deliverable, not a gap.
- **Small, verified, reversible changes.** Additive wherever possible; the default (feature-off / Hugging Face)
  path stays byte-identical until an explicit cutover. Prove behavior with tests, not assertions.
- **Full-suite gate.** `cd apps/api && python -m pytest tests/ -q` must be green before every commit; **report the
  real count.** Never commit on a red or uninspected suite. When a legit behavior change breaks an old test, update
  the test to the new contract and say why.
- **One phase at a time; stop and report.** Honor the user's explicit "Do NOT" lists exactly. Many phases are
  audit-only. Do not drift into a later phase or touch frontend / Render / Supabase / canonical schema / Governor /
  provider-architecture without explicit authorization.
- **Honest reporting always.** Failing tests are reported with their output; skipped steps are stated; done-and-
  verified is stated plainly without hedging. No fabricated progress or metrics.
- **Provider-independence and one-inference are sacred.** Everything routes through the `ReasoningProvider` seam;
  exactly one billable inference per investigation; adjudication/validation/Governor are provider-agnostic.
- **The `omisphere-platform-guardian` skill** encodes the standing guardrails (coordination-first framing,
  evidence-not-verdicts, SAVEPOINT-isolated best-effort writes, corroboration-gate precision discipline, test
  gates, the PR workflow). It loads at session start — follow it.
- **Reports are detailed and structured.** The user consumes long, tabular, `file:line`-cited markdown reports and
  sometimes pastes them back or re-sends an authorization mid-turn. Density and precision beat brevity here.

## Key decisions & rationale (decision log)

- **Canonical schema is DERIVED from `analyst_response_schema.json`, not hand-copied** → one machine-readable
  source of truth; prose contract + local validator + OpenRouter structured-output all reference it; cannot drift.
- **Omi-owned fields are overlaid from the deterministic Floor AFTER canonical validation** → the model never
  fabricates provenance/subject/echoed numbers/corroboration; the Floor already computes correct values.
- **The six domains are GATING** (missing/empty/malformed → deterministic Floor) → "one canonical contract" is
  all-or-nothing; stricter validity, but the *fallback policy* is unchanged (existing Floor, no repair inference).
- **The Master Analyst Protocol == the compiled `pp.system`** (not a newly authored prompt) → the repository stays
  the source of truth; the OpenRouter preset is *expected* to contain exactly this text (hash recorded, remote
  content not — and cannot be — cryptographically verified).
- **In preset mode the request sends only the Investigation Package** (no system message) → don't resend the master
  prompt; verified against OpenRouter's preset shallow-merge behavior.
- **The HF path (`remote.py`) is untouched and remains the default** → zero production risk until an explicit cutover.
- **Provider label is threaded, not hardcoded** (`qwen-omi-analyst-v1` vs `openrouter-omi-analyst-v1`) → honest
  forensics without breaking existing traces/tests.
- **Planned for 3B: drop the council `framework` JSON from the compiled prompt** → it describes a 13-specialist
  council the single-inference Lead Investigator doesn't use (identity contradiction + wasted tokens); keep it as
  internal metadata only.
- **Open item for 3B:** the user is separately designing the Master Analyst Protocol's final wording — v1 must
  **not invent doctrine**; author it from the Phase 3A spec (§8), conservative on the ⚠ under-defined fields.

## 1. How this program operates (collaboration protocol)

- The user drives the program in **explicit, numbered phase authorizations** (e.g. "PHASE 3B AUTHORIZATION — …").
  Each authorization is detailed and includes hard "Do NOT" constraints. **Wait for the authorization before
  implementing.** Do not jump ahead to a later phase.
- Each phase is **audit → (report) → implement → verify → report**, and you **STOP after each phase** and wait
  for the next authorization. Several phases are audit-only / report-only — respect that.
- Deliverables are returned as detailed markdown reports in chat. The user sometimes **re-sends the same
  authorization mid-turn** — treat it as the same instruction, keep going.
- After an implementation phase: run the full suite, commit + push, ensure PR #82 reflects it, update this log.
- A repo stop-hook nags to commit uncommitted changes — commit/push completed, verified work (it's expected).

---

## 2. What the program is

Evolve OmiSphere's AI Analyst into a **provider-independent, evidence-owning** system:

- **Omi owns:** evidence collection, deterministic detectors/measurements, EvidenceRepository, Snapshot,
  InvestigationComposer, immutable InvestigationPackage, the analytical **doctrine / system instructions**,
  the canonical **ComprehensiveAssessment output contract**, validation/Governor, persistence, website.
- **The provider (OpenRouter, or Hugging Face today) is transport only** — routes to a model that performs
  **exactly ONE comprehensive inference** and returns one canonical assessment.
- **One investigation = one primary model inference.** Six analytical domains are reasoning lenses *inside*
  that one inference, plus a Lead-Investigator synthesis.

### Production reasoning pipeline (current)
```
scan → EvidenceRepository.snapshot (es:) → InvestigationComposer.compose → InvestigationPackage (ipkg:)
     → investigation_render (alias A#/C#/N# + dedup + coverage budget)
     → build_comprehensive_investigation_prompt_package
     → pp.system (compiled Master Analyst Protocol) + pp.user (Investigation Package evidence, 9 sections)
     → run_stage_inference → _reasoning_transport (HF _qwen_transport | _openrouter_transport)  ← ONE inference
     → _adjudicate: canonical-schema validate → overlay Omi-owned fields from Floor → Governor
     → persist analyst_assessment_v1 → API → website (analyst-panel.tsx)
```
Entry: `scan.py` (on a NEW investigation) → `analyst.maybe_autogenerate` → background `generate_and_persist`
→ `assess_payload` → `assess_investigation` → `_assess_core` (the ONE production path). The website panel
also triggers `POST /v1/investigations/{slug}/analyst` on mount (safety-net generation).

---

## 3. Phase status

| Phase | Title | Status | Commit |
|---|---|---|---|
| 0 | Provenance & instruction-content propagation proof | ✅ done | `19e8491` |
| 1 | ONE canonical ComprehensiveAssessment output contract | ✅ done | `9b17401` |
| 2 | OpenRouter preset-based ReasoningProvider (behind the seam) | ✅ done | `c6981ea` |
| 3A | Master Analyst Protocol evidence-semantics audit (read-only) | ✅ done | this log |
| **3B** | **Author & wire Master Analyst Protocol v1** | ✅ **done** | this session (see §6, §9) |
| 4 (audit) | Canonical Response Integration — end-to-end data-flow audit (read-only) | ✅ done | this session |
| **4A** | **Canonical Response Integration — Analyst Panel surfaces structured fields** | ✅ **done** | this session (frontend only) |
| 4B | AI Experience Integration (account pages, VerdictWidget seeding, viewer) | ⬜ not started — planned, not authorized | — |
| 5 (audit) | OpenRouter Production Integration — provider-layer audit (read-only) | ✅ done | this session |
| **5A** | **OpenRouter operational readiness layer (provider-aware diagnostics)** | ✅ **done** | this session (backend only) |
| **5B** | **OpenRouter production cutover — code readiness + verification (NOT deployed)** | ✅ **done** | this session (§13 Render checklist) |
| deploy | Operator: create preset `omi-master-v1`, set Render env, monitored cutover | ⬜ operator action — see §13 | — |
| later | Model benchmarking (same package + instructions across models) | ⬜ not started | — |

---

## 4. Environment & tooling

- **Runtime:** Python 3.11, `pytest` from `apps/api` (cwd matters — run tests there). Frontend: `apps/web`,
  gate `cd apps/web && npm run typecheck`.
- **Sandbox limits:** the Supabase DB and the HF inference endpoint are **NOT reachable** from this environment
  (proxy 403 / TCP timeout). **Do not retry or circumvent policy denials.** Verify via tests, never live prod calls.
- **GitHub:** use the **GitHub MCP tools** (`mcp__github__*`) — `gh` CLI is **not** available. MCP scope is
  restricted to `mcif-test/omi`. Owner param is `mcif-test`, repo `omi`.
- **Git push:** `git push -u origin claude/stoic-edison-2ueecx`; retry on transient network errors.
- **Commits/PRs:** clear messages; end commit messages with the `Claude-Session:` trailer only. **Do NOT put the
  model identifier anywhere in commits, PR text, code, or this file** (chat replies only). PR bodies end with the
  "Generated with Claude Code" line.
- **Scratch:** use the session scratchpad dir for temp files, not `/tmp`.

---

## 5. Key files (the map)

**Reasoning / provider**
- `apps/api/app/reasoning/analyst.py` — `_assess_core` (the ONE production path), `_reasoning_transport`
  (provider dispatch), `_qwen_transport` (HF), `_openrouter_transport`, `reasoning_provider* / _provider_token_present`,
  `field_provenance()` (model vs Omi ownership), the `investigation_trace` dict (forensics).
- `apps/api/app/reasoning/runtime.py` — `run_stage_inference` / `AIInvestigationRuntime.infer` / `_adjudicate` /
  `_canonical_candidate` (canonical validation + Floor overlay + Governor). **Adjudication is provider-agnostic.**
- `apps/api/app/reasoning/model_providers/` — `base.py` (ReasoningProvider protocol + `ReasoningRequest/Response`
  + typed errors), `remote.py` (HF — **untouched by Phase 2**), `openrouter.py` (Phase 2), `config.py`, `mock.py`.
- `apps/api/app/reasoning/prompts/master_protocol.py` — `compile_master_analyst_protocol()` (== `pp.system`,
  hash == `system_prompt_sha`); `master_analyst_protocol_identity()` (lean, no body — for the trace).
- `apps/api/app/reasoning/prompt/stage_builder.py` — `assemble_stage_system` (the 6-block system assembly),
  `build_prompt`, `register_stage_prompt`.

**Instruction assets (compile into the Master Analyst Protocol == `pp.system`)**
- `apps/api/app/reasoning/prompts/_assets/omi_analyst_v1.txt` — base identity + 10 absolute rules.
- `apps/api/app/reasoning/prompts/constitution.py` — 12 constitutional blocks.
- `apps/api/app/reasoning/prompts/framework.py` — specialist-council catalog. **Phase 3B: no longer injected
  into the compiled prompt** (removed from `assemble_stage_system`); retained as internal metadata only —
  still loaded, content-hashed, and recorded in the manifest as `framework_hash`.
- `apps/api/app/reasoning/knowledge/` — knowledge library (top 12 entries injected).
- `apps/api/app/reasoning/prompts/comprehensive_investigation_template.py` — comprehensive `system_task`,
  **`comprehensive_investigation_canonical_schema()`**, schema-derived output contract, section keys.

**Evidence (what the model sees)**
- `apps/api/app/reasoning/evidence_bundles.py` — 7 immutable bundles + every model-visible field dataclass.
- `apps/api/app/reasoning/investigation_render/render.py` — projects the package into the 9 model-facing sections.
- `apps/api/app/reasoning/investigation_composer.py` — InvestigationPackage + `evidence_index` (citable ids).
- `apps/api/app/reasoning/context/investigation.py` — InvestigationContext (upstream field semantics).
- `apps/api/app/detection/scoring.py` — `overall_probability`, `single_axis_capped`, convergence, `logit_delta`,
  `decorrelation_factor`, tier.
- `apps/api/app/detection/coordination/aggregate.py` — `DISCRIMINATIVE_DETECTORS`, corroboration gate, reliability.
- `apps/api/app/intelligence/omiscore.py` — `omi_score` / `authenticity_score`.

**Output contract / validation**
- `ml/analyst/analyst_response_schema.json` — the wrapper schema the canonical schema derives from.
- `apps/api/app/governor/comprehensive.py` — `validate_comprehensive_model_output` (the ONE canonical parser),
  `validate_comprehensive_sections`.
- `apps/api/app/governor/governor.py` — the Governor.
- `ml/analyst/omi_analyst/schema_validate.py` — `validate_analyst_response` (wrapper validator, reused by the canonical parser).
- `ml/analyst/hf_repo/prompts/…json` — published HF mirrors (drift-guarded; regenerate via `prompts/export.py`).

**Frontend (do NOT change without explicit approval)**
- `apps/web/app/(app)/investigations/[slug]/analyst-panel.tsx` — consumes the wrapper + 6 `*_reasoning` sections.

**Tests to know**
- `apps/api/tests/test_instruction_provenance.py` — Phase 0: asset text → `pp.system/.user` →
  `ReasoningRequest` at the provider boundary; source-change → hash/id change; determinism; canonical contract
  reaches the model.
- `apps/api/tests/test_comprehensive_contract.py` — Phase 1: one canonical schema; 6 domains first-class;
  missing/forbidden fail; Omi metadata not required from the model; projection after validation; ONE inference.
- `apps/api/tests/test_openrouter_provider.py` — Phase 2: seam, selection, preset reaches request, package reaches
  provider, master prompt NOT resent, one schema for structured output, valid→path, invalid→Floor, ONE inference,
  errors forensic, key never leaks, HF/Floor no-regress.
- `apps/api/tests/test_one_inference_invariant.py` — structural proof of exactly one inference path (the runtime →
  `_reasoning_transport` → concrete transports).
- `apps/api/tests/test_comprehensive_cutover.py` — valid model output → model_backed; invalid/malformed → Floor.

---

## 6. Phase detail (what shipped)

### Phase 0 — provenance (`19e8491`)
Executable proof the compiled instruction TEXT reaches the provider request (a hash alone is insufficient).
Added additive trace field `investigation_trace.compiled_system_instruction_hash` (= `pp.manifest["system_prompt_sha"]`).

### Phase 1 — ONE canonical output contract (`9b17401`)
One canonical schema derived from `analyst_response_schema.json` with the **6 domains as first-class REQUIRED
properties**; the model-facing OUTPUT CONTRACT is **rendered deterministically from the schema** (no drift). The
runtime validates the model's full output and **overlays Omi-owned fields from the Floor after validation**
(`_canonical_candidate`). Missing/empty/malformed domain → deterministic Floor (no repair inference). Root cause
fixed: the old wrapper schema required the model to fabricate Omi provenance AND forbade the sidecars → every real
response fell to Floor.

### Phase 2 — OpenRouter provider (`c6981ea`)
OpenRouter behind the existing `ReasoningProvider` seam (selection is configuration). Preset mode
(`model="@preset/<slug>"`, user-only message — master prompt NOT resent) and direct mode (system+user); native
structured output via the **same** Phase-1 schema; usage(tokens+cost)+generation-id capture; one-inference retry
(transient 5xx/429/connection only — never a post-generation timeout); API key in the `Authorization` header only.
`master_protocol.py` makes the repository the source of truth for the preset content. HF `remote.py` untouched;
Floor unchanged; ONE inference preserved.

### Phase 3B — author & wire Master Analyst Protocol v1 (this session)
Authored v1 as stable doctrine **from §8 only** (no invented semantics; conservative on the ⚠ under-defined
fields; entity-only citation grain). **Content edits (4 files):**
- `prompts/_assets/omi_analyst_v1.txt` — rewrote to the **single Lead Investigator at investigation grain**
  (was account-grain "the subject"); kept the 10-rule spine + tone; Rule 10 now **defers to the canonical
  schema** (no hand-listed fields that could drift) and names the Omi-injected fields the model must not
  fabricate. Kept the test anchors (`You are OMI ANALYST`, `EVIDENCE, NOT VERDICT`); mirror
  `ml/analyst/analyst_system_prompt_v1.md` fenced block updated to match (drift guard). Registry version
  stays `v1` (in-place content revision; `prompt_hash` moves).
- `prompts/constitution.py` — `_GLOBAL` reframed from "specialist inside a council" to the **single Lead
  Investigator**; `_CITATION_RULES` rewritten to the **entity-only grain** (cite A#/C#/N# + omitted-entity
  aliases; name detectors in prose, never as ids; never cite memory/manifest ids); **new
  `_EVIDENCE_SEMANTICS` block** (universal §8.2 principles: measurement≠conclusion, OmiScore is an index not a
  probability, correlated detectors count ~once / no double-count, `coordination_adjusted` already
  coord-derived, campaign reuses clusters, structure≠intent, memory=background, coverage≠suspicion); swept
  residual "specialist/council/ruling" wording; **`CONSTITUTION_VERSION` v1→v2** (13 blocks now).
- `prompts/comprehensive_investigation_template.py` — folded the **§8.4 six-domain method** into
  `system_task` (what each domain reads + strong-signal vs false-positive guard; ⚠ `spread_ratio` /
  `inauthenticity_score` taught as "directional, read conservatively"); **template `citmpl-v2`→`citmpl-v3`**.
  Canonical schema + `_render_output_contract` **untouched**.
- `prompt/stage_builder.py` — **removed the `SPECIALIST INVESTIGATION FRAMEWORK` JSON block from
  `assemble_stage_system`** (the compiled `pp.system`). The council catalog contradicted the single-inference
  identity; it stays **internal metadata** (still loaded, still content-hashed, still in the manifest as
  `framework_hash`). Only ~271 tokens (the audit §8.7 over-estimated: the compiled block was the *summary*,
  not the full module). `template.py` / `builder.py` (the unwired legacy investigation builder) untouched, so
  its drift-guarded mirror stays green.

**Mirrors regenerated** via `python -m app.reasoning.prompts.export`: `prompt_manifest.json`,
`prompt_catalog.json`, `comprehensive_investigation_prompt_template.json`, `SPECIALIST_FRAMEWORK.md`,
`BEHAVIORAL_ANALYST.md` (the last two moved only by the `constitution v2` / `framework_hash` propagation —
`framework_hash` embeds `constitution_hash`). Base-prompt `.md` mirror updated by hand.

**Compiled Master Analyst Protocol v1 (as of Phase 3B — superseded by the final-doctrine pass, see header/§13):**
hash **`map:ea25de153d030eae9a5f7eea`**, version
`map/prompt:v1+constitution:v2+framework:v1+template:citmpl-v3`, ~27,300 chars ≈ **6,825 tokens** (from 6,040;
within the ≲7–8k target). Vendor-neutral (no provider/model vendor names in the compiled text). **Zero
changes** to: OpenRouter provider, canonical schema, Governor, runtime, Repository/Snapshot/Composer,
persistence, frontend, deterministic/scoring engine, one-inference path.

**Tests:** inverted `test_framework_content_reaches_compiled_system` →
`test_council_framework_is_not_injected_but_stays_manifest_metadata` (framework absent from `pp.system`, still
in the manifest); added `test_v1_doctrine_blocks_reach_compiled_system` (single-investigator identity +
Evidence Semantics + entity citation grain + six-domain method all reach the model; no council terminology
survives); flipped the two framework-marker assertions (`test_prompt_builder`,
`test_investigation_summary_stage`) to assert **absence**; updated the hardcoded investigation `package_hash`
(`pkg:ad831…`→`pkg:ff8791ad17b431c4befb6c5b`) and the constitution block count (12→13). **Full suite: 1319
passed, 1 warning.**

---

## 7. Config & env-var reference

Settings use pydantic `env_prefix="OMI_"` (field `foo_bar` → `OMI_FOO_BAR`). Secrets are read from `os.environ`
directly (never settings, never persisted).

| Env var | Field / usage | Default |
|---|---|---|
| `OMI_ANALYST_ENABLED` | `analyst_enabled` — master on/off | false |
| `OMI_ANALYST_PROVIDER` | `analyst_provider` — `huggingface` \| `openrouter` | `huggingface` |
| `OMI_ANALYST_ENDPOINT_URL` | HF endpoint (HF path) | none |
| `OMI_ANALYST_ENDPOINT_API` | `generate` \| `messages` (HF) | `generate` |
| `OMI_ANALYST_MODEL_ID` | served model id (HF) | Mistral-7B-Instruct-v0.3 |
| `OMI_OPENROUTER_PRESET` | `openrouter_preset` — preset slug (preset mode) | none |
| `OMI_OPENROUTER_MODEL` | `openrouter_model` — model slug (direct mode / override) | none |
| `OMI_OPENROUTER_BASE_URL` | `openrouter_base_url` | `https://openrouter.ai/api/v1/chat/completions` |
| `OMI_OPENROUTER_STRUCTURED_OUTPUT` | send `response_format` json_schema | true |
| `OMI_OPENROUTER_REFERER` / `OMI_OPENROUTER_TITLE` | dashboard attribution headers | none |
| `HF_TOKEN` / `HUGGINGFACE_HUB_TOKEN` | **secret** (HF path), env-only | — |
| `OPENROUTER_API_KEY` | **secret** (OpenRouter path), env-only | — |

**Provider label** (governance.provider on model-backed): HF = `qwen-omi-analyst-v1`, OpenRouter =
`openrouter-omi-analyst-v1` (`analyst.reasoning_provider_name`).

---

## 8. Phase 3A — evidence-semantics spec (full; write Phase 3B from this)

### 8.1 What the model receives (`pp.user`, from `render.py`)
Nine sections as compact **positional-row tables** (column headers declared once). Accounts `A#`, clusters `C#`,
narratives `N#`; a `legend` resolves them. `bundle_id (eb:)`, `package_id (ipkg:)`, `snapshot_id (es:)` are
manifest/trace only — **NOT in `pp.user`**.

- `investigation_summary`: `overall_probability, overall_tier, confidence, convergence_score, inputs_provided,
  platform, post_content_id`, `coordination_digest{coordination_score,coordination_tier,single_axis_capped,
  discriminative_methods,cluster_count}`, `drivers[[name,impact,direction,logit_delta,decorrelation_factor,evidence]]`,
  `accounts_digest{count,flagged_count,high_count,max_probability,mean_probability}`,
  `cross_links[[kind,severity,evidence,related_refs]]`, `weak_signals[]`,
  `memory[[type,label,confidence,influence_class,epistemic_status]]`.
- `coordination_analysis`: `coordination_score, coordination_tier, single_axis_capped, discriminative_methods[],
  clusters[[C#,method,[A#],members_count,score,discriminative,evidence]], relationships[[type,from,to,count]], cluster_count`.
- `account_analysis`: table `[account(A#), overall_probability, coordination_adjusted_probability, tier, confidence,
  signals[[detector,probability,confidence,supplemental,evidence]],
  contributions[[detector,impact,direction,logit_delta,decorrelation_factor,evidence]], weak_signals[],
  omiscore[omi_score,authenticity_score]]`; `memory_priors[]`; `omitted_account_refs[A#]`; `coverage{}`.
- `commenter_history`: `[account(A#), activity_sample_count, matched_prior_neighbors, from_cache]`.
- `comment_analysis`: `thread_probability, thread_tier, comment_count,
  near_duplicate_groups[[exemplar,count,[A#],earliest,latest,similarity,is_duplicate_group]], omitted_group_count, coverage{}`.
- `narrative_analysis`: `[narrative(N#), member_count, distinct_authors, spread_ratio, inauthenticity_score]`.
- `campaign_analysis`: `candidate_cluster_refs[C#], count`.
- `coverage`: `mode(complete|large_investigation), total_evidence_tokens_est, budget{}, domains{}, sampling{},
  token_estimator, note`.
- `legend`: `A#→author_ref, C#→cl:…, N#→nr:…`.

### 8.2 Evidence-semantics dictionary
Cat: **OBS** raw observation · **DET** deterministic measurement · **DTX** detector output · **REL** relationship
· **HIST** historical/memory · **COV** coverage · **ID** identifier.

| Field (source) | Cat | Range | Meaning | Does NOT prove | Correlation/double-count |
|---|---|---|---|---|---|
| `overall_probability` (scoring `sigmoid(posterior_logit)`) | DET | 0–1 | calibrated engine suspicion (echo, never recompute) | inauthenticity as fact | drives omi_score(25%), ~inverse authenticity |
| `coordination_adjusted_probability` (elevate.py, passthrough) | DET | 0–1/null | suspicion after corroboration-gated coordination elevation | independent suspicion | already coordination-derived — don't re-add as coord evidence |
| `tier` | DET | low/mod/elev/high | band of overall_probability (gate can cap) | a verdict | derived from overall_probability |
| `confidence` (scoring, decorrelated) | DET | 0–1 | data sufficiency (correlation-adjusted) | suspicion level | orthogonal |
| `convergence_score` (payload) | DET | 0–1 ⚠ | ≥2 independent axes agreeing | — | ⚠ exact formula not in reasoning layer |
| `signals[].probability/confidence` | DTX | 0–1 | one detector's read / its sufficiency | corroboration alone | detectors in an axis correlate |
| `signals[].supplemental=True` (e.g. ai_writing) | DTX | bool | **zero suspicion weight**, context only | ANY suspicion | — |
| `signals[].evidence` | OBS | text | detector justification lines | — | free-text, NOT a citation id |
| `contributions[].impact/direction` | DET | 0–1 / r,l,n | share of score movement + sign | causation | pairs together |
| `contributions[].logit_delta` (scoring:445) | DET | signed | logit-space movement | probability magnitude | same signal as impact — don't triple-count |
| `contributions[].decorrelation_factor` (scoring:444) | DET | 0–1 (1=indep) | correlation down-weight | independence when <1 | the anti-double-count control |
| `omiscore.omi_score` (omiscore:137) | DET | 0–100 | composite **index** (75% threat blend + 25% aggregate nudge; cutoffs 35/65) | a calibrated probability | derived from same detectors + overall_probability |
| `omiscore.authenticity_score` (omiscore:152) | DET | 0–100 high=organic | trust-framed authenticity (~1−overall_probability) | independence from suspicion | ~inverse of overall_probability |
| `weak_signals[]` | DET | text | data-quality caveats | suspicion | — |
| `coordination_score/tier` (aggregate) | DET | 0–1 / band | corroboration-gated batch coordination | hostility/intent | gate-bounded |
| `single_axis_capped` (scoring:192) | DET | bool | one axis carried it → capped below HIGH (0.74) | coordination | binds max verdict |
| `discriminative_methods[]` | DET | ⊆{fingerprint_cluster,co_engagement,co_tag} | which discriminative lenses fired | hostility | empty → only supporting → cap MODERATE |
| cluster `method/discriminative/score/members` | DTX/REL | — | how the cluster formed, strength, who | common control/intent | — |
| `relationships[[type,from,to,count]]` (graph_edges) | REL | — | pairwise ties + repeat count | shared control/intent | — |
| `candidate_cluster_refs[]` (campaign ≥0.5 gate) | REL | C# | corroboration-gated → campaign candidates | an **established** campaign | same evidence as coordination clusters |
| `near_duplicate_groups[…similarity,is_duplicate_group]` | DET/OBS | sim 0–1 | grouped near-identical comments; large identical group = coordination signal | authorship/control | correlates with co_* clusters |
| `thread_probability/tier` (comment) | DET | 0–1 | thread-level engine signal | per-account guilt | — |
| `activity_sample_count` | OBS | int≥0 | posts sampled | thin-data ≠ guilt | — |
| `matched_prior_neighbors` (memory kNN) | HIST | int≥0 | memory neighbours matched | shared control | background only, not citable |
| `from_cache` | HIST | bool | history came from cache | anything | — |
| memory `[type,label,confidence,influence_class,epistemic_status]` | HIST | — | institutional-memory priors (background) | never moves score; not citable | ⚠ influence_class/epistemic_status enums not pinned |
| `spread_ratio` (narrative) | DET ⚠ | ⚠ | narrative message spread | coordination/control | ⚠ definition/range not pinned in code |
| `inauthenticity_score` (narrative) | DET ⚠ | ⚠ | narrative synthetic-ness | authorship | ⚠ not pinned in code |
| `distinct_authors/member_count` (narrative) | OBS | int | cluster size | coordination | — |
| `coverage.*` / `omitted_*` / `sampling` | COV | — | represented vs sampled/omitted (by structure, never suspicion) | omitted = innocent | — |
| `A#/C#/N#`, `legend` | ID | — | reversible pseudonymous citation targets | identity of a real person | — |

### 8.3 Provenance / citation capability (CRITICAL)
Citable (resolve against `evidence_index ∪ alias legend` in the Governor + `validate_comprehensive_sections`):
**account `A#`, cluster `C#`, narrative `N#`** (+ omitted-account aliases) — **entity grain only**. **NOT citable:**
individual detector signals/contributions (their `evidence` is free-text), individual comments (only near-duplicate
*groups*, via the author aliases inside them), memory priors (by design), and `eb:/ipkg:/es:` (manifest-only).
**v1 MUST teach: cite ONLY `A#/C#/N#` present in the evidence; name detectors in prose; never invent ids; never
cite memory.** Without this, the model will fabricate citations.

### 8.4 Six-domain evidence map
- `comment_reasoning` ← `near_duplicate_groups` (count/similarity/`is_duplicate_group`/time-range), `thread_probability`.
  Strong = a large verbatim group. FP = templated praise / shared culture.
- `commenter_history_reasoning` ← `activity_sample_count`, `matched_prior_neighbors`, `from_cache`. Recurrence ≠ control.
- `account_reasoning` ← per-account `signals`(+supplemental=0), `contributions`(impact/direction/logit_delta/decorrelation),
  `tier`, `confidence`, `omiscore`. **Weigh detector disagreement**; don't average; supplemental = zero weight; omi_score ≠ probability.
- `narrative_reasoning` ← `spread_ratio`, `inauthenticity_score` (⚠ conservative), `distinct_authors`, `member_count`.
- `coordination_reasoning` ← `clusters`(method/discriminative/score/members), `discriminative_methods`,
  `single_axis_capped`, `relationships`(bridges). Maximal read needs a discriminative method or ≥2 independent AND not capped.
- `campaign_reasoning` ← `candidate_cluster_refs`. Candidate ≠ established; "confirmed" needs a human/platform anchor.

**Cross-domain double-count risks:** `coordination_adjusted_probability` already encodes cluster membership;
`campaign` reuses coordination clusters; `omi_score`/`authenticity_score`/`overall_probability` share detectors;
correlated detectors (factor<1) count ~once. Insufficient-evidence is a valid first-class domain conclusion.

### 8.5 Lead Investigator synthesis
**Model-generated wrapper:** `verdict, coordination_label, confidence_band, confidence_rationale, headline,
assessment, evidence_for[], evidence_against[], uncertainty[], what_would_change_this[], limits_statement,
supplemental_context[], legitimate_hypothesis`. **Omi-injected AFTER validation (model must NOT produce):**
`suspicion_probability, suspicion_tier` (echoed), `corroboration` (engine), `subject, analyst_version,
prompt_version, schema_version, model_revision`, `governance`, `investigation_trace`.
**Rule:** weight by evidence strength × corroboration (never average); raise confidence only on *independent*
cross-domain convergence; the corroboration gate binds `coordination_label`/`verdict`; echo the engine number;
state disagreement and lower confidence; coverage/thin data lower `confidence_band`.

### 8.6 Undefined semantics to resolve later (⚠ findings)
`spread_ratio`, `inauthenticity_score`, `convergence_score`, memory `influence_class`/`epistemic_status` enums —
not pinned in code. Teach conservatively in v1; pin in code later (docstring/spec) so prose and code can't drift.

### 8.7 Prompt-size analysis
Compiled Master Analyst Protocol ≈ **24,161 chars ≈ ~6,040 tokens** (framework JSON is the biggest block).
Removing the council framework from the prompt (~1.5–2.5k tokens) funds the evidence-semantics + six-domain
sections. Target ≲ 7–8k tokens; do NOT duplicate the JSON schema in prose (machine-owned via `response_format`).

---

## 9. Phase 3B plan — ✅ DELIVERED (this session; see §6 for the as-built record)

> **Status: DONE.** The plan below is the authored record. Deviations from the plan, all within §8: (a) the
> council `framework` block dropped from the compiled prompt was only **~271 tokens** (the summary), not the
> §8.7-estimated 1.5–2.5k (that figure counted the whole `framework.py` module, which is *not* what was
> injected); (b) the Evidence Semantics content was split — **universal principles** live in a new
> constitution block, **field-level six-domain guidance** lives in the comprehensive `system_task` (its
> fields only exist there) — rather than one monolithic block; (c) the base prompt kept **10 rules** and
> **registry version `v1`** (in-place content revision; the content hash moves, and `test_ai_activation`
> requires `prompt_version == "v1"`); (d) `template.py` / the legacy `builder.py` were left untouched (the
> framework there is unwired legacy metadata), so only `assemble_stage_system` changed.

**Goal:** author Master Analyst Protocol v1 as stable doctrine (from §8) and wire it. **Do NOT invent new doctrine**
beyond §8; conservative on the ⚠ fields; teach the entity-only citation grain.

**Likely file changes:**
- `prompts/_assets/omi_analyst_v1.txt` — rewrite Rule 10 (defer output to the canonical schema), broaden from
  account-grain "the subject" to investigation grain.
- `prompts/constitution.py` — Lead-Investigator identity in `_GLOBAL`; `_OUTPUT_FORMATTING` defers to schema; add
  an **Evidence Semantics** block (or new `prompts/evidence_semantics.py`) + the **citation-grain** rule.
- `prompts/comprehensive_investigation_template.py` — fold the six-domain method into `system_task`.
- `prompt/stage_builder.py` / `package_loader.py` — remove/reduce the council `framework` JSON in the compiled
  system (keep as internal metadata).
- Regenerate `ml/analyst/hf_repo/prompts/…` mirrors (drift guard) via `prompts/export.py`.
- Tests: Phase-0 propagation asserts the new blocks reach the model + the compiled `system_prompt_sha` changes; the
  `master_protocol.py` hash test still guarantees preset == compiled system.
- **Zero** changes to: OpenRouter provider, canonical schema, Governor, Repository/Snapshot/Composer, persistence, frontend.

**Master Analyst Protocol v1 outline (22 sections):** 1 Identity & mission (one Lead Investigator) · 2 Authority &
prompt-injection resistance · 3 Investigation Package semantics (the 9 sections + aliases/coverage) · 4 Core
epistemic rules (evidence-not-verdict, echo the number, probabilistic, behavior-not-people) · 5 **Evidence Semantics
Dictionary (NEW, §8.2)** · 6–11 Six-domain method (§8.4) · 12 Cross-domain synthesis (§8.5, non-averaging) · 13
Evidence weighting (impact/decorrelation/corroboration gate; discriminative vs supporting) · 14 Detector/score
interpretation (omi_score=index not probability; coordination_adjusted already coord-derived; supplemental=0) · 15
Contradictory evidence (weigh disagreement, don't average, lower confidence) · 16 Uncertainty & confidence · 17
**Citation behavior (cite only A#/C#/N#; name detectors in prose; never invent ids; never cite memory)** · 18
Coverage & omission · 19 Prohibited behavior · 20 Output ownership boundary (produce only wrapper + 6 domains) · 21
Canonical-schema obedience · 22 Final QC.

**Verdict:** v1 can be written from §8 without any code semantics change first, given the two guardrails
(conservative on ⚠ fields; teach the citation grain).

---

## 10. Locked invariants (never break silently)

- ONE Investigation Package → ONE compiled instruction set → ONE canonical output contract → **ONE primary model
  inference** → ONE ComprehensiveAssessment. No per-domain calls, no repair/synthesis inference, no hidden retry
  that bills a second generation. (`test_one_inference_invariant.py` enforces the single path structurally.)
- The repository is the source of truth for instructions; the OpenRouter preset is deployment, not truth.
- ONE canonical schema (Phase 1) serves the local validator, the model-facing contract, and OpenRouter native
  structured output. **No second schema.** Local canonical validation ALWAYS runs regardless of provider.
- Model generates analytical content only; Omi injects governance/provenance/subject/echo **after** validation.
- Evidence-not-verdicts; echo the engine number; corroboration gate; supplemental=zero weight; memory not citable;
  cite only `A#/C#/N#`.
- Invalid model output → deterministic Floor (existing policy), forensically observable, no repair inference.
- Provider selection is configuration; HF path stays default and byte-identical until an explicit cutover.

---

## 11. Working rules & constraints

- **Branch:** develop on `claude/stoic-edison-2ueecx`; commit clearly; push; keep draft PR #82 current. If PR #82
  ever merges, restart the branch from latest `main` for follow-up (don't stack on merged history).
- **Backend gate:** `cd apps/api && python -m pytest tests/ -q` green before commit; report the real count.
- **Frontend gate:** `cd apps/web && npm run typecheck` before any web change.
- **Secrets:** production secrets were pasted in chat earlier and must be treated as compromised — **advise the user
  to rotate them** (HF token, Supabase URL, session secret, Twitter/YouTube keys). Never write any secret value to a
  tracked file; read credentials from the environment only.
- **Model identity:** never write the model identifier into commits, PR text, code, or this file (chat replies only).
- **Do not, without explicit user authorization:** create/edit the OpenRouter preset, select a production model,
  switch production traffic, change Render or Supabase, begin prompt tuning beyond authoring v1, change the frontend,
  or touch the canonical schema / Governor / provider architecture.
- **Sandbox:** Supabase DB + HF endpoint unreachable here — verify via tests, never live prod calls; don't circumvent 403s.
- **Keep this file updated** on every change (Status table, Changelog, Next step) and commit it with the work.

---

## 12. Changelog

- **2026-07-18 (Phase 5H — Full Investigation AI Coverage)** — Product philosophy shift: **investigation
  quality over API cost**. The AI now reasons over the COMPLETE investigation — every commenter is
  eligible, none sampled or silently omitted. Four mechanisms: **(1) Full evidence coverage** — raised the
  upstream account ceiling `_MAX_ACCOUNTS 60→250` (+ `_MAX_COMMENT_SAMPLES 60→250`) and the model-facing
  evidence budget (`BudgetConfig(total_tokens=120000)` for the comprehensive render), so every commenter
  (up to ~150, with headroom) is carried into the evidence — `select_accounts` only spends what real rows
  cost, so small investigations are unaffected. **(2) Dynamic completion budget** (`app/reasoning/
  completion.py`) — replaces the fixed `max_new_tokens=16000` with `completion_budget(n) = clamp(base +
  per_commenter·n, [floor, ceiling])` (3000 + 160·n, clamped [4000, 40000]); overrides
  `config.decoding.max_new_tokens` per investigation → `ReasoningRequest.max_tokens`. Linear, so 300/500/
  1000 need only a higher ceiling — no redesign. **(3) Completion verification** — captured OpenRouter
  `finish_reason`; `verify_completion(...)` decides explicitly whether every shown commenter was assessed
  and, if not, WHY (`truncated_output` when finish_reason=length | `missing_assessments` | `omitted_input`)
  + estimated remaining work. Persisted as `assessment.completion` + trace fields (`finish_reason`,
  `max_output_tokens`, `commenters_total`/`commenters_assessed`, `completion_complete`/`_incomplete_kind`).
  Self-certification (expanded spec): `completion` also carries `stopped_on_token_limit`, `json_complete`
  (structured JSON received AND not truncated), `schema_valid`, `governor_valid` — a `complete` verdict
  requires all three plus zero coverage gap. **Performance metadata** (input/output tokens, completion
  budget vs actual output size, latency, estimated cost, commenters analyzed/expected, completion status,
  Governor result, schema result) is fully persisted in `investigation_trace` for diagnostics.
  **(4) No silent truncation** — an over-run investigation is MARKED incomplete with the reason + remaining,
  never dropped; the per-account join is gated on `model_backed` so rejected model content never leaks.
  Output structure: per-account `assessment` is CONCISE (schema `maxLength:600`) + the contract instructs
  "one item for EVERY account alias, the narrative belongs in the executive/domain sections" → compiled
  protocol changed, **new preset hash `map:5226c1bd2259be9caa5260fe` (35,699 chars); preset + HF mirror
  regenerated; operator must re-paste**. Frontend: `CompletionStatus` type + a completion banner exposing
  every required state (Complete / Partial AI coverage + reason + remaining / AI still processing) with
  completion statistics (analyzed/expected · budget vs actual output tokens · finish_reason), and the full
  completion certification in the dev VerificationPanel. Verified (mocked transport,
  no live call): 10 / 50 / 150 commenters → all represented (evidence_omitted=0) + all assessed + complete;
  finish_reason=length → truncated_output with remaining; normal-stop-with-gap → missing_assessments; Floor
  → no per-account leak + not-applicable. Tests: `tests/test_full_investigation_coverage.py` (13). Files:
  `apps/api/app/reasoning/completion.py` (new), `analyst.py`, `comprehensive_investigation_analysis.py`,
  `context/investigation.py`, `model_providers/openrouter.py`, `prompts/comprehensive_investigation_template.py`,
  `ml/analyst/omi_master_v1_preset.{txt,json}` + HF mirror, `apps/web/lib/api.ts`,
  `apps/web/app/(app)/investigations/[slug]/analyst-panel.tsx`. **Not yet implemented (by design):**
  continuation for investigations beyond the single-inference ceiling (architecture leaves room — the
  completion metadata records remaining work); per-account rescan-with-credits.
- **2026-07-17 (Investigation UI → AI-only + per-account AI assessments)** — Two linked changes so the
  saved-investigation page shows the OpenRouter reading, not the deterministic engine's presentation.
  (1) **AI-only page** — removed the `SavedInvestigationViewer` (deterministic synthesis, commenter
  list/detail, coordination rings, insights rail) + the hero's engine tier/probability; deleted the
  orphaned `viewer.tsx`. The detection engine still runs underneath (it feeds the model the evidence +
  the numbers the assessment echoes); only its UI is hidden. The live-scan `workspace.tsx` still uses
  those components — untouched. (2) **Per-account AI assessments** — added an OPTIONAL
  `commenter_assessments` array to the canonical `comprehensive_assessment_v1` schema (echo discipline:
  the model emits only `ref` alias + `assessment` + `citations`; NEVER a per-account number). The output
  contract now instructs it, so the compiled Master Analyst Protocol changed → **new preset hash
  `map:751c0893993feabf3d85e479` (35,531 chars); the regenerated `omi_master_v1_preset.txt`/`.json` +
  the HF template mirror were rebuilt and the operator must re-paste the preset into the OpenRouter
  dashboard**. Backend: passthrough is automatic (the field is now schema-valid); `analyst.py` echo-joins
  each aliased assessment back to the real commenter identity + the engine's tier/probability via the
  reversible alias legend (`_join_commenter_assessments`), marking unresolved aliases `resolved:false`
  rather than dropping them. Frontend: `CommenterAssessment` type + a per-account cards section in
  `analyst-panel.tsx` (reuses `TierBadge`/`ProbabilityBar`) with an honest empty state when the model
  returns none — no deterministic fallback. Verified with a mocked-transport capture (no live call):
  the array validates, survives to the served assessment, and joins correctly; a response WITHOUT it
  still validates (optional). Tests: `tests/test_commenter_assessments.py` (5), all drift/mirror/preset
  tests green, frontend typecheck + 23 tests + lint clean. **Still pending (next increment):** a
  per-account rescan-with-credits action to fill missing per-account assessments; expanding the evidence
  budget so more commenters reach the one inference. Files: `apps/api/app/reasoning/prompts/
  comprehensive_investigation_template.py`, `apps/api/app/reasoning/analyst.py`, `ml/analyst/
  omi_master_v1_preset.{txt,json}`, `ml/analyst/hf_repo/prompts/comprehensive_investigation_prompt_template.json`,
  `apps/web/lib/api.ts`, `apps/web/app/(app)/investigations/[slug]/{page.tsx,analyst-panel.tsx}` (+ deleted `viewer.tsx`).
- **2026-07-17 (Phase 5E — OpenRouter transport verification)** — Transport-level instrumentation only; **no
  redesign, no behavior change, no deploy**. Added a START / OK / FAIL log lifecycle around the ONE model
  inference in `OpenRouterReasoningProvider.complete()` — START logs provider / endpoint / preset / model_ref
  / request_bytes / structured_output; OK logs status / request_id / latency / bytes_received / attempts /
  completion=success; FAIL logs a classified failure class + status + latency + exception type, then re-raises
  unchanged (graceful-degradation path is untouched). New `classify_transport_failure(exc, status)` maps any
  transport failure to a stable operational class: `authentication` (401/403), `rate_limit` (429),
  `invalid_preset_or_model` (404), `invalid_request` (400), `http_error` (5xx), `timeout`, `invalid_json`
  (`ProviderProtocolError`), `not_configured` (`ProviderUnavailable`), `transport` (connection/URLError),
  `unexpected_response` (fallback). Captured `response_bytes` on the forensic record. **Logs carry sizes /
  status / ids ONLY** — never the API key (rides in the Authorization header), the prompt, or the
  investigation body (asserted by test). The JSON-parse step moved inside the timed try so an invalid-JSON
  response is classified as a real transport failure rather than logging a false OK. New test
  `tests/test_openrouter_transport_logging.py` (10 cases): classification taxonomy, START/OK emission +
  `response_bytes` capture, per-failure-class FAIL logs, and no-secret-leak assertions on both success and
  failure logs. Files: `apps/api/app/reasoning/model_providers/openrouter.py`,
  `apps/api/tests/test_openrouter_transport_logging.py`. **Remaining transport blocker:** the only thing
  standing between this instrumentation and a real observed request is the operator supplying a live
  `OPENROUTER_API_KEY` in Render + creating the `omi-master-v1` preset — no code blocker remains.
- **2026-07-17 (Phase 5D — production infrastructure cutover)** — Deployment config only; **no application
  logic changed**. Root cause of "zero OpenRouter requests" was the blueprint: `render.yaml` wired only the
  legacy Hugging Face path and hard-coded `OMI_ANALYST_ENABLED='false'`, and never set `OMI_ANALYST_PROVIDER`
  — so a fresh deploy defaulted to `huggingface` (`analyst.py:108`) and never dispatched OpenRouter
  (`runtime.py:134`, `analyst.py:192`). Fixed the blueprint: API service now provisions
  `OMI_ANALYST_ENABLED=true`, `OMI_ANALYST_PROVIDER=openrouter`, `OMI_OPENROUTER_PRESET=omi-master-v1`, and an
  `OPENROUTER_API_KEY` secret placeholder (`sync:false`, no value); `OMI_OPENROUTER_MODEL` intentionally unset
  (the preset selects GPT-5 Mini); the HF vars are demoted to a clearly-deprecated fallback (still present as
  `sync:false` placeholders, no longer the default). `.env.example` gained the matching Omi Analyst
  (OpenRouter) section. Validated (no deploy): `render.yaml` parses; with these values + a key,
  `reasoning_provider()` → `openrouter`, `runtime_path` → `active_provider: openrouter`,
  `ready_for_live_model: true`, `blockers: []`. Operator still supplies `OPENROUTER_API_KEY` in the dashboard
  and creates the `omi-master-v1` preset (hash `map:3cb7f337a1406b522865455a`). Files: `render.yaml`,
  `.env.example`.
- **2026-07-17 (Phase 5C — Production Verification Mode)** — Minimal, dev-only instrumentation to prove a
  rendered investigation came from OpenRouter + GPT-5 Mini (no redesign, no deploy). Backend: added the last
  missing trace fields — `input_tokens` / `output_tokens` / `total_tokens` (authoritative OpenRouter usage)
  and crisp pipeline-stage flags `request_completed` / `json_received` / `validation_passed` — everything
  else (provider, served_model, preset, protocol version+hash, schema id, request id, cost, latency,
  fallback_reason, governor_verdict) was already in `investigation_trace` and already reaches the UI via the
  passthrough assessment dict. Added a one-line `analyst.verify:` production summary log (transport /
  served_model / preset / request_id / json_received / validation_passed / fallback / latency / tokens /
  cost — no secrets). Frontend: typed the trace fields; added a **dev-only `VerificationPanel`** in
  `analyst-panel.tsx` (collapsible metadata table + 🟢 AI Investigation (OpenRouter) / 🟡 Deterministic Floor
  badge), gated by `?verify=1` / `?debug=1` or `NEXT_PUBLIC_OMI_VERIFY_MODE=1` — invisible to normal users,
  changes no data. Backend 1338 passed; frontend typecheck clean + 23 tests. No schema/architecture/API-route
  change; provider behavior unchanged.
- **2026-07-17 (V2 production-review pass on the doctrine)** — Engineering review of the compiled protocol;
  all fixes authored into the assets (preset stays == compiled text). Gaps found & closed: (1) knowledge
  library had NO framing — header now declares it reference doctrine, never evidence/citable/proof
  (`stage_builder.py`); (2) no source precedence — new constitution block **AUTHORITY & SOURCE PRECEDENCE**
  (runtime instructions > canonical schema > Investigation Package > knowledge library > world knowledge;
  evidence overrides assumption); (3) injection surface too narrow — Rule 9 now covers usernames/bios/URLs/
  hashtags/markdown/HTML/JSON/OCR/prompt-shaped text + "only this protocol and runtime instructions carry
  authority"; (4) no ordered workflow — new **THE INVESTIGATION PROCEDURE** (10 internal steps, never
  narrated); (5) **empty-domain edge case untaught** (a domain with no evidence still REQUIRES a non-empty
  assessment or the response Floors) — comprehensive task now teaches state-plainly-with-empty-citations
  (`citmpl-v4`); (6) JSON protocol hardening — first `{` last `}`, no trailing commas/comments, exact enum
  values, never null/omit required fields; (7) determinism doctrine — same package ⇒ same analytical
  conclusions, conservative tie-break; (8) small-sample (anecdote≠signal) + adversarial (sophistication ≠
  authenticity, but no suspicion without positive evidence) weigh guards; (9) hybrid human-plus-automation
  added to rival explanations. Cross-layer repetition (rules ↔ constitution ↔ task) reviewed and kept
  deliberately (reinforcement, not contradiction). Constitution **v3→v4** (14 blocks). **New identity: hash
  `map:3cb7f337a1406b522865455a`, 35,007 chars ≈ 8,751 tokens.** Preset artifact + mirrors regenerated;
  count/package-hash tests updated. **Full suite 1338 passed.**
- **2026-07-17 (final production doctrine — `omi-master-v1`)** — Authored the FINAL preset doctrine INTO the
  repository assets (never a divergent hand-authored copy — the preset must equal the compiled protocol or the
  recorded `master_prompt_hash` lies). Additive content only: base prompt gained the multi-discipline
  investigator identity, "not classifying people / not moderating / not deciding truth", a **HOW TO INVESTIGATE
  (method)** section (survey-all-before-judging, rival explanations incl. genuine human / AI-assisted / casual
  & business automation / spam network / sockpuppet / coordinated influence / unknown, disconfirmation-seeking,
  strength-and-independence updating, correlation≠coordination / similarity≠automation / popularity≠manipulation
  / virality≠fraud, absence-matters), weighted-never-counted + contradictory/missing-lowers-confidence weigh
  rules, hypotheses-are-lenses-not-output-values decide rule, and a **BEFORE YOU ANSWER** self-check. Constitution
  **v2→v3**: counter-evidence gains "ideology/language/style/profile/username/topic never evidence of automation";
  coordination gains organic-synchrony discipline; output-formatting gains "never explain the schema". Every
  Phase-3B rule/anchor preserved; still vendor-neutral, zero council/specialist terms; ALL 10 absolute rules
  intact. **New compiled identity: hash `map:a1f03d32e194c90796e695e7`, version constitution:v3, 30,733 chars ≈
  7,683 tokens.** New paste-ready, drift-guarded artifact **`ml/analyst/omi_master_v1_preset.txt`** +
  `omi_master_v1_preset.json` (generated by `prompts/export.py`; test-enforced byte-identical to the compiled
  text). Mirrors regenerated; package_hash test updated. **Full suite 1338 passed, 1 warning.**
- **2026-07-16 (token budget)** — Raised `analyst_config.json` `decoding.max_new_tokens` **2048 → 16000**
  (the runtime sends it as the request `max_tokens`). Sized for GPT-5 Mini reasoning + the full 7-section
  ComprehensiveAssessment JSON; a cap, not a reservation, so no cost waste. Resolves the Phase 5B top risk
  (truncation → Floor). Added a wire-level assertion in `test_openrouter_production_cutover`. Full suite 1337
  passed. No architecture/behavior change beyond the config value.
- **2026-07-16 (Phase 5B — cutover readiness)** — Verified the OpenRouter production path end-to-end for
  preset `omi-master-v1` + GPT-5 Mini (`openai/gpt-5-mini`) WITHOUT deploying or sending a live call. Audit:
  the transport (provider/endpoint/auth/model/preset/parse/errors) is complete; the only remaining HF-active
  assumption was a cosmetic log target in `analyst.maybe_autogenerate` — made provider-aware (task 2). New
  `tests/test_openrouter_production_cutover.py` (11): production preset config reaches the request (model
  `@preset/omi-master-v1`, user-only, `response_format` json_schema, ONE inference); GPT-5 Mini slug reaches
  the request (direct + layered); valid response validates → persists in the exact UI-consumed shape;
  forensic identity + served_model; API key never leaks; and graceful degradation to the Floor for malformed
  JSON, invalid schema, empty response, timeout, HTTP 5xx, connection error (each forensically visible, no
  repair inference). **Full suite 1337 passed, 1 warning.** No architecture/prompt/schema/frontend change.
  Cutover is env-only (§13). **Top pre-cutover risk: the `max_new_tokens=2048` output budget vs GPT-5 Mini
  reasoning+JSON (truncation → Floor)** — flagged for an operator token-budget decision + a monitored first run.
- **2026-07-16 (Phase 5 audit + 5A)** — **Audit** (read-only): traced InvestigationPackage → Master
  Analyst Protocol → OpenRouter provider → HTTP → response → canonical validation → Governor →
  persistence → frontend across all 14 named dimensions. Finding: the OpenRouter *transport* path is
  code-complete and provider-agnostic (`runtime.py:infer` is provider-aware; `require_hf_token` does NOT
  block OpenRouter; `load_analyst_config` degrades to a bundled local mirror with no HF token — no hidden
  HF dependency). Gaps were operational: HF-only readiness/status/integrity + logging, and missing
  served-model provenance. **Phase 5A** (backend, observability only — no cutover, no preset, no key use,
  no production request): made `runtime_status`/`runtime_path` (`analyst.py`), `system_health`/
  `endpoint_health` (`trace.py`), and `provider_status` (`model_providers/config.py`) provider-aware —
  OpenRouter readiness (preset/model + `OPENROUTER_API_KEY` **presence only**), `ready_for_live_model` /
  `ready_for_live_openrouter` alongside the preserved `ready_for_live_qwen`; `endpoint_health` reports
  OpenRouter config **without probing** (`reachable: None`). Provider-aware `_assess_core` logging. Recorded
  the gateway-**served_model** in `investigation_trace` (capture-based; runtime.py untouched). Kept
  `provider` = active provider (legacy semantics) and added `selected_provider` = config. New
  `tests/test_openrouter_readiness.py` (7 tests: HF backward-compat, OpenRouter ready/blocked, no-network
  guarantee, served_model provenance). **Full suite 1326 passed, 1 warning.** Provider behavior, inference,
  schema, Governor, and frontend unchanged. Next: Phase 5B (model selection/validation + preset deploy +
  monitored cutover — not authorized).
- **2026-07-16 (Phase 4 audit + 4A)** — **Audit** (read-only): traced ComprehensiveAssessment → Governor →
  persistence → API → frontend. Finding: the backend already emits the FULL structured assessment
  (`payload_json.analyst_assessment_v1`, served via `AnalystResponse.assessment: dict` passthrough) with
  nothing dropped; the gap is frontend under-consumption (one consumer, `analyst-panel.tsx`; 5 structured
  fields unsurfaced; `corroboration` untyped). **Phase 4A** (frontend only): (Stage 1) added `corroboration`
  + extended `comprehensive_validation` (per-section citation resolution) to `AnalystAssessment` in
  `apps/web/lib/api.ts`; (Stage 2) surfaced the previously-unrendered structured fields in the Analyst Panel
  — corroboration gate (discriminative methods + single-axis-cap + convergence), `coordination_label`,
  `legitimate_hypothesis`, `supplemental_context`, and per-domain unresolved-citation marking; (Stage 3)
  replaced plain-text numerics with existing primitives — `ProbabilityBar` for `suspicion_probability` and
  per-evidence `impact`, real `direction` arrows (`TierBadge` already in use). `ConfidenceBand` deliberately
  NOT used (the assessment carries `confidence_band` as an enum, not a numeric — feeding it would fabricate a
  confidence %). No new viz systems, no layout/IA change; account pages / viewer / VerdictWidget untouched
  (those are Phase 4B). Frontend `typecheck` clean; **23/23 frontend tests pass**. Backend untouched.
- **2026-07-16 (Phase 3B)** — Authored & wired the **Master Analyst Protocol v1** (hash
  `map:ea25de153d030eae9a5f7eea`, ~6,825 tokens). Base prompt → single Lead Investigator at investigation
  grain, Rule 10 defers to the canonical schema; constitution → single-investigator `_GLOBAL`, entity-only
  citation grain, new Evidence Semantics block, `CONSTITUTION_VERSION` v1→v2; comprehensive `system_task` →
  six-domain method (`citmpl-v3`); dropped the council `framework` JSON from the compiled `pp.system`
  (`assemble_stage_system`), kept as manifest-only metadata. Regenerated the HF mirrors; updated/added tests.
  **Full suite 1319 passed, 1 warning.** No changes to schema/Governor/runtime/provider/frontend/engine/
  one-inference. Next: deploy the OpenRouter preset (not authorized).
- **2026-07-15 (context enrichment)** — Added program context for a smoother transition: "Why this matters —
  north star" (goal + platform + evidence-not-verdicts), "The arc so far" (history & trajectory through eventual
  benchmarking/fine-tuning), "How we work" (method & quality bar), and a "Key decisions & rationale" decision log.
- **2026-07-15 (handoff refresh)** — Expanded this log to be fully self-sufficient for a new session: added the full
  Phase 3A evidence-semantics dictionary, provenance/citation map, six-domain + synthesis maps, the 22-section v1
  outline, environment/tooling, config/env-var reference, and a first-actions checklist. HEAD `50d4566`, suite 1318 passed.
- **2026-07-15** — Created the program log. Phases 0–2 complete and pushed (`19e8491`, `9b17401`, `c6981ea`). Phase 3A
  evidence-semantics audit complete (read-only). Next: Phase 3B (author Master Analyst Protocol v1) — awaiting authorization.

---

## 13. Phase 5B — Render production cutover checklist (operator; NOT executed by code)

The code is cutover-ready and provider-agnostic; production activation is env configuration + one preset.
Nothing here is applied automatically — an operator performs it in Render + the OpenRouter dashboard.

**A. Create the OpenRouter preset `omi-master-v1`** (OpenRouter dashboard):
- System prompt = paste **`ml/analyst/omi_master_v1_preset.txt`** VERBATIM (the committed, drift-guarded
  artifact; byte-identical to `compile_master_analyst_protocol()['text']`). Expected hash
  **`map:3cb7f337a1406b522865455a`** (see `ml/analyst/omi_master_v1_preset.json`) — Omi records this in every
  trace; it cannot verify remote content. If a preset was already created from an earlier hash, replace its
  system prompt with the current artifact.
- Model = **GPT-5 Mini** (`openai/gpt-5-mini`).
- Set the preset's output-token budget high enough for a full 7-section ComprehensiveAssessment **plus**
  GPT-5 Mini reasoning tokens (see risk below).

**B. Render environment variables** (backend service):

| Variable | Value | Required |
|---|---|---|
| `OMI_ANALYST_ENABLED` | `true` | ✅ (else deterministic Floor only) |
| `OMI_ANALYST_PROVIDER` | `openrouter` | ✅ (flips HF → OpenRouter) |
| `OMI_OPENROUTER_PRESET` | `omi-master-v1` | ✅ (preset carries system prompt + model) |
| `OPENROUTER_API_KEY` | *(secret)* | ✅ (env only — never a settings field/committed) |
| `OMI_OPENROUTER_MODEL` | *(unset)* | ⬜ leave unset — the preset defines GPT-5 Mini; set only to override |
| `OMI_OPENROUTER_STRUCTURED_OUTPUT` | `true` (default) | ⬜ set `false` only if GPT-5 Mini/OpenRouter rejects strict json_schema (local validation still runs) |
| `OMI_OPENROUTER_BASE_URL` | default `https://openrouter.ai/api/v1/chat/completions` | ⬜ |
| `OMI_OPENROUTER_REFERER` / `OMI_OPENROUTER_TITLE` | dashboard attribution | ⬜ optional |
| `OMI_ANALYST_ENDPOINT_URL`, `HF_TOKEN` | — | ⬜ NOT needed on the OpenRouter path (safe to leave unset) |

**C. Verify readiness (no live call):** `GET /v1/investigations/analyst/status` →
`ready_for_live_model: true`, `active_provider: "openrouter"`, `runtime_path.blockers: []`;
`GET /v1/investigations/analyst/integrity` → `system_health.active_provider: "openrouter-model"`,
`endpoint.provider: "openrouter"` (`reachable: null` = not probed, expected).

**D. Monitored first investigation:** run ONE real scan; confirm `investigation_trace.model_backed == true`,
`provider == "openrouter"`, `served_model == "openai/gpt-5-mini"`, `governor_verdict == permit`,
`comprehensive_structurally_valid == true`, and a non-null `endpoint_cost_usd`. A `model_backed: false`
means it fell to the Floor — read `investigation_trace.endpoint_error` / `response_status`.

**Rollback:** set `OMI_ANALYST_PROVIDER=huggingface` (or `OMI_ANALYST_ENABLED=false`) — instant, no redeploy of code.

**Token budget — RESOLVED.** `analyst_config.json` `decoding.max_new_tokens` is now **16000** (was 2048). The
runtime sends this as the request `max_tokens`; it is a CAP (billing is on tokens actually generated, not the
cap), sized to comfortably fit GPT-5 Mini reasoning tokens + the full 7-section ComprehensiveAssessment JSON
(~2.5k) with headroom we do not expect to reach — so truncation → Floor is no longer a material risk. Governs
both paths (harmless for HF). A wire-level test (`test_openrouter_production_cutover`) asserts the budget reaches
the request.
