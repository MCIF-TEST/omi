# OMI_ENGINEERING_SPRINT_009 — Contextual Reasoning (report)

> **Engineering sprint.** Improved the existing AI-backed Behavior Analyst by improving the
> **information it receives**, not the model or the council size. A deterministic **Context
> Builder** turns the Evidence Bundle + Institutional Memory into structured, **budgeted**,
> **fully-attributed** context — it never invents a fact, every synthesized statement keeps its
> evidence references, and the output is versioned + content-addressed. Quality metrics are
> exposed through Shadow Mode, which can now compare **raw evidence vs structured context** to
> decide whether structuring improves the read. No new specialist; the Governor is untouched;
> future AI specialists inherit the Context Builder with no architectural change.

## A. GitHub commits

One commit on `claude/stoic-edison-2ueecx`. One new package (`app/reasoning/context/`), plus
additive edits: the AI analyst gains a structured-context mode (raw stays the default), the
shadow runner records a `context` block + a raw-vs-structured comparison, two new settings, and
one admin route. **Zero** changes to the engine, scoring, OmiScore, the Binder, the Evidence
Bundle, the **Governor**, the Blackboard, the Contracts, or the Orchestrator control plane.
Sprint 002–008 paths run untouched; the raw prompt is byte-identical (the behavior analyst's
default behavior is unchanged).

## B. Context Builder implementation (`app/reasoning/context/`)

`build_context(bundle, store=…, budget=…)` is a **deterministic projection** of the Evidence
Bundle + Memory — it computes nothing and invents nothing. It produces the charter's sections,
each capped by budget and **fully attributed**:
- **behavioral_summary**, **strongest_supporting**, **strongest_contradicting** (ranked by
  impact; supplemental signals excluded), **uncertainty_summary** (contradictions / unknowns /
  missing evidence), **prior_context** (Institutional Memory — labeled background, never proof),
  **coordination_highlights**, **graph_highlights**, **narrative_highlights**,
  **metadata_highlights**, **investigation_timeline**.
- **Context compression — multiple budgets** (`Compact` / `Standard` / `Comprehensive`) that
  cap items per section and select sections to **preserve evidence quality, not token count**
  (Standard/Comprehensive reach full evidence coverage; Compact trades coverage for size).
- **Context attribution** — every `ContextStatement` carries its references (bundle `ev:` ids,
  `ko:` memory provenance, or `epistemics.*` for absence). No synthesized statement loses
  traceability. Output is **versioned** (`ctx-v1`) and **content-addressed** (`context_hash`),
  rendered to a single prompt string.
- The AI Behavior Analyst executes raw (default) or structured context, config-driven
  (`OMI_ANALYST_CONTEXT_MODE` / `_BUDGET`); the structured context is captured into
  `last_context` for Shadow Mode. Any future specialist reuses the builder (it works on the
  bundle, for any contract).

## C. Context quality metrics (`app/reasoning/context/metrics.py`)

Deterministic measurements over a built context:
- **evidence_coverage** — share of informative bundle evidence the context cites;
- **citation_retention** — share of statements carrying a reference (target **1.0**: full
  traceability — verified by construction);
- **compression_ratio** — context tokens / raw-context tokens;
- **token_utilization** — context tokens / the budget's token cap;
- **context_completeness** — share of the budget's sections that are populated.
Exposed through Shadow Mode (the `ShadowReport.context` block) and the admin context route —
**model-independent**, so they are measurable today without a live endpoint.

## D. Shadow comparison support (`app/reasoning/shadow/`)

- `ShadowReport.context` records the structured-context metrics of the shadow run — captured
  **even on fallback**, because the Context Builder runs deterministically regardless of the
  model. `versioning.prompt` now also carries `context_mode` + `context_budget`.
- `compare_context_modes(payload, …)` runs the shadow pipeline once per context mode (same
  prompt, same model) and compares the two AI reads, surfacing each mode's context metrics —
  the apparatus that answers *does structured context improve reasoning quality?*
- Admin route `POST /v1/admin/shadow/context/{slug}` returns the built context + metrics
  offline, and the raw-vs-structured execution comparison when a model endpoint is configured.

## E. Test results

`cd apps/api && python -m pytest tests/ -q` → **898 passed** (was 877; **+21**), 0
regressions. `tests/test_context_builder.py` + `tests/test_context_shadow.py` cover:
- **deterministic context generation** (stable `context_hash` + `to_dict`; unknown budget →
  standard);
- **evidence preservation** (behavioral evidence preserved, supplemental excluded; coverage by
  budget) and **citation preservation** (every statement attributed; retention 1.0; memory
  provenance retained);
- **context budget selection** (strictly nested section sets; per-section caps) and
  **compression correctness** (Compact smaller than Comprehensive; ratios computed);
- **shadow integration** (structured metrics surfaced, including on fallback; raw default
  marked), **`compare_context_modes`**, **replay determinism**, the admin route;
- **regression safety** — raw is the default and unchanged; **production is
  context-independent**.

## F. Engineering readiness

- **Context Builder + metrics: ready and measurable today.** Structured context is
  deterministic, versioned, fully attributed, budgeted, and its quality metrics are computed
  **without a model** — so the *information-quality* improvement is real and inspectable now via
  the context route and the shadow `context` block.
- **Reasoning-quality signal: still gated on live inference.** Whether structured context
  changes the *model's read* (raw vs structured) is null by construction offline (the AI falls
  back to deterministic); `compare_context_modes` is proven with deterministic providers and
  will yield real signal the moment the endpoint exists.
- **Constitution: intact.** Governor untouched; raw prompt byte-identical; production
  context-independent; the builder never invents, never moves the number, and preserves full
  citation traceability. Structuring the context cannot weaken a guarantee that lives below it.

## G. Recommendation for Sprint 010

1. **Provision the endpoint and run raw-vs-structured + budget sweeps over the gold corpus.**
   Use `compare_context_modes` and the Sprint-008 corpus (controls included) to test whether
   structured context **raises label agreement without raising control FPR**, and which budget
   is best — the first evidence for promoting structured context to the default
   (`OMI_ANALYST_CONTEXT_MODE=structured`).
2. **Enrich the bundle so the empty highlight sections carry signal.** `narrative_highlights`,
   `metadata_highlights`, and `graph_highlights` are wired but thin because the Binder doesn't
   yet project those facets. Extend the Binder (additively) to populate narrative / metadata /
   graph facets from the existing engine stores, so the Context Builder's completeness rises —
   improving context quality with no model change, exactly this sprint's thesis.

---

*Long-term architecture over short-term sophistication. Reasoning improves by improving the
information supplied to the model — not its size or the council's complexity. The Context
Builder is deterministic, versioned, budgeted, and fully attributed; it never invents; the
constitution held (Governor untouched, production context-independent, number echoed not moved,
citations preserved). No engine / scoring / OmiScore change. Gates green at commit time (898
backend tests). GitHub remains the source of truth; Hugging Face remains the source of AI
assets.*
