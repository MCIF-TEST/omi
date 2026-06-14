# PHASE 6 — PMF VALIDATION EXECUTION PLAN

> **Mode transition:** building → validation. This document authorizes founder
> action only. No new product features, no redesign, no new platforms, no new
> detectors, no new telemetry, no new infrastructure. Everything below is
> executable with what exists today plus env-var/ops configuration.

---

## Brutal-honesty preface — the situation as it actually is

Every point below is tied to a verified fact in the repo, not vibes.

1. **Omi has zero recorded real users.** Every number we are proud of — FPR
   0.000 on the boundary hold, 711 green tests, ~10s time-to-value — is
   self-graded homework on data we curated. None of it is evidence that anyone
   wants this. Phase 6 is the first time the thesis touches reality.
2. **We have dramatically more product than validated demand.** 24 API route
   modules, ~32 web pages, Stripe billing, a referral system, watchlists, a
   monitoring scheduler with email/webhook alert delivery, bulk scans, a graph
   view, narratives, content intelligence, an optional ML scorer, an LLM
   commentary layer. That is series-A surface area on pre-first-user evidence.
   The honest reading: building was comfortable and recruiting was scary. The
   discipline of this phase is that the only allowed "build" is ops config.
3. **A blueprint is not a deployment.** `render.yaml` provisions web + API +
   paid Postgres in one click, but nothing in the repo proves a live URL exists
   today. If there is no production URL, PMF validation cannot start —
   that is Week-0 prerequisite #1, and it is ops work, not product work.
4. **As configured, a trial user cannot run the primary ICP's scan.** Free
   trial = 3 credits (`OMI_FREE_TRIAL_CREDITS`). A Twitter/X batch scan
   (the "is this reply-swarm coordinated?" case — the OSINT researcher's bread
   and butter) costs 10 credits per ≤50-commenter batch. Trial covers YouTube
   batches (1 credit) and single-account X deep-scans (1 credit), but not one
   X batch. The most important user hits a wall before their first real value
   moment. Fix is env/manual (raise the grant for the window, or hand-grant
   credits to the 25) — zero code.
5. **X scans cost real founder cash.** twitterapi.io ≈ $0.005/post read; a
   50-commenter batch at lean history depth ≈ $3.50 of API cost. 25 users ×
   a handful of scans = a real budget line (~$150–300). Decide it now, not
   mid-conversation. YouTube is effectively free (10k units/day ≈ 195 scans).
6. **Platform fit is a coin we have not flipped.** We support YouTube and X.
   A large share of current influence-ops work lives on Telegram, TikTok, and
   Meta platforms. If most of the 25 say "my live case is on Telegram," PMF
   fails for coverage reasons before product reasons — and that is a finding
   to record, not rationalize. (It would NOT authorize building a platform;
   it would change who we recruit or what we conclude.)
7. **The 0.000 FPR is on our own controls.** First contact with real
   adversarial data will produce some rate of embarrassing output. Plan to
   receive that gracefully: an expert showing us a false positive is the most
   valuable artifact this phase can produce. It is data, not insult.
8. **The featured demo is curated, and experts may clock that in 30 seconds.**
   The bet is that the evidence-and-counter-evidence framing carries
   credibility anyway. That is Assumption A5 below — a bet, not a fact.
9. **Transactional email is probably not wired.** The only SMTP consumer in
   the codebase is monitoring-alert delivery (`notifications/delivery.py`,
   env-gated, off by default). Password-reset pages and endpoints exist, but
   whether a reset email actually sends must be verified in the Week-0 smoke
   test. A locked-out stranger doesn't file a bug — they vanish.
10. **25 conversations is signal-finding, not statistics.** The only thing
    that keeps it honest is pre-committed pass/fail criteria written *before*
    the first call (Step 2 §F). Without them we will rationalize whatever
    happens as "encouraging."

**The one number that matters:** how many of 25 hand-picked target users bring
a case of their own (not the demo) through Omi within the validation window.

---

## STEP 1 — Capability audit: what a user can actually do today

Tag on every group: **validated by real users — NONE.** That tag is the point
of this phase.

### Core value (the scan → evidence loop)
- **URL → full coordination scan**: YouTube video commenter batches; X/Twitter
  single-account deep scans and multi-account thread batches. Sync + async job
  paths; async jobs have a 300s timeout reaper with credit refund.
