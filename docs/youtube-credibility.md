# YouTube credibility — what we ship today

This is the honest brief on what the YouTube ingestion adapter does, how it
fails, and how we ensure the failures don't strand users. Read this if
you're an operator setting up a deploy, an engineer touching the YouTube
code, or a customer trying to decide whether to trust the platform.

---

## What we ship

YouTube ingestion has three entry points, each backed by a typed
exception layer so failures are uniform:

1. **`POST /v1/scan/youtube/video`** — paste a video ID/URL. Pulls every
   commenter on the video (up to `scan_max_commenters`, default 100),
   then for each commenter pulls their profile and recent comment
   history (`scan_max_history_per_commenter`, default 50). Runs the
   eight-detector engine against every commenter. Returns a per-commenter
   risk table plus a video-level tier distribution. Costs 1 credit.

2. **`POST /v1/scan/youtube/account`** — paste a channel handle, URL, or
   raw ID. Resolves the channel, pulls profile + recent comment history,
   runs the engine against that single account. Persists the result and
   updates the fingerprint store. Costs 1 credit.

3. **`POST /v1/scan/link`** — single-input dispatcher: paste any YouTube
   URL and we classify it (video vs channel) and run the comprehensive
   flow. Persists as a saved investigation. Costs 1 credit.

The same eight detectors fire regardless of entry point. The coordination
detectors only run on multi-commenter scans (`/youtube/video` and
`/link?kind=video`).

---

## Quota math

The YouTube Data API v3 is metered in "quota units". The free tier
allocates **10,000 units per day** to the project, resetting at midnight
Pacific Time. Most calls cost 1 unit:

| Call | Cost |
|---|---|
| `commentThreads.list` (one page of up to 100 comments) | 1 |
| `channels.list` (profile lookup) | 1 |
| Resolving a `@handle` to a UC… ID | 1 |

In practice:

* A video scan with 100 commenters and the default 50-comment history per
  commenter consumes roughly **100 × 2 + 1 ≈ 201 units**.
* An account scan consumes **2–3 units** (resolve + profile + history).

At the free-tier cap, that's about **50 video scans or 3,000 account
scans per day** across the entire service. The dashboard
service-health pill warns at 80% and 95% usage so admins can pause
intake before scans start to 503.

`OMI_YOUTUBE_DAILY_QUOTA` overrides the 10,000 default if you've
requested a quota increase from Google.

---

## How failures are handled

Every YouTube API call is wrapped by `app/integrations/youtube_errors.py`,
which translates `googleapiclient.errors.HttpError` into one of five
typed exceptions:

| Exception | Trigger | User-facing response | Credit refund? |
|---|---|---|---|
| `YouTubeQuotaExceededError` | Daily quota gone, rate limit hit | 503 + `Retry-After: 3600` + "try again after midnight Pacific" | **Yes** |
| `YouTubeAuthError` | API key invalid, revoked, restricted | 503 + "team has been notified" | **Yes** |
| `YouTubeNotFoundError` | Video or channel doesn't exist | 404 + "may have been deleted or made private" | **Yes** |
| `YouTubeAccessError` | Private, comments disabled, geo-blocked | 404 + "may be private or have comments disabled" | **No** (the lookup ran) |
| `YouTubeClientError` (base) | Anything else from YouTube | 502 + "unexpected error, try again" | **Yes** |

The route layer in `app/routes/scan.py` catches these uniformly via
`_handle_youtube_error()`. The refund logic in `app/core/auth.py`
(`refund_credits`) atomically restores the user's credit *and* flips the
most recent matching `ScanLog` row to `success=0` so the audit trail
matches the refund.

**The contract:** *a failed scan never costs a credit*. The one exception
is `YouTubeAccessError` (private channel, comments disabled) — there the
user's input was syntactically fine and the API call actually ran, so
the quota was consumed and we don't pretend it didn't happen.

---

## Detector calibration

The engine includes a calibration harness at `apps/api/scripts/calibrate.py`
that runs the eight detectors against a labeled fixture set and reports:

* **Brier score** — global probabilistic calibration error.
* **Tier accuracy** — exact match between predicted tier and labeled tier.
* **Macro-F1** — average F1 across the four tiers.
* **Per-tier precision/recall/F1** — surfaces which tiers we systematically
  over- or under-predict.
* **Per-detector influence** — which detectors are pulling the most
  weight in the final score.
* **Confusion matrix** — every (expected → predicted) pair with counts.

Run it locally:

```bash
cd apps/api
python -m scripts.calibrate
```

For CI integration, save a baseline and use `--check`:

```bash
# Save baseline once after a known-good calibration:
python -m scripts.calibrate --json > calibration-baseline.json
git add calibration-baseline.json

# In CI:
python -m scripts.calibrate --check calibration-baseline.json
# Exits non-zero if Brier worsens by >0.01 OR accuracy/F1 drops by >0.02.
```

The bundled fixture (`scripts/fixtures/calibration.json`) covers 65
synthetic cases across categories like `ai_content`, `engagement_farm`,
`human_low_volume`, `scheduler_bot`, and thin-data ambiguous cases. The
fixture is **not** a public-dataset benchmark — it's our internal
sanity check. We do not claim production-grade precision/recall on real
YouTube data based on this fixture alone; it's a regression-detection
tool, not a vendor-comparison benchmark.

If you find specific real-world cases that the engine misclassifies, the
right move is to add a fixture row with the observed inputs and the
correct tier so future runs catch regressions on it.

---

## Operator runbook — when YouTube breaks

| Symptom | Likely cause | Fix |
|---|---|---|
| Every scan returns 503 immediately | API key unset, invalid, or rejected | Verify `OMI_YOUTUBE_API_KEY` in Render. Check Google Cloud Console for project status. |
| Scans return 503 with `Retry-After: 3600` | Daily quota exhausted | Wait until midnight Pacific OR request a quota increase from Google. |
| Some scans 404, others succeed | User-supplied URLs are private / deleted | No action — this is expected and credits are refunded. |
| Quota meter climbing faster than expected | Lots of large videos being scanned | Lower `scan_max_commenters` in env config. |
| Service-health pill stuck on yellow | Either quota at 80% or DB on SQLite | Check `/v1/status` payload; both fields are present. |

The `/v1/status` endpoint returns the live state including
`youtube_configured`, `youtube_quota_used_today`, and
`youtube_quota_daily_limit`. Anyone with admin can hit it directly; the
service-health pill in the topbar surfaces a summary to everyone.
