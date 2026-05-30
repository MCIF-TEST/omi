# OmiSphere — Gap Resolution Master Tracker

> **Purpose:** Single source of truth for the multi-phase adversarial audit remediation.
> Work one gap at a time, in the order given. Update the **Status** field as you go.
> When you say *"execute gap N"*, the engineer implements that gap end-to-end (code,
> tests, commit) and flips its status to ✅ Done.

**Last updated:** 2026-05-30
**Active branch:** `claude/ecstatic-babbage-wu1f4`
**Repo:** `mcif-test/omi`

---

## How to use this document

1. Gaps are grouped by the audit **Phase** that produced them.
2. Within a phase, gaps are ordered by **execution sequence** (dependencies first).
3. Each gap has a fixed ID (`GAP-01`…) that never changes, so you can always say
   *"execute GAP-04"* and it's unambiguous.
4. **Do not skip ahead past a hard dependency.** Dependencies are listed per gap.
5. Status legend:
   - ⬜ **Not started**
   - 🟦 **Partial** — some infrastructure exists; needs completion
   - 🟨 **In progress** — actively being implemented this session
   - ✅ **Done** — implemented, tested, committed
   - ⏸️ **Blocked** — waiting on a dependency

---

## Status summary (the one table to glance at)

| ID | Gap | Phase | Priority | Complexity | Impact | Status | Depends on |
|----|-----|-------|----------|-----------|--------|--------|-----------|
| GAP-01 | Ground truth dataset | 1 | Immediate | Medium | Transformational | 🟦 Partial | — |
| GAP-02 | Signal independence / overconfident scores | 2 | Immediate | Low→Med | High | ⬜ | GAP-01 (Phase B) |
| GAP-03 | AI-writing detection is harmful | 2 | Immediate | Low | High | ⬜ | — |
| GAP-05 | Confidence not calibrated | 2 | Immediate | Low→Med | High | ⬜ | GAP-01 |
| GAP-06 | No explainability layer | 2 | Immediate | Medium | High | ⬜ | — |
| GAP-07 | False positives on ESL / fan communities | 2 | Immediate | Medium | High | ⬜ | GAP-03 |
| GAP-04 | False negatives on hybrid operations | 2 | Next | High | Transformational | ⬜ | GAP-01 |
| GAP-08 | No adversarial robustness | 2 | Next | Med→High | High | ⬜ | — |
| GAP-10 | No behavioral cross-account linking | 2 | Next | Medium | High | 🟦 Partial | — |
| GAP-09 | Single-platform bias | 1 | Next | Med→High | High | ⬜ | — |
| GAP-11 | No persistent campaign tracking | 1 | Next | Medium | High | 🟦 Partial | — |
| GAP-12 | No enterprise features (RBAC/SSO/audit) | 1 | Next | Med→High | High | 🟦 Partial | — |

> 🟦 **Partial** means the codebase already ships scaffolding. Details in each gap's
> "Current state in codebase" section — this is what saves you from rebuilding what exists.

---

## EXECUTION ORDER (the sequence to actually work in)

This is the order to call *"execute GAP-N"*. It respects dependencies and front-loads
trust/accuracy fixes (cheap, high-impact) before the big network-detection build.

```
WAVE 1 — Trust & honesty (no new data required, ship first)
  1. GAP-03  Remove AI-writing from composite score
  2. GAP-06  Evidence/explainability layer
  3. GAP-02  Signal decorrelation (Phase A)
  4. GAP-05  Confidence display honesty
  5. GAP-07  Community anchor + per-community thresholds

WAVE 2 — Data foundation (unlocks the ML-dependent work)
  6. GAP-01  Ground truth dataset (complete the partial build)
  7. GAP-02  Calibrated scorer (Phase B — needs GAP-01)
  8. GAP-05  Calibration pipeline (Phase B — needs GAP-01)

WAVE 3 — Detection depth (the moat)
  9. GAP-10  Behavioral fingerprint cross-account linking (complete partial)
 10. GAP-08  Adversarial-robust signals (graph entropy, linguistic drift)
 11. GAP-04  Campaign / network-level analysis

WAVE 4 — Reach & enterprise
 12. GAP-09  Multi-platform (Reddit, Telegram)
 13. GAP-11  Campaign Monitor (complete partial)
 14. GAP-12  Enterprise (RBAC/SSO/audit — complete partial)
```

---

