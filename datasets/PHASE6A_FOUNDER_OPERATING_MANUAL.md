# PHASE 6A — FOUNDER OPERATING MANUAL

> Operational system only. No code, no features, no redesign. Everything here is
> executable by the founder with the product as it stands plus ops/config.
> Grounded in the verified product (credits: YouTube batch = 1, X batch = 10,
> trial = 3; `/v1/admin/learning`; `/rc/{token}` public reports; Stripe $9.99/mo).

---

## STEP 1 — WEEK 0 CHECKLIST (complete before contacting a single user)

Rule: every box is checked or explicitly waived **in writing with a reason**.
Three items are hard blockers (marked �USER cannot succeed without it).
**Run all user-facing tests on a throwaway NON-ADMIN account** — admin accounts
skip credit consumption, so testing as admin hides the credit wall that real
users hit.

### 1.1 Deployment verification
- [ ] Production web URL loads over HTTPS (not a localhost/preview link).
- [ ] `GET /health` on the API returns ok.
- [ ] Web talks to API in production (a real action — e.g. signup — succeeds end to end, proving `OMI_API_ORIGIN` is wired).
- [ ] �USER **Postgres is a PAID tier**, not Render free (free databases are deleted ~90 days → total loss of every investigation, fingerprint, and label). Confirm in the dashboard.
- [ ] Env set: `OMI_TWITTER_API_KEY`, `OMI_YOUTUBE_API_KEY`, `OMI_SESSION_SECRET` (stable across deploys), `OMI_PUBLIC_BASE_URL` (matches the real domain), `OMI_REQUIRE_AUTH=true`.
- [ ] A redeploy does not log users out (session secret is persistent, not regenerated).

