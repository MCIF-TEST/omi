# Omi Analyst — Hugging Face Model Lifecycle Strategy (E)

> **Status: specification only.** No upload, no training, no deployment, no
> production wiring. This defines how Hugging Face serves as the **first-class
> registry, store, and version system** for Omi Analyst — and how Analyst model
> versions evolve V1→V4 on the Hub. It mirrors the conventions already established in
> `ml/HUGGING_FACE_INTEGRATION_PLAN.md` (lifecycle tags, pin-never-latest, private
> repos, env-flip rollback) and the model-card discipline in
> `ml/models/omi-behavioral-v1/model_card.md`.

---

## 0. Confirmed reality (verified this session via the HF connector)

- Authenticated as **`Andrewexiga`** (the Omi HF account).
- **`Andrewexiga/omi-analyst-v1`** — exists, **private**, region `us`. This is the
  **permanent home** of Omi Analyst.
- **`Qwen/Qwen3-4B-Thinking-2507-FP8`** — exists: 4.41B params, `qwen3` architecture,
  FP8 quantized, **Apache-2.0**, `text-generation` / `conversational`, a "Thinking"
  (reasoning-trace) variant. This is the **V1 base model**.

Apache-2.0 permits private hosting, fine-tuning, and redistribution of derivatives —
no licensing blocker for the V1→V4 path.

---

## 1. Hugging Face's role (and its hard boundary)

Hugging Face is Omi's **ML layer for the Analyst**: model registry, model storage,
versioning, fine-tuned checkpoints, eval artifacts, datasets, system prompts,
configuration, model cards, and experiment tracking.

> **Boundary (inherited from `HUGGING_FACE_INTEGRATION_PLAN.md`):** HF is **never the
> primary backend**. It never holds the six production stores, never serves a
> first-party user request from the production DB path, and a HF outage must never
> take down OmiSphere. Render + Postgres remain the system of record; the Analyst is
> async, cached, and degrades to the deterministic template.

### Responsibility → HF location map (every responsibility the task names)

| Responsibility | Where on HF | Form |
|---|---|---|
| **Model Registry** | `Andrewexiga/omi-analyst-v1` revisions + lifecycle tags | git-backed, immutable revisions |
| **Model Storage** | `Andrewexiga/omi-analyst-v1` | base pointer (V1/V2), LoRA adapter (V3), merged weights (V4) |
| **Model Versioning** | HF revisions (sha) + semantic tags (`v1`,`v2`,…) | commit history = audit trail |
| **Future Fine-Tuned Checkpoints** | `Andrewexiga/omi-analyst-v1` (adapters in `adapters/`) | safetensors LoRA / merged FP8 |
| **Analyst Evaluation Artifacts** | `Andrewexiga/omi-analyst-v1/evaluation/` + eval **dataset** repo | metrics.json, reports, reliability tables |
| **Analyst Datasets** | separate private **dataset** repos (`omi-analyst-eval`, `omi-analyst-sft`) | governed, versioned, deduped |
| **Analyst System Prompts** | `Andrewexiga/omi-analyst-v1/prompts/` | versioned `.md`/`.txt`, `prompt_version` |
| **Analyst Configuration** | `Andrewexiga/omi-analyst-v1/config/` | decoding params, schema pointer, generation config |
| **Analyst Model Cards** | `Andrewexiga/omi-analyst-v1/README.md` (+ per-version cards) | the HF model card |
| **Analyst Experiment Tracking** | `Andrewexiga/omi-analyst-v1/experiments/` (+ optional W&B) | run manifests, configs, seeds, metrics |

---

## 2. The Analyst registry: `Andrewexiga/omi-analyst-v1`

One repo is the **permanent home** for all Analyst versions. (Despite the `-v1`
suffix, this repo is the *registry*; V2/V3/V4 are **revisions + tags** inside it, not
new repos — so the audit trail stays in one place. A separate repo is created only if
a base-model family changes.)

