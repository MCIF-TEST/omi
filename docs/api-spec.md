# OMISPHERE — API Spec

Endpoint catalog for the `omi` engine HTTP service (`apps/api`). Generated
from the route definitions; keep it in sync when routes change.

**Conventions**

- All JSON. Base path is the same origin as the web app (Next.js rewrites
  `/api/*` → this service in dev; same domain in production).
- **Auth**: most `/v1/*` endpoints require a logged-in session
  (`omi_session` cookie) via the `require_user` dependency. When
  `OMI_REQUIRE_AUTH=false` (local mode) auth is bypassed with a synthetic
  unlimited user. Endpoints marked **admin** additionally require
  `is_admin`. Endpoints marked **public** need no session.
- **Credits**: comprehensive scans consume one credit (402 when exhausted).

---

## Auth — `/v1/auth`

| Method | Path | Notes |
|---|---|---|
| POST | `/v1/auth/signup` | public · rate-limited 5/hr/IP |
| POST | `/v1/auth/login` | public · rate-limited 10/min/IP |
| POST | `/v1/auth/logout` | clears session |
| POST | `/v1/auth/forgot-password` | public · always 200 (anti-enumeration) · 5/hr/IP |
| POST | `/v1/auth/reset-password` | public · consumes single-use token, logs in |
| DELETE | `/v1/auth/account` | deletes account + personal data (email confirm) |
| GET | `/v1/auth/me` | current user or null |
| GET | `/v1/auth/notifications` | alert delivery prefs |
| PUT | `/v1/auth/notifications` | update email/webhook prefs |

## Scanning — `/v1/scan`

| Method | Path | Notes |
|---|---|---|
| GET | `/v1/scan/classify` | classify a URL → platform/kind |
| POST | `/v1/scan/link` | scan any URL (auto-detect video/channel) |
| POST | `/v1/scan/comprehensive` | full comprehensive scan |
| POST | `/v1/scan/youtube/video` | scan a video's comment section |
| POST | `/v1/scan/youtube/full` | scan a video + all commenters |
| POST | `/v1/scan/youtube/account` | scan one account + recent comments |
| POST | `/v1/scan/demo` | public · capped demo scan (landing page) |
| POST | `/v1/scan/bulk` | queue an async multi-URL job |
| GET | `/v1/scan/bulk` | list your bulk jobs |
| GET | `/v1/scan/bulk/{job_id}` | poll a bulk job |

## Analysis (stateless engine) — `/v1/analyze`, `/v1/intelligence`

| Method | Path | Notes |
|---|---|---|
| POST | `/v1/analyze/account` | rule engine over a supplied profile + posts |
| POST | `/v1/analyze/comments` | rule engine over supplied comments |
| POST | `/v1/intelligence/score` | OmiScore for a profile + posts |
| POST | `/v1/intelligence/comments` | OmiScore for a comment batch |
| GET | `/v1/intelligence/account/{platform}/{external_id}` | reconstruct OmiScore from stored scan |
| GET | `/v1/intelligence/benchmark` | **admin** · seed_v1 accuracy scoreboard |
| GET | `/v1/intelligence/benchmark/coordination` | **admin** |
| GET | `/v1/intelligence/benchmark/rescue` | **admin** |
| GET | `/v1/intelligence/benchmark/memory` | **admin** |
| GET | `/v1/intelligence/ml-status` | **admin** · learned-scorer status |

## Accounts, channels, content

