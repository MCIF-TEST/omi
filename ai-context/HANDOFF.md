# OmiSphere — HANDOFF (current project state)

> The most frequently updated file. Update on every code change (see
> "Maintenance rules" at the bottom). This supersedes the legacy root
> `/HANDOFF.md` (dated 2026-05-29), which is kept only for history.

_Last updated: 2026-06-18 · active branch: `claude/focused-turing-upy6c`_

---

## Current Objective

Establish lightweight, durable project memory (`ai-context/`) so context
survives across Claude sessions. Recent work has been an **audit-remediation
phase**: verify a specific finding against the code, then ship the smallest
safe fix, one at a time, with full gates green before commit.

## Recently Completed

Newest first. (Branch auto-merges into `main` in the remote env.)

| Date | Commit | What | Files (area) | User impact |
|------|--------|------|--------------|-------------|
| 2026-06-18 | _(this change)_ | **Omi Feature Schema V1** — complete inventory of every feature/signal/metric (8 attrs each) + the canonical 42-dim `build_feature_vector` contract as the Behavioral Intelligence Model input; docs only | `ml/features/OMI_FEATURE_SCHEMA_V1.md` | Proprietary signals catalogued; exact, versioned training-input contract established |
| 2026-06-18 | `a5199b0` | **Hugging Face integration plan** — HF as the ML layer (dataset hosting + CPU training + model registry) completing the existing train→push→load→blend seam; Render/Postgres preserved; ~$0–2/mo; docs only | `ml/HUGGING_FACE_INTEGRATION_PLAN.md` | Clear, budget-safe path to wire a learned scorer via HF without touching production |
| 2026-06-18 | `577fba6` | **Omi Neural Network V1 architecture plan** — CPU-only, <$50/mo, glass-box (GBT/monotonic-MLP) learned prior that augments the corroboration-gated rule engine via the dormant `app/ml/scorer.py` seam; docs only | `ml/OMI_NEURAL_NETWORK_V1.md` | Concrete, constraint-faithful plan for a learned scorer; no model trained, scoring untouched |
| 2026-06-18 | `e0abe64` | **Omi Intelligence Foundation** — create decoupled top-level `ml/` ML scaffold (datasets/features/models/training/evaluation/inference/schemas), docs-only, no production wiring | `ml/**` (13 READMEs) + `ai-context/ARCHITECTURE.md` | Forward-looking ML R&D has a structured, governed home; engine untouched |
| 2026-06-18 | `61100f1` | Create `ai-context/` project-memory system | `ai-context/VISION.md`, `ARCHITECTURE.md`, `HANDOFF.md` | Context persists across sessions; less re-derivation |
| 2026-06-15 | `eb9dafa` | Monitoring **platform awareness** — watchlists store `platform`; History links route by it; safe backfill→youtube + heal-on-rewatch; scheduler restricted to youtube | api: models/db/schemas/service/scheduler/routes + tests; web: monitoring + account-actions + commenter-detail + api.ts | X watchlists link to the correct history view |
| 2026-06-15 | `08440f4` | Monitoring **workflow** — one-click "Add to Monitoring" on commenter-detail (reuses watchlist infra) | web: `investigate/commenter-detail.tsx` | Monitor an account from inside the investigation flow |
| 2026-06-15 | `46be015` | **Content DB ingestion fix** — comprehensive scan path now records ContentEntity/CommentBatch/ContentComment (was only `/youtube/full`) | api: orchestrator/scan + tests + conftest | Content DB actually populates from normal scans |
| 2026-06-15 | `c0c7952` | **Account-history title enrichment** — show content titles (from ContentEntity) instead of raw IDs | api: scan + test; web: api.ts + commenter-detail | Readable "on \<title\>" instead of raw video IDs |
| 2026-06-15 | `07fa85c` | **Campaign anonymized-account labeling** — label disclosure-hash member IDs honestly + provenance note (never hides a real handle) | web: campaign-identity + campaign/public pages | No hashed IDs masquerading as usernames |
| 2026-06-15 | `7ce46aa` | **Narrative false-positive fix** — corroboration-gate the coordination label; account-suspicion alone can't drive "coordinated"; terminology corrected | api: `narrative/coordination.py` + tests; web: narrative page | Fewer organic clusters mislabeled coordinated |
| 2026-06-15 | `f869bbd` | **Investigation confidence visibility** (D1) — surface confidence on the investigations list | api/web investigations list | No confidence-blind comparisons |
| 2026-06-15 | `65b8259` | **Platform routing fix** (Sprint A) — eliminate X→YouTube deep-scan fall-through | api: scan routing | X accounts no longer mis-scanned as YouTube |