- **Privacy:** private. Scoped tokens: a **read-only** token for serving; a
  write token only for the offline publish job.
- **Versioning:** every Analyst version is an **immutable HF revision** (commit sha),
  also given a human tag (`v1`, `v2`, …) and a lifecycle tag (§3).
- **Reproducibility:** every revision pins (a) the base-model revision it derives
  from, (b) the `prompt_version`, (c) the `schema_version`, (d) the eval-dataset
  revision it was measured on.

See `REPOSITORY_STRUCTURE.md` (deliverable F) for the exact file/folder layout of
this repo.

---

## 3. Lifecycle tags & promotion workflow

Identical state machine to the detector registry in
`HUGGING_FACE_INTEGRATION_PLAN.md` §D/§E:

```
        offline eval gate            shadow holds            analyst review
  build ───────────────▶ shadow ──────────────▶ candidate ──────────────▶ production
   │  (ml/analyst eval)    │ (generate + log,      │ (served to a subset    │ (default
   │                       │  do NOT surface)      │  / behind a flag)      │  Analyst)
   └───────────────────────┴───────────────────────┴────────────────────────┘
                          rollback = repoint pinned revision / flip flag
```

- **build → shadow:** must pass the §5 offline eval gate (schema validity,
  faithfulness, calibration, verdict-bound compliance, legitimate-coordination FPR).
- **shadow:** the revision generates assessments that are **logged and compared**, but
  the product still shows the template/previous version. No user impact.
- **shadow → candidate:** shadow agreement + no regressions over N bundles → tag
  `candidate`, expose behind a flag to a subset.
- **candidate → production:** sustained analyst-accept rate + no precision regression →
  tag `production`. Promotion is a **deliberate tag + config change**, never automatic.
- **Pin a revision, never `latest`.** Production points at a pinned sha (reproducible,
  blue/green at the artifact level).

---

## 4. Serving model (honest engineering note)

A 4.4B FP8 reasoning model is **not** the CPU-only, in-process, sub-millisecond
profile of the dormant tabular `app/ml/scorer.py`. The Analyst is therefore served
**off the request-critical path**:

- **Async + cached**, exactly like today's `app/reasoning/` commentary (generated in
  the background, cached on the `Investigation` row, regenerated only on explicit
  refresh). A scan never blocks on the Analyst.
- **Inference options (gated, off by default):**
  1. **HF Inference Endpoint** (dedicated, private) pointed at the pinned revision —
     simplest, pay-per-use, scales to zero.
  2. **Small dedicated GPU** (Render/other) running vLLM/TGI with the FP8 weights —
     FP8 4.4B ≈ ~4.5 GB, fits a modest GPU; best if volume is steady.
  3. **Batched offline reasoning** — assessments computed in a queue, not per request.
- **Always-on fallback:** the deterministic `TemplateProvider` remains the default and
  the failover, so the product works with the Analyst disabled or unreachable (same
  graceful-degradation contract as `AnthropicProvider` today).
- **Cost discipline:** off by default; enabled deliberately. Endpoint scale-to-zero or
  a single small GPU keeps this bounded. This is a **deliberate, separately-scoped
  architectural addition** beyond the current ~$20/mo Render footprint — flagged and
  optional, never silently switched on.

> This deviates from the "CPU-only, in-process" assumption of the tabular ML plan, and
> that deviation is stated openly here rather than buried — the reasoning layer has
> different serving economics than a learned scalar prior, and the async/cached/
> fallback design is what keeps it safe.

---

## 5. Boot / config / rollback (mirrors the scorer seam)

- **Boot:** when enabled, the serving layer resolves the pinned revision via
  `huggingface_hub` (download adapter/config, or point the inference endpoint at the
  revision), loads decoding config + the pinned `prompt_version` + `schema_version`.
- **New env (all pinned / `sync:false`):** `OMI_ANALYST_HF_REPO`
  (`Andrewexiga/omi-analyst-v1`), `OMI_ANALYST_HF_REVISION` (**pinned sha, never
  latest**), `OMI_ANALYST_ENABLED` (default false), `OMI_ANALYST_ENDPOINT_URL`,
  `HF_TOKEN` (read-only).
