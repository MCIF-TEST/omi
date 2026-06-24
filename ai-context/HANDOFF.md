# OmiSphere — HANDOFF (current project state)

> **Read this first, every session.** This is the single most frequently
> updated file and the canonical "where are we / what is everything" map.
> Update it on every code change (see *Maintenance rules* at the bottom).
> It supersedes the legacy root `/HANDOFF.md` (dated 2026-05-29, describes a
> long-resolved push-token incident) — that file is kept only for history and
> should not be trusted for current state.

_Last updated: 2026-06-24 · active branch: `claude/stoic-edison-2ueecx` · last large arc: **Omi Analyst working implementation** (OMI_ANALYST_IMPLEMENTATION_V1; ml/ R&D, schema-valid, 25/25 tests; no train/prod/engine change; see §2.0)_

---

## 0. TL;DR — what OmiSphere is and where we are

**What it is.** OmiSphere is a coordination-intelligence platform: it scores
how likely an account / comment-section / narrative / campaign reflects
**inauthentic or coordinated behavior**, and — crucially — shows the *evidence
and confidence behind the number*, never a bare verdict. Core doctrine:
*evidence, not verdict*; a **corroboration gate** (no single non-discriminative
signal may drive a maximal "coordinated" verdict); store probabilities +
evidence, never persisted verdicts.

**Shape of the system.**
- `apps/api` — FastAPI backend: the detection engine, scoring, six data
  "stores," all routes, persistence, integrations (YouTube live; X/Twitter
  partial). This is production and is **stable** — do not change scoring/engine
  logic without explicit scope.
- `apps/web` — Next.js 14 (App Router) frontend, "OmiSphere" intelligence
  command center. **Just received a full UI Evolution this session** (see §2).
- `ml/` — decoupled, **R&D-only** ML/Hugging Face workspace (datasets, feature/
  label schemas, a PyTorch behavioral NN foundation, a unified corpus, HF
  connectivity/upload/sync pipelines). **Nothing here is wired into production
  scoring yet** — the `app/ml/scorer.py` blend seam is dormant by design.
- `datasets/` — the governed ground-truth corpora + their manifest/trust docs.
- `references/`, `docs/`, `ai-context/`, `infrastructure/`, `packages/` —
  design taste references, long-form docs, project memory, deploy config, shared
  types. Details in §3.

**Where we are right now (state of play).**
- **Frontend:** UI Evolution V1 is **complete** — every screen (26 pages) was
  re-skinned into the neutral-obsidian + electric-blue→violet "intelligence"
  identity, and a 7-point UX critique was addressed (verdict hero, evidence
  columns, contrast, tier consistency, etc.). Typecheck + build green.
- **ML/HF:** Foundations are **built but offline.** A behavioral NN foundation,
  a trainable dataset pipeline, a unified normalized corpus, and read/write HF
  connectivity + upload + auto-sync pipelines all exist and are tested — but the
  honest finding is the V1 behavioral model is a *username-morphology shortcut*
  (no-username AUC ≈ random), so **the binding constraint is new labeled data,
  not more modeling.**
- **Backend:** Unchanged this session. Last backend work (mid-June) made
  monitoring platform-aware and fixed narrative false-positives / content
  ingestion. Stable, gated, green.
- **Strategic:** Repeatedly surfaced across audits — engineering is *ahead of
  adoption*; the real lever is users/distribution, not more features.

---

## 1. Current Objective

No active feature build in flight. The last large workstreams (UI Evolution V1;
ML/HF/corpus foundations) are landed. Default posture is back to
**audit-remediation**: verify a finding against the code, ship the smallest safe
fix with all gates green, one at a time. The highest-value *open* item is
**Open Finding #1** (scoring decision-surface simplification — UI-only, zero
engine risk; see §4). The highest-value *strategic* lever is user acquisition.

---

## 2. Recently Completed (this session, newest arc first)

Branch auto-merges into `main` in the remote env. Grouped by workstream; commit
hashes are the tip of each arc.

