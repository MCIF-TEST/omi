# OmiSphere Dataset Intake Spec (Tier-2C P1+P2)

How to commit Known-Good and Known-Mixed corpora so the ingest pipeline picks
them up **with no further code**. The adapters, governance, and tests for this
contract already exist (`labeled_tweets` adapter; `known-good/` + `known-mixed/`
dir-rules in `manifest.toml`; `tests/test_labeled_tweets_adapter.py`).

## TL;DR
Drop per-tweet CSVs under `datasets/known-good/` or `datasets/known-mixed/`.
Each file needs a **user-id column** and a **text column**; the **label comes
from the filename**. That's it.

## Directory layout
```
datasets/
  known-good/                              # active humans WITH tweet text
    cresci2017_genuine_tweets.csv          # REQUIRED: the timelines (text)
    cresci2017_genuine_users.csv           # optional: profile companion
    cresci2017_spambots_tweets.csv         # bots WITH text (optional negative)
  known-mixed/                             # legitimate-but-coordination-shaped
    known_mixed_journalists_tweets.csv
    known_mixed_news_orgs_tweets.csv
    known_mixed_brands_tweets.csv
    known_mixed_politicians_tweets.csv
    known_mixed_activists_tweets.csv
```

## Per-tweet timeline files (the important ones)
One **row per tweet**. Required columns (any one alias works):

| Field | Accepted column names |
|---|---|
| user id | `user_id`, `userid`, `author_id`, `tweet_user_id` |
| tweet text | `text`, `tweet_text`, `full_text`, `tweet`, `content` |

Optional extra columns (e.g. `created_at`, `lang`) are ignored safely. The
`labeled_tweets` adapter collapses all of a user's rows into **one account with
its full text corpus** (via `coalesce_records`) — this is the capability the
profile-only `real_users.csv` lacks.

### Label = filename (no label column needed)
| Filename contains | Resulting label | expected_tier |
|---|---|---|
| `genuine`, `human`, `real`, `authentic`, `legit`, `organic` | `human` | low |
| `bot`, `fake`, `spam`, `spambot`, `troll`, `ai`, `synthetic` | `bot` | high |
| `mixed` | `human` (legitimate) | low |

**Known-Mixed naming:** `known_mixed_<category>_tweets.csv`. They are labeled
`human` (the directive: *don't* label them bad) and the **category is preserved
as `campaign_id`** (the file stem) so the eval can measure Omi's behavior on
each legitimate cohort separately.

## Optional profile companion (`*_users.csv`)
Cresci-2017 `users.csv` schema (`screen_name`, `followers_count`,
`friends_count`, `statuses_count`, ...). Filename must carry the same
genuine/bot hint. Matched by the existing `twitter_user_features` adapter
(adds follower/following metadata; carries no text on its own).

## Governance (already in place)
`known-good/` and `known-mixed/` are pre-declared `status = "validation"` in
`datasets/manifest.toml`. Files ingest as validation (the quality gate runs but
is advisory for vouched dirs). Promote to `train` after the first calibration
review.

## After committing — verify & evaluate
```
# 1. Dry-run discovery: confirm each file is supported + adapter-matched.
python -c "from app.ml.datasets.discovery import discover; from app.ml.datasets.paths import default_datasets_dir; \
[print(f.supported, f.adapter.name if f.adapter else '-', f.rel_path) \
 for f in discover(default_datasets_dir()) if 'known-' in f.rel_path]"

# 2. Ingest into the DB (runs analyze_account + writes AccountLabel rows).
#    (use the project's ingest entrypoint, e.g. ingest_directory)

# 3. Re-run the trust evaluation / calibration against real labels.
python apps/api/scripts/calibrate.py --from-db
```

## What this unblocks
- First **FPR test of `style`/`temporal_semantic` against real humans WITH
  text** — the gap Tier-2C identified.
- **Known-Mixed** precision: does Omi flag legitimate coordination (newsroom
  house style, brand scheduling, activist networks)?
- The **memory-anchoring gate**: a text-bearing labeled neighborhood on BOTH
  sides (currently the human side has no text), the precondition the Trust
  Boundary analysis showed is required for safe anchoring.