- **Six coordination detectors** (temporal_semantic, fingerprint_cluster,
  age_cohort, style_match, co_engagement, co_tag) feeding a **corroboration
  gate** — a lone supporting detector is ceilinged at 0.49 and can never
  produce a maximal verdict on its own.
- **Signal decorrelation** (content/timing redundancy discounts) so correlated
  detectors don't double-count; optional learned correlation model.
- **OmiScore** with principled exclusions: AI-writing style never adds
  suspicion (ESL/Grammarly false-positive protection); community standing is a
  downward-only anchor; contextual dimensions excluded from threat scoring.
- **Campaign store with recurrence**: clusters materialize into durable
  Campaigns/Members/Observations; the same network re-surfacing across scans
  merges instead of duplicating.
- **Cross-scan memory**: account fingerprints + k-NN re-identification.
- **Member-level elevation gate + boundary hold** — member FPR measured to
  0.000 on legitimate controls, at zero recall cost (PHASE5_REPORT).
- **Honest result states**: coordination_found / organic / insufficient_data /
  scan_incomplete (≥30% fetch failures is never sold as "clean").
- **Narratives** (message-grain clustering), **content intelligence** store,
  **graph view**, **bulk scans**, **LLM commentary** with a no-key template
  fallback.

### Trust
- Evidence-FOR and evidence-AGAINST on every verdict; confidence and
  uncertainty always surfaced; analyst verdict + notes are user-owned
  conclusions (the machine never persists "this IS a campaign").
- Corroboration gate + discriminative/supporting detector split; decorrelation.
- First-view "how to read this" guidance (Phase 5) on campaign + public reports.
- Privacy posture: first-party only, no IP storage (hashed, 10-min TTL dedup
  only), whitelisted event recorder, privacy-page disclosure.
- Published measurement program: member-elevation harness + PHASE3/4/5 +
  TRUST_BOUNDARY_TRACKING reports in-repo.
- Hardening: login/signup/reset rate limits; public-report rate limiting.

### Distribution
- Public investigation reports `/r/{token}` and public campaign reports
  `/rc/{token}` — mint/revoke, idempotent tokens, no-auth read.
- Markdown + JSON exports of reports and campaigns.
- Featured campaigns on the landing page (~10s cold-visitor path to a real
  report) with cross-featured navigation; seeded via `content/seed.py` +
  `content/featured.py`.
- Referral bonus system (`core/referrals.py`).
- Marketing surfaces: pricing, about, privacy, terms.

### Workflow
- Auth (signup/login/forgot/reset), credits with per-batch pricing
  (YouTube 1 credit / X 10 credits per ≤50-commenter batch), Stripe $9.99/mo
  subscription with idempotent webhook handling.
- Investigation history (slugs, labels, batches, re-scan), analyst verdict +
  notes, watchlists + monitoring scheduler (recheck cadence, narrative-spike
  and high-tier-surge alerting) with email/webhook delivery — env-gated,
  off by default.
- Channels / content / accounts drill-downs, search, settings (including
  calibration + engine), dashboard with the WTP prompt.

### Analytics (founder-facing)
- EventLog five-question learning system — six whitelisted event kinds,
  SAVEPOINT-isolated writes: featured_viewed, campaign_export,
  campaign_share_minted, public_report_view (per-IP-hash deduped),
  wtp_answer, wtp_dismissed.
- **`GET /v1/admin/learning`** — answers Q1–Q5 literally from EventLog +
  existing ledgers (User/ScanLog/Investigation), with definitions, caveats,
  and verbatim WTP answers. Admin-gated.
- `/v1/metrics` ops metrics; YouTube quota status; scan logs; offline
  member-elevation measurement harness.

### Env-gated inventory (exists, but OFF until configured)
X scans (API key), YouTube scans (API key), Stripe (3 vars), monitoring
(flag), alert email (SMTP), LLM commentary (key — falls back to template),
ML scorer (off by default). This list IS the production-setup checklist.

---

## STEP 2 — The PMF Validation System

### A. Recruitment workflow (pipeline)
Stages, tracked per person:
`prospect → contacted → replied → report_opened → call_booked → call_done →
activated (ran own-case scan) → returning (2nd scan, week 2) → reference
(would be quoted / intro others)`.

- Build the 25-prospect list before first contact (composition: 12 OSINT /
  8 journalists / 5 T&S — over-index the sharpest ICP so one segment can
  produce a clean signal).