### 0. Omi Analyst — working implementation (`ml/analyst/omi_analyst/`) ← newest
Goal (OMI_ANALYST_IMPLEMENTATION_V1): a **runnable, schema-validated Omi Analyst** that
interprets existing engine evidence into the four assessment types (account, campaign,
narrative, investigation), each with supporting + contradicting evidence, a confidence
explanation, an uncertainty statement, and a recommended next step. **No fine-tune, no
train, no detector/scoring/OmiScore/apps change** — built entirely in the decoupled `ml/`
tree. Grounded in the real `app/reasoning/` seam (`LLMProvider`/`ProviderResult`/template
fallback) + the engine evidence shapes (`ScanResult`/`SignalResult`/`DetectorContribution`/
`ScoreBreakdown`/OmiScore/coordination/narrative). Built `ml/analyst/omi_analyst/`:
`config.py` (loads `analyst_config.json` from the HF registry `Andrewexiga/omi-analyst-v1`
with local-mirror fallback), `evidence_bundle.py` (Appendix-A projection),
`providers.py` (**DeterministicAnalystProvider** always-on + schema-valid, **QwenAnalystProvider**
gated/off-by-default with graceful fallback — mirrors AnthropicProvider→Template),
`schema_validate.py` (dependency-free validator vs `analyst_response_schema.json` + banned-phrase
+ F1/F5 guards), `store.py` (JSONL output store for future training data), `analyst.py`
(orchestrator with the 4 entry points). Plus `run_analyst_demo.py` (all 4 valid) and
`test_omi_analyst.py` (**25/25 green**). Echoes engine probability/tier (never recomputes),
respects the corroboration gate (non-discriminative coordination can't reach `coordinated`),
treats supplemental ai_writing as context, forces `inconclusive` on thin data. **Off by
default**; deterministic path makes it work today. Production wiring (add `OmiAnalystProvider`
to `app/reasoning/`, async/cached, template fallback) is the documented next step (spec
Appendix B) — intentionally NOT done to keep the engine untouched.

### 0a. Omi Analyst — HF model registration / import (`ml/analyst/hf_repo/` + pipeline)
Goal (OMI_ANALYST_MODEL_IMPORT_V1): make `Andrewexiga/omi-analyst-v1` the permanent,
*configured* registry for the reasoning model — **no fine-tune, no train, no
production/scoring/detector/OmiScore change**. Audited HF live via the connector:
authenticated `Andrewexiga`; the target repo **exists but was an empty private shell**
(only `region:us`, no card, no `base_model`); base `Qwen/Qwen3-4B-Thinking-2507-FP8`
verified (qwen3, ~4.41B, FP8, Apache-2.0). Authored the **push-ready HF repo** under
`ml/analyst/hf_repo/` — the **model card** (root `README.md` whose `base_model:` YAML
metadata is what *configures the foundation model* on the Hub), `config/analyst_config.json`
+ `generation_config.json`, `base/BASE_MODEL.md` (V1 ships **no weights**), `.gitattributes`
— plus a manifest-driven registration pipeline (`hf_repo_manifest.toml`,
`register_hf_model.py` validate-default/`--upload`, `test_register_hf_model.py` **11/11
green**) and a **pull verifier** (`ml/inference/hf_analyst_pull_check.py`) with two
manual-dispatch workflows (`hf-analyst-register.yml`, `hf-analyst-pull.yml`) following the
existing HF-CI pattern. **Honest status: the HF repo is NOT yet populated** — this remote
container has no `HF_TOKEN`/`huggingface_hub` (the HF MCP is read-only), so the actual write
runs via the existing **GitHub Actions `HF_TOKEN` secret** (trigger `hf-analyst-register`
mode=upload; then `hf-analyst-pull` to confirm GitHub can pull it). Lifecycle + versioning
were already specced in `huggingface_model_lifecycle.md` / `future_finetuning_strategy.md` /
`REPOSITORY_STRUCTURE.md`.

### 0b. Omi Analyst V1 — specification for the reasoning layer (`ml/analyst/`, spec-only)
Goal: define **how Omi Analyst thinks** before any build/fine-tune/deploy. Omi Analyst
is the **reasoning layer** (powered by `Qwen/Qwen3-4B-Thinking-2507-FP8`, home HF
`Andrewexiga/omi-analyst-v1`) that *interprets* the engine's evidence — it is **not**
the detector. Researched ground truth first (evidence schemas in `app/schemas.py` +
`intelligence/schemas.py`; the `app/reasoning/` LLM seam it slots into; corroboration
gate; 42-dim feature + label contracts; the username-shortcut audit; HF account/repo
verified live via the connector). Produced **`ml/analyst/`**: `OMI_ANALYST_SPEC_V1.md`
(21-section operating manual), `analyst_system_prompt_v1.md`,
`analyst_response_schema.json` (draft 2020-12, validated), `future_finetuning_strategy.md`,
`huggingface_model_lifecycle.md`, `REPOSITORY_STRUCTURE.md`, `README.md`. Core
contract: evidence-not-verdict, echoes (never recomputes) engine scores, respects the
corroboration gate / single-axis cap, supplemental signals (AI-writing) are context
not suspicion, mandatory counter-evidence + uncertainty, async/cached/template-fallback
serving (no request-path change). **No code, scoring, model, dataset, or deployment
changed.** Honest blocker recorded: V1/V2 (base + prompt) are doable now; V3/V4
(fine-tune) are blocked on **gold reasoning labels (0 rows today)** — same lesson as
the behavioral model. Updated `ml/README.md` + this file.

### A. UI Evolution V1 — full product-design transformation (frontend only)
Goal: make OmiSphere *look and feel* like a premium OSINT / intelligence command
center, not a social-analytics dashboard — **without** touching backend logic,
scoring, APIs, DB, or ML. Design `references/` used as *taste guidance, not
clones*. Living record: `apps/web/UI_EVOLUTION.md`. Every increment
`typecheck` + `next build` verified (26/26 pages).

| Commit | What |
|--------|------|
| `321a770` | **UX fixes #3/#4/#7** — human-readable titles (bounded by backend `label`), tier-vocabulary consistency via the `TierBadge` pill, mono/gradient-border discipline |
| `a83def6` | **UX fixes #1/#2/#6** — verdict *hero* (fused ScoreRing 96→132px + tier + "% inauthenticity probability" + ConfidenceBand); evidence-for/against rebuilt as two columns with check/dash icons |
| `a1d1f51` | **UX fix #5** — lifted secondary-text contrast to WCAG AA (new `--text-*` tokens) |
| `2f101ea`→`c16a1ff` | **Page sweep 1–18** — every surface re-skinned to the blue→violet identity: shell/dashboard/campaigns/narratives/investigations lists, account & investigation detail, content DB, campaign & narrative detail, auth, settings, landing, marketing shell, graph, monitoring, search, bulk, pricing, about, investigate workspace, content detail, channel detail, public report |
| `7addff8` | **New visual language** — neutral obsidian canvas + rebuilt primitives (card/button/badge/input/dialog) |
| `f344136`,`a290ae1` | Design-token foundation; ConfidenceBand reads uncertainty as desaturation |
| `994c655` | Added `references/` design systems + `apps/web/DESIGN_REFERENCES.md` direction (docs/assets only) |

Locked identity: neutral-obsidian surfaces; electric-blue→violet `--grad-brand`
signature (blue = action/authenticity, violet = AI-reasoning/coordination);
aurora atmosphere; cluster-1..8 colors; confidence-as-desaturation; display
numerals for stats; rounded-full pill badges; `TierBadge` = color+label+dot+
tooltip-scale. Honest caveats: human titles are bounded by backend `label`;
graph node cluster-coloring needs backend `community_id` (out of FE-only scope).

### B. Hugging Face connectivity + upload + auto-sync (ml/ only, offline)
| Commit | What |
|--------|------|
| `e5ec8b1` | **Auto-sync** GitHub→HF datasets (`ml/datasets/hf_sync.py`, `sync_config.toml`, GH workflow `hf-sync-datasets.yml`) |
| `895f796` | **Production-safe upload** pipeline GitHub→HF (`ml/datasets/hf_upload.py`, `upload_manifest.toml`, workflow `hf-dataset-upload.yml`) |
| `4b994b6` | HF dataset **read+write** connectivity check (`ml/inference/hf_dataset_connectivity_check.py`, workflow `hf-dataset-connectivity.yml`) |
| `bb5e1ec` | Read-only HF connectivity check (`ml/inference/hf_connectivity_check.py`, workflow `hf-connectivity.yml`, `HF_CONNECTIVITY.md`) |

### C. Behavioral neural-network foundation + trainable dataset (ml/ only, offline)
| Commit | What |
|--------|------|
| `819d6f8` | **Trainable dataset pipeline** — `dataset_builder.py` emits train/validation/test parquet under `ml/models/omi_behavioral_nn/data/` per OMI_FEATURE_SCHEMA_V1 |
| `561723d` | **OmiBehavioralNet V1 foundation** — PyTorch CPU MLP (`model.py`, `train_nn.py`, `evaluate_nn.py`, `predict_nn.py`, tests); `ml/OMI_NEURAL_NETWORK_V1.md` |

### D. Unified corpus — discovery, normalization, audit (ml/ only, offline)
| Commit | What |
|--------|------|
| `bf1ce23`,`b7b26da`,`89e7684` | **Corpus audit** — full uncapped line-by-line scan of every governed dataset → `ml/corpus/CORPUS_AUDIT_V1.md` + stats/CSV/quality report; V1-readiness recommendation |
| `d85eaad` | **Unified corpus** — discovery + normalization into one schema (`ml/corpus/omi_corpus.py`, `UNIFIED_OMI_SCHEMA.md`, `data/merged_corpus.parquet`) |

### E. ML/HF foundations + project memory (earlier this session)
| Commit | What |
|--------|------|
| `8614ebb` | HF dataset **organization** V1 — inventory + migration map + upload plan (docs only; no files moved — a physical move would break prod path reads + poison-gating) |
| `3fdc19b` | Behavioral V2 **data audit** — proved V1 is a username shortcut (no-username AUC 0.546 ≈ random) → prioritize new data, not modeling |
| `aaf80fd` | Omi Behavioral Model **V1** — offline XGBoost baseline (held-out F1 0.876 / AUC 0.982 but ~89% gain = username morphology) |
| `6e5c485` | Omi **Label** Schema V1 (docs) — engine-independent label contract |
| `4c0d84e` | Omi **Feature** Schema V1 (docs) — canonical 42-dim `build_feature_vector` contract |
| `a5199b0` | **Hugging Face integration plan** (docs) — HF as the ML layer |
| `577fba6` | Omi **Neural Network V1** architecture plan (docs) |
| `e0abe64` | **Omi Intelligence Foundation** — created decoupled top-level `ml/` scaffold (docs-only, no prod wiring) |
| `61100f1` | Created the **`ai-context/`** project-memory system (this file + VISION + ARCHITECTURE) |

### F. Backend remediation (mid-June, pre-dates this session's ML/UI arcs)
`eb9dafa` monitoring platform-awareness · `08440f4` one-click Add-to-Monitoring ·
`46be015` content-DB ingestion from comprehensive scan · `c0c7952` human-readable
content titles · `07fa85c` honest campaign anonymized-member labeling ·
`7ce46aa` narrative false-positive fix (corroboration-gate the coordination
label) · `f869bbd` investigation-confidence visibility · `65b8259` X→YouTube
scan-routing fix.

---

## 3. Repository map — every folder & file does what

Annotated tree. `/` = directory. One line = its job. (Generated artifacts —
`__pycache__/`, `.next/`, `node_modules/`, `*.egg-info/`, `.pytest_cache/` —
omitted.)

```
omi/
├── ai-context/                 Project memory — READ ALL THREE at session start
│   ├── HANDOFF.md              ← this file: current state + repo map (update every change)
│   ├── ARCHITECTURE.md         How the system is built (engine, stores, data flow, ml/ seam)
│   └── VISION.md               Mission / product scope / doctrine (evidence-not-verdict)
│
├── apps/
│   ├── api/                    FastAPI backend — PRODUCTION; the detection engine
│   │   ├── app/
│   │   │   ├── main.py         FastAPI app factory, router mounting, middleware wiring
│   │   │   ├── orchestrator.py Scan orchestration — runs a full account/content scan end-to-end
│   │   │   ├── schemas.py      Top-level Pydantic request/response models
│   │   │   ├── detection/      THE ENGINE — per-signal detectors + scoring
│   │   │   │   ├── engine.py           Detector orchestration → combined signals
│   │   │   │   ├── scoring.py          Probability blend + tier banding (LOW/MOD/ELEV/HIGH)
│   │   │   │   ├── ai_writing.py       AI-generated-text signal
│   │   │   │   ├── semantic.py         Semantic-similarity / message-uniformity signal
│   │   │   │   ├── temporal.py         Timing / burst / synchrony signal
│   │   │   │   ├── voice.py            Stylometric "voice" fingerprint signal
│   │   │   │   ├── profile.py          Account-profile heuristics
│   │   │   │   ├── engagement.py       Engagement-pattern signal
│   │   │   │   ├── community.py        Community/cluster membership signal
│   │   │   │   ├── narrative.py        Narrative-alignment signal
│   │   │   │   ├── trend.py            Trend/velocity signal
│   │   │   │   ├── correlation.py      Cross-signal correlation
│   │   │   │   ├── correlation_fit.py  Fitted correlation weights/calibration
│   │   │   │   └── coordination/       CLUSTER-LEVEL coordination detectors
│   │   │   │       ├── aggregate.py            Combine coordination sub-signals (corroboration gate)
│   │   │   │       ├── co_engagement.py        Co-engagement (same targets) detector
│   │   │   │       ├── co_tag.py               Shared-hashtag/tag detector
│   │   │   │       ├── cohort.py               Account-cohort grouping
│   │   │   │       ├── elevate.py              Member-elevation (who's central) logic
│   │   │   │       ├── fingerprint_cluster.py  Cluster accounts by stylometric fingerprint
│   │   │   │       ├── reply_pods.py           Reply-pod (amplification ring) detector
│   │   │   │       ├── style_match.py          Cross-account style matching
│   │   │   │       ├── temporal_semantic.py    Joint timing+content coordination
│   │   │   │       └── _types.py               Shared dataclasses for coordination
│   │   │   ├── intelligence/   Composite "OmiScore" surface
│   │   │   │   ├── omiscore.py         OmiScore 0–100 re-blend (+25% nudge from overall_prob)
│   │   │   │   ├── signals.py          Per-dimension signal assembly for the score
│   │   │   │   └── schemas.py          OmiScore response schemas
│   │   │   ├── memory/         CROSS-SCAN MEMORY (one of the six stores)
│   │   │   │   ├── fingerprint.py      Persist/lookup stylometric fingerprints
│   │   │   │   └── prior.py            Prior-neighbor (similarity, not confirmed link) memory
│   │   │   ├── graph/          Coordination graph (edges store)
│   │   │   │   ├── algorithms.py       Graph algorithms (components, centrality)
│   │   │   │   ├── service.py          Graph build/query service
│   │   │   │   └── store.py            Graph persistence
│   │   │   ├── narrative/      Narrative store + clustering
│   │   │   │   ├── clustering.py       Cluster comments/posts into narratives
│   │   │   │   ├── coordination.py     Corroboration-gated "coordinated narrative" label
│   │   │   │   ├── embeddings.py       Embedding helpers (off by default in dev)
│   │   │   │   └── service.py          Narrative CRUD/query
│   │   │   ├── campaigns/      Campaign store
│   │   │   │   └── service.py          Campaign assembly + member identity
│   │   │   ├── content/        Content store (videos/comment-sections)
│   │   │   │   ├── service.py          Content CRUD/query
│   │   │   │   ├── platforms.py        Per-platform content adapters
│   │   │   │   ├── featured.py         Featured/seed content surfacing
│   │   │   │   ├── seed.py             Seed-content loader
│   │   │   │   └── featured_campaigns.json   Static featured-campaign data
│   │   │   ├── investigations/ (none — investigations live in routes + storage)
│   │   │   ├── integrations/   External platform clients
│   │   │   │   ├── youtube.py / youtube_errors.py   YouTube Data API client (LIVE)
│   │   │   │   ├── twitter.py / twitter_errors.py   X/Twitter client (PARTIAL)
│   │   │   │   └── source.py           Source-abstraction over platforms
│   │   │   ├── monitoring/     Watchlists + background re-scan
│   │   │   │   ├── service.py          Watchlist CRUD
│   │   │   │   ├── scheduler.py        Background re-scan loop (YouTube-only — see Finding #2)
│   │   │   │   └── anomalies.py        Anomaly detection over monitored series
│   │   │   ├── reasoning/      Natural-language commentary
│   │   │   │   ├── commentary.py       Generate analyst commentary (LLM or template)
│   │   │   │   └── providers.py        LLM provider plumbing (Anthropic; off by default)
│   │   │   ├── reports/        Report generation
│   │   │   │   ├── campaign_pack.py    Campaign report pack builder
│   │   │   │   └── templates.py        Report templates
│   │   │   ├── evaluation/     OFFLINE engine benchmarks (not request-path)
│   │   │   │   ├── benchmark.py / metrics.py        Harness + metrics
│   │   │   │   ├── coordination_benchmark.py        Coordination accuracy
│   │   │   │   ├── coordination_rescue_… / rescue_benchmark.py  False-negative rescue
│   │   │   │   ├── io_coordination.py               Influence-operation coordination eval
│   │   │   │   ├── member_elevation.py              Member-elevation eval
│   │   │   │   ├── memory_benchmark.py              Cross-scan memory eval
│   │   │   │   ├── ai_writing_benchmark.py          AI-writing detector eval
│   │   │   │   └── benchmarks/*.json                Frozen benchmark fixtures
│   │   │   ├── ml/             DORMANT learned-scorer seam (offline; not wired to prod)
│   │   │   │   ├── scorer.py           Load+blend a learned model IF present (no-op otherwise)
│   │   │   │   ├── features.py         build_feature_vector — the 42-dim contract
│   │   │   │   ├── export.py           Export training rows from prod data
│   │   │   │   ├── public_import.py    Import public datasets
│   │   │   │   └── datasets/           Dataset plumbing for the seam
│   │   │   │       ├── registry.py / manifest.py    Dataset registry + manifest gate
│   │   │   │       ├── adapters.py / ingest.py      Per-source adapters + ingestion
│   │   │   │       ├── normalize.py / records.py    Normalization + record types
│   │   │   │       ├── quality.py / ledger.py       Quality checks + provenance ledger
│   │   │   │       ├── discovery.py / paths.py      Dataset discovery + path resolution
│   │   │   │       ├── synthetic.py                 Synthetic-data generation
│   │   │   │       ├── text_corpus.py               Text-corpus loader
│   │   │   │       └── botscore_reference.py        Botometer-style reference scores
│   │   │   ├── analytics/event_log.py   Append-only analytics event log
│   │   │   ├── notifications/delivery.py Email/webhook alert delivery (SMTP off by default)
│   │   │   ├── core/           Cross-cutting infra
│   │   │   │   ├── config.py           Settings/env (feature flags: LLM/Stripe/SMTP/scheduler off in dev)
│   │   │   │   ├── auth.py             Auth helpers
│   │   │   │   ├── middleware.py       Request middleware
│   │   │   │   ├── rate_limit.py       Rate limiting
│   │   │   │   ├── cache.py            Caching
│   │   │   │   ├── background.py       Background-task helpers
│   │   │   │   ├── metrics.py          App metrics
│   │   │   │   ├── ip.py               IP utilities
│   │   │   │   └── referrals.py        Referral logic
│   │   │   ├── storage/        PERSISTENCE
│   │   │   │   ├── db.py               Engine/session; SAVEPOINT-isolated best-effort writes
│   │   │   │   ├── models.py           SQLAlchemy ORM models (all six stores)
│   │   │   │   └── repository.py       Repository/query layer
│   │   │   └── routes/         HTTP API (one file per surface; names self-describe)
│   │   │       ├── scan.py / scan_async.py   Synchronous + async scan endpoints
│   │   │       ├── analyze.py / accounts.py / channels.py / content.py
│   │   │       ├── investigations.py / campaigns.py / narratives.py / graph.py
│   │   │       ├── monitoring.py / watchlists.py / activity.py / metrics.py
│   │   │       ├── intelligence.py / reasoning.py / reports.py / labels.py
│   │   │       ├── learning.py / bulk.py / auth.py / billing.py / health.py
│   │   │       └── scan helpers shared via orchestrator.py
│   │   ├── alembic/            DB migrations (env.py, versions/*) + alembic.ini
│   │   ├── ml_training/train.py   Legacy in-api training entry (superseded by top-level ml/)
│   │   ├── scripts/           Ops/dev CLIs: calibrate, datasets, fit_correlation, profile_scan, train_model
│   │   ├── tests/             88 pytest files — the backend gate (`pytest tests/ -q`)
│   │   ├── pyproject.toml / requirements.txt / runtime.txt / README.md
│   │
│   └── web/                    Next.js 14 App Router frontend — "OmiSphere"
│       ├── app/
│       │   ├── layout.tsx / page.tsx / globals.css   Root layout, home, design tokens
│       │   ├── landing-page.tsx / demo-scan-form.tsx Marketing landing + demo form
│       │   ├── (app)/          Authenticated product (has its own layout.tsx = app shell)
│       │   │   ├── dashboard/          Intelligence workspace home (+ loading, wtp-prompt)
│       │   │   ├── investigate/        The scan workspace: workspace, scan-input, synthesis
│       │   │   │                       (verdict hero), commenter-list/-detail, insights-rail
│       │   │   ├── investigations/[slug]/   Saved investigation: viewer, verdict/share/commentary
│       │   │   ├── accounts/[external_id]/  Account intelligence detail
│       │   │   ├── channels/[platform]/     Channel intelligence detail
│       │   │   ├── content/[platform]/,authors/  Content database + author views
│       │   │   ├── campaigns/[campaign_key]/     Campaigns list + coordination detail
│       │   │   ├── narratives/[id]/         Narratives list + detail ("how ideas spread")
│       │   │   ├── graph/              Coordination graph (graph-client/-explorer, radial island)
│       │   │   ├── monitoring/         Watchlists (client, watchlist-form/-row)
│       │   │   ├── search/             Global search (search-client)
│       │   │   ├── bulk/               Bulk scan (bulk-client)
│       │   │   └── settings/          Account/engine/calibration/activity/notifications/referral
│       │   ├── (auth)/         login / signup / forgot-password / reset-password
│       │   ├── (marketing)/    about / pricing / privacy / terms (+ marketing layout)
│       │   └── (public)/       r/ (public report) + rc/ (public campaign) — shareable, no-auth
│       ├── components/
│       │   ├── layout/         app-shell, sidebar, topbar, mobile-nav, service-health
│       │   ├── shared/         Domain widgets: score-ring, tier-badge, confidence-band,
│       │   │                   trust-lists (evidence columns), threat-breakdown,
│       │   │                   commenter-threat-panel, probability-bar, how-to-read,
│       │   │                   command-palette, sparkline, animated-number, reveal,
│       │   │                   hero-visual, logo, scroll-progress, loading-skeletons
│       │   ├── ui/             Primitives: card, button, badge, input, dialog, skeleton
│       │   └── viz/            radial-graph (force/radial graph viz)
│       ├── lib/                api.ts (client + types), api-server.ts (RSC fetch),
│       │                       auth, env, format, plan, cn, scan-job, scan-platform,
│       │                       campaign-identity, use-polling (+ *.test.ts vitest gate)
│       ├── middleware.ts       Edge middleware (auth/routing)
│       ├── tailwind.config.ts / postcss.config.mjs / next.config.mjs / tsconfig.json
│       ├── UI_EVOLUTION.md     Living record of the UI Evolution V1 work (this session)
│       └── DESIGN_REFERENCES.md  How the references/ systems informed the identity
│
├── ml/                        DECOUPLED ML / Hugging Face R&D — OFFLINE, not wired to prod
│   ├── README.md              ml/ orientation
│   ├── OMI_NEURAL_NETWORK_V1.md      NN architecture plan (CPU, glass-box, augments engine)
│   ├── HUGGING_FACE_INTEGRATION_PLAN.md  HF as dataset host + CPU trainer + model registry
│   ├── analyst/              OMI ANALYST spec — the REASONING layer (Qwen3-4B-Thinking; HF Andrewexiga/omi-analyst-v1)
│   │   ├── OMI_ANALYST_SPEC_V1.md     21-section operating manual (mission→safety)
│   │   ├── analyst_system_prompt_v1.md   V1 base-Qwen system prompt + user-message assembly
│   │   ├── analyst_response_schema.json  draft-2020-12 structured-output contract (validated)
│   │   ├── future_finetuning_strategy.md V1→V4 + dataset structure (blocker: gold labels = 0 rows)
│   │   ├── huggingface_model_lifecycle.md  HF as first-class registry/store/versioning
│   │   ├── REPOSITORY_STRUCTURE.md    recommended layout of the HF model repo
│   │   ├── README.md                  folder orientation
│   │   ├── hf_repo/                   PUSH-READY HF model repo (OMI_ANALYST_MODEL_IMPORT_V1):
│   │   │                              README.md=model card (base_model metadata), config/, base/BASE_MODEL.md, .gitattributes — no weights
│   │   ├── hf_repo_manifest.toml      GitHub→HF file map for the registry
│   │   ├── register_hf_model.py       registration pipeline (validate-default / --upload); never publishes weights
│   │   ├── test_register_hf_model.py  offline self-test (11/11)
│   │   ├── omi_analyst/               WORKING IMPLEMENTATION (OMI_ANALYST_IMPLEMENTATION_V1):
│   │   │                              config·evidence_bundle·providers(deterministic+Qwen)·schema_validate·store·analyst
│   │   ├── run_analyst_demo.py        runs all 4 assessments on sample evidence (all valid)
│   │   └── test_omi_analyst.py        offline test suite (25/25)
│   ├── features/              OMI_FEATURE_SCHEMA_V1.md — the canonical 42-dim feature contract
│   ├── schemas/              OMI_LABEL_SCHEMA_V1.md — engine-independent label contract
│   ├── corpus/               Unified corpus: discovery → normalization → audit
│   │   ├── omi_corpus.py             Build the merged corpus
│   │   ├── audit.py / audit_full.py  Capped + full uncapped line-by-line audit
│   │   ├── UNIFIED_OMI_SCHEMA.md     The one schema all sources normalize to
│   │   ├── CORPUS_AUDIT_V1.md        Audit findings + V1-readiness recommendation
│   │   ├── inventory.{md,json} / audit_stats.json / audit_per_dataset.csv
│   │   ├── data_quality_report.md / schema_comparison.md
│   │   ├── data/merged_corpus.parquet   The normalized corpus artifact
│   │   └── test_*.py                 Audit/corpus tests
│   ├── datasets/             HF dataset pipelines + per-store staging
│   │   ├── hf_upload.py / upload_manifest.toml      Production-safe GitHub→HF upload
│   │   ├── hf_sync.py / sync_config.toml / sync_upload_manifest.toml  Auto-sync
│   │   ├── HF_DATASET_UPLOAD.md / HF_DATASET_SYNC.md / README.md
│   │   ├── dataset_inventory.{md,json}
│   │   ├── accounts/ analyst_verdicts/ campaigns/ investigations/ narratives/  (README staging)
│   │   └── test_hf_*.py
│   ├── inference/            HF connectivity probes
│   │   ├── hf_connectivity_check.py          Read-only HF reachability
│   │   ├── hf_dataset_connectivity_check.py  Read+write dataset round-trip
│   │   ├── hf_analyst_pull_check.py          Verify GitHub can PULL omi-analyst-v1 (snapshot_download)
│   │   └── HF_CONNECTIVITY.md / README.md
│   ├── models/
│   │   ├── omi-behavioral-v1/        XGBoost baseline: model.joblib, holdout, metrics,
│   │   │                             model_card.md, SHADOW_MODE_PLAN.md
│   │   └── omi_behavioral_nn/        PyTorch NN foundation: model.py, train_nn.py,
│   │                                 evaluate_nn.py, predict_nn.py, dataset_builder.py,
│   │                                 data/{train,validation,test}.parquet, tests, report
│   ├── training/behavioral_v1/       dataset.py + train.py for the baseline
│   └── evaluation/
│       ├── behavioral_v1/            V1 eval outputs
│       └── behavioral_v2_audit/      The "username shortcut" audit (key honest finding)
│
├── datasets/                  GOVERNED ground-truth corpora (production reads these)
│   ├── manifest.toml          THE GATE — which datasets are trusted; keeps poison quarantined
│   ├── 2020-05/ 2020-09/ 2021-02/   Time-sliced influence-operation datasets
│   ├── astroturf/ cresci-rtbust-2019/   Public bot/astroturf benchmark sets
│   ├── East Africa/ Changyu Culture/ Xinjiang(…)/   Regional IO datasets
│   ├── ai vs human text/      AI-vs-human text corpus
│   ├── Datasets/              Nested mixed sources (TwitterData_*, IRA/, GRU/, botscore, …)
│   ├── DATASET_INVENTORY.md / DATASET_MIGRATION_MAP.md / HUGGING_FACE_UPLOAD_PLAN.md
│   ├── DATASET_INTELLIGENCE_AUDIT.md / INTAKE.md
│   ├── TRUST_BOUNDARY*.md / TRUST_DATASET.md   Trust/poison governance
│   └── PHASE0–6*.md / EXECUTION_ROADMAP.md     Strategic/validation playbooks (founder/PMF)
│
├── references/               UI TASTE references (NOT to clone) — used by UI Evolution
│   ├── linear/ perplexity/ arc_browser/ vercel/ stripe/
│   └── notion/ airtable/ retool/ Cursor/
│
├── docs/                     Long-form documentation
│   ├── architecture.md / api-spec.md / design-system.md / operations.md / roadmap.md
│   ├── dataset-training.md / engine-evaluation.md / youtube-credibility.md
│   ├── PRODUCT_INTELLIGENCE_AUDIT.md / GAP_EXECUTION_NOTES.md
│   └── omisphere-{strategic-assessment,tier2-audit,cross-platform-integration}.md
│
├── infrastructure/           docker-compose.yml + render.yaml (deploy)
├── packages/shared/          Shared types/contracts across apps (README)
├── scripts/                  Windows dev helpers: setup_omisphere.bat, start_omisphere.bat
├── .github/workflows/        CI: tests.yml + hf-connectivity / hf-dataset-connectivity /
│                             hf-dataset-upload / hf-sync-datasets / hf-analyst-register / hf-analyst-pull
├── .claude/                  Claude Code project config (skills, settings)
├── render.yaml / requirements.txt / runtime.txt   Root deploy/runtime config
├── .env.example              Env template
├── README.md                 Repo top-level readme
└── HANDOFF.md                LEGACY root handoff (2026-05-29) — superseded by this file
```

---

## 4. Open Audit Findings

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
   - Note: the UI Evolution introduced a fused **verdict hero** (ScoreRing+tier+
     ConfidenceBand) which partially advances this, but the OmiScore dial demotion
     itself is still open.
2. **Monitoring scheduler is YouTube-only (KNOWN LIMITATION).** The background
   watchlist re-scan loop (`app/monitoring/scheduler.py`) only re-scans
   `platform == "youtube"` rows. X watchlists are captured/routed/displayed
   correctly but not re-scanned by the scheduler (needs Twitter client wiring).
3. **"Coordination" terminology overload.** The word labels four different
   grains — account dimension, cluster aggregate, narrative score, campaign
   score. Not a value bug; a clarity/disambiguation cleanup.
4. **(UI follow-up, optional) Tier-pill consolidation.** A few ad-hoc tier chips
   remain instead of the shared `TierBadge`. They're colorblind-safe (labels +
   dots), so this is a polish sweep, not a correctness issue.

