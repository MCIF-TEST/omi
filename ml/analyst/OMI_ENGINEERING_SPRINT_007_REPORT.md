# OMI_ENGINEERING_SPRINT_007 — Evaluation & Shadow Mode (report)

> **Engineering sprint.** Transitioned from implementation to **evaluation**. The deterministic
> council remains the production path users see; the AI-backed council now runs **in parallel,
> for comparison only**, through a complete Shadow Mode pipeline: every evaluation produces a
> deterministic result, an AI-backed result, the mandatory Governor outcome on each, and a
> **deterministic comparison artifact** — all persisted, replayable, and aggregated into
> engineering statistics. No AI reasoning is exposed to end users. The pipeline runs with or
> without a live model (the AI council falls back to deterministic when no endpoint is set), so
> activation of live AI is **configuration only**.

## A. GitHub commits

One commit on `claude/stoic-edison-2ueecx`. One new standalone package
(`app/reasoning/shadow/`), one new admin route module (`app/routes/shadow.py`), one new test
file, and two-line additive edits (router registration in `app/main.py`). **Zero** changes to
the engine, scoring, OmiScore, the Binder, the Evidence Bundle, the Governor, the Blackboard,
the Contracts, the Orchestrator, the model providers, or the AI specialist. Sprint 002–006
paths run untouched; Shadow Mode is purely additive and engineering-only.

## B. Shadow Mode implementation (`app/reasoning/shadow/runner.py`)

`run_shadow(payload, …)` runs **both** councils over the same investigation and returns one
`ShadowReport`:
1. the **deterministic** council result (production — what the user receives),
2. the **AI-backed** council result (shadow — evaluation only),
3. the **Constitutional Governor** outcome on each (mandatory on both paths),
4. the deterministic **comparison** artifact.

The two councils are **identical except the Behavior Analyst** (deterministic vs AI-backed),
so the comparison isolates exactly one variable. The production result is computed from the
deterministic council and is never affected by the shadow run. **Runtime requirement met:** the
AI council's `RemoteAnalyst` falls back to deterministic when no endpoint is configured, so the
pipeline is fully operational today — `ai_mode` is reported as `ai` | `fallback` | `deterministic`.

## C. Comparison engine (`app/reasoning/shadow/compare.py`)

`compare(production, shadow)` is a **pure, deterministic** function (it carries a content-hash
`comparison_id`; no wall-clock or latency enters it). It captures:
- **agreement / disagreement** over the categorical reads (verdict, tier, confidence band,
  coordination label);
- **evidence overlap** (Jaccard of cited refs, shared / shadow-only / production-only) and
  **citation quality** (well-formed-`ev:` ratio);
- **confidence delta** + the constitutional invariant **`number_preserved`** (an AI specialist
  must never move the engine number — `confidence_delta == 0`);
- **uncertainty deltas** (counts + set differences);
- **Governor outcomes** on both paths (permitted, violation codes, Floor fallback);
- a deterministic **blackboard digest** per council (artifact counts, findings, citations).
Latency / retries / provider diagnostics / fallback are recorded **separately** in the report's
`diagnostics` block — keeping the comparison itself deterministic.

## D. Replay system (`app/reasoning/shadow/replay.py`)

`replay(payload, previous=…)` re-runs the pipeline and compares to a stored `ShadowReport`,
pinned on **(Evidence Bundle id + Memory revision + Model revision)** — `memory_revision(store)`
is a deterministic stamp of the knowledge-graph state. The **deterministic production path
reproduces bit-for-bit** (same bundle ⇒ same assessment + same `ValidationTrace` id); the
shadow path reproduces exactly under a deterministic provider (or the fallback). Under a *live*
model it may **drift**, which replay surfaces and attributes to a changed model / memory
revision — never to nondeterminism in the architecture. Replay is engineering + evaluation only.

## E. Observability APIs (`app/routes/shadow.py`, admin-only — `/v1/admin/shadow/*`)