## Open Audit Findings

1. **Scoring decision-surface redundancy (OPEN, investigated, not implemented).**
   At the account level the UI shows **two** composite verdicts side-by-side:
   `overall_probability` (the "inauthentic %" ScoreRing) + 4-level `tier`, AND
   the **OmiScore** dial (0–100) + 3-level `risk_level` + `authenticity_score`
   (≈100−inauthenticity). OmiScore is a re-blend of the same detectors (+25%
   nudge from `overall_probability`), so the numbers are redundant and the two
   category systems can visibly conflict (e.g. "ELEVATED" vs "MEDIUM risk").
   - Surfaces: `web/components/shared/threat-breakdown.tsx`, and the pages that
     mount it — `investigate/commenter-detail.tsx`,
     `accounts/[external_id]/page.tsx`, `investigations/[slug]/viewer.tsx`.
   - Recommended (UI-only, no engine change): keep ScoreRing+Tier as the single
     headline; demote OmiScore's dial/risk_level/authenticity chip and keep only
     its dimension bars + evidence as the "why"; show one tier vocabulary;
     rename the account dimension `coordination_probability` to disambiguate it
     from the cluster-level Coordination Score.
2. **Monitoring scheduler is YouTube-only (KNOWN LIMITATION).** The background
   watchlist re-scan loop (`app/monitoring/scheduler.py`) only re-scans
   `platform == "youtube"` rows. X watchlists are captured/routed/displayed
   correctly but not re-scanned by the scheduler (needs Twitter client wiring).
3. **"Coordination" terminology overload.** The word labels four different
   grains — account dimension, cluster aggregate, narrative score, campaign
   score. Not a value bug; a clarity/disambiguation cleanup.

(Investigated and found already-correct this session: **Narrative evidence
drill-down** — comments + commenters are already stored and surfaced; no fix
needed.)

## Deferred Features

- Platform-aware (X) scheduler re-scan (depends on finding #2).
- Healing platform for pre-existing watchlists happens only on re-watch (old
  rows stay backfilled to "youtube" until then) — acceptable fallback.
- Strategic (from PMF/moat/decision audits): the binding constraint is **real
  users / distribution, not more code.** Engineering is ahead of adoption.

## Known Constraints

- **Engine guardrails (do not violate):** never let one non-discriminative
  signal drive a maximal coordination verdict (corroboration gate); store
  evidence/probabilities, never persisted verdicts; best-effort writes are
  SAVEPOINT-isolated; respect `datasets/manifest.toml` (keep poison quarantined).
- **Gates:** full backend `pytest` (~746), web `typecheck` + `vitest` + `build`;
  commit only on green; match surrounding style.
- **Remote-env git:** push directly to `github.com` with a PAT (the local proxy
  403s); PR creation via the integration 403s ("not accessible by integration")
  and the env auto-merges the session branch into `main`.
- **Off by default in dev:** Anthropic LLM (template fallback), Stripe, SMTP
  alerts (webhook still works), background monitoring scheduler, embeddings.
- **Commit-signature "Unverified" stop-hook warnings are a closed topic — take
  no action on them.**

## Next Recommended Task

Implement **Open Finding #1** (scoring decision-surface simplification) as a
scoped, UI-only change — highest-value open item, zero engine risk. Strategically,
the larger lever is user acquisition, not more features.

---

## Maintenance rules (for every future session)

**Startup protocol — before any task, read:** `ai-context/VISION.md`,
`ai-context/ARCHITECTURE.md`, `ai-context/HANDOFF.md`. Treat them as
authoritative; don't assume facts that contradict them.

**On completing a code change:**
1. Update this file's _Recently Completed_ (date, commit hash, issue solved,
   files changed, user impact) and adjust _Open Findings_ / _Next Task_.
2. If the architecture changed → update `ARCHITECTURE.md`.
3. If mission/product scope changed → update `VISION.md`.

Keep it markdown-only. No databases, vector stores, embeddings, agents,
background AI workers, or orchestration — this is context preservation, nothing
more.