- Work in **waves of 5**, 2–3 days apart; each wave's message adapts from the
  last wave's response data. Never blast 25 at once — that burns the list
  before anything is learned.
- Refill rule: every "no / silence after 2 touches" is replaced by a new
  prospect of the same ICP so 25 *quality conversations* is the constant, not
  25 attempts.

### B. Outreach workflow
- **Artifact-first, one-question ask.** The unit of outreach is a live public
  report (`/rc/...`) in the prospect's own domain + one sharp question —
  never a pitch, never a feature list, never "feedback on my startup?"
- Channel priority: warm intro > artifact DM > public reply to a live
  "is this coordinated?" thread > short personal email > value-first
  community post. No HN/ProductHunt launch, no ads, no mass email.
- Personalization is mandatory: every first message references a specific
  thing they published. If you can't write that sentence, they're the wrong
  prospect.
- Follow-up discipline: T+3d one nudge with a *different* artifact angle;
  T+10d polite close. Max 2 touches ever. Reply to any response within 24h;
  book interested people within 72h.

### C. Interview workflow (20 minutes, scripted)
1. **0–3 min — their world:** "Walk me through the last time you had to decide
   whether a cluster of accounts was coordinated. What did you actually do?"
   (Baseline workflow + tooling + hours spent.)
2. **3–10 min — cold read, say-aloud:** open a report they haven't seen;
   ask them to narrate what they think it claims. *Do not help. Do not
   defend.* This is the live test of comprehension (A6) and of the
   counter-evidence framing (A5).
3. **10–15 min — the five questions** (Step 2 §E mapping below).
4. **15–18 min — the close that matters:** "Is there a case on your desk
   *right now* you'd run through this?" If yes — get them to run it live or
   schedule it within 48h with credits pre-granted.
5. **18–20 min — WTP:** "If this saved you the hours you described, what's
   that worth? Who holds that budget?" The awkwardness is the data.

Rules: notes verbatim where possible; never argue with a false positive —
ask "what tells you it's wrong?"; never promise features; log same day.

### D. Feedback workflow
- Single tracker (spreadsheet — deliberately NOT built into Omi). Every note
  tagged to Q1–Q5 and to assumption IDs A1–A10 (Step 5).
- **Friday synthesis ritual (weekly):** read `GET /v1/admin/learning` + the
  tracker; update each assumption's status (supported / contradicted /
  untested); write the next wave's message changes; update the parking lot.
- **Parking lot:** every feature request goes in with the requester's name and
  the underlying job-to-be-done. Nothing gets built during the window.
- **The one exception (pre-declared):** a *trust-breaking defect* — wrong
  evidence shown, a false positive an expert demonstrates on their own case,
  a broken public report — confirmed by ≥2 independent users pauses
  recruiting and gets fixed immediately. Trust defects compound; feature gaps
  don't. This is the only path back into code during Phase 6.

### E. Success metrics (pre-committed)
| # | Signal | Threshold (of 25 quality conversations) |
|---|---|---|
| S1 ⭐ | Real-case pull | ≥ 5 run a case of their own |
| S2 | Activation | ≥ 40% of report-openers run their own scan within 7d |
| S3 | Trust | ≥ 3 unprompted "I would cite/defend this" (or actually do) |
| S4 | Distribution | ≥ 3 unprompted shares that get read (new-viewer report views) |
| S5 | Retention | ≥ 5 run a second scan in week 2+ without a nudge |
| S6 | WTP | ≥ 3 concrete dollar answers *with a named budget owner* |

### F. Failure metrics (pre-committed — written before the first call)
| # | Trigger | Meaning / action |
|---|---|---|
| F1 | < 2 real cases after 25 quality conversations | The magic moment is not a painkiller for this ICP. Re-segment (likely narrow to pure-OSINT) or revisit the thesis. Do not build your way out. |
| F2 | Reply rate < 10% after 2 waves including warm paths | Targeting/message failure, not product failure. Fix venue + message before continuing; conversations not sent don't count. |
| F3 | ≥ 50% of cold reads stall or misread the verdict in 60s | Comprehension failure (A6). Messaging/copy defect — adjust report copy only if it qualifies under the §D exception; otherwise script the explanation and log it. |
| F4 | ≥ 2 experts independently reject verdicts on their own cases | Trust defect (A4/A5). Pause recruiting, fix, resume. The only build-authorizing failure. |
| F5 | > 40% of real-user scans end scan_incomplete | The core loop breaks on real workloads (A7). Ops/quota problem — fix keys/depth config; if structural, that is a finding for the gate. |
| F6 | Majority of live cases on unsupported platforms | Coverage falsification (A3). Record honestly; re-target recruiting to YouTube/X-native cases for the remainder; carry the finding to the gate. |
| F7 | 0 concrete WTP answers across all 25 | No commercial pull at current shape/price. Not a kill on its own pre-PMF, but it forces the gate discussion. |
| F8 | < 15 quality conversations completed by end of week 3 | Founder-execution failure. The bottleneck is recruiting hours, not the product. Extend one week max; if still short, that itself is the finding. |

