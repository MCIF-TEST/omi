# OMI_ENGINEERING_SPRINT_004 — Analyst Council Foundation (report)

> **Engineering sprint.** Built Omi's **permanent intelligence-execution framework** — the
> model the council will use forever. Deterministic implementations establish the model;
> any future reasoning model (Qwen, LoRA, ensemble) plugs in through the same contracts
> **without an orchestration change**. The Governor is mandatory; the Floor is the
> fallback. All new modules are additive (zero edits to existing files).

## A. GitHub commits

One commit on `claude/stoic-edison-2ueecx`. Two new standalone packages
(`app/reasoning/contracts/`, `app/reasoning/orchestrator/`) + tests; nothing existing was
modified, so the engine, the live analyst path (Sprint 003), and the deterministic
foundation (Sprint 002) are all untouched.

## B. Council implementation

- **Modules** (`orchestrator/modules.py`) — deterministic, each behind a contract, talking
  only through the blackboard:
  - **Behavior Analyst** (Tier 1) → cited `Finding`s from behavioral evidence (excludes
    supplemental signals).
  - **Counter-Evidence Analyst** (Tier 2, Red Team) → a `Critique` (exculpatory case +
    `would_flip_if`).
  - **Judge** (Tier 3) → a Governor-valid `Ruling` assembled from the findings + critique
    (echoes the engine number, surfaces both sides + uncertainty, respects the gate,
    stays falsifiable).
  - **FloorJudge** → the always-valid deterministic fallback Ruling (bundle-only).
- **Orchestrator** (`orchestrator/orchestrator.py`) — the deterministic control plane:
  Budget Controller, tier-ordered scheduler, contract-validated module execution,
  blackboard management, **mandatory Governor gate**, and **Floor fallback** on REJECT.
  Same payload → same assessment → same `ValidationTrace` (deterministic).
- **`AnalystModule`** interface (a `@runtime_checkable` Protocol: `.contract` + `.run`) is
  the permanent plug point — the proven seam for swapping a deterministic analyst for a
  model-backed one.

## C. Blackboard implementation (`orchestrator/blackboard.py`)

- **Shared evidence workspace** over one read-only Evidence Bundle.
- **Immutable evidence references** — artifacts cite `ev:` ids; the blackboard resolves
  them against the bundle.
- **Shared citation registry** (`bundle.citation_index()`).
- **Append-only artifacts** + **phase-gated views** (`view_for(contract)`): a Tier-N module
  sees only artifacts produced by tiers `< N` — information hiding that keeps specialists
  blind to peers (anti-anchoring) while staying deterministic.

## D. Reasoning contracts (`contracts/`)

- **`ReasoningContract`** — frozen + versioned (`contract_version`); declares module, tier,
  lens (`inputs`), `output_kind`, constraints. Validation invalid → raises.
- **Typed artifacts** — `Finding` / `Critique` / `Ruling` (open registry; Hypothesis /
  Calibration add without touching the orchestrator), each carrying `evidence_refs`.
- **`validate_artifact`** — checks kind matches the contract and every citation resolves;
  the orchestrator drops invalid artifacts (degrades, never breaks).

## E. Test results

`cd apps/api && python -m pytest tests/ -q` → **798 passed** (was 787; **+11**), 0
regressions. `tests/test_council.py` covers every required area:
- **blackboard** — append-only + phase-gated views + citation registry;
- **contract validation** — versioned/frozen, resolve-or-reject, invalid kind raises;
- **council execution** — Behavior findings (supplemental excluded), Counter-Evidence
  critique;
- **orchestrator** — full council run, **deterministic** execution, budget `floor_only`
  path;
- **Governor integration** — the council Ruling passes the Governor; **REJECT → Floor**
  fallback;
- **AI readiness** — a **custom module plugs in via the contract** with no orchestration
  change (and satisfies the `AnalystModule` Protocol).

## F. Recommendation for Sprint 005

Two complementary tracks (both GPU-free, in our control):
1. **Make the council production-reachable, flagged + off by default.** Add an
   orchestrator-backed branch to the live `/analyst` path (selectable via the Budget
   Controller / a settings flag), so the council can be shadow-compared to the
   single-provider Floor path — the Governor + Floor are already proven, so this is safe.
   Persist the `ValidationTrace` (and a blackboard digest) to a durable audit store.
2. **Broaden the council** with the remaining deterministic specialists (Language,
   Coordination, Narrative, Graph, Metadata, Memory) and the synthesis tier (Hypothesis
   Generator, Strategy, Risk & Calibration) — all behind the existing contracts — and add
   the **Memory-retrieval seam** (`PriorContext`) as a read-only blackboard input.

When a live HF endpoint appears (the standing external blocker), a Qwen-backed module
implements `AnalystModule` and replaces any deterministic analyst with **no orchestration
change** — exactly what this sprint's framework guarantees.

---

*Long-term architecture over short-term sophistication. No engine / scoring / OmiScore
change; modules couple only through contracts; the Governor is mandatory and the Floor is
the fallback; execution is deterministic. Gates green at commit time (798 backend tests).
GitHub remains the source of truth; Hugging Face remains the source of AI assets.*
