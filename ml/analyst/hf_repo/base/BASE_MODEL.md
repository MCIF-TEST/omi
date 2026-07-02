# Base model — `omi-analyst-v1`

> **V1/V2 ship no weights of their own.** Omi Analyst V1 *derives from* a foundation
> model + the Omi system prompt + the response schema. This file is the **pointer** that
> records exactly which foundation model, so the running Analyst and its base stay
> reproducibly pinned together.

## Foundation model

| | |
|---|---|
| **Repo** | [`mistralai/Mistral-7B-Instruct-v0.3`](https://hf.co/mistralai/Mistral-7B-Instruct-v0.3) |
| **Architecture** | `mistral` · ~7.25B params · BF16 · instruction-tuned (v0.3: function-calling-capable, extended 32k vocab) |
| **License** | Apache-2.0 (permits private hosting, fine-tuning, redistribution of derivatives) |
| **Derives from** | `mistralai/Mistral-7B-v0.3` (base) |
| **Pinned revision** | `main` — **MUST be replaced with an immutable commit sha before serving** |

## Why a pointer and not weights

V1's value is the **contract** (system prompt + response schema + decoding config), not a
new checkpoint. Storing a pointer keeps the registry small, the provenance explicit, and
the upgrade path clean: V3 adds a small LoRA **adapter** over this same base (under
`adapters/`), and V4 may ship merged FP8 weights — both still record this base here.

## How "the model" is loaded (V1)

1. Resolve the **pinned base revision** of `mistralai/Mistral-7B-Instruct-v0.3` via
   `huggingface_hub` (or point an HF Inference Endpoint at it).
2. Apply this repo's `config/analyst_config.json` (decoding + schema pointer),
   `prompts/analyst_system_prompt_v1.md`, and `schema/analyst_response_schema.json`.
3. Generate and validate the final JSON object against the
   response schema before use (invalid → deterministic template fallback). The client's
   thinking-trace strip remains as an inert safeguard for thinking-variant models.

## Pinning discipline (non-negotiable before serving)

`main` is a moving reference and is **not reproducible**. Before any shadow/candidate/
production serving, pin `base_model_revision` in `config/analyst_config.json` to a
specific base-model **commit sha**, and pin *this* registry repo's own revision sha in
the serving config. See the GitHub `huggingface_model_lifecycle.md` §3/§5.