---

## STEP 3 — Founder operating playbook: the first 25

### Week 0 — prerequisites (ops only; nothing here is product work)
1. **Deploy or verify the production URL** (Render blueprint: web + API +
   *paid* Postgres — the free tier deletes data at ~90 days).
   Fill: X + YouTube API keys, session secret, public base URL,
   `OMI_SUPER_ADMIN_EMAILS` (must include the email you'll log in with, or
   `/v1/admin/learning` will 403), Stripe keys (optional but enables S6
   testing with real money).
2. **Credits for the cohort:** raise `OMI_FREE_TRIAL_CREDITS` for the window
   (e.g. 25) or hand-grant per tester — otherwise no trial user can run an X
   batch scan (10 credits > 3). Decide the API budget: ~$150–300.
3. **Smoke test ×3 outsiders** (non-founder friends, not ICP): cold signup →
   scan a URL they choose → open the report → mint a share → open it
   logged-out. Also: trigger forgot-password and confirm what actually
   happens. Every step must complete unaided. Fix only ops/config blockers.
4. **Verify the featured campaign is seeded** and the landing → `/rc/...`
   path works on production.
5. **Set up the tracker** (schema below) and block **2h/day** on the calendar
   for outreach + calls. This phase is sales-research work; the calendar
   block is the real commitment.

### Who to target (recognition heuristics)
- **A. OSINT / disinfo researchers (12):** they post "here's the network"
  threads with account screenshots; vocabulary: coordination, astroturfing,
  inauthentic behavior, ban evasion. Think-tank fellows, DFRLab-style
  analysts, Bellingcat-orbit contributors, SIO diaspora.
- **B. Investigative journalists on the influence beat (8):** bylines on
  bot-network / influence-op stories; freelancers pitching them; they need a
  defensible "organic or coordinated?" call before publication.
- **C. T&S / integrity professionals at small-mid platforms (5):** TSPA
  members; titles containing integrity / platform abuse / T&S ops; they
  triage brigading and review-fraud reports without Meta-scale tooling.
- **Platform-fit screen (apply to every prospect):** prefer people whose
  public work involves YouTube or X cases — that's what Omi can scan today.
  Logging "my case is on Telegram" answers is A3 data, but don't fill the
  list with guaranteed mismatches.

### Where to find them
- **A:** Bluesky OSINT/journo cluster; the X disinfo-research cluster and its
  reply network; Bellingcat Discord; r/OSINT; EU DisinfoLab / NATO StratCom /
  MisinfoCon orbit; SIO alumni.
- **B:** IRE + NICAR listservs and attendee lists; Hacks/Hackers chapters;
  ONA; journalism Slacks; serious disinfo Substack comment sections.
- **C:** TSPA forum/Slack; TrustCon speaker/attendee lists; integrity
  LinkedIn cohorts.
- **Warm-path mining:** conference speaker lists are the best 2nd-degree
  source; one specific intro ask per connector.

### How to contact them
Channel order: warm intro → artifact DM → public reply on a live thread →
short personal email. One person, one personalized message, one question.

### What to send (skeletons — adapt per wave)
- **A (researcher):** "Your thread on [specific network] — the hardest part
  looked like proving the accounts were linked, not finding them. We built a
  scanner that assembles the evidence *and the counter-evidence* for exactly
  that call. Here's a live read on [domain-relevant campaign]: [/rc link].
  Does the evidence-against section earn your trust or read as hedging?"
- **B (journalist):** "You wrote [story]. If a reply-swarm hit a source's
  post tomorrow, what would you need to print 'coordinated' safely? This is
  the report we'd hand your editor: [/rc link]. Would this survive your
  standards desk?"
