# OMI Feature Schema V1 — Behavioral Intelligence Model inputs

> **Status: documentation only.** No model built, no training, no scoring change.
> This is the authoritative inventory of every feature/signal/metric OmiSphere
> generates and the exact, versioned input contract a future **Behavioral
> Intelligence Model** would train on. It formalizes the existing
> `apps/api/app/ml/features.py` (`build_feature_vector`, `FEATURE_SCHEMA_VERSION = 1`),
> which is already the single source of truth shared by training and serving.

Attribute legend per feature: **Range** · **Stored?** (persisted in a DB column)
· **Exportable?** · **ML** (suitability ⭐⭐⭐ high / ⭐⭐ medium / ⭐ low or
leakage-risk) · **Explain** (analyst explainability value).

---

## A. Complete Feature Inventory

### A1 — Behavioral Fingerprint (21 dims) — *Omi's core proprietary signal*
Source: `app/memory/fingerprint.py` (`_FEATURES`, `extract_fingerprint`); persisted
as `Account.fingerprint_json`; normalized to [0,1] in-vector via `(raw−lo)/(hi−lo)`.
**Stored ✅ · Exportable ✅ · ML ⭐⭐⭐ · Explain ⭐⭐⭐** (each maps to a named human behavior; platform-agnostic by design).

| Feature | Detector | Raw range | Meaning |
|---|---|---|---|
| `fp_interval_cov` | temporal | 0–2 | coefficient of variation of inter-post intervals (mechanical regularity) |
| `fp_quiet_hours` | temporal | 0–12 | count of zero-activity hours (human sleep cycle vs 24/7 bot) |
| `fp_burst_ratio` | temporal | 0–30 | peak-burst vs baseline posting |
| `fp_peak_hourly_rate` | temporal | 0–30 | max posts/hour |
| `fp_mean_cosine` | semantic | 0–1 | mean pairwise text similarity (repetition) |
| `fp_top_cluster_mass` | semantic | 0–1 | share of posts in the dominant text cluster |
| `fp_mean_ngram_jaccard` | semantic | 0–1 | n-gram overlap (templating) |
| `fp_burstiness` | ai_writing | 0–1.2 | sentence-length burstiness (AI-text tell) |
| `fp_hedge_rate` | ai_writing | 0–0.5 | hedging-phrase rate |
| `fp_em_dash_rate` | ai_writing | 0–1 | em-dash usage rate |
| `fp_sentence_start_rep` | ai_writing | 0–1 | repeated sentence openers |
| `fp_handle_entropy` | profile | 0–5 | character entropy of the handle (random-handle tell) |
| `fp_posts_per_day` | profile | 0–100 | lifetime posting velocity |
| `fp_follower_ratio_log` | profile | −3–3 | log10 follower/following ratio |
| `fp_bio_quality` | profile | 0–30 | bio richness score |
| `fp_emoji_density` | engagement | 0–0.30 | emoji per token |
| `fp_url_inclusion_rate` | engagement | 0–1 | share of posts with URLs |
| `fp_emoji_burst_rate` | engagement | 0–1 | emoji-burst rate |
| `fp_engagement_bait_rate` | engagement | 0–0.50 | engagement-bait phrasing rate |
| `fp_overall_probability` | aggregate | 0–1 | the engine's own verdict (the prior the model re-aggregates) |
| `fp_confidence` | aggregate | 0–1 | engine data-sufficiency |

### A2 — Detector block (16 dims) — `(probability, confidence)` per detector
Source: `app/ml/features.py:_DETECTOR_ORDER`; each from `app/detection/<name>.py` →
`SignalResult{probability, confidence, evidence[], sub_signals{}, supplemental}`
(`schemas.py:53`). Persisted in `Scan.signals_json`. **Stored ✅ · Exportable ✅ · ML ⭐⭐⭐ · Explain ⭐⭐⭐.** Both values [0,1]; absent detector → (0.5, 0.0).

`det_temporal_*`, `det_semantic_*`, `det_ai_writing_*` (supplemental — context, never raises suspicion), `det_voice_*` (`voice.py`), `det_engagement_*`, `det_profile_*`, `det_memory_*` (fingerprint k-NN prior), `det_coordination_*` (injected cross-account signal).
*Not in the 42-vector but generated:* `narrative` (`detection/narrative.py`) and `community` (`detection/community.py`, downward-only) detectors — candidate V2 additions.

