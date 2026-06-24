# Recommended Repository Structure — `Andrewexiga/omi-analyst-v1` (F)

> **Status: specification only.** No files are uploaded by this document. This is the
> recommended layout for the **Hugging Face model repository** that is the permanent
> home of Omi Analyst. It conforms to `huggingface_model_lifecycle.md` (E) and the HF
> conventions in `ml/HUGGING_FACE_INTEGRATION_PLAN.md`. The GitHub-side specs (this
> `ml/analyst/` folder) are the **source of truth**; the HF repo **mirrors** the
> approved, versioned artifacts.

---

## 0. Two repos, one source of truth

| Repo | Role | Authority |
|---|---|---|
| **GitHub** `omi/ml/analyst/` | The specs, schema, prompts, strategy (this folder) | **Source of truth** — versioned in the app monorepo, reviewed via PR |
| **HF model** `Andrewexiga/omi-analyst-v1` | Registry/store/versioning of the running Analyst (weights, adapters, eval artifacts, the *published* prompt/schema/config) | **Mirror + runtime registry** — immutable revisions, lifecycle tags |
| **HF datasets** `Andrewexiga/omi-analyst-eval`, `omi-analyst-sft` | Eval + SFT data | Governed dataset repos (see E §6) |

The prompt/schema/config are **authored in GitHub** and **published to HF** at each
revision, so the running model and its contract are pinned together and reproducible.

---

## 1. Recommended layout of `Andrewexiga/omi-analyst-v1`

```
Andrewexiga/omi-analyst-v1/                 (private HF model repo — the registry)
│
├── README.md                  ← the HF MODEL CARD (current production revision)
│                                 overview · intended-use boundary (interprets evidence,
│                                 is NOT a detector/enforcement system) · eval results ·
│                                 limitations · promotion status. Per E §7.
│
├── config/
│   ├── analyst_config.json    decoding params (temperature ~0.2, max_tokens, top_p),
│   │                          response_format pointer, base-model id + pinned revision,
│   │                          prompt_version, schema_version it expects
│   └── generation_config.json HF generation config (stop tokens, thinking-trace handling)
│
├── prompts/                   ← versioned system prompts (published from ml/analyst/)
│   ├── analyst_system_prompt_v1.md
│   └── CHANGELOG.md           what changed between prompt_versions and why
│
├── schema/
│   └── analyst_response_schema.json   ← published copy of deliverable C (pinned per revision)
│
├── base/                      ← V1/V2: NO weights, just a pointer
│   └── BASE_MODEL.md          "derives from Qwen/Qwen3-4B-Thinking-2507-FP8 @ <revision>";
│                              V1/V2 ship no weights of their own (base + prompt only)
│
├── adapters/                  ← V3+: fine-tuned checkpoints (LoRA/QLoRA)
│   └── v3/
│       ├── adapter_model.safetensors      the small adapter artifact
│       ├── adapter_config.json
│       └── TRAIN_MANIFEST.json            base rev · dataset rev · hyperparams · seed
│   (V4 may ship merged FP8 weights here instead of an adapter)
│
├── evaluation/                ← Analyst evaluation artifacts (per E)
│   ├── v1/
│   │   ├── metrics.json        schema-validity · faithfulness · calibration ·
│   │   │                       verdict-bound compliance · counter-evidence recall ·
│   │   │                       legitimate-coordination FPR · banned-phrase rate
│   │   ├── reliability.json     confidence-band calibration table
│   │   └── REPORT.md            human-readable eval summary + which eval-dataset revision
│   └── v2/ …                    one folder per Analyst version
│
├── experiments/               ← experiment tracking (run ledger; git history = audit trail)
│   └── runs/<run_id>/
│       ├── run_manifest.json   config · base rev · dataset rev · seed · metrics
│       └── notes.md
│
├── model_cards/               ← per-version cards (README.md tracks current production)
│   ├── model_card_v1.md
│   └── model_card_v2.md
│
└── .gitattributes             LFS for *.safetensors
```

### Lifecycle tags (HF revision tags, not folders)
`shadow` · `candidate` · `production` — applied to revisions, per E §3. Plus semantic
tags `v1`, `v2`, `v3`, `v4`. Production serving pins a **revision sha**, never a
moving tag.

---

## 2. What each Analyst version actually stores here

| Version | Stored in the repo | Notes |
|---|---|---|
| **V1** (base Qwen) | `config/`, `prompts/v1`, `schema/`, `base/BASE_MODEL.md`, `evaluation/v1/`, `model_cards/model_card_v1.md` | **No weights** — base model + system prompt. The contract *is* the artifact. |
| **V2** (prompt-engineered) | + `prompts/v2`, few-shot exemplars, `evaluation/v2/` | Still no weights; refined prompt + in-context examples + schema-constrained decoding. |
| **V3** (fine-tuned) | + `adapters/v3/` (LoRA), `evaluation/v3/`, `experiments/runs/...` | Small adapter over the base; reversible; tiny artifact. |
| **V4** (Omi reasoning model) | + `adapters/v4/` or merged FP8 weights, preference-tuning run manifests | DPO/RLAIF; precision-frontier FPR is a hard gate. |

---

## 3. Companion dataset repos (governed; see E §6 and D)

```
Andrewexiga/omi-analyst-eval/      (private dataset)   held-out eval bundles + reference assessments
│   ├── README.md (dataset card: provenance, governance, grain coverage, trap coverage)
│   ├── bundles/         evidence bundles (one per case, schema-projected)
│   ├── references/      human target outputs (valid against analyst_response_schema.json)
│   └── manifest.toml    governance: split, source, grouping keys (account/campaign)

Andrewexiga/omi-analyst-sft/       (private dataset)   V3 gold reasoning set — EMPTY until gold collected
│   ├── README.md (dataset card; states the 0-row blocker honestly)
│   ├── train/  validation/        (bundle → JSON + report [+ reasoning trace]) pairs
│   └── manifest.toml    by-account/by-campaign/by-domain splits; quarantine excluded
```

Both follow the same governance as the behavioral datasets: only manifest-approved
splits sync, PII stays hashed, grouped splits prevent account/campaign leakage, and
the dataset card states limitations plainly.

---

## 4. Publish flow (GitHub → HF), when implemented later

1. Author/modify specs in `omi/ml/analyst/` (PR-reviewed in the monorepo).
2. An offline publish job (a later, scoped task) pushes the approved
   `prompts/`, `schema/`, `config/` to a new HF **revision**, plus any adapter/eval
   artifacts.
3. The revision is tagged `shadow`, runs the eval gate, and advances
   `shadow → candidate → production` per E §3.
4. Production config pins the resulting **revision sha**.

This keeps GitHub authoritative for the contract and HF authoritative for the *running
artifact + its immutable history* — no drift, full reproducibility.

---

## 5. Naming & hygiene conventions

- **Pin revisions, never `latest`** (reproducibility + safe rollback).
- **One registry repo** (`omi-analyst-v1`) for all versions; a new repo only on a
  base-model family change.
- **Private repos + scoped tokens:** read-only for serving, write only for the publish
  job.
- **LFS** for any weights/adapters; specs/prompts/schema/config stay as plain text so
  they diff cleanly in HF's git history.
- **Every revision is self-describing:** its model card records base rev, prompt
  version, schema version, eval-dataset revision, and promotion status.

---

*Specification only. No HF repository was created or modified by this document; it
recommends the structure for the existing private `Andrewexiga/omi-analyst-v1` and its
companion dataset repos.*