| Method | Path | Notes |
|---|---|---|
| GET | `/v1/accounts/search` | search by platform + handle |
| GET | `/v1/accounts/{platform}/{external_id}/history` | scan-history timeline |
| GET | `/v1/accounts/{platform}/{external_id}/analysis` | latest analysis |
| GET | `/v1/channels/{platform}/{external_id}/intelligence` | channel-level aggregation |
| GET | `/v1/content` | list scanned content (paginated, filterable) |
| GET | `/v1/content/{platform}/{content_id}` | content detail |
| GET | `/v1/content/{platform}/{content_id}/batches` | comment-batch history |
| POST | `/v1/content/{platform}/{content_id}/rescan` | re-fetch comments |
| GET | `/v1/content/{platform}/{content_id}/diff` | compare batch snapshots |
| GET | `/v1/content/{platform}/{content_id}/comments` | comments on content |
| GET | `/v1/content/{platform}/{content_id}/reply-tree` | threaded replies |
| GET | `/v1/content/{platform}/{content_id}/reply-pods` | engagement clusters |
| GET | `/v1/content/authors/{platform}/{author_external_id}` | author presence |
| GET | `/v1/content/authors/{platform}/{author_external_id}/comments` | author's comments |

## Graphs (user-curated) — `/v1/graphs`

| Method | Path | Notes |
|---|---|---|
| GET | `/v1/graphs` | list your named graphs |
| POST | `/v1/graphs` | create a graph |
| GET | `/v1/graphs/{graph_id}` | members + coordination edges between them |
| PATCH | `/v1/graphs/{graph_id}` | rename |
| DELETE | `/v1/graphs/{graph_id}` | delete |
| POST | `/v1/graphs/{graph_id}/members` | add a profile |
| DELETE | `/v1/graphs/{graph_id}/members/{external_id}` | remove a profile |

## Investigations, reports, reasoning

| Method | Path | Notes |
|---|---|---|
| GET | `/v1/investigations` | list your investigations |
| GET | `/v1/investigations/{slug}` | investigation detail |
| PATCH | `/v1/investigations/{slug}` | update verdict + notes |
| POST | `/v1/investigations/{slug}/share` | mint public share token |
| DELETE | `/v1/investigations/{slug}/share` | revoke token |
| POST | `/v1/investigations/{slug}/commentary` | generate/return LLM commentary |
| GET | `/r/{token}` | **public** · report view payload |
| GET | `/r/{token}/markdown` | **public** · Markdown export |
| GET | `/r/{token}/json` | **public** · JSON export |

## Narratives, monitoring, watchlists, labels, activity

| Method | Path | Notes |
|---|---|---|
| GET | `/v1/narratives` | trending narrative clusters |
| GET | `/v1/narratives/{narrative_id}` | narrative detail |
| GET | `/v1/monitoring/feed` | global anomaly feed |
| GET | `/v1/monitoring/alerts` | your alerts |
| POST | `/v1/monitoring/alerts/{alert_id}/read` | mark read |
| POST | `/v1/monitoring/run-pass` | **admin** · trigger anomaly pass |
| POST | `/v1/monitoring/test-alert` | **admin** · send a test alert |
| GET | `/v1/watchlists` | list |
| POST | `/v1/watchlists` | add |
| DELETE | `/v1/watchlists/{watchlist_id}` | remove |
| POST | `/v1/labels` | upsert ground-truth label |
| DELETE | `/v1/labels/{label_id}` | remove label |
| GET | `/v1/labels` | list your labels |
| GET | `/v1/labels/calibration` | export calibration fixture |
| GET | `/v1/labels/calibration/evaluate` | metrics over fixture |
| GET | `/v1/labels/training/summary` | training-corpus stats |
| GET | `/v1/labels/training/export` | JSONL export for retraining |
| GET | `/v1/activity` | your scan activity (paginated) |

## Billing — `/v1/billing`

| Method | Path | Notes |
|---|---|---|
| POST | `/v1/billing/create-checkout-session` | Stripe checkout (503 if unconfigured) |
| POST | `/v1/billing/portal` | Stripe customer portal |
| POST | `/v1/billing/webhook` | public · Stripe event sink (signature-verified) |

## Health & ops

| Method | Path | Notes |
|---|---|---|
| GET | `/` | public · root |
| GET | `/health` | public · liveness |
| GET | `/v1/status` | engine state (cached) |
| GET | `/v1/metrics` | **admin** · process + DB stats |

---

*84 endpoints. Source of truth is `apps/api/app/routes/*.py`; FastAPI also
serves interactive docs at `/docs`.*