### A3 — Account metadata (5 dims)
Source: `app/ml/features.py:_metadata_block` from `Profile`. **Stored ✅** (Account/Profile fields) **· Exportable ✅ · ML ⭐⭐ · Explain ⭐⭐⭐.** All log1p-normalized to [0,1].
`meta_log_followers`, `meta_log_following`, `meta_log_account_age_days`, `meta_verified` {0,1}, `meta_log_post_count`.

**→ A1+A2+A3 = the canonical 42-dim `build_feature_vector`, `FEATURE_SCHEMA_VERSION=1`, append-only.**

### A4 — Aggregate scan outputs — `app/detection/scoring.py`
| Feature | Range | Stored | Export | ML | Explain | Notes |
|---|---|---|---|---|---|---|
| `overall_probability` | 0–1 | ✅ `Scan`/`Account.last_score` | ✅ | ⭐ (target/baseline, **not** a clean input — leakage if label derives from it) | ⭐⭐⭐ | headline inauthenticity |
| `confidence` | 0–1 | ✅ `Scan`/`Account.last_confidence` | ✅ | ⭐⭐ (feature + gate) | ⭐⭐⭐ | data sufficiency |
| `tier` | LOW/MOD/ELEV/HIGH | ✅ | ✅ | ⭐⭐ (ordinal target) | ⭐⭐⭐ | bucketed verdict |
| `score_breakdown` {prior_logit, detector_logit_sum, convergence_bonus_logit, posterior_logit, single_axis_capped, final_probability} | logits / bool | ❌ **not serialized** | ⚠️ in-engine only | ⭐⭐ | ⭐⭐⭐ | the log-odds math (explainability-audit gap) |
| `contributions[]` {probability, confidence, weight, decorrelation_factor, logit_delta, impact, direction} | mixed | ❌ (commenter only) | ⚠️ partial | ⭐⭐ | ⭐⭐⭐ | per-detector signed attribution |
| `reasons[]`, `weak_signals[]`, `score_adjustments[]` | text | ✅ (commenter)/partial | ✅ | ⭐ | ⭐⭐⭐ | why / missing-data / convergence+cap notes |
| `suspected_intent` / `intent_label` | enum | ✅ | ✅ | ⭐ | ⭐⭐⭐ | plain-language category |

### A5 — Memory / k-NN — `app/memory/`
`fingerprint` (21-d vector, A1) **✅ stored** `Account.fingerprint_json`; `matched_prior_neighbors` (count, ✅ `Account`); memory prior signal (→ `det_memory_*`). **ML ⭐⭐⭐** (the cross-scan learning loop) **· Explain ⭐⭐** (similarity, not confirmed identity).

### A6 — Coordination metrics (network/cluster grain) — `app/detection/coordination/`
Source `aggregate.py`, methods: `temporal_semantic`, `fingerprint_cluster`, `cohort`(age), `style_match`, `co_engagement`, `co_tag`, `reply_pods`. **ML ⭐⭐⭐ for a *coordination* model (different grain — pairs/clusters, not one account) · Explain ⭐⭐⭐.**
| Feature | Range | Stored | Notes |
|---|---|---|---|
| `coordination_score` / `weighted_mean` / `corroboration` / `ungated_score` | 0–1 | ✅ `VideoScan.coordination_score` | corroboration-gated max |
| `gated` | bool | ⚠️ | capped-for-lack-of-corroboration flag |
| per-method `DetectorContribution`{method, score, confidence, reliability, mean_weight, evidence} | mixed | ⚠️ | reliability priors in `DETECTOR_RELIABILITY` |
| `CoordinationCluster`{method, members, score, evidence, metadata} | 0–1 | ⚠️ (edges) | the cluster verdict |
| `CoordinationEdge`{observation_count, methods_json, mean_cluster_score, last_shared_parent} | counts/0–1 | ✅ | cumulative cross-scan pairs (graph features) |

