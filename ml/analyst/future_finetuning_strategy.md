# Omi Analyst — Future Fine-Tuning Strategy (D)

> **Status: specification only.** No training, no dataset built, no checkpoint
> produced, no deployment. This defines *how* future Analyst fine-tuning datasets
> should be structured and *how* the model should evolve V1→V4 — so that when the
> prerequisite data exists, the path is already designed. It inherits the governance,
> anti-leakage, and anti-shortcut discipline proven necessary by
> `ml/evaluation/behavioral_v2_audit/REPORT.md`, `ml/corpus/CORPUS_AUDIT_V1.md`,
> `ml/schemas/OMI_LABEL_SCHEMA_V1.md`, and `ml/OMI_NEURAL_NETWORK_V1.md`.

---

## 0. The honest headline (read first)

> **The binding constraint on a fine-tuned Omi Analyst is DATA, not modeling** —
> specifically **analyst-verdict gold labels and worked reasoning traces, which are
> currently 0 rows committed** in this repository (`Investigation.verdict` is a
> runtime store; `OMI_LABEL_SCHEMA_V1` §E confirms the gold set is empty).
>
> This is the *same* lesson the behavioral model learned the hard way: V1's headline
> metrics were a mirage — 71% of its discrimination came from a username-string
> artifact, and behavior-only AUC collapsed to 0.546 (random) once the shortcut was
> removed. **Do not repeat that mistake on the Analyst.** A fine-tune on thin or
> engine-derived data would teach the Analyst to imitate the engine's verdicts (a
> reasoning shortcut), not to reason about evidence.

**Therefore:** V1 (base) and V2 (prompt-engineered) are the correct *first*
investments and are achievable now. V3 (fine-tuned) and V4 (Omi reasoning model)
are **blocked on collecting the gold reasoning dataset** described in §3.

---

## 1. The evolution path (what each version is and what it needs)

| Version | What it is | Training? | Prerequisite | Achievable now? |
|---|---|---|---|---|
| **V1** | **Base `Qwen3-4B-Thinking-2507-FP8`** + `analyst_system_prompt_v1.md` | None | The Evidence Bundle contract + system prompt (this folder) | **Yes** |
| **V2** | **Prompt-engineered Analyst** — refined prompt, few-shot exemplars, schema-constrained decoding | None (in-context) | A small **analyst-eval set** of hand-built bundles + reference assessments (§2) | **Yes (small effort)** |
| **V3** | **Fine-tuned Analyst** — SFT on `(bundle → JSON + report)` pairs | **SFT** | The **gold reasoning dataset** (§3): analyst-verdict labels + worked traces, governed, deduped, leakage-split | **No — blocked on data** |
| **V4** | **Omi-specific reasoning model** — preference/RL-tuned on analyst feedback | **DPO/RLAIF** | Accumulated **accept/edit/reject** feedback + failure-mode negatives (§4) | **No — blocked on V3 + feedback loop** |

The progression is deliberately **least-invasive-first**: get as far as possible with
prompting before spending a single training step, because (a) the Thinking model is
already a capable reasoner, and (b) the risk of a fine-tune is teaching the wrong
thing on weak data.

---

## 2. V2 prerequisite — the analyst-eval set (build this first)

A held-out evaluation set is required *before* any fine-tune, to measure whether a
change helped. It is also the seed for V3 data.

- **Unit:** one `(Evidence Bundle, reference assessment)` pair, where the reference
  is a **human-written** target output valid against `analyst_response_schema.json`.
- **Construction:** hand-build bundles that span the grains (account, campaign,
  narrative, comment_section, commenter) and the **failure-mode traps** from
  `OMI_ANALYST_SPEC_V1.md` §18 — thin data (must abstain), single-axis cap (must not
  over-call), legitimate coordination (must not flag a newsroom), supplemental-only
  (must not treat AI-writing as suspicion), conflicting evidence (must report both
  sides + lower confidence).
- **Size:** start at ~50–100 curated bundles (the same order as the engine's
  `seed_v1.json` benchmark, 65 cases). Quality over volume.
