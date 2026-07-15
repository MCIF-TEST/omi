# OmiSphere AI Analyst — Program Log & Session Handoff

> **READ THIS FIRST.** This is the single source of continuity for the OmiSphere AI Analyst
> provider-independence program. A brand-new Claude Code session should be able to resume **flawlessly
> from this file alone**. **Whoever works on this program MUST update this file as part of every change**
> (new phase, new commit, new decision, new finding) — keep *Status*, *Changelog*, and *Next step* current,
> and commit the update alongside the work.

| | |
|---|---|
| **Last updated** | 2026-07-15 — handoff refresh + program context (north star, arc, method, decisions) for a new session (post Phase 3A) |
| **Repo** | `mcif-test/omi` (FastAPI `apps/api` + Next.js `apps/web` + `ml/analyst/` package) |
| **Working branch** | `claude/stoic-edison-2ueecx` |
| **Current HEAD** | `50d4566` (working tree clean at handoff) |
| **Pull request** | draft **PR #82**, base `main` — covers Phases 0–2 (+ this log) |
| **Verify command** | `cd apps/api && python -m pytest tests/ -q` |
| **Latest green suite** | **1318 passed, 1 warning** (pre-existing Starlette/httpx deprecation — unrelated, ignore) |
| **Next step** | **Phase 3B — author & wire Master Analyst Protocol v1** (NOT started; awaiting user authorization) |

---

## 0. First actions for a new session (do these in order)

1. `git checkout claude/stoic-edison-2ueecx && git pull` — confirm HEAD is at/after `50d4566`.
2. Read this whole file. It contains the full Phase 3A spec needed to write Phase 3B — you do **not** need the prior transcript.
3. `cd apps/api && python -m pytest tests/ -q` — confirm the green baseline (~1318 passed). Full suite ≈ 3.5–4.5 min.
4. Do **not** start implementing until the user issues the next phase authorization (see §1). Phase 3B is planned in §9 but **not authorized to build** yet.
5. When you make any change: keep the backend suite green, commit to the branch, push, keep PR #82 current, and **update this file** (§Status, §Changelog, §Next step).

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
| **3B** | **Author & wire Master Analyst Protocol v1** | ⬜ **NOT STARTED — planned in §9** | — |
| later | Deploy OpenRouter preset + select model + production cutover | ⬜ not started | — |
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
- `apps/api/app/reasoning/prompts/framework.py` — specialist-council catalog (injected as JSON; **candidate to
  remove from the prompt** — Phase 3A §7).
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

## 9. Phase 3B plan (planned; NOT authorized to build yet)

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

- **2026-07-15 (context enrichment)** — Added program context for a smoother transition: "Why this matters —
  north star" (goal + platform + evidence-not-verdicts), "The arc so far" (history & trajectory through eventual
  benchmarking/fine-tuning), "How we work" (method & quality bar), and a "Key decisions & rationale" decision log.
- **2026-07-15 (handoff refresh)** — Expanded this log to be fully self-sufficient for a new session: added the full
  Phase 3A evidence-semantics dictionary, provenance/citation map, six-domain + synthesis maps, the 22-section v1
  outline, environment/tooling, config/env-var reference, and a first-actions checklist. HEAD `50d4566`, suite 1318 passed.
- **2026-07-15** — Created the program log. Phases 0–2 complete and pushed (`19e8491`, `9b17401`, `c6981ea`). Phase 3A
  evidence-semantics audit complete (read-only). Next: Phase 3B (author Master Analyst Protocol v1) — awaiting authorization.