- **C (T&S):** "When a brigading report lands in your queue, what does triage
  cost you today? This is a 60-second coordination read with the evidence
  attached: [/rc link]. What would it need to drop into your casework?"
- Never send: a deck, a feature list, a Calendly-first ask, or "any feedback
  appreciated."

### How to follow up
- T+3d: one nudge, different artifact or angle. T+10d: polite close. Max 2
  touches. Respond to any reply within 24h; book within 72h; pre-grant
  credits before every call so "run your case now" is frictionless.

### How to log responses
Tracker columns (one row per prospect):
`name | ICP (A/B/C) | where found | warm path | sent date | wave # |
artifact sent | stage (pipeline) | reply verbatim | call date |
cold-read result (clean/stalled/misread) | own-case? (Y/N + platform) |
case outcome (confirmed/rejected/incomplete) | trust quote | WTP answer |
budget owner | assumption tags (A1–A10) | follow-ups used (0–2) | next action`
Log same-day, verbatim quotes over paraphrase. The tracker — not memory —
is the input to Friday synthesis and the final gate.

---

## STEP 4 — PMF dashboard (design only; Phase 4 data only)

**Constraint compliance:** zero new telemetry, zero new event types, zero new
infrastructure, zero new UI. The dashboard is a weekly one-page readout
assembled from `GET /v1/admin/learning` (already built, admin-gated) plus the
founder tracker. At N=25, a JSON endpoint read on Friday *is* the dashboard;
building a UI for it would be procrastination with extra steps.

| Row | PMF question | Source (exists today) | Number to read | Threshold (Step 2) | What it CANNOT tell you |
|---|---|---|---|---|---|
| 1 | Did they experience value? | `q1`: activated_users, activation_rate, first_week_activation, reached_featured_value_surface | % of cohort activated (export / share / published / successful scan) within 7d | S2 ≥ 40% | Whether the value was *their case* or the demo — own-case comes from the tracker |
| 2 | Did they come back? | `q2`: returned_users (≥2 distinct active days) | return rate, week-over-week | S5 ≥ 5 second-scan users | Passive visits are invisible (accepted blind spot — no session telemetry by design) |
| 3 | Did they share it? | `q3`: shares minted, public_report_views (per-IP-hash deduped), views_per_share | minted → actually-read conversion; "dead share" rate | S4 ≥ 3 read shares | WHO viewed (deliberately unknowable — no IP storage); pair with "who did you send it to?" |
| 4 | Did they trust it? | `q4`: verdict_concluded rate, with_analyst_notes | % of investigations the analyst was willing to conclude | S3 (qualitative) | Trust itself. Conclusion-rate is a proxy; real signal is interview quotes + F4 watch |
| 5 | Would they pay? | `q5`: subscribed_users (real Stripe status), verbatim wtp_answers | subscriptions; concrete-number WTP answers | S6 ≥ 3 with budget owner | Price elasticity; whether $9.99/mo is even the right packaging (see A9) |

Plus one guardrail row from the tracker (not the EventLog, and we will NOT
add an event for it): **scan_incomplete frequency** reported by users (F5).

Cadence: read every Friday before synthesis; paste the five numbers + deltas
into the tracker's summary tab so the trend survives the session.

---

## STEP 5 — Top 10 unvalidated assumptions, ranked by risk

Risk = (damage if false) × (current uncertainty). A1 is existential; A10 is
merely important.

**A1. A working investigator will bring a real case.** *Why:* this is the
company. Every other answer is noise without it. *Test:* the 25-user push;
"case on your desk right now?" close in every call; pre-granted credits.
*Validated:* ≥5 own-case scans (S1). *Falsified:* <2 after 25 quality
conversations (F1).

**A2. A stranger can reach and use the product unaided.** *Why:* if signup,
scanning, or password reset fails without founder hand-holding, every
downstream metric reads "no demand" when the truth is "broken funnel."
*Test:* Week-0 smoke test ×3 outsiders, including forgot-password.
*Validated:* 3/3 complete signup → own scan → share unaided. *Falsified:* any
step needs founder intervention (fix = ops config only).

**A3. Their live cases are on platforms Omi can scan (YouTube/X).** *Why:*
coverage mismatch fails PMF before product quality ever gets tested. *Test:*
ask "where does your current case live?" in every call; log platform on every
own-case row. *Validated:* ≥60% of offered cases are YouTube/X. *Falsified:*
majority Telegram/TikTok/Meta (F6) — recorded as a finding, not a build
ticket.

