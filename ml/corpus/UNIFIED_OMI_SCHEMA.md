# Unified Omi Corpus Schema (V1)

The single standardized record schema that represents **every** discovered Omi
dataset — account, tweet, comment, and text grains — in one corpus, without
collapsing their differences. Implemented in `ml/corpus/omi_corpus.py`
(`RECORD_FIELDS`, the converters, and `build_merged_corpus`).

## Design principle (why one schema can hold all grains)
Datasets differ in **grain** (one row = an account vs a tweet vs a comment vs a
text sample), **label encoding**, and **features** (numeric profile stats vs raw
text). A naive merge would silently mix grains. Instead the schema is a **long,
discriminated record**: every row carries an explicit `grain` + `domain`, a
nullable `text`, a nullable `numeric_features_json`, and a normalized
`authenticity_label` (nullable). Consumers **filter by grain/domain** before
training — the corpus is a standardized *container*, not a single training
population.

## Fields
| field | type | meaning |
|---|---|---|
| `record_id` | str | stable 16-hex id (`dataset:author:text:idx`) |
| `dataset` | str | source dataset (file stem) |
| `source_path` | str | repo-relative source file |
| `domain` | str | `authenticity` · `coordination` · `bot` · `ai_text` · `reference` · `other` |
| `grain` | str | `account` · `tweet` · `comment` · `text` · `unknown` |
| `text` | str? | textual content (tweet/comment/AI sample); null for profile rows |
| `author_id` | str? | account identity (hashed where the source hashes it) |
| `created_at` | str? | source timestamp string, where present |
| `lang` | str? | language code, where present |
| `authenticity_label` | int? | **0 = authentic, 1 = inauthentic**; null where unmapped |
| `label_raw` | str? | the original label value before normalization |
| `label_source` | str | how the label was derived (see below) |
| `numeric_features_json` | str? | JSON of source numeric features (profile sets) |
| `governance_status` | str | from `datasets/manifest.toml` (train/validation/…) |
| `schema_version` | int | `1` |

## Label normalization (→ `authenticity_label`, 0=authentic / 1=inauthentic)
| `label_source` | rule |
|---|---|
| `column:is_fake` | `is_fake > 0.5 → 1` |
| `column:human_or_ai` / `column:label` | ai/generated/machine/fake → 1; human/real → 0 |
| `column:Label(1=human)` | TwitterData `Label`: **inverted** (1=human→0, 0=bot→1) |
| `column:is_bot_flag` | true/1 → 1; false/0 → 0 |
| `filename` | `real_users → 0`, `fake_users → 1` |
| `tsv_label` | word contains bot/spam/fake → 1; human/genuine → 0 |
| `io_disclosure` | state-attributed IO → 1 (implicit) |
| `join:cresci_tsv` | cresci tweet joined to its account label via the TSV |
| `none` | unlabeled (e.g. reference / unjoined) → null |

## Grain / domain by source family
| family | domain | grain | text? | numeric? |
|---|---|---|---|---|
| `fsm_profile`, `userdump` | authenticity | account | – | ✅ |
| `twitterdata` | authenticity | tweet | ✅ | – |
| `io_tweets` | coordination | tweet | ✅ | follower/following |
| `io_users` | coordination | account | bio | follower/following |
| `ai_text_v1`, `ai_text_2026` | ai_text | text | ✅ | – |
| `reddit_comment` | bot | comment | – | ✅ |
| `bot_tsv`, `cresci_json` | bot | account/tweet | (json) | – |
| `reference` | reference | account | – | ✅ (bot_score) |

## Governance & integrity (enforced by the pipeline)
- **Merge excludes `archive` + `quarantine`** (poison stays out); only
  `train`/`validation`/`reference` normalize into the corpus.
- **Originals are never modified** — all reads are read-only; ZIPs are inspected
  in-memory.
- **Fidelity over cleansing**: the corpus preserves source features faithfully
  (including the username-morphology columns) and **flags** leakage in the
  quality report rather than silently dropping — the per-grain training builders
  apply the anti-shortcut policy.
- **Per-file caps** keep the committed corpus small; raise `--max-rows` to
  reproduce the full normalization.

## Supported formats
CSV, TSV, JSON, JSONL, Parquet, ZIP (members inspected without extraction).
XLSX is profiled when an engine is available. Unparseable / unconvertible files
are listed in the data quality report (req 9).

*Versioning: append-only; a new field appends and bumps `schema_version`.*
