# OMI Label Schema V1 — ground-truth audit & training-label contract

> **Status: documentation only.** No model trained, no scoring change, no ML
> implementation. This audits every label source available to Omi and defines the
> label contract a future Behavioral / Coordination model would train against. It
> complements `ml/features/OMI_FEATURE_SCHEMA_V1.md` (the inputs); this file is the
> targets.

Key distinction throughout: **in-product label stores** are DB tables (runtime
data — **0 rows committed in this repo**), while **external label sources** are the
committed corpora under `datasets/` audited previously.

---

## Label-source inventory

| # | Source | Location | Schema (label field) | Records (repo) | Label type | Trust | ML suitability |
|---|---|---|---|---|---|---|---|
| 1 | **Analyst verdicts** | `Investigation.verdict` (`models.py:454`; enum `schemas.py:1187`) | `confirmed_bot_ring / likely_inauthentic / mixed / likely_authentic / inconclusive` + `confidence`, `notes` | **0** (runtime) | case-grain, human | ★★★★★ (human, analyst-controlled) | ⭐⭐ (gold, but empty + case-grain, not account) |
| 2 | **Account labels** | `AccountLabel` (`account_labels`, `models.py:733`) | `label` ∈ {bot, human, unclear, commercial_spam, political_coord, engagement_farm, ai_content, suspended}; `expected_tier`; `confidence` {high,medium}; `source` {manual, youtube_suspension, imported_dataset}; `rationale` | **0** (runtime) | account-grain, human/platform | ★★★★★ for `youtube_suspension`; ★★★★ manual-high | ⭐⭐⭐ (the canonical store; drives `--from-db` calibration; populated via `public_import.py`) |
| 3 | **State-actor IO** | `datasets/{2020-05,2020-09,2021-02,Changyu Culture,East Africa,Datasets/{GRU,IRA,Xinjiang}}` | implicit positive = disclosed coordinated (manifest `political_coord/high`, `twitter_io_disclosure`) | **tens of thousands of accounts** (8 archives) | account + coordination, platform-attributed | ★★★★★ (platform disclosure) | ⭐⭐⭐ (positive class for authenticity **and** coordination) |
| 4 | **Bot/fake accounts** | `datasets/Datasets/Fake Social Media Account Detection Dataset/*` | `is_fake` / filename / `Bot Label` | global_2.0 **3,000** (1941/1059); real_users **2,500**; fake_users **2,500**; reddit **small**; bot_detection_data **~50,000** | account-grain, dataset | ★★★★ global_2.0; ★★★ real/fake_users; ☆ bot_detection_data | ⭐⭐⭐ global_2.0; ⭐⭐ real/fake; ❌ bot_detection_data (quarantined noise) |
| 5 | **Human/genuine** | `real_users.csv`; `TwitterData_Joined.csv`; (`known-good`/`known-mixed` **declared, absent**) | filename / `Label` 1=human | real_users **2,500**; TwitterData_Joined **96 accts / 308k tweets** | account-grain, dataset | ★★★ (pre-normalized) / ★★★★ (TwitterData_Joined) | ⭐⭐⭐ negative class (the missing `known-mixed` is the precision-control gap) |
| 6 | **Coordination** | IO archives (#3, group membership); `app/evaluation/benchmarks/coordination_v1.json` (40 KB), `coordination_rescue_v1.json` | cluster/group membership | IO groups + benchmark scenarios | cluster/network grain | ★★★★★ IO; ★★★ benchmark (curated) | ⭐⭐⭐ IO group labels; ⭐⭐ benchmark (eval) |
| 7 | **Campaign** | `app/content/featured_campaigns.json` (2) | `coordination_score`, `confidence` — **engine-derived** | 2 | campaign-grain, **derived** | ☆ as a *label* (it's an output) | ❌ as training label (leakage); ✅ demo/eval only |
| 8 | **Narrative** | `Narrative`/`NarrativeMembership` | none — engine-derived message clusters | runtime | — | ☆ (no independent human label) | ❌ no ground-truth labels exist |
| 9 | **Benchmarks** | `app/evaluation/benchmarks/{seed_v1,coordination_v1,coordination_rescue_v1,memory_v1}.json` | `label`, `expected_tier`, `expected_probability` | seed_v1 **65** + 3 sets | curated/synthetic | ★★★ (curated eval, partly synthetic) | ⭐⭐ **evaluation only**, not training (synthetic + engine-calibrated probabilities) |
| 10 | **AI-vs-human text** | `datasets/ai vs human text/*` | `human_or_ai` / `label` | v1 **~17,052**; 2026 **~2,000** | **text-grain** | ★★★ | ⭐⭐ for the `ai_writing` context signal — **not** an authenticity label |
| 11 | **Bot-score (continuous)** | `datasets/Datasets/activity_botscore.csv` | `bot_score_english` (continuous, **no class**) | — | account, continuous | ★★ | ⭐ reference/calibration only (no class label) |
| 12 | **Needs adapter** | `astroturf/astroturf.tsv`, `cresci-rtbust-2019/*.tsv` | id + human/bot | small | account-grain | ★★★ (known benchmarks) | ⭐⭐ once the headerless adapter lands |

---

## Formal label contract — OMI_LABEL_SCHEMA_V1

```
schema: omi_labels
version: 1
grains:
  account_authenticity:                 # primary — Behavioral Model V1
    target: y ∈ {0 = authentic, 1 = inauthentic}
    derived_from (categorical → binary):
      inauthentic(1): bot, commercial_spam, political_coord, engagement_farm,
                      ai_content, suspended       # AccountLabel.label / is_fake / IO
      authentic(0):   human                       # real_users / known-good
      drop:           unclear / mixed / inconclusive  # ambiguous — exclude from train
    source_precedence (highest trust wins on conflict):
      1 analyst_verdict | youtube_suspension      # human / platform moderation
      2 io_disclosure                             # platform-attributed coordination
      3 dataset_label                             # is_fake / filename / Label
      4 heuristic_threshold                       # bot_score cut (reference only)
    fields: {label, label_binary, label_source, label_confidence (high|medium|0..1),
             provenance, platform, account_external_id_hashed, labeled_at}
    HARD RULE: label must be ENGINE-INDEPENDENT — never the engine's own
               tier / overall_probability / OmiScore (else circular, see §D).
  coordination:                          # separate model, cluster/pair grain
    target: cluster_membership (accounts disclosed/confirmed in the same operation)
    source: io_disclosure (group id) | analyst-confirmed campaign
    note: featured_campaigns scores are ENGINE OUTPUTS → not labels.
  text_ai (auxiliary, ai_writing only): {human_or_ai}   # NOT an authenticity label
maps_to: AccountLabel store (models.py:733) via app/ml/public_import.py
governance: datasets/manifest.toml (train/validation only; quarantine excluded)
eval_only: benchmarks/* (seed_v1 etc.) — never used to train a generalizing model
```

---

## A. Labels that can train an **authenticity** model
Account-grain, engine-independent, usable today:
- **`AccountLabel`** (bot/human/suspended/spam/farm/ai_content → binary) — the canonical store + `public_import.py` ingestion (currently 0 rows; fills from operators or imports).
- **IO disclosures** (#3) → positive class (tens of thousands).
- **`fake_social_media_global_2.0`** (3,000 balanced `is_fake`) — cleanest single trainable set.
- **`real_users` / `fake_users`** (2,500 each), **`TwitterData_Joined`** (`Label`), **cresci/astroturf** (post-adapter).
Negatives need the absent **`known-mixed`** legitimate-coordination controls for a precision-valid set.

## B. Labels that can train a **coordination** model
- **IO-disclosure group membership** (#3) — the strongest coordination ground truth (accounts attributed to the same operation = positive coordinated cluster).
- **`coordination_v1` / `coordination_rescue_v1`** benchmarks — evaluation, not training.
- Not featured_campaigns (engine-derived; leakage).

## C. Labels that are **unsuitable**
- `bot_detection_data.csv` (~50k — quarantined: label ≈ random noise).
- `fake_social_media.csv` (99.8% single class), `ai_vs_human_text.csv` (templated stub), `TwitterData_FE/Twitter_Data` (unverified overlap), `article_discusses_claim` (wrong domain).
- `activity_botscore` (continuous, **no class** — reference only).
- `Narrative*` (no independent human labels).
- Ambiguous classes (`unclear`/`mixed`/`inconclusive`) — exclude from training (keep for ambiguity analysis).

## D. Labels that create **leakage risk**
- **Engine-derived "labels":** `featured_campaigns.coordination_score/confidence`, `seed_v1.expected_probability/expected_tier`, and **any use of the engine's own `tier`/`overall_probability`/OmiScore as a label** → circular (the model would learn to predict the engine, since the engine's outputs are also features).
- **Confirmation bias:** `Investigation.verdict` / `AccountLabel.expected_tier` set *after* the labeler saw the engine's verdict. Mitigate by training on the categorical `label` ("what it IS") not `expected_tier` ("what the engine should say"), and by preferring engine-blind sources (`youtube_suspension`, `io_disclosure`).
- **Reminder:** the 42-dim feature vector intentionally includes engine outputs (`fp_overall_probability`, detector block) — fine for the additive re-aggregator design **only if** the label is engine-independent.

## E. Does Omi have enough trustworthy labels to train **Behavioral Model V1**?

### **PARTIALLY.**

**Enough to train a v1 baseline now:** engine-independent, account-grain labels exist in usable volume — `fake_social_media_global_2.0` (3,000 balanced), `real_users`/`fake_users` (2,500 each), `TwitterData_Joined`, plus tens of thousands of IO-disclosure positives, all importable into `AccountLabel` via the existing `public_import.py`, with `seed_v1` + benchmarks as the held-out eval gate. A shadow v1 classifier is trainable today.

**Not enough for a trustworthy, promotable V1 (why not YES):**
1. The **highest-trust labels (analyst verdicts + manual/`youtube_suspension` `AccountLabel`s) are runtime-empty** in the repo — 0 committed gold rows.
2. The **`known-mixed` legitimate-coordination negative controls are absent** → the precision gate (FPR on legitimate controls) cannot be measured.
3. Positives are **X/Twitter-only** — no YouTube authenticity labels, though the engine scores YouTube (domain shift).
4. **Leakage hazards** (engine-derived labels, post-verdict confirmation bias) must be actively excluded.
5. Some sets are pre-normalized (feature-parity) or await adapters (cresci/astroturf).

**Net:** train and benchmark a **shadow** v1 baseline now on the clean external labels; **block promotion** until (a) operator/analyst `AccountLabel`s accumulate, (b) `known-mixed` controls exist, and (c) some YouTube-domain labels are added. This matches the Dataset Audit's *PARTIALLY-ready* verdict and the NN/HF plans' shadow-first promotion gate.

*Findings and schema only — no training, no scoring change, no implementation.*
