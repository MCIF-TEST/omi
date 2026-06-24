---
license: apache-2.0
base_model: Qwen/Qwen3-4B-Thinking-2507-FP8
library_name: transformers
pipeline_tag: text-generation
tags:
- omisphere
- omi-analyst
- coordination-intelligence
- reasoning
- evidence-interpretation
- not-a-detector
language:
- en
---

# Omi Analyst — `omi-analyst-v1`

> **The foundation model is not the detection engine.** Omi Analyst is the
> **reasoning layer** that *interprets* the evidence the OmiSphere detection engine
> already computed. It never recomputes a detector, overrides a score, or invents a
> signal. It is **decision support for a human analyst — not a detector, not an
> enforcement system, and not evidence about any real person.**

This is the HF model card (root `README.md`) for the **permanent registry** of Omi
Analyst. Despite the `-v1` suffix, this single repo is the home for *all* Analyst
versions — V2/V3/V4 are **revisions + tags inside this repo**, never new repos (see
*Versioning*). The GitHub monorepo `omi/ml/analyst/` is the **source of truth** for the
spec/prompt/schema; this repo **mirrors** the approved, versioned artifacts and is the
runtime registry.

## Overview

| | |
|---|---|
| **Name** | `Andrewexiga/omi-analyst-v1` (private registry) |
| **Role** | Reasoning layer — interprets engine evidence into an explainable, evidence-bounded assessment |
| **Foundation model** | [`Qwen/Qwen3-4B-Thinking-2507-FP8`](https://hf.co/Qwen/Qwen3-4B-Thinking-2507-FP8) — qwen3, ~4.41B params, FP8, Apache-2.0, reasoning ("Thinking") variant |
| **Current version** | **V1** — base model + system prompt. **Ships no weights** (the *contract* is the artifact) |
| **Output** | A structured JSON object valid against `schema/analyst_response_schema.json` (draft 2020-12) + a human-readable report |
| **Prompt** | `prompts/analyst_system_prompt_v1.md` (`prompt_version: v1`) |
| **Config** | `config/analyst_config.json` (decoding, schema pointer, base-model pin), `config/generation_config.json` |
| **Promotion status** | **Not promoted** — registry/structure only. No shadow/candidate/production serving. |

## What V1 actually is

V1 is the **base Qwen reasoning model + the Omi Analyst system prompt + the response
schema**. There are **no fine-tuned weights** in this revision — loading "the model"
means: pull `Qwen/Qwen3-4B-Thinking-2507-FP8` at its pinned revision, then apply this
repo's `prompts/`, `schema/`, and `config/`. The reproducible artifact is the
**contract**, not a checkpoint. (V3+ adds LoRA adapters under `adapters/`; see the
GitHub `future_finetuning_strategy.md`.)

## Intended use & boundary

- **Intended:** turn an OmiSphere **evidence bundle** (detector contributions, OmiScore,
  coordination/narrative/campaign signals, investigation context) into a structured
  assessment — verdict *recommendation*, calibrated confidence, **evidence-for**,
  **evidence-against**, and **named uncertainty** — for a human analyst to act on.
- **Not intended:** as a detector or classifier, as an enforcement/automation trigger,
  or as a statement of fact about a real individual. It **echoes** engine scores; it
  does not produce them.
- **Doctrine (inherited from `ai-context/VISION.md`):** evidence not verdict ·
  probabilistic language only · describe behavior not people · respect the
  **corroboration gate** and single-axis cap · supplemental signals (e.g. AI-writing)
  are context, never suspicion · always report counter-evidence · name uncertainty ·
  the human analyst sets the verdict.

## Serving (honest engineering note)

A 4.4B FP8 reasoning model is **not** the CPU-only, in-process profile of the dormant
tabular scorer. The Analyst is served **off the request-critical path**: async +
cached, with the deterministic `TemplateProvider` as the always-on fallback, and is
**off by default**. A scan never blocks on the Analyst, and a HF outage cannot take
down OmiSphere (Render + Postgres remain the system of record). See the GitHub
`huggingface_model_lifecycle.md` §4–5 for the serving/rollback contract.

## Evaluation

**V1 has not been evaluated yet — and this card will not show fabricated metrics.**
The evaluation gate (schema-validity, faithfulness, calibration, verdict-bound
compliance, counter-evidence recall, **legitimate-coordination FPR**, banned-phrase
rate) runs against a held-out eval dataset (`Andrewexiga/omi-analyst-eval`) that is the
**V2 prerequisite and is not yet built**. Until that gate is passed, this revision
stays **pre-shadow / not promoted**.

## Limitations (stated plainly)

- **Gold reasoning labels = 0 rows today.** V1/V2 (base + prompt) are achievable now;
  **V3/V4 fine-tuning is blocked on data** — analyst-verdict gold and worked reasoning
  traces do not yet exist. This mirrors the behavioral-model lesson: the binding
  constraint is data, not modeling.
- **Domain shift:** the underlying engine is validated mostly on X/Twitter and YouTube;
  assessments outside that domain are weaker-grounded.
- **Inherits the evidence's limits:** the Analyst can only be as right as the evidence
  bundle it is given; it must surface that uncertainty, not paper over it.

## Versioning

- Every Analyst version is an **immutable HF revision (commit sha)** with a semantic tag
  (`v1`, `v2`, …) and a lifecycle tag (`shadow` / `candidate` / `production`).
- **Pin a revision sha, never `latest`** (reproducibility + safe rollback).
- One registry repo for all versions; a new repo is created only on a base-model
  **family** change.

## Provenance & licensing

Derived from `Qwen/Qwen3-4B-Thinking-2507-FP8` (**Apache-2.0**), which permits private
hosting, fine-tuning, and redistribution of derivatives — no licensing blocker for the
V1→V4 path. This registry repo is **private**.

## Source of truth

The authoritative spec lives in the GitHub monorepo, not here:
`omi/ml/analyst/` — `OMI_ANALYST_SPEC_V1.md` (operating manual),
`analyst_system_prompt_v1.md`, `analyst_response_schema.json`,
`future_finetuning_strategy.md`, `huggingface_model_lifecycle.md`,
`REPOSITORY_STRUCTURE.md`. This card and the files beside it are the **published
mirror** of those approved artifacts.

---

*Registry/structure only. No weights, no fine-tune, no training, no production wiring,
and no change to OmiSphere scoring, detectors, or OmiScore were introduced by this
repository.*