### A7 — Narrative metrics (message-cluster grain) — `app/narrative/coordination.py`
`CoordinationScores` — 8 weighted signals + derived. **Stored ✅** (`Narrative`/`NarrativeMembership`) **· ML ⭐⭐ for a *narrative* model · Explain ⭐⭐⭐.** All [0,1].
8 signals (weight): `inauthenticity_fraction`(.18), `temporal_burst_score`(.15), `timing_entropy_anomaly`(.12), `repost_overlap`(.15), `cross_parent_spread`(.10), `author_concentration`(.10), `persistence_score`(.08), `semantic_cohesion`(.12, posts-per-author ratio — **not** topical). Derived: `coordination_score`, `cluster_confidence` (# firing), `narrative_corroboration` (# firing excl. inauthenticity), `manipulation_probability`, `synchronization_intensity`, `coordination_label` (organic/mixed/suspicious/coordinated/manipulation_network), `risk_tier`. Narrative shape: `member_count`, `distinct_authors`, `spread_ratio`, `centroid_json`.

### A8 — Campaign metrics — `app/campaigns/`, `storage/models.py`
`Campaign`{`coordination_score`, `max_coordination_score`, `confidence`, `member_count`, `methods`, `hashtags`, `mentions`}; `CampaignMember`; `CampaignObservation`. **Stored ✅ · Exportable ✅ · ML ⭐⭐ (campaign grain) · Explain ⭐⭐⭐.**

### A9 — Content metrics — `ContentEntity` / `CommentBatch`
`latest_coordination_score`, `total_comments_collected`, `total_distinct_authors`, `contributor_count`, `latest_tier_distribution`, `latest_reply_pod_count`; batch `coordination_score`, `tier_distribution`, `new/duplicate/distinct_authors counts`. **Stored ✅ · ML ⭐⭐ (aggregate context) · Explain ⭐⭐.**

### A10 — OmiScore dimensions (derived, **not stored**) — `app/intelligence/omiscore.py`
`omi_score`, `authenticity_score`, `coordination_probability`, `amplification_probability`, `spam_probability`, `ai_generation_probability`, `risk_level` + per-dimension contributions + `top_evidence`. **Stored ❌ (recomputed) · ML ⭐ (derived from A2 → circular as inputs) · Explain ⭐⭐⭐** (best as explainability *targets*, not features).

### A11 — Confidence metrics (cross-cutting)
`scan.confidence` (A4), `cluster_confidence` (A7), dimension confidence (A10), `campaign.confidence` (A8), memory confidence, label confidence (`AccountLabel.confidence` high/medium). **ML ⭐⭐ (feature + gate) · Explain ⭐⭐⭐.**

### A12 — Labels (targets, not features) — analyst-controlled ground truth
`Investigation.verdict` (confirmed_bot_ring / likely_inauthentic / mixed / likely_authentic / inconclusive), `AccountLabel`{label, confidence}. **Stored ✅ · the gold training target (see §D).**

---

## B. Feature Quality Assessment
- **Best (V1-ready):** A1 fingerprint — normalized, bounded, append-only, **stored on every account**, platform-agnostic, each dim human-named. A2 detector block + A3 metadata complete a clean, train/serve-skew-free 42-dim contract (one function builds both).
- **Strong but grain-separate:** A6 coordination + A7 narrative + A8 campaign are real, explainable signals but at **different grains** (pair/cluster, message, campaign) → they feed **separate models**, not the account vector.
- **Use with care (leakage/circularity):** A4 `overall_probability`/`tier` and A10 OmiScore are engine **outputs**. Including the engine's prior (`fp_overall_probability`, detector block) is intentional — the V1 model *re-aggregates / residual-learns* over the engine (per `features.py` docstring). But the **label must be engine-independent** (analyst/disclosure/dataset), never the engine's own tier, or training is circular.
- **Generated but not surfaced for training:** A4 `score_breakdown` / full `contributions` are computed and **discarded at the API edge** (explainability-audit gap) — serialize them for offline training + explainability.
- **Coverage gaps in the 42-vector:** `voice` is in the detector block but its sub-signals aren't in the fingerprint; `narrative` + `community` detectors are generated but excluded from the vector.

## C. Missing Features (for a stronger model)
1. **Engine-independent labels at scale** — exported `Investigation.verdict` (gold) + the legitimate-coordination controls (`known-mixed`) are absent (Dataset Audit gap). Highest-value missing input.
2. **Temporal-evolution features** — fingerprint/score drift across an account's `Scan` history is stored row-wise but not vectorized (a bot's trajectory differs from a human's).
3. **Graph/network features** — `CoordinationEdge` degree, clustering coefficient, k-NN neighbor-tier density are not in the account vector (would carry coordination context into the per-account model).
4. **Content-context features** — parent content type/title, audience size around a comment.
5. **`narrative` + `community` detector pair** — generated, not yet in the vector.
6. **Optional raw-text embeddings** — `sentence-transformers/all-MiniLM-L6-v2` exists (TF-IDF fallback); precompute offline if added (CPU-budget per the NN/HF plans).

## D. Recommended Training Inputs
**Behavioral Intelligence Model V1 (account grain):**
- **Inputs:** the canonical **42-dim `build_feature_vector`** (A1 fingerprint 21 + A2 detector 16 + A3 metadata 5). This is the contract; do not reorder/remove (append-only + bump `FEATURE_SCHEMA_VERSION`).
- **Label:** binary authenticity, source precedence analyst_verdict > io_disclosure > dataset_label > heuristic (per the NN plan), **engine-independent** to avoid circularity.
- **Frame:** the model is an additive **re-aggregator** over engine signals (blends behind `use_ml_scorer`/`ml_blend_weight`), not a from-scratch detector — consistent with the dormant `app/ml/scorer.py`.
- **Exclude as inputs:** A10 OmiScore (circular), and any feature collinear with the chosen label.
- **V2 candidates:** + A5 graph features, + temporal-drift, + `narrative`/`community` detectors (append-only, schema v2).
- **Separate models (do not merge grains):** coordination (A6, pair/cluster) and narrative (A7, message) train on their own feature sets + the corroboration-gate label.

## E. OMI_FEATURE_SCHEMA_V1 (formal contract)

```
schema: omi_behavioral_features
version: 1                      # == app/ml/features.FEATURE_SCHEMA_VERSION
grain: account
dim: 42                         # append-only; reorder/remove breaks artifacts
source_of_truth: apps/api/app/ml/features.py:build_feature_vector
blocks:
  fingerprint:  21  # A1 — names fp_*, normalized [0,1]
  detectors:    16  # A2 — det_<d>_{probability,confidence} for
                    #      [temporal, semantic, ai_writing, voice, engagement,
                    #       profile, memory, coordination]; [0,1]; absent→(0.5,0.0)
  metadata:      5  # A3 — meta_log_followers, meta_log_following,
                    #      meta_log_account_age_days, meta_verified, meta_log_post_count
provenance_required: [platform, account_external_id_hashed, scan_id, scanned_at,
                      feature_schema_version, engine_version]
label:
  name: authenticity            # 1 = inauthentic, 0 = authentic
  source: {analyst_verdict > io_disclosure > dataset_label > heuristic}
  confidence: [0,1]
  rule: engine-INDEPENDENT (never the engine's own tier/probability)
exclusions_as_input: [omi_score, authenticity_score, risk_level,   # A10 (circular)
                      any label-collinear feature]
companion_schemas (separate grains, separate models):
  coordination_features: grain=pair|cluster  src=app/detection/coordination/*  (A6)
  narrative_features:    grain=message_cluster src=app/narrative/coordination.py (A7)
governance: datasets/manifest.toml (train/validation only; quarantine excluded)
versioning: append-only; new feature → append + bump version; record version in
            every artifact; scorer refuses a mismatched feature_schema_version
```

**Bottom line:** Omi's proprietary intelligence is the **21-dim behavioral
fingerprint + 8 detector signals**, already normalized, stored on every account,
and exposed through one train/serve-safe contract (`build_feature_vector`, 42-dim,
v1). That contract is the foundation for the Behavioral Intelligence Model; the
only true blockers to training are engine-independent **labels** (analyst verdicts
+ `known-mixed` controls), not features. Coordination, narrative, and campaign
metrics are first-class signals but belong to their own grain-specific models.

*Documentation only — no model, no training, no scoring or production change.*
