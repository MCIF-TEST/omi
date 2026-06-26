# OMI_ENGINEERING_SPRINT_005 — Institutional Intelligence Memory (report)

> **Engineering sprint.** Gave Omi a memory: an append-only institutional knowledge graph
> whose confidence rises with independent corroboration, falls with contradiction, and
> decays without re-observation. Memory enters reasoning as **another specialist analyst**
> through the **existing Reasoning Contracts** — no new subsystem, no orchestration change.
> The constitutional core holds throughout: **memory is context, never proof.** It never
> raises suspicion, never changes the engine's number, and is subordinate to evidence. The
> Governor stays mandatory; the Floor stays the fallback; every change is additive and
> backward-compatible.

## A. GitHub commits

One commit on `claude/stoic-edison-2ueecx`. One new standalone package
(`app/memory/graph/`) + two test files; the council was extended **through its contracts
only** — the Memory artifact kind, a Tier-1 `MemoryAnalyst`, a `memories()` view accessor,
and context-only memory folding in the Judge's assembly. No engine, scoring, OmiScore,
Governor, Binder, Evidence Bundle, or Orchestrator-control change. Sprint 002–004 paths run
untouched (the default council still has no Memory member; Memory is opt-in).

## B. Institutional Memory implementation (`app/memory/graph/`)

Implements the deterministic core of `OMI_INTELLIGENCE_MEMORY_SYSTEM_V1`. Standalone —
imports only `app.evidence`.

- **`objects.py` — knowledge graph + observation ledger.** A `KnowledgeObject` stores
  **evidence and observed patterns, never a verdict**; its confidence / stability / status
  are *pure functions of an append-only `ObservationLedgerEntry` list* (recomputed, never
  overwritten). The guarantees are baked into the math:
  - **Confidence evolution** — saturating corroboration `1 − 0.6^n_sup`, contradiction
    penalty `1 − 0.5·(n_con/total)`, half-life **decay** `0.5^(days/180)`. So memory can
    **never ossify into self-fulfilling prophecy** — un-reobserved priors fade.
  - **Independent corroboration only** — support is counted by **distinct independence
    keys**, not raw observations (no double-counting a single account/campaign).
  - **Memory-influence quarantine** — entries flagged `memory_influence="primed"` are
    excluded from the independent-support count: **memory cannot confirm itself** (no
    self-reinforcing loop).
  - **Falsifiable by construction** — `epistemic_status` tops out at `corroborated`
    (n_sup ≥ 3 ∧ stability ≥ 0.6); contradiction → `contested`; below `retirement_floor`
    (0.12) → `retired`. There is no "confirmed truth" state.
  - **Influence cap** — `influence_class ∈ {context, exculpatory}`, **never
    discriminative**; controls (`is_control`) are forced exculpatory.
- **`store.py` — append-only, evidence-gated write path.** `ingest()` accepts only
  structural candidates `{type, family, label, signature, is_control}` extracted from
  **settled Evidence Bundles** + human/platform anchors — **the LLM is never a write
  source**. A candidate is matched to an existing object (type + signature Jaccard ≥ 0.5)
  or created; the observation is **appended** and version-stamped. Nothing is hard-deleted
  — retirement and supersession are statuses, kept for audit.
- **`retrieval.py` — deterministic `PriorContext`.** `retrieve(store, bundle, now)` ranks
  priors by **signature containment** (share of a prior's firing detectors present in the
  current evidence) × confidence × stability, with an **exculpatory boost** for controls
  (×1.5 — memory is freer to exonerate than to incriminate). **Provenance + falsifiability:**
  matched references are **bundle `ev:` ids** (resolvable for citation); the `ko_id` is
  carried as provenance. A pure function of `(store, bundle, now)` — deterministic, no model.

## C. Memory Analyst implementation (`orchestrator/modules.py` · `MemoryAnalyst`)

A **Tier-1 specialist** that participates in the council through the **same `AnalystModule`
interface** as every other analyst (`.contract` + `.run(view) -> [Artifact]`):

- Retrieves `PriorContext`, then emits one **`Memory` artifact** (new typed artifact, open
  registry) that **distinguishes supporting and contradicting history**: exculpatory priors
  (controls / contradicting patterns) → `contradicting`; consistent priors → `supporting`
  (context only); low-confidence/low-stability matches → `uncertainty`.
