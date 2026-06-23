# `ml/analyst/` — Omi Analyst specification (OMI_ANALYST_SPEC_V1)

> **Status: specification only.** Nothing here is imported by, wired into, or run by
> `apps/api` / `apps/web`. It does not modify the detection engine, scoring,
> coordination logic, or any API. It is the **operating manual** for Omi's future
> reasoning layer and the long-term Hugging Face strategy for evolving it.

## What Omi Analyst is

The **reasoning layer** that interprets evidence produced by the OmiSphere detection
engine and turns it into explainable, evidence-bounded investigation reports, verdict
recommendations, confidence assessments, counter-evidence, and uncertainty.

> **The foundation model is not the detection engine.** Detection (behavioral,
> coordination, narrative, neural-network, investigation evidence) is computed
> *before* the Analyst runs and is its **input**. The Analyst interprets evidence; it
> never recomputes a detector, overrides a score, or invents a signal.

- **Powered by:** `Qwen/Qwen3-4B-Thinking-2507-FP8` (HF, Apache-2.0, reasoning model).
- **Permanent home:** Hugging Face model repo `Andrewexiga/omi-analyst-v1` (private).
- **Evolution path:** V1 base → V2 prompt-engineered → V3 fine-tuned → V4 Omi reasoning model.
- **Slots into:** the existing `apps/api/app/reasoning/` seam (the `LLMProvider`
  protocol; today `TemplateProvider`/`AnthropicProvider`) as a future Qwen-backed
  provider — async, cached, with the deterministic template as the always-on fallback.

## Files in this folder

| File | Deliverable | What it defines |
|---|---|---|
| `OMI_ANALYST_SPEC_V1.md` | **A** | The full 21-section operating manual: mission, principles, evidence hierarchy & weighting, confidence/verdict/uncertainty/counter-evidence frameworks, the five investigation frameworks (account/campaign/narrative/comment/commenter), explainability, output standards, failure modes, safety. |
| `analyst_system_prompt_v1.md` | **B** | The V1 system prompt for the base Qwen model + how the user/evidence message is assembled. |
| `analyst_response_schema.json` | **C** | JSON Schema (draft 2020-12) for the Analyst's structured response. |
| `future_finetuning_strategy.md` | **D** | How future fine-tuning datasets are structured and how V1→V4 evolves. The honest blocker: gold reasoning labels (0 rows today). |
| `huggingface_model_lifecycle.md` | **E** | HF as the first-class registry/store/versioning layer; lifecycle tags, serving, rollback, cost. |
| `REPOSITORY_STRUCTURE.md` | **F** | Recommended layout of the `Andrewexiga/omi-analyst-v1` HF repo + companion dataset repos. |

## Core doctrine (inherited from `ai-context/VISION.md`)

Evidence, not verdict · probabilistic language only · describe behavior not people ·
respect the corroboration gate and single-axis cap · supplemental signals (AI-writing)
are context, never suspicion · always report counter-evidence · name uncertainty ·
the human analyst sets the verdict — Omi informs it.

## Honest status

- **V1 / V2 are achievable now** (base model + prompt + schema + eval set).
- **V3 / V4 are blocked on data** — analyst-verdict gold labels and worked reasoning
  traces are **0 rows committed** today. This mirrors the behavioral-model lesson
  (`ml/evaluation/behavioral_v2_audit/`): the binding constraint is data, not modeling.
- **No production change, no training, no deployment** was made by these specs.

## Read order

1. `OMI_ANALYST_SPEC_V1.md` (the manual) →
2. `analyst_response_schema.json` + `analyst_system_prompt_v1.md` (the contract) →
3. `future_finetuning_strategy.md` + `huggingface_model_lifecycle.md` +
   `REPOSITORY_STRUCTURE.md` (the long-term plan).