- **Home:** a private HF **dataset** repo (e.g. `Andrewexiga/omi-analyst-eval`),
  governed and versioned (see `huggingface_model_lifecycle.md`).
- **Metrics (the eval harness, `ml/analyst/` later):**
  - **Schema validity rate** (must be ~100%).
  - **Faithfulness** — every claim's `evidence_refs` resolve to a real bundle item
    (no fabrication, F1).
  - **Calibration of `confidence_band`** vs the engine confidence (no inflation, F2).
  - **Verdict-bound compliance** — never exceeds corroboration (F3/F4), `inconclusive`
    on insufficient data (F10).
  - **Counter-evidence recall** — `evidence_against` present whenever `lowers`
    contributions exist (F5).
  - **Banned-phrase rate** = 0 (F7).
  - **Agreement with the human reference verdict** (secondary — calibration and
    faithfulness lead, because Omi sells honest reasoning, not label-matching).

---

## 3. V3 prerequisite — the gold reasoning dataset (the real blocker)

This is the SFT corpus. It does not exist yet; this section specifies exactly how to
build it when the source data accrues.

### 3.1 Unit of training
One example = **`(Evidence Bundle input → target output)`**, where the target output
is the **full structured JSON** (`analyst_response_schema.json`) **plus** the rendered
human report (`OMI_ANALYST_SPEC_V1.md` §17), and — for the Thinking model — a
**reference reasoning trace** that walks the evidence to the verdict.

### 3.2 Where the data comes from (in priority order)
1. **Analyst-verdict gold** — `ml/datasets/analyst_verdicts/` (the designated gold
   store in `ml/README.md`) populated from exported, de-identified
   `Investigation.verdict` + `Investigation.payload_json` snapshots. The payload is
   the bundle; the analyst's `verdict` + `notes` anchor the target. **Currently 0
   rows — this is the collection priority.**
2. **Worked expert examples** — human analysts (or careful curation) authoring
   reference assessments over real bundles, especially edge cases and false-positive
   traps. The V2 eval set (§2) is the seed.
3. **Engine-derived bundles, human-authored targets** — bundles are cheap (run the
   engine offline over governed timelines); the *targets* must be human, not the
   engine's own verdict, to avoid the reasoning shortcut.

### 3.3 Hard rules (carried from the label/feature/corpus audits)
- **Engine-independent targets.** The target verdict must come from a human or
  platform anchor, **never** the engine's own `tier`/`overall_probability`/OmiScore —
  otherwise the Analyst learns to parrot the engine (the direct analogue of the
  username shortcut). The *bundle* legitimately contains engine outputs as evidence;
  the *target* must not be derived from them.
- **No confirmation-bias leakage.** Prefer targets authored **blind** to the engine's
  headline where feasible, or explicitly flag post-hoc targets (mirrors
  `OMI_LABEL_SCHEMA_V1` §D).
- **By-account / by-campaign / by-domain splits.** Never let the same account,
  campaign, or IO operation span train and eval — the corpus audit showed
  1.37M rows behind only ~10,239 accounts with 17.6% near-duplicates; tweet/bundle
  grain MUST use grouped splits or effective sample size collapses.
- **Global dedup before splitting.** Drop exact and near-duplicate bundles
  (the corpus has 36k exact + 230k near-dup texts) so metrics don't inflate.
- **Governance.** Source only `train`/`validation` per `datasets/manifest.toml`;
  quarantine/archive (poison) never enters a fine-tune set. PII stays
  hashed/pseudonymous.
- **Balance the traps.** Deliberately over-sample the precision-frontier cases
  (legitimate coordination, single-axis, thin data) so the Analyst is trained to
  *not* over-call — the opposite of optimizing raw accuracy.
- **Negatives included.** The failure-mode catalogue (§18) becomes **negative
  examples** — `(bundle → bad output)` pairs labeled as violations — used for V4
  preference data and for SFT "what not to do" contrastive pairs.