**A4. Detection quality survives real adversarial data.** *Why:* FPR 0.000
was measured on curated controls; experts will bring the messy real world.
One demonstrated false positive in front of a journalist costs more trust
than ten true positives earn. *Test:* first 10 own-case scans reviewed
against the user's own ground truth in-call. *Validated:* no expert
demonstrates an obviously-organic cluster flagged hostile; ≥1 confirmed true
finding. *Falsified:* ≥2 experts reject verdicts on their own cases (F4 —
the only failure that re-authorizes code).

**A5. Counter-evidence framing builds trust rather than doubt.** *Why:* it is
our core differentiator bet. If experts read evidence-against as "the tool
isn't sure of anything," the positioning inverts. *Test:* the cold-read
say-aloud + "does the against-section earn trust or read as hedging?"
*Validated:* ≥3 unprompted would-cite statements (S3). *Falsified:* repeated
"hedging" reactions or experts skipping the against-section entirely.

**A6. A cold expert understands the report in 60 seconds.** *Why:* Phase 5's
comprehension guidance was reasoned, never human-tested; confusion at first
view kills activation silently. *Test:* say-aloud cold reads. *Validated:*
≥70% correctly state the claim + confidence unaided. *Falsified:* ≥50% stall
or misread (F3).

**A7. Fetching holds up on real targets.** *Why:* scan_incomplete exists
because fetches fail; real targets are bigger and messier than fixtures, and
the X path depends on a third-party reseller (twitterapi.io) with its own
reliability. *Test:* track incomplete/failed outcomes across all own-case
scans (tracker, not telemetry). *Validated:* <20% incomplete. *Falsified:*
>40% (F5) — the magic moment physically can't happen.

**A8. The curated demo transfers to "I'll run mine."** *Why:* demo-impressed
≠ activated; the "cool demo" trap is the most common false positive in early
validation. *Test:* q1 featured_reached vs own-scan rate (S2 funnel) +
expert reaction to the demo's curation. *Validated:* ≥40% of report-openers
run their own scan in 7d. *Falsified:* high demo views, near-zero own scans.

**A9. Someone will pay — and the payer is reachable.** *Why:* the passion
ICP (independent OSINT) is often budgetless; the budget ICP (T&S) buys
through procurement and may need API/SSO/scale we explicitly will not build
now. Also honest: $9.99/mo is hobbyist pricing for a professional evidence
tool — possibly mispackaged for every ICP. *Test:* WTP close in all 25 +
budget-owner question; Stripe live = a real purchase is possible during the
window. *Validated:* ≥3 concrete numbers with named budget owners (S6); any
actual subscription is gold. *Falsified:* zero concrete answers (F7), or all
numbers an order of magnitude below sustainability.

**A10. Shared reports actually spread.** *Why:* public reports are the only
built-in distribution engine; if minted links go unread, growth has no organic
channel. *Test:* q3 minted→viewed conversion (deduped views) + "who did you
send it to?" *Validated:* ≥3 unprompted shares with real new-viewer reads
(S4). *Falsified:* shares minted but views ≈ senders only; or nobody mints
at all.

---

## Operating cadence and the gate

- **Week 0:** prerequisites + smoke test + list building.
- **Weeks 1–3:** waves of 5; calls within 72h; Friday synthesis each week;
  refill the list to hold "25 quality conversations" constant.
- **Week 4:** synthesis + the gate.

**Gate outcomes (pre-committed):**
- **STRONG** (S1 + S3 met, no F-triggers): Phase 7 = concentrate on the
  winning segment; pricing/packaging test; second cohort of 25 from that
  segment only. Still no feature building until the parking lot shows the
  same job-to-be-done ≥5 times.
- **MIXED** (some S-metrics, no F1): iterate ICP + message, run a second 25.
  No building.
- **FAIL** (F1): the thesis as targeted is wrong. Re-segment or stop. The
  parking lot and tracker are the post-mortem evidence either way.
- **TRUST DEFECT** (F4): pause, fix, resume — the only build path.

The deliverable of Phase 6 is not code and not even users. It is **a
truthful, evidence-backed answer to the five questions**, in writing, that
Phase 7 can be staked on.
