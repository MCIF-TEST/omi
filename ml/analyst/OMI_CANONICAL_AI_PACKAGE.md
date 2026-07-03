# Omi — Canonical AI Package (final production AI architecture, increment 1)

> **Objective.** Make the Hugging Face deployment package the **canonical AI layer**, keep the
> deterministic engine as the **authoritative source of evidence**, and run **one investigation →
> one model inference → one governed report**. This increment establishes the canonical package as
> a first-class, content-addressed, drift-guarded runtime unit and completes the single-surface
> consolidation. The prompt-*content* promotion (framework/knowledge text into the prompt body) is
> the operator-validated Phase 2 — see §5.

---

## 1. Current runtime (before this sprint)

```
User → scan → DETERMINISTIC ENGINE (authoritative) → Investigation.payload_json
  → maybe_autogenerate → assess_payload → Evidence Bundle → Prompt Registry (in-app)
     → Memory → RemoteReasoningProvider → HF Mistral → Governor → Floor-on-reject → cache
REPORT: AnalystPanel (governed, HF) — with a MANUAL "Generate/Regenerate" button
      + CommentaryBlock (a SECOND free-text AI surface via providers.py → Anthropic/template)
No single "AI package" identity; prompt/framework/knowledge/constitution provenance scattered.
```

## 2. Final runtime (this sprint)

```
User → scan → DETERMINISTIC ENGINE (unchanged, authoritative) → Evidence Bundle
  → Memory → assess_payload
     → load_ai_package()  ── the CANONICAL, content-addressed AI deployment package ──
          prompt registry (ph:) · specialist framework (sf:) · knowledge library (il:) ·
          constitution (cx:)  → package_hash (pkg:)   [loaded from bundled data == published to HF]
     → RemoteReasoningProvider → HF Mistral-7B → structured JSON → MANDATORY Governor
     → Floor on reject → persist (assessment carries ai_package + metrics + governance)
REPORT: ONE AI surface — AnalystPanel, AUTO-loaded (no manual generation). Commentary retired.
```

The website talks only to the backend; the backend calls the HF **inference** endpoint (the Governor
+ token stay server-side). **Nothing fetches prompts from GitHub or HF at runtime** — verified: the
web tree has zero `github.com`/`githubusercontent` references, and the package loads from bundled
data. "HF is canonical" is proven by a **drift guard** (runtime package == the published HF
manifests), not by coupling every investigation to HF availability.

## 3. Files changed

| File | Change |
|---|---|
| `apps/api/app/reasoning/package.py` | **NEW** — `AIPackage` + `load_ai_package()`: the canonical, content-addressed AI deployment package (prompt/framework/knowledge/constitution → `package_hash`). |
| `apps/api/app/reasoning/analyst.py` | `assess_payload` loads the package and records `ai_package` provenance + `metrics.package_hash` on every assessment. |
| `apps/api/app/routes/reasoning.py` | `/analyst/integrity` exposes the live `ai_package`. |
| `apps/web/.../analyst-panel.tsx` | Removed **manual analyst generation** (Generate/Regenerate buttons); auto-load only. |
| `apps/web/.../investigations/[slug]/page.tsx` | Removed the duplicate **CommentaryBlock** — one governed AI surface per report. |
| `apps/web/.../commentary-block.tsx` | **Deleted** (orphaned dead code). |
| `apps/api/tests/test_ai_package.py` | **NEW** (6) — package completeness, determinism, the **drift guard** (runtime == published HF package), provenance on the assessment, integrity exposure. |

Kept (deliberately, to avoid breaking live features / destructive churn): `providers.py` and the
`/commentary` backend route — the second provider abstraction still powers **account** and
**narrative** free-text analysis (`accounts.py`, `narratives.py`), so it is not obsolete. Only the
duplicate *investigation-report* commentary surface was retired.

## 4. End-to-end verification (this environment)

One investigation, driven through the real API with the analyst configured (messages API) against a
logging HF stand-in:
- `scan → 202`, then **exactly ONE** request reached the endpoint:
  `POST /v1/chat/completions model=mistralai/Mistral-7B-Instruct-v0.3 auth=yes`.
- Governed result: provider `qwen-omi-analyst-v1` (model-backed), **Governor `permit`**.
- The report assessment carries `ai_package = pkg:28d757…` (`source: deployed-ai-package, published
  to HF Andrewexiga/omi-analyst-v1`) with components `ph:715d… / sf:a93f… / il:36e59…`, and
  `metrics.package_hash` matches.
- Drift guard green: runtime `ph:/sf:/il:/cx:` == the published `prompt_manifest` / `prompt_catalog`
  / `knowledge_manifest`.
- Backend suite green (count in the commit); `next build` + `tsc --noEmit` pass.

**Not verifiable here:** the *live* HF endpoint (egress to huggingface.co is blocked; no live URL).
Operator runs `endpoint_smoke_test()` → `model_backed:true, model_matches:true` against the real
endpoint to close that leg — the code path and package provenance are proven.

## 5. Remaining blockers / next increments

1. **Prompt-content promotion (Phase 2).** Compose the Specialist Framework handbook + relevant
   Knowledge Library entries + the Context Builder's structured context INTO the single Mistral
   prompt, and extend the response schema to the richer report sections (Behavioral / Coordination /
   Narrative / Authenticity / Alternative Explanations / Recommended Next Investigation). This is a
   **model-behavior change** requiring live-endpoint A/B evaluation (Gold-Corpus control-FPR must not
   regress — the precision frontier) that **cannot be validated from this sandbox** (the model is
   mocked; the deterministic floor ignores the prompt). It is the right next sprint, operator-run.
2. **Persistent database** (still #1): sqlite on Render's ephemeral disk loses users, investigations,
   and cached assessments on redeploy → move `OMI_DATABASE_URL` to Postgres.
3. **Authoritative token/cost**: capture the endpoint `usage` object into `metrics` (replaces the
   char/4 estimate).
4. **Optional**: retire the `/commentary` backend route + DB columns once account/narrative analysis
   is migrated off `providers.py` (a separate, non-urgent consolidation).

---

*Preserved: deterministic evidence generation (authoritative), the mandatory Governor, the always-on
Floor, explainability, and reproducibility (now including a single `package_hash` per assessment).
No detector, score, or OmiScore was touched.*