(Investigated and found already-correct: **Narrative evidence drill-down** —
comments + commenters are already stored and surfaced; no fix needed.)

(Honest ML finding — not a "fix," a direction: the behavioral V1 model is a
username-morphology shortcut; **new labeled data is the constraint**, so do not
wire a learned scorer into `app/ml/scorer.py` on V1's strength.)

---

## 5. Deferred Features

- Platform-aware (X) scheduler re-scan (depends on Finding #2).
- Healing platform for pre-existing watchlists happens only on re-watch (old
  rows stay backfilled to "youtube" until then) — acceptable fallback.
- Wiring a learned scorer through the dormant `app/ml/scorer.py` seam — deferred
  until there's data that isn't a username shortcut.
- Strategic (from PMF/moat/decision audits): the binding constraint is **real
  users / distribution, not more code.** Engineering is ahead of adoption.

---

## 6. Known Constraints

- **Engine guardrails (do not violate):** never let one non-discriminative
  signal drive a maximal coordination verdict (corroboration gate); store
  evidence/probabilities, never persisted verdicts; best-effort writes are
  SAVEPOINT-isolated; respect `datasets/manifest.toml` (keep poison quarantined).
- **Scope discipline:** the UI Evolution V1 was **frontend/design only** — no
  backend logic, scoring, API, DB, or ML changes. The `ml/` tree is **R&D and
  offline** — do not wire it into production scoring without explicit scope.
- **Gates:** backend `cd apps/api && python -m pytest tests/ -q`; web
  `cd apps/web && npm run typecheck` + `npm run build` (set `OMI_API_ORIGIN`
  and `OMI_PUBLIC_BASE_URL` for build) + `npm run test` (vitest). Commit only on
  green; match surrounding style.
- **Remote-env git:** push directly to `github.com` with a PAT (the local proxy
  403s); PR creation via the integration 403s ("not accessible by integration")
  and the env auto-merges the session branch into `main`.
- **Off by default in dev:** Anthropic LLM (template fallback), Stripe, SMTP
  alerts (webhook still works), background monitoring scheduler, embeddings.
- **Commit-signature "Unverified" stop-hook warnings are a closed topic — take
  no action on them.**

---

## 7. Next Recommended Task

Implement **Open Finding #1** (scoring decision-surface simplification) as a
scoped, UI-only change — highest-value open item, zero engine risk. If picking
up ML instead, the prerequisite is **new labeled data**, not more modeling
(per the V2 audit). Strategically, the larger lever is user acquisition.

**Omi Analyst follow-ups (now that the spec exists, `ml/analyst/`):** the
spec-faithful, low-risk next steps, in order — (1) build the offline **Evidence
Bundle** projection (Appendix A) from the existing scan objects; (2) author the
**analyst-eval set** (~50–100 hand-built bundles + reference assessments) — this is
the V2 prerequisite and the gate for everything after; (3) implement a flagged,
async **`OmiAnalystProvider`** in `app/reasoning/` (Qwen-backed, template fallback,
off by default) emitting JSON valid against `analyst_response_schema.json`. **V3/V4
fine-tuning stays blocked on gold reasoning labels (0 rows).** All of this is
separately scoped — the spec itself changed no production code.

---

## Maintenance rules (for every future session)

**Startup protocol — before any task, read:** `ai-context/VISION.md`,
`ai-context/ARCHITECTURE.md`, `ai-context/HANDOFF.md`. Treat them as
authoritative; don't assume facts that contradict them.

**On completing a code change:**
1. Update §2 *Recently Completed* (date, commit hash, issue solved, files
   changed, user impact) and adjust §4 *Open Findings* / §7 *Next Task*.
2. If a folder/file was added, moved, or repurposed → update the §3 repo map.
3. If the architecture changed → update `ARCHITECTURE.md`.
4. If mission/product scope changed → update `VISION.md`.

Keep it markdown-only. No databases, vector stores, embeddings, agents,
background AI workers, or orchestration — this is context preservation, nothing
more.