- **Cites bundle evidence** (`ev:` ids) so the artifact resolves against the blackboard and
  passes both contract validation and Governor S2; **records uncertainty** explicitly.
- Its contract encodes the constitutional limits as constraints: *memory is context, never
  proof · never raises suspicion (no evidence_for) · cite bundle evidence; ko ids are
  provenance · exculpatory priors may lower, never raise.*
- **AI readiness:** swapping this deterministic analyst for a **Qwen-backed** one is a
  drop-in — same contract, same artifact — with **no change to the Orchestrator,
  Blackboard, Contracts, or Governor**.

## D. Blackboard integration (`orchestrator/blackboard.py` · `modules.py`)

Memory flows through the *existing* phase-gated blackboard, not a side channel:

- `BlackboardView.memories()` exposes posted `Memory` artifacts, tier-gated exactly like
  `findings()`/`critiques()` — the Tier-3 **Judge sees Tier-1 memory; a Tier-1 module stays
  blind** to it (anti-anchoring preserved).
- **Context-only folding** in `build_ruling_assessment(...)`: a `contradicting` (exculpatory)
  prior is surfaced as `evidence_against` tagged `memory:<type>`; a `supporting` prior is
  reported under `uncertainty` as *"Institutional memory (context, not proof): …"*. Memory
  **never enters `evidence_for`, never touches the echoed number / tier, and never feeds the
  corroboration gate** — so the Governor's echo-guard, gate, and S6 boundary stay intact by
  construction. **Evidence over memory** is enforced structurally, not by convention.

## E. Test results

`cd apps/api && python -m pytest tests/ -q` → **818 passed** (was 798; **+20**), 0
regressions. Two new suites cover every required area:

- **`tests/test_memory_graph.py` (13)** — confidence evolution (corroboration ↑, contradiction
  ↓), half-life decay, independence dedup, the **memory-influence quarantine**, epistemic-status
  ladder + retirement, store ingest/observe/supersede (append-only), and retrieval
  matching / control-boost / decay-ranking.
- **`tests/test_memory_council.py` (7)** — the `Memory` artifact shape, **contract validation**
  (valid + fabricated-citation reject), **blackboard integration** (Judge sees Tier-1 memory;
  Tier-1 blind), **Governor compatibility** (`test_council_with_memory_passes_governor_and_
  preserves_echo` — permits, asserts the number is **unchanged at 0.72**, control surfaces as
  `memory:`-tagged `evidence_against` and **never** as `evidence_for`), supporting-prior-is-
  context-only, full-council **determinism**, and the `AnalystModule` Protocol check.

## F. Recommendation for Sprint 006

Two complementary tracks (both GPU-free, in our control):

1. **Close the memory write loop + persist.** Add the **evidence-gated extractor** that
   turns a *settled* Evidence Bundle (and human anchors) into `ingest()` candidates, so
   memory is written from real investigations — with the quarantine flag set whenever a
   prior influenced that investigation (the loop-breaker, end to end). Back the in-memory
   `MemoryStore` with a durable store behind the same interface, and persist the
   `ValidationTrace` + a blackboard digest to the audit store (carried over from Sprint 004
   track 1).
2. **Make the council production-reachable, flagged + off by default**, *with* the Memory
   Analyst as an opt-in member — so a memory-aware council can be shadow-compared to the
   proven single-provider Floor path on the live `/analyst` route (Budget Controller /
   settings flag), the Governor + Floor already guaranteeing safety.

When a live HF endpoint appears (the standing external blocker), a Qwen-backed Memory
Analyst implements `AnalystModule` and replaces the deterministic one with **no
orchestration change** — exactly what this sprint's framework guarantees.

---

*Long-term architecture over short-term sophistication. Memory is context, never proof:
evidence over memory, no self-reinforcing loops, provenance + falsifiability, append-only,
independent corroboration, constitutional compliance. No engine / scoring / OmiScore change;
modules couple only through contracts; the Governor is mandatory and the Floor is the
fallback; execution is deterministic. Gates green at commit time (818 backend tests). GitHub
remains the source of truth; Hugging Face remains the source of AI assets.*