# PHASE 1 — Product Reality Audit (findings → gaps)

Overall Phase 1 honest score: **product is real and functional, but single-platform,
single-shot, and lacks the trust scaffolding enterprise buyers require.**

---

### GAP-01 — Ground Truth Dataset 🟦 Partial

**Gap:** Detection signals are unvalidated against labeled real-world data.

**Why it matters (≤3 sentences):** Precision/recall are theoretical without ground truth.
It is the root dependency for calibration (GAP-05) and the learned scorer (GAP-02 Phase B).
Without it, every other detection claim is unfalsifiable.

**Current state in codebase (what already exists — do NOT rebuild):**
- ✅ `AccountLabel` model (`apps/api/app/storage/models.py`) — operator labels with
  `label`, `expected_tier`, `confidence`, `source`, `rationale`, per-(account,user) unique.
- ✅ `/v1/labels` admin CRUD routes (`apps/api/app/routes/labels.py`) — create/update/delete/list.
- ✅ `/v1/labels/calibration` + `/calibration/evaluate` — in-process precision/recall/Brier/F1.
- ✅ `/v1/labels/training/export` — JSONL training corpus export.
- ✅ Calibration CLI (`apps/api/scripts/calibrate.py`) with `--from-db` and `--check` CI guard.
- ✅ Dataset ingestion CLI (`apps/api/scripts/datasets.py`) + `app/ml/datasets/`.
- ✅ Ground-truth label widget in UI (`accounts/[external_id]/label-widget.tsx`).

**What remains (the actual work for this gap):**
- ⬜ **Stream A — archive ingestion:** `scripts/ingest_ground_truth.py` to pull public IO
  archives (Stanford Internet Observatory, Twitter/X IO disclosures) into `AccountLabel`
  with `source="imported_dataset"`.
- ⬜ **Stream B — synthetic corpus:** generator producing the 4 false-positive personas
  (coordinated-inauthentic, organic-fan, AI-assisted-legit, ESL) as regression fixtures.
- ⬜ **Stream C — operator annotation in-flow:** annotation affordance is admin-only and
  account-detail-only today; extend to the investigation/threat-breakdown flow so analysts
  label in context (not just from the account page).
- ⬜ Wire a periodic calibration summary surfaced on the dashboard (amber→green at N labels).

**Data:** Public IO archives (~50GB), synthetic (<1GB), incremental operator labels.
**Engineering:** 2 new scripts, 1 extended UI affordance, 1 dashboard indicator.
**Priority:** Immediate · **Complexity:** Medium · **Impact:** Transformational
**Depends on:** — · **Unblocks:** GAP-02(B), GAP-05(B), GAP-04

---

### GAP-09 — Single-Platform Bias ⬜

**Gap:** Only YouTube is supported; cross-platform operations are invisible.

**Why it matters:** Modern influence ops coordinate across platforms; one-platform analysis
is structurally incomplete. Enterprise buyers monitor many platforms and will see the gap
immediately.

**Current state in codebase:**
- `apps/api/app/integrations/youtube.py` is the only connector; no platform abstraction.
- Models already carry a generic `platform` column everywhere (good — schema is ready).

**What remains:**
- ⬜ `services/platforms/base.py` `PlatformConnector` ABC; refactor YouTube to implement it.
- ⬜ Reddit connector (official API, free tier).
- ⬜ Telegram connector (`telethon`, MTProto).
- ⬜ Cross-platform entity resolution + `cross_platform_entities` table.

**Priority:** Next · **Complexity:** Med-High · **Impact:** High
**Depends on:** — · **Unblocks:** richer GAP-04

---

### GAP-11 — No Persistent Campaign Tracking 🟦 Partial

**Gap:** Analysis is single-shot; no way to watch an operation evolve over time.

**Why it matters:** Influence ops run for weeks; analysts need delta intelligence, not
snapshots. This converts OmiSphere from a tool into a monitoring platform.

**Current state in codebase (already exists):**
- ✅ `Watchlist` + `Alert` models and `/v1/monitoring` routes (feed, alerts, run-pass).
- ✅ Alert delivery (email/webhook) with `delivered_at`/`delivery_status` tracking.
- ✅ `Investigation` model with continuation batches + stable slug.

**What remains:**
- ⬜ A first-class `Campaign` concept (named set of accounts/keywords + schedule) distinct
  from per-target watchlists.
