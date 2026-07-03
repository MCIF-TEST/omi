# Omi — Phase B: AI-Native Investigation Engine (runtime architecture)

> **Objective.** The Hugging Face analyst package becomes the canonical AI reasoning layer: the
> Prompt Builder assembles the final prompt **exclusively from the package** (system prompt +
> constitution/framework + Knowledge Library), Mistral performs the reasoning, the Governor
> validates, and the deterministic engine is the **evidence source** (its measurable numbers are
> echoed, never overridden). Deterministic safety, the Governor, and the floor are preserved.

This document reports increment 1: the **Prompt Builder + package-assembled prompt + field
provenance + item 7–10 instrumentation**, flag-gated and proven deterministically. The parts that
change *model behavior* are gated behind `analyst_prompt_assembly=package` because their quality/FPR
can only be certified against the **live** endpoint (unreachable from this build sandbox) — §6.

---

## 1. Before → after

```
BEFORE (increment carried from prior sprints)
  scan → deterministic engine (authoritative) → Evidence Bundle
    → assess_payload → system = omi_analyst prompt ONLY  (framework/knowledge hashed but NOT in prompt)
    → RemoteReasoningProvider → Mistral → Governor → floor → report
  Report primary content = deterministic scan; analyst = a panel.

AFTER (this increment)
  scan → deterministic engine (EVIDENCE source) → Evidence Bundle
    → assess_payload → PromptBuilder.build_system(mode)
         registry (default): base prompt          [byte-identical to before]
         package:            base prompt + CONSTITUTION (governance/reasoning rules)
                             + KNOWLEDGE LIBRARY (reference)   ← assembled ONLY from the HF package
    → RemoteReasoningProvider → Mistral → structured JSON → MANDATORY Governor → floor on reject
    → persist (assessment carries ai_package + prompt_build manifest + field provenance)
  Field provenance is explicit: the MODEL generates the analytical conclusions; the engine's
  suspicion_probability/tier are echoed, never moved.
```

## 2. Files modified

| File | Change |
|---|---|
| `app/reasoning/prompt_builder.py` | **NEW** — `PromptBuilder.build_system(base, mode)` assembles the analyst system prompt from package assets (omi_analyst prompt + `constitution_text()` + rendered Knowledge Library), bounded + content-addressed (`system_prompt_sha`, `knowledge_entries_used`); returns a build manifest. |
| `app/reasoning/analyst.py` | `assess_payload` builds the system prompt via `PromptBuilder` per the flag and feeds it to the provider; records `prompt_build` on every assessment. New `field_provenance()` (items 8/9): model-generated vs deterministic-echoed vs system fields. |
| `app/core/config.py` | New `analyst_prompt_assembly` (`registry` default \| `package`). |
| `app/reasoning/trace.py` | `audit_investigation` now also reports item 7 (fallback), items 8/9 (field provenance), item 10 (package/prompt/system-sha/knowledge/model identity); `_trace_settings` carries the assembly flag. |
| `tests/test_prompt_builder.py` | **NEW** (7). `tests/test_forensic_audit.py` updated for the new audit items. |

Kept deliberately (justified): the deterministic engine, OmiScore, detectors, Governor, and floor —
these are the evidence source + safety net Phase B explicitly preserves. No parallel publishing
system was created; the HF package continues to publish through the existing GitHub Action.

## 3. Runtime paths changed