### 1.2 Account creation tests (non-admin throwaway account)
- [ ] Cold signup completes from the live site with no founder intervention.
- [ ] Trial credits granted on signup; record the exact number shown.
- [ ] �USER **Trial credits ≥ one X batch (10).** Default is 3 → a trial user CANNOT run the primary OSINT scan. Resolve before outreach: raise `OMI_FREE_TRIAL_CREDITS` for the window (e.g. 25), or pre-grant per tester. Re-verify after the change on a fresh account.
- [ ] Login, logout, and log back in all work; session persists across a browser restart.
- [ ] �USER **Forgot-password actually delivers an email.** Trigger it and confirm a real message arrives. (SMTP may be unconfigured — the only mail path in the build is monitoring alerts. A locked-out stranger won't file a bug; they vanish.) If no email: configure SMTP, or have a documented manual reset path before outreach.

### 1.3 Scan tests (non-admin account, so credits decrement)
- [ ] YouTube video scan: paste a URL → completes → report shows evidence + confidence + a result state. Credit decrements by 1.
- [ ] X single-account deep scan completes; credit decrements by 1.
- [ ] X batch scan (multi-account thread) completes; credit decrements by 10. Confirm the test account had enough credits (ties to 1.2).
- [ ] Async path: a slow/large scan finishes; a deliberately bad URL fails cleanly and **refunds** credits (300s reaper works) — user never polls forever.
- [ ] Sanity on quality (do this with cases where you know the answer): a known-coordinated case surfaces coordination; a known-organic case does NOT get flagged hostile. One embarrassing false positive in front of an expert is the most expensive thing that can happen.
- [ ] `scan_incomplete` appears (not a false "clean") when a scan has heavy fetch failures — confirm by scanning something likely to rate-limit.

### 1.4 Share tests
- [ ] Mint a share on an investigation → open `/r/{token}` in incognito (logged out) → renders.
- [ ] Mint a share on a campaign → open `/rc/{token}` logged out → renders.
- [ ] Revoke a share → the public URL now 404s.
- [ ] Markdown export downloads and is readable; JSON export downloads and parses.
- [ ] The seeded featured campaign loads publicly (`/rc/cmp_feat_cn_xinjiang`) and the landing-page CTA reaches it (~10s cold path). This is the artifact every outreach message links — it must be live.
- [ ] Normal repeated viewing of a public report is not blocked by rate limiting (limiter only catches a hammering scraper).

### 1.5 Payment tests
Decide first: **are you running real payments during the window?** (You can validate WTP verbally without it, but a live purchase is the strongest S6 signal.)
- [ ] If yes: `OMI_STRIPE_SECRET_KEY`, `OMI_STRIPE_WEBHOOK_SECRET`, `OMI_STRIPE_PRICE_ID` set; webhook registered at `…/v1/billing/webhook`.
- [ ] Checkout opens (create-checkout-session returns a hosted URL); a Stripe **test-mode** purchase completes and redirects back.
- [ ] Webhook marks the subscription active and grants the monthly credits; status is visible in `/v1/admin/learning` → `q5.subscribed_users`.
- [ ] If NOT running payments: confirm billing routes return the graceful 503 ("billing isn't configured") rather than erroring, so a curious user doesn't hit a broken page.

### 1.6 Analytics verification (the learning loop must actually record)
- [ ] `GET /v1/admin/learning` returns 200 for your account and shows the five questions.
- [ ] Do a value action (export or mint a share) → `q1.activated_users` / `q3.shares_minted` reflect it.
- [ ] View a public report from a different device/IP → `q3.public_report_views` increments; view it 3× rapidly from one IP → still counts once (dedup works).
- [ ] As a returner (≥2 investigations), the WTP prompt appears; submit an answer → it shows verbatim in `q5.wtp_answers`; dismiss → it never reappears.
- [ ] Spot-check: no raw IPs or PII stored in the event log (first-party, hashed-only by design).

### 1.7 Admin verification
- [ ] 🔑 Your login email is in `OMI_SUPER_ADMIN_EMAILS` (else `/v1/admin/learning` and `/v1/metrics` 403). Co-founder's too if applicable.
- [ ] Admin account skips credit consumption (confirm — and remember this is exactly why user tests use a non-admin account).
- [ ] `/v1/metrics` loads.
- [ ] Decide the credit-grant mechanism for testers: env bump (`OMI_FREE_TRIAL_CREDITS`) is the reliable lever. If you want per-user grants, verify an admin path exists; if not, the env bump is it.

### Go / No-Go gate
**GO only when:** production URL live · paid Postgres · the three �USER blockers resolved (trial credits ≥10, forgot-password email works, data is durable) · one full happy path done end to end on a non-admin account (signup → X batch scan → report → mint share → open logged out) · `/v1/admin/learning` reflects those actions. Until then, do not contact anyone — a broken funnel will read as "no demand."

---

## STEP 2 — 25-USER RECRUITMENT TRACKER

One spreadsheet, one row per prospect. Three blocks: who they are, how outreach
went, what they taught you.

### Fields

**Identity & targeting**
| Field | Type | Values / notes |
|---|---|---|
| `name` | text | |
| `handle_or_email` | text | primary contact |
| `icp` | enum | A=OSINT · B=Journalist · C=T&S |
| `source` | text | where you found them (specific venue) |
| `evidence` | text | the specific post/story/role that qualifies them |
| `platform_fit` | enum | YouTube/X · Mixed · Unsupported (Telegram/TikTok/Meta) |
| `warm_path` | text | connector name, or "cold" |
| `fit_score` | 0–100 | computed (rubric below) |

**Outreach**
| Field | Type | Values / notes |
|---|---|---|
| `wave` | int | 1–5 (assigned at prioritization) |
| `channel` | enum | warm-intro · DM · public-reply · email |
| `artifact_sent` | text | which `/rc` report link |
| `sent_date` | date | |
| `followups_used` | 0–2 | hard cap 2 |
| `status` | enum | pipeline (below) |
| `reply_verbatim` | text | paste exact words |

**Validation signals (filled post-contact)**
| Field | Type | Maps to |
|---|---|---|
| `cold_read_result` | enum | clean / stalled / misread → A6/F3 |
| `own_case` | enum + text | Y/N + platform → A1/A3/S1 |
| `case_outcome` | enum | confirmed / rejected / incomplete → A4/A7 |
| `ran_own_scan` | bool + date | S2 |
| `returned` | bool + date | second scan, wk2+ → S5 |
| `trust_quote` | text | unprompted would-cite → A5/S3 |
| `shared_with` | text | who they sent it to → A10/S4 |
| `wtp_answer` | text | verbatim → S6 |
| `budget_owner` | text | named person/role → S6 |
| `signal_score` | int | computed (rubric below) |
| `assumption_tags` | multi | A1–A10 touched |
| `next_action` | text | |

### Statuses (pipeline)
`prospect → queued → contacted → replied → report_opened → call_booked →
call_done → activated → returning → reference`
Terminal: `no_reply` (after 2 touches) · `declined` · `disqualified` (wrong ICP
or unsupported platform with no real case). Disqualified/no_reply trigger the
refill rule — replace with a same-ICP prospect so **25 quality conversations**
stays the constant.

### Scoring system (two scores, different jobs)

**Fit Score (0–100)** — prioritizes *who to contact*. Sum:
- Active case now (working a relevant coordination question): **0–30** ← weight heaviest; it's A1.
- Platform fit (YouTube/X): 0–25 (Mixed 12, Unsupported 0) ← A3.
- ICP sharpness (A=20, B=14, C=10): 0–20.
- Reachability (warm path 15 / 2nd-degree 8 / cold 3): 0–15.
- Reach/influence (would their adoption pull others?): 0–10.

**Signal Score** — measures *validation produced*, accrues after contact:
opened report +1 · gave cold read +2 · **brought own case +5** · **ran own scan
+5** · returned (2nd scan) +4 · unprompted would-cite +3 · shared (got read) +3
· WTP with named budget +3. This is each user's contribution to S1–S6; the
column you sort by in the Friday review.

### Prioritization system
1. Compute Fit Score for all prospects; sort descending.
2. Enforce composition: 12 A / 8 B / 5 C across the 25.
3. Assign waves of 5: each wave gets the current highest-Fit prospects **spread across all three ICPs**, so every wave tests A/B/C and you're never blind to a segment.
4. Contact wave N, wait 2–3 days, read results, adjust the message, then wave N+1.
5. Cap follow-ups at 2 per prospect. Don't over-invest in a non-responder when a fresh high-Fit prospect is available.
6. Refill on every terminal status to hold the cohort at 25 quality conversations.

---

## STEP 3 — FIRST 10 OUTREACH MESSAGES

Principles for all: artifact-first (lead with a live `/rc` report in their
domain), **one** question, no pitch, no deck, no feature list, no Calendly-first
ask. Personalize the [bracket] or don't send. Keep under ~90 words.

### OSINT researchers (A)

**#1 — Cold DM (primary)**
> [Name] — your thread on [specific network/campaign] stuck with me; the hard part looked like *proving* the accounts were linked, not spotting them. I built a scanner that lays out the evidence **and the counter-evidence** for that exact call. Here's a live read on [domain-relevant case]: [/rc link]. Honest question — does the "evidence against" section earn your trust, or read as hedging?

**#2 — Warm-intro request (to a connector, not the prospect)**
> [Connector] — you know [Name]'s coordination work. I built a tool that assembles the evidence + counter-evidence for "is this cluster coordinated?" and I'd value their brutal read on one report, not a pitch. Worth a one-line intro? Here's the artifact so you can judge first: [/rc link].

**#3 — Public reply (to a live "is this coordinated?" thread)**
> Curious what you'd make of this — ran a coordination read on a similar cluster; it shows the linking evidence and the points against it side by side: [/rc link]. Not selling anything, genuinely want to know if the against-column changes your read.

**#4 — Follow-up (T+3d, different angle, once)**
> No worries if this isn't your thing. One concrete thing in case it's useful: [/rc link] is the kind of output in ~60s for a network you'd otherwise map by hand. If you've got a cluster on your desk, I'll run it free — reply with a link.

### Investigative journalists (B)

**#5 — Cold email**
> Subject: the "coordinated" call before you publish
> [Name] — your piece on [story] is why I'm writing. If a reply-swarm hit a source's post tomorrow, what would you need to print "coordinated" *safely*? This is the report we'd hand your editor — claim, evidence, and the case against: [/rc link]. Would it survive your standards desk?

**#6 — DM referencing their story**
> [Name] — following your [beat] reporting. Built something that does the "organic or coordinated?" triage with the evidence attached, including what argues against. Live example: [/rc link]. If you're chasing a network now, I'll run it and send the report — no ask attached.

**#7 — Follow-up (T+3d, once)**
> Last note — if a coordination question ever lands on deadline, the offer stands: send the post/handles, I'll return a shareable report you can scrutinize. [/rc link] is what it looks like.

### Trust & Safety professionals (C)

**#8 — Cold email / LinkedIn**
> [Name] — when a brigading or review-fraud report hits your queue, what does triage cost you today? This is a ~60-second coordination read with the evidence (and counter-evidence) attached, exportable into casework: [/rc link]. What would it need to be useful in your workflow?

**#9 — Warm intro via TSPA/peer**
> [Connector] — could you intro me to [Name]? I built a coordination-triage tool that outputs evidence-first reports for casework, and I want their integrity-team perspective on whether it'd hold up in an appeal. Artifact first so you can vet it: [/rc link].

**#10 — Follow-up (T+3d, once)**
> Understood if the timing's off. If a coordination case comes through your queue, I'll run it and hand you the report to poke holes in: [/rc link]. Genuinely after the holes, not a sale.

---

## STEP 4 — INTERVIEW SCRIPT (word-for-word, non-leading)

**Design rules (read before every call):**
- Ask about their **past and present behavior**, never about hypothetical futures or your idea. "Would you use…" / "Do you like…" / "Would you pay…" are banned — they generate polite lies.
- **Talk less.** Silence after a question pulls the truth. Count to five.
- Never explain or defend the product during the cold read. Confusion you talk them out of is confusion you'll never hear about again.
- Separate **what they say** from **what they do** — the only hard usefulness signal is whether they run their own case. Compliments are not data.
- Capture verbatim. Tag each answer to Q1–Q5 and A1–A10 after the call.

**0. Framing (say this)**
> "Thanks for the time. This isn't a demo and I'm not going to pitch you. I'm trying to find out where this tool is wrong and where it's useless, so the bluntest thing you can say is the most helpful. Mind if I take notes / record so I quote you accurately rather than paraphrasing? You can tell me to cut anything."

**1. Their world — usefulness baseline (non-leading)**
> "Walk me through the last time you had to decide whether a group of accounts was acting in a coordinated way. What was actually going on?"
> *(then, only as probes)* "What did you do first?" · "What tools did you reach for?" · "How long did that take, start to finish?" · "What was the most annoying part?" · "What did you do with the result once you had it?"
> DON'T say: "Wouldn't a tool that does that automatically be helpful?" Let the pain describe itself.

**2. Cold read — confusion + comprehension (say-aloud protocol)**
> "I'm going to share a report you haven't seen. Read it like it landed in your inbox and just say out loud what you think it's telling you — what it's claiming and how sure it is. I'll stay quiet."
> *(stay silent. note every stall, scroll-back, or misread. when they pause)* "Keep going — what do you make of that part?"
> *(only after they finish)* "Anything on here confusing, or that you'd want defined?"
> DON'T explain a section they misread. The misread IS the finding (A6/F3).

**3. Trust — the counter-evidence probe (non-leading)**
> "Pick the part of this you trust most, and the part you trust least. Why those?"
> *(then)* "There's a section laying out the evidence *against* the conclusion. What did you think when you saw that?"
> *(then, the real one)* "If you put this conclusion in something with your name on it, what would a hostile reviewer attack first?"
> DON'T say "Doesn't the counter-evidence make it more trustworthy?" — that's the answer you're hoping for; asking it guarantees you hear it.

**4. The real-case close — behavioral usefulness (the one that matters)**
> "Is there a case on your desk *right now* you'd want to look at this way?"
> *(if yes)* "Want to run it now? I'll watch and stay out of the way." *(then watch — do they get to a result? do they believe it? what do they do next?)*
> *(if no)* "When was the last time you had one?" *(gauge real frequency — a 'someday' is a no)*
> This is S1/A1. A live own-case run beats any verbal praise in the whole call.

**5. Willingness to pay — Mom Test style (no leading, no your-price-first)**
> "How does your team handle tools like this today — is there a budget, or is it whatever's free?"
> *(then)* "What do you (or your org) currently spend to answer this kind of question — in tools, or in hours?"
> *(then)* "If something reliably saved you the [X hours they named earlier], who would decide whether to pay for it, and roughly what band would they not blink at?"
> DON'T say "Would you pay $9.99/month?" Anchoring your price first destroys the signal. Let them price the pain; capture the number AND the budget owner.

**6. Wrap**
> "Two last things. Who else doing this kind of work should I be talking to? And is it alright if I follow up in a couple of weeks to see if you've had a case to point at it?"
> *(log referrals as new prospects; a real intro offer is itself a strong signal)*

---

## STEP 5 — FOUNDER WEEKLY REVIEW (Friday template)

Copy this every Friday. Fill from `GET /v1/admin/learning` + the tracker.
Evidence rule: every claim needs a **quote + who said it** or a **number**. No
adjectives without a source.

```
# OMI WEEKLY REVIEW — Week __  (dates ______ to ______)

## Funnel snapshot (cumulative)
Prospects contacted: __   Replied: __   Reports opened: __
Calls done: __   Activated (own scan): __   Returning: __
Quality conversations to date: __ / 25

## The five numbers (from /v1/admin/learning)
Q1 value      — activation rate: __%   first-week: __   (target S2 ≥40%)
Q2 return     — return rate: __%   returning users: __  (target S5 ≥5)
Q3 share      — minted: __   read views: __   views/share: __ (target S4 ≥3)
Q4 trust      — concluded: __%   w/ notes: __   (proxy only)
Q5 pay        — subscribed: __   concrete WTP-with-budget: __ (target S6 ≥3)
Real cases brought this week: __   cumulative: __  ⭐ (target S1 ≥5)

## 1. What did users LOVE?  (behavior > words)
- [quote / who] — and what they DID (ran case? shared? returned?)
- …

## 2. What CONFUSED users?  (from cold reads)
- [where they stalled/misread — quote / who] → which report section
- …

## 3. Which assumptions got STRONGER this week?
- A_: [evidence — quote/number/who]
- …

## 4. Which assumptions got WEAKER this week?
- A_: [evidence — quote/number/who]
- …

## 5. What to IGNORE (logged, NOT actioned)
- Feature requests → parking lot: [request / who / underlying job]
- One-off opinions with no behavior behind them
- Anything that's a redesign or a new platform
- (Reminder: only a trust-defect confirmed by ≥2 users re-opens code)

## 6. What DESERVES ACTION (ops/message/targeting only)
- Outreach: message/venue changes for next wave: ___
- Ops: any Week-0-style blocker that surfaced (credits, email, scan fails): ___
- Trust defect? (F4) → pause / fix / resume:  Y / N — detail: ___

## Failure-trigger watch
F1 real cases <2? __  F2 reply <10%? __  F3 cold-read ≥50% stall? __
F4 ≥2 expert rejects? __  F5 >40% incomplete? __  F6 platform mismatch? __
F7 zero WTP? __  F8 <15 convos by wk3? __    (any TRUE → act per Phase 6 plan)

## State of validation (one line)
"As of Week __, the evidence says: ___________________________________."

## Next wave plan
Wave __: who (names), channel, message change, target send date.
```

**The discipline:** this review is the product of Phase 6, not the code. If a
Friday passes where you can't fill section 1 with a behavior (not a compliment),
that itself is the week's most important finding.