- ⬜ Per-run snapshots + `delta_events` (new accounts activated, score escalation, pivots).
- ⬜ Campaign timeline UI (sparkline of score over runs).

**Priority:** Next · **Complexity:** Medium · **Impact:** High
**Depends on:** GAP-04 (campaign scoring) for full value

---

### GAP-12 — No Enterprise Features (RBAC / SSO / Audit) 🟦 Partial

**Gap:** No SSO, no real role model, no audit log, no workspace isolation.

**Why it matters:** These are procurement table stakes; their absence blocks enterprise
revenue entirely.

**Current state in codebase (already exists):**
- ✅ `User.is_admin` soft flag + `_require_admin` gating on sensitive routes.
- ✅ `/v1/activity` audit-log-style endpoint and `ScanLog` audit trail.
- ✅ Session auth via signed cookies; password reset; referral/anti-abuse IP hashing.

**What remains:**
- ⬜ Three-tier RBAC (admin/analyst/viewer) + `WorkspaceMembership`.
- ⬜ Workspaces + row-level isolation (Postgres RLS in prod).
- ⬜ Tamper-resistant append-only `audit_log` (INSERT-only role) with CSV export.
- ⬜ SAML 2.0 SSO (`python-saml`).

**Priority:** Next · **Complexity:** Med-High · **Impact:** High
**Depends on:** —

---

# PHASE 2 — Intelligence & Detection Audit (findings → gaps)

Overall Phase 2 honest score: **Detection maturity ≈ 4.3/10.** Signals are plausible but
unvalidated, partly correlated (overconfident), weak against ESL/fan-community false
positives, and near-blind to sophisticated hybrid operations.

---

### GAP-03 — AI-Writing Detection Is Actively Harmful ⬜

**Gap:** `ai_generation_probability` over-fires on ESL/grammar-tool users and is trivially bypassed.

**Why it matters:** It generates false positives on legitimate international users and is
the easiest signal to game, damaging trust more than it adds detection value.

**Current state in codebase:**
- AI-writing detector lives in `app/detection/` and contributes to the composite score.
- Benchmarks already exist: `tests/test_ai_writing_benchmark.py`, `datasets benchmark-text`
  (these confirm: high precision, low coverage — i.e., weak as a scored signal).

**What remains:**
- ⬜ Remove from composite/risk-level weighting.
- ⬜ Demote to a `supplemental: true` field with a visible caveat.
- ⬜ Render in a separate "Supplemental signals" section in `threat-breakdown.tsx`.

**Priority:** Immediate · **Complexity:** Low · **Impact:** High · **Depends on:** —
**▶ First in execution order (Wave 1, step 1).**

---

### GAP-06 — No Explainability Layer ⬜

**Gap:** Scores lack specific, named, quantified evidence per signal.

**Why it matters:** Analysts and enterprise/compliance buyers won't act on black-box scores;
"the model says so" fails in every professional use case.

**Current state in codebase:**
- API schema already has `top_evidence` and per-dimension `contributions` fields;
  `threat-breakdown.tsx` already renders them — they're just under-populated/generic.

**What remains:**
- ⬜ Each detector returns an `evidence: list[str]` of specific observations (templates per signal).
- ⬜ Composite scorer ranks evidence by contribution and fills `top_evidence` with real text.
- ⬜ No frontend rebuild needed — populate existing fields correctly.

**Priority:** Immediate · **Complexity:** Medium · **Impact:** High · **Depends on:** —

---

### GAP-02 — Signal Independence / Overconfident Scores ⬜

**Gap:** Correlated timing signals are summed as independent evidence → inflated confidence.

**Why it matters:** A "73%" that maps to ~45% real accuracy drives bad analyst calls and churn.

**What remains:**
- ⬜ **Phase A (no data):** decorrelation penalty matrix on co-firing timing signals.
- ⬜ **Phase B (needs GAP-01):** calibrated logistic regression + Platt scaling; CI gate on ECE.

**Priority:** Immediate (A) / Next (B) · **Complexity:** Low→Med · **Impact:** High
**Depends on:** GAP-01 for Phase B

---

### GAP-05 — Confidence Not Calibrated ⬜

**Gap:** Confidence is a point estimate with no empirical calibration.

**Why it matters:** False certainty is worse than honest uncertainty for analyst trust and sales.