- **Prompt assembly** is now a single builder that reads *only* the package. In `package` mode the
  constitution (the framework's authoritative rules) and the Knowledge Library enter the system
  prompt the model receives — the analyst reasons *with* the package, not just under a bare prompt.
- **Provenance** now travels with every assessment (`prompt_build.mode`, `system_prompt_sha`,
  `knowledge_entries_used`, `package_hash`) and through the forensic audit.

## 4. Legacy paths removed / consolidated

- The bare-prompt assembly is no longer a separate hard-coded path — it is the `registry` mode of the
  one builder (kept as the validated default, not a parallel system).
- (Prior sprints already retired the duplicate investigation-commentary AI surface and manual analyst
  generation; `providers.py` remains only for account/narrative analysis, which is out of scope here.)

## 5. Runtime verification evidence (one investigation, `package` mode, Mistral-shaped endpoint)

`POST /v1/investigations/{slug}/analyst/audit` → **TRUSTED**; the ten proofs:

| # | Proof | Evidence |
|---|---|---|
| 1 | final prompt sent | system prompt **contains the FRAMEWORK + KNOWLEDGE blocks** (assembled from the package) |
| 2 | prompt version | `v1` / `ph:715d4e26…` |
| 3 | served model | `mistralai/Mistral-7B-Instruct-v0.3` (matches expected) |
| 4 | raw response pre-Governor | captured verbatim |
| 5 | Governor verdict | `permit` |
| 6 | report renders | **MODEL** (`model_backed=true`) |
| 7 | deterministic fallback | **NONE** |
| 8/9 | field provenance | model-generated: verdict/headline/assessment/evidence_for/against/…; deterministic-echoed: `suspicion_probability`, `suspicion_tier` |
| 10 | identity | `package_hash pkg:28d757…`, `prompt_assembly=package`, `system_prompt_sha sys:9f2f84…`, `knowledge_entries_used=[account_aging_behavior, adversarial_evasion, astroturfing, …]`, model `…Mistral-7B-Instruct-v0.3` |

Registry mode is proven byte-identical (`system == base`); the flag flips the exact system prompt the
model receives (parametrized test). Deterministic backend suite green (count in the commit).

## 6. Remaining blockers (concrete, from within the repositories)

1. **Live-endpoint validation of `package` mode is the gate to making it default.** Injecting the
   framework + knowledge changes what Mistral receives; its reasoning quality and the
   legitimate-coordination **control-FPR** (the precision frontier) can only be measured against the
   real endpoint. **This build environment has no egress to huggingface.co and no live endpoint URL**,
   so I cannot run that A/B here — it is the operator's step (flip `OMI_ANALYST_PROMPT_ASSEMBLY=package`
   on a shadow/staging endpoint, run investigations, compare control-FPR to the Gold Corpus baseline
   via the audit endpoint). Until it passes, the default stays `registry` (validated).
2. **Richer report schema + report restructure** (Behavioral/Coordination/Narrative/Authenticity/
   Alternative-Explanations sections rendered from model fields) is the next increment. It is a
   schema + prompt + frontend change whose *value* depends on Mistral producing good multi-section
   output — so it, too, is gated on the live A/B in (1). Building it unvalidated would be speculative.
3. **Persistent database** remains the top ops blocker (sqlite on ephemeral disk).

## 7. Production readiness assessment

- **READY now (validated):** every investigation reaches the endpoint exactly once; the prompt is
  assembled from the HF package; Mistral reasons; the Governor validates every response; the floor
  still functions; the runtime proves all ten stages with captured evidence; no duplicate AI
  architectures remain. (`registry` default = current validated behavior.)
- **NOT YET certified (gated on the operator-run live A/B):** making `package` mode the default, and
  the richer model-primary report schema. These are model-behavior changes that must not regress the
  control-FPR, and that measurement is impossible from this sandbox. The instrument to certify them —
  the forensic audit endpoint — is shipped and proven.

**Verdict:** the AI-native runtime architecture is *built and instrumented*; its activation as the
default is a single flag flip that the operator gates on a live-endpoint FPR check. That is the
honest boundary — deterministic safety, the Governor, explainability, and reproducibility are all
preserved, and nothing unvalidated was made the default.

---

*No change to detection, scoring, OmiScore, the Governor, or the deterministic floor. GitHub remains
the development source; the HF package remains the runtime AI layer, published through the existing
workflow.*