Durable storage: each report is persisted in `Investigation.payload_json` under
`shadow_evaluation_v1` (SAVEPOINT-isolated, Platform Guardian §4), so **every investigation
becomes replayable** from its own row. Engineering endpoints (gated on `is_admin`, never
user-facing):
- `GET /status` — pipeline + AI-specialist readiness (no secrets);
- `GET /stats` — `aggregate_stats` over all stored reports: AI success / fallback /
  citation-failure rates, agreement + number-preserved rates, Governor stats, average latency,
  agreement trend;
- `POST /investigations/{slug}` — run (or return cached) a shadow evaluation for one
  investigation; **the user's production result is unaffected** (only an eval block is added);
- `GET /investigations/{slug}` — read the stored report.

## F. Test results

`cd apps/api && python -m pytest tests/ -q` → **859 passed** (was 846; **+13**), 0
regressions. `tests/test_shadow_mode.py` covers every required area:
- **comparison correctness + metric accuracy** (exact Jaccard / deltas / agreement) and
  **determinism** (stable `comparison_id`);
- **shadow execution** — deterministic (no provider), AI (mock provider), and **fallback**
  (provider error) — each with the right `ai_mode` + Governor permit;
- **Governor compatibility** — both paths permitted; **`number_preserved`** holds on the AI path;
- **replay determinism** (production + shadow reproduce) and **drift detection** (changed model
  → shadow does not reproduce, production still does);
- **metric accuracy** of `aggregate_stats`; **memory-revision** determinism + sensitivity;
- **artifact persistence** + the **admin routes** (run / cache / fetch / stats / status / 404);
- **regression safety** — the shadow run's production assessment **equals** the standalone
  deterministic council's.

## G. Engineering readiness assessment

The question — *does the AI-backed council outperform the deterministic baseline?* — now has a
**measurement apparatus**, but **not yet a verdict**, and that is the honest state:
- **Apparatus: ready.** Shadow execution, deterministic comparison, replay, persistence, and
  aggregate stats are implemented, tested, and operational **without a live model**.
- **Evidence: not yet collectable at signal.** With no HF endpoint, the AI specialist falls
  back to deterministic, so today every shadow run reports `ai_mode=deterministic`,
  `overall_agreement=true`, `number_preserved=true` — correct, but a **null result by
  construction**. Real agreement/disagreement signal requires the live endpoint.
- **Constitutional safety: confirmed.** Across all exercised paths the AI never moved the engine
  number, never fabricated a citation that survived, and never bypassed the Governor; on every
  failure it fell back. The architecture is **safe to run AI in shadow** the moment the endpoint
  exists — no further structural change required.

**Verdict:** ready to *measure*; the comparative answer is **pending live inference**.

## H. Recommendation for Sprint 008

1. **Provision the HF endpoint and collect a shadow corpus.** With `OMI_ANALYST_ENABLED=true` +
   `OMI_ANALYST_ENDPOINT_URL` + `HF_TOKEN`, run Shadow Mode across a labeled evaluation set
   (including the **legitimate-coordination controls** — Platform Guardian §3) and read
   `/v1/admin/shadow/stats`. This produces the first real AI-vs-deterministic evidence.
2. **Add an evaluation harness over the corpus.** A deterministic batch runner that replays a
   fixed bundle set under a pinned model revision and reports agreement trends, disagreement
   exemplars, citation-quality, and **FPR on the controls** — the precision frontier that
   governs whether AI may ever be promoted. Only after that evidence clears should a second
   specialist go AI-backed or any AI reasoning approach production users.

---

*Long-term architecture over short-term sophistication. The deterministic path stays in
production; AI runs in shadow for measurement only; the comparison is deterministic and every
investigation is replayable. The constitution held — number echoed not moved, citations
resolvable, Governor mandatory, Floor the fallback. No engine / scoring / OmiScore change. Gates
green at commit time (859 backend tests). GitHub remains the source of truth; Hugging Face
remains the source of AI assets.*