**What remains:**
- ⬜ **Display:** band instead of point estimate + `confidence_calibration_status` field + caveat.
- ⬜ **Pipeline (needs GAP-01):** reliability curve + ECE recalculation, Platt recalibration trigger.

**Priority:** Immediate (display) / Next (pipeline) · **Complexity:** Low→Med · **Impact:** High
**Depends on:** GAP-01 for the pipeline

---

### GAP-07 — False Positives on ESL / Fan Communities ⬜

**Gap:** Coordination/temporal signals over-trigger on legitimate synchronized communities.

**Why it matters:** False positives destroy analyst trust faster than misses; flagging a fan
community or ESL speaker trains analysts to ignore OmiSphere.

**What remains:**
- ⬜ Community anchor check (`services/event_anchor.py`) against Google Trends RSS / sports /
  trending — suppress coordination when a real event explains the cluster.
- ⬜ `events` table + hourly fetch.
- ⬜ Per-community threshold table (sports/political/news/entertainment/unknown).

**Priority:** Immediate · **Complexity:** Medium · **Impact:** High · **Depends on:** GAP-03

---

### GAP-04 — False Negatives on Sophisticated Hybrid Operations ⬜

**Gap:** Per-account scoring is near-blind to 80%-human/20%-automation networks.

**Why it matters:** Hybrid ops are the dominant state-level tactic; missing them means failing
on the cases that matter most. This is the central detection gap.

**What remains:**
- ⬜ Narrative velocity + semantic cluster density signals (network-level).
- ⬜ `POST /v1/analysis/campaign` batch endpoint (up to 500 accounts).
- ⬜ Account role classification (originator/amplifier/peripheral).
- ⬜ Embedding cache; network graph output.

**Priority:** Next · **Complexity:** High · **Impact:** Transformational
**Depends on:** GAP-01 (validation), benefits from GAP-10

---

### GAP-08 — No Adversarial Robustness ⬜

**Gap:** Every current signal is defeatable by a reader of basic bot-detection literature.

**Why it matters:** Zero structural bypass cost today; the product needs signals that are
expensive to game.

**What remains:**
- ⬜ Interaction graph entropy signal (structurally hard to fake).
- ⬜ Linguistic fingerprint drift signal (detects ghostwriter/takeover handoffs).
- ⬜ Register both in the scoring pipeline.

**Priority:** Next · **Complexity:** Med-High · **Impact:** High · **Depends on:** —

---

### GAP-10 — No Behavioral Cross-Account Linking 🟦 Partial

**Gap:** Account rotation resets accumulated suspicion; cells cycle cheap accounts to evade.

**Why it matters:** Without linking, a well-run operation defeats per-account analysis indefinitely.

**Current state in codebase (already exists):**
- ✅ `Account.fingerprint_json` stores a normalized fingerprint vector.
- ✅ `app/memory/` fingerprint caching + `tests/test_memory_*.py` benchmarks.
- ✅ `CoordinationEdge` persistent cross-scan pair coordination.

**What remains:**
- ⬜ Expand fingerprint to the full 128-dim feature set (temporal/linguistic/engagement/content).
- ⬜ ANN match at analysis time (`sqlite-vec` dev / `pgvector` prod) surfacing matches to
  suspended/flagged accounts.
- ⬜ `linked_accounts` field in API + evidence fragment.

**Priority:** Next · **Complexity:** Medium · **Impact:** High · **Depends on:** —

---

## Scope checkpoints (where each milestone draws the line)

**MVP (pilot-ready, false-positive-safe):**
GAP-03, GAP-06, GAP-02(A), GAP-05(display), GAP-07, GAP-01(complete), GAP-10(passive matches).

**v1 (enterprise-sellable):**
+ GAP-04 (campaign mode), GAP-08, GAP-09 (Reddit+Telegram), GAP-11 (Campaign Monitor),
GAP-12 (RBAC/SSO/audit), GAP-02(B)/GAP-05(pipeline) once labels exist.

**v2 (category-defining moat):**
Real-time streaming, adversary attribution, predictive escalation, LinkedIn/YouTube/TikTok
connectors, narrative genealogy, fingerprint-similarity discovery search.

---

## Change log

| Date | Gap | Change | By |
|------|-----|--------|----|
| 2026-05-30 | — | Tracker created; current-state audit of codebase folded in | execution |

> Append a row every time a gap's status changes. Keep this honest — the tracker is only
> useful if it reflects what's actually in `main`/the active branch.