- **Rollback — three independent levers (any one is sufficient):**
  1. **Kill switch:** `OMI_ANALYST_ENABLED=false` → template fallback resumes; no
     redeploy. (Same env-flip philosophy as `OMI_USE_ML_SCORER`.)
  2. **Version rollback:** repoint `OMI_ANALYST_HF_REVISION` to the prior immutable
     revision + restart.
  3. **Schema guard:** an output that fails `analyst_response_schema.json` is rejected
     and the template is used — a bad model revision cannot ship a malformed verdict.
- **Postgres is never touched by the Analyst layer** → an Analyst failure cannot lose
  or corrupt the system of record.

---

## 6. Datasets on HF (Analyst-specific)

Per `future_finetuning_strategy.md`, two governed **dataset** repos (private,
versioned, `manifest`-disciplined, quarantine never synced):

- **`Andrewexiga/omi-analyst-eval`** — the held-out eval set (hand-built bundles +
  reference assessments). Every Analyst revision records the eval-dataset revision it
  was measured on.
- **`Andrewexiga/omi-analyst-sft`** — the V3 gold reasoning dataset
  (`bundle → JSON + report [+ trace]`). **Empty until analyst-verdict gold is
  collected** — the real blocker.

Dataset governance is enforced **at sync**, exactly as for the behavioral datasets:
only manifest-approved splits, PII hashed, by-account/by-campaign grouping preserved.

---

## 7. Model card requirements (every Analyst revision)

Each production-eligible revision ships an HF model card (the `README.md` of the repo
revision) carrying, at minimum (matching `omi-behavioral-v1/model_card.md`):

- **Overview:** version, base model + revision, task (evidence interpretation, NOT
  detection), output (structured JSON + report), prompt_version, schema_version.
- **Intended use & boundary:** decision support for a human analyst; **not** a
  detector, **not** an enforcement system, **not** evidence about a real person.
- **Eval results:** schema validity, faithfulness, calibration, verdict-bound
  compliance, counter-evidence recall, **legitimate-coordination FPR**, banned-phrase
  rate — on the pinned eval-dataset revision.
- **Limitations (stated plainly):** the honest data constraint (gold reasoning set
  empty for V1/V2), domain-shift (engine validated mostly on X), the failure modes
  it is and isn't robust to.
- **Promotion status:** `shadow` / `candidate` / `production` and what gates it passed.

---

## 8. Experiment tracking

- **In-repo:** an `experiments/` folder of run manifests (config, base + dataset
  revisions, seed, hyperparameters, resulting metrics) — git history is the immutable
  ledger, no external service required (same self-contained philosophy as the rest of
  `ml/`).
- **Optional:** Weights & Biases for richer dashboards if/when fine-tuning volume
  grows — additive, never a dependency for reproducibility.

---

## 9. Cost posture

| Item | Plan | ~$/mo |
|---|---|---|
| Existing Render baseline (api/web/postgres) | unchanged | ~20 |
| HF private model repo (`omi-analyst-v1`) | free tier | 0 |
| HF private dataset repos (eval/sft) | free tier | 0 |
| Analyst inference (when enabled) | HF Endpoint scale-to-zero **or** one small GPU | variable, gated, off by default |
| Analyst disabled (default) | template fallback | 0 |

V1/V2 spec + registry + eval set cost **~$0**. Inference cost is incurred only when
the Analyst is deliberately enabled, and is bounded by scale-to-zero or a single small
instance. Explicitly avoided: always-on GPU, per-request synchronous LLM calls, any
design that puts the Analyst on the scan-critical path.

---

*Specification only. No HF upload, no checkpoint, no endpoint, no production change.
Hugging Face is the Analyst's registry/store/versioning layer; Render + Postgres
remain the system of record; the Analyst is async, cached, gated, and template-backed.*