### 3.4 Target-output authoring standard
Every target JSON must itself pass the §2 metrics (schema-valid, faithful, calibrated,
bound-compliant, counter-evidence-complete, zero banned phrases). A target that
violates the spec poisons the model — targets are reviewed to the same bar as the
model's outputs.

### 3.5 SFT method (when data exists)
- **Approach:** parameter-efficient SFT (LoRA/QLoRA) on the base
  `Qwen3-4B-Thinking-2507` — small, CPU/GPU-modest, cheap, reversible (the adapter is
  a tiny artifact alongside the base pointer). Full-parameter tuning is unnecessary at
  this data scale and risks catastrophic forgetting of the base reasoning ability.
- **Format:** chat-format `(system, user=bundle, assistant=target JSON[+trace])`.
- **Reasoning supervision:** include reference Thinking traces so the model learns
  Omi's *weighing procedure* (rank by impact, honor the gate, surface counter-
  evidence), not just the final JSON.
- **Reproducibility:** every run records base-model revision, dataset revision,
  hyperparameters, seed, and emits a model card — identical discipline to
  `OMI_NEURAL_NETWORK_V1` §1.

---

## 4. V4 — the Omi-specific reasoning model

Once V3 is serving and a feedback loop exists:

- **Signal:** analyst **accept / edit / reject** actions on Analyst outputs in the
  product (a natural, low-friction preference signal), plus the §18 failure-mode
  negatives.
- **Method:** preference optimization (DPO or RLAIF) on `(chosen, rejected)` pairs —
  chosen = accepted/edited-to outputs, rejected = the original or a known violation.
- **Objective:** internalize what the prompt currently enforces externally — the
  corroboration gate, counter-evidence discipline, confidence calibration, abstention
  on thin data — so the model is robustly Omi-aligned even under prompt drift.
- **Guardrail:** preference tuning must not increase the over-call rate. The
  precision-frontier eval (legitimate-coordination FPR) is a **hard gate** on every
  V4 candidate, exactly as control-FPR gates the behavioral model.

---

## 5. Evaluation gates before any promotion (all versions)

A new Analyst revision is promotable only if, on the held-out eval set, it:
1. **≥ 99% schema-valid** output.
2. **0 fabrication** (all `evidence_refs` resolve) and **0 banned phrases**.
3. **No confidence inflation** and **no verdict-bound violations** (F2/F3/F4/F8/F10).
4. **Counter-evidence recall ≥** the prior version (F5).
5. **Does not regress legitimate-coordination FPR** — the precision frontier
   (Phase 3 discipline). A version that "decides more" by flagging benign
   coordination **fails**.
6. **Beats the prior version** on faithfulness + calibration by a pre-registered
   margin (else no promotion).
7. **Ships a model card** (data, metrics, limits, failure modes, intended use).

These map onto the HF lifecycle `shadow → candidate → production` flow in
`huggingface_model_lifecycle.md`.

---

## 6. What NOT to do (anti-patterns, learned from prior Omi ML work)

- **Do not fine-tune on engine verdicts as targets** — produces a reasoning shortcut
  (the Analyst analogue of the username artifact).
- **Do not optimize for verdict accuracy** — optimize for faithfulness + calibration +
  not-over-calling. Accuracy on an imbalanced/edge-heavy set is a mirage (corpus is
  89% positive).
- **Do not train before the held-out eval set exists** — you cannot tell whether a
  fine-tune helped without it.
- **Do not let the model fetch or assume data** — fine-tuning is on the fixed bundle;
  the Analyst never learns to "look things up".
- **Do not skip dedup / grouped splits** — near-duplicate IO bundles will inflate
  every metric.
- **Do not promote on V1-style headline numbers** — require the precision-frontier
  gate and a model card, every time.

---

*Specification only. No dataset, no training, no checkpoint, no deployment. The
prerequisite for a fine-tuned Omi Analyst is the gold reasoning dataset (§3); until it
exists, the value is in V1/V2 prompting and in collecting analyst-verdict gold.*
