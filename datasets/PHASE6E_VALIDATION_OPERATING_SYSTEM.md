# PHASE 6E — FOUNDER VALIDATION OPERATING SYSTEM

> Operational validation instruments only. No product, no engineering, no
> roadmap. Design principle (borrowed from Omi's own trust architecture):
> **evidence, not verdicts** — the instruments store observations, quotes, and
> confidence; they never store a conclusion as truth. Records are append-only
> and revisable; the verdict happens once, at the gate, citing the ledger.

---

## STEP 1 — THE PROSPECT SPREADSHEET (exact structure)

One workbook, five tabs. Tab 1 is the operating surface; the rest feed it.

### Tab 1 — `PROSPECTS` (one row per person)

**Block A — Identity & targeting (filled at sourcing)**
| Col | Field | Type | Allowed values / rule |
|---|---|---|---|
| A | `id` | text | `P001`–`P040` (25 active + bench), never reused |
| B | `name` | text | |
| C | `contact` | text | handle or email actually used |
| D | `icp` | enum | `A-OSINT` · `B-Journalist` · `C-T&S` |
| E | `source` | text | specific venue found (e.g. "r/OSINT thread 6/3") |
| F | `fit_evidence` | text | the post/story/role that qualifies them |
| G | `platform_fit` | enum | `xy` (X/YouTube) · `mixed` · `unsupported` |
| H | `warm_path` | text | connector name · `2nd-degree` · `cold` |
| I | `fit_score` | 0–100 | 6D rubric (30 case / 25 platform / 20 ICP / 15 reach / 10 influence) |
| J | `wave` | enum | `1`–`5` · `bench` |

**Block B — Outreach state (filled as you work)**
| Col | Field | Type | Allowed values / rule |
|---|---|---|---|
| K | `channel` | enum | `warm-intro` · `dm` · `public-reply` · `email` · `linkedin` |
| L | `artifact` | enum | `gru` · `xinjiang` · `custom-/r/` |
| M | `sent_date` | date | |
| N | `followups` | 0–2 | hard cap 2, then terminal |
| O | `status` | enum | see status table below |
| P | `reply_verbatim` | text | paste exact words, never paraphrase |
| Q | `call_date` | date | |
| R | `note_id` | text | `N-P001-1` — links to the interview note (Step 2) |

**Block C — Validation signals (filled post-contact; behaviors only)**
| Col | Field | Type | Allowed values / rule |
|---|---|---|---|
| S | `cold_read` | enum | `clean` · `stalled` · `misread` · `n/a` |
| T | `own_case` | enum+text | `Y`/`N` + platform if Y |
| U | `case_outcome` | enum | `confirmed` · `rejected` · `incomplete` · `n/a` |
| V | `ran_own_scan` | date | blank = no |
| W | `returned` | date | 2nd scan, unprompted |
| X | `trust_quote` | text | verbatim, unprompted only |
| Y | `shared_with` | text | who they sent the report to |
| Z | `wtp_answer` | text | verbatim |
| AA | `budget_owner` | text | named role/person |
| AB | `signal_score` | int | computed: open+1 · cold-read+2 · own-case+5 · own-scan+5 · returned+4 · would-cite+3 · shared-read+3 · WTP-w-budget+3 |
| AC | `assumption_tags` | multi | ledger IDs this row touched (O1, TR2, …) |
| AD | `next_action` | text+date | one action, one due date |
| AE | `notes` | text | anything that fits nowhere else |

### Statuses (col O) — definitions and transition rules
| Status | Means | Enters when |
|---|---|---|
| `prospect` | sourced, unscored | row created |
| `queued` | scored, wave assigned | Day-3 ranking done |
| `contacted` | first message sent | M filled |
| `replied` | any response | P filled (within 24h of reply) |
| `report_opened` | artifact read | q3 view ties out, or they reference its content |
| `call_booked` | time agreed | Q filled |
| `call_done` | interview complete | R filled same day |
| `activated` | ran their own case | V filled — the row that matters |
| `returning` | 2nd unprompted scan | W filled |
| `reference` | would be quoted / intros others | X or referral given |
| `no_reply` ⛔ | 2 touches, silence | N=2 + 7 days — triggers bench refill |
| `declined` ⛔ | said no | refill |
| `disqualified` ⛔ | red flag found late | refill; log why in AE |

Rules: statuses only move forward (a stalled deal keeps its furthest status —
history is never rewritten). Every terminal ⛔ same-day triggers a bench
promotion so the active cohort stays at 25.

### Tab 2 — `DAILY_LOG`
`date | sent | replies | opens(q3) | own_scans | calls_run | 1 verbatim | note`
One line per day, filled in minute 12–15 of the daily (6B).

### Tab 3 — `PARKING_LOT` (feature asks go here to die until the gate)
`date | P-id | request verbatim | underlying job-to-be-done | job_count`
`job_count` = how many DIFFERENT prospects have named the same job. This
column is what the n=25 gate reads (≥8 same-job = Pivot-product evidence).

### Tab 4 — `EVIDENCE_LEDGER` — Step 3's table, live.

### Tab 5 — `WEEKLY` (Friday snapshot)
`week | real_cases_cum | own-scan_rate | trust_net (cites − FPs) | wtp_w_budget | segment_concentration | S-flags met | F-flags fired | one-line state`
— the five Reality-Dashboard numbers (6C) plus flags, pasted so trends survive.

---

## STEP 2 — THE INTERVIEW NOTE TEMPLATE

One note per call, `N-{P-id}-{n}`, written DURING the call, finalized within
the hour. Mirrors the 6A script so nothing depends on memory.

```
NOTE N-____-__        Prospect: P___  (ICP __)      Date: ____
Consent: notes Y/N · recording Y/N      Duration: __ min
Their current role/context (1 line, their words):

[1] THEIR WORLD — last real coordination case
- The case, as they told it (their words):
- What they did first / tools used:
- Hours it took:                 - Most annoying part (verbatim):
- What they did with the result:
- How often this happens (their estimate):

[2] COLD READ (artifact: ____)   — founder stayed silent: Y/N
- Their narration, key phrases verbatim:
- Stall points (which section, what they said):
- Misreads (what they thought it claimed vs. what it claims):
- Time to first correct statement of the claim: ~__ s
- Confusion they named when asked:

[3] TRUST
- Trusts MOST (what + why, verbatim):
- Trusts LEAST (what + why, verbatim):
- Reaction to the evidence-AGAINST section (verbatim):
- "What would a hostile reviewer attack first?" (verbatim):
- Any demonstrated error/false positive? (exactly what they showed):

[4] REAL-CASE CLOSE
- Case on desk now? Y/N — platform: ____
- Ran it live? Y/N — what happened (facts: completed / incomplete / result):
- Their reaction to THEIR OWN case's result (verbatim):
- If no case: when was the last one?

[5] WILLINGNESS TO PAY (no price named by founder: confirm ☐)
- How they buy tools today:
- Current spend (tools / hours):
- Their band (verbatim):            - Budget owner (named):

[6] WRAP
- Referrals offered (names → new prospect rows):
- Follow-up consent: Y/N
- Feature asks → PARKING_LOT rows created: __

SURPRISES (mandatory — see Step 4):
OBSERVATION vs INTERPRETATION line:
- They said/did:            - I think it means (clearly marked as mine):
```

### Never record
- **Anything after "off the record"** — stop writing, visibly.
- **Third-party case data** — the accounts/people in THEIR investigations.
  Write "a ~40-account network on X," never the handle list. Their case
  subjects are not your data (the same first-party minimalism Omi itself
  practices).
- **Recordings without explicit consent**, ever.
- **Your rebuttals or defenses** — you shouldn't have made any; if you
  slipped, log "I defended X — discount their next answer," not the defense.
- **Interpretation written as their words** — the OBS/INT line exists so your
  reading never masquerades as their statement.
- **Promises** — you don't make feature promises; a promise accidentally made
  gets logged as a mistake to correct, not a commitment to track.
- **Enthusiasm coded as commitment** — "I'd totally use this" is a quote in
  [the trust section], never a `Y` in own_case/activated.
- **Irrelevant personal detail** — politics, health, gossip, employer
  grievances beyond workflow facts.
- **Litmus:** write every note as if the prospect will read it. If a line
  would embarrass you or burn them, it doesn't belong in the system.

---

## STEP 3 — THE EVIDENCE LEDGER (live instrument)

Seeded from the Phase 6C ledger (same IDs). Append-only: evidence rows are
never deleted — contradicting evidence accumulates next to supporting, exactly
like campaign observations. Confidence moves **only** when a cited entry lands.

**Columns:** `id | assumption (short) | tier | confidence | supporting evidence (cite N-### or tracker col) | contradicting evidence (cite) | last_updated | trend (↑/↓/—)`

**Seed state (today — before any user contact):**
| id | Assumption | Tier | Conf. | Supporting | Contradicting |
|---|---|---|---|---|---|
| O1 | OSINT have the pain, recurring | 1 | 30% | none — reasoning only | none yet |
| O2 | They'll trust output vs. redo manually | 2 | 25% | none | none yet |
| O3 | OSINT cases live on X/YouTube | 1 | 30% | none | none yet |
| O4 | Reachable by cold founder | 3 | 45% | community visibility | none yet |
| O5 | OSINT is the right primary ICP | 3 | 30% | none — a bet | none yet |
| J1 | Journalists need pre-publish call | 2 | 45% | beat exists, no incumbent | none yet |
| J2 | They'd cite an automated tool | 2 | 20% | none | none yet |
| J3 | Need recurs per reporter | 3 | 30% | none | none yet |
| J4 | /rc report is the right format | 3 | 40% | editors want backup docs | none yet |
| T1 | T&S cases have public footprint | 1 | 25% | none | none yet |
| T2 | T&S can adopt external SaaS | 2 | 30% | none | none yet |
| T3 | T&S contact holds budget | 2 | 30% | none | none yet |
| T4 | Output fits casework | 3 | 40% | export exists | none yet |
| P1 | $9.99 is right price/packaging | 2 | 18% | none — number was chosen | structural doubt (pro tool, hobby price) |
| P2 | Credit metering acceptable | 3 | 25% | tracks cost | none yet |
| P3 | Individuals pay personally | 3 | 25% | none | none yet |
| P4 | Any WTP exists | 2 | 30% | none | none yet |
| AC1 | 60-second comprehension | 2 | 35% | guidance shipped (untested) | none yet |
| AC2 | Demo → own case converts | 2 | 25% | none | none yet |
| AC3 | Stranger self-serves unaided | 2 | 50% | flows pass tests | none yet |
| AC4 | Trial reaches value moment | 1 | 10% | — | **structural: 3 credits < 10/X-batch until Week-0 fix** |
| AC5 | Featured artifact triggers "run mine" | 3 | 30% | real cases, recognizable | none yet |
| AC6 | Fetch holds on real targets | 2 | 30% | fixtures + refund reaper | none yet |
| TR1 | Counter-evidence builds trust | 1 | 30% | design thesis | none yet |
| TR2 | Detection holds on real data | 1 | 25% | FPR 0.000 on OWN controls only | none yet |
| TR3 | Experts will cede judgment | 1 | 25% | none | structural doubt (show-your-work culture) |
| TR4 | Users want evidence over verdicts | 3 | 40% | aligns with rigor norms | none yet |
| SH1 | Users mint shares | 3 | 30% | infra exists | none yet |
| SH2 | Shares get read | 2 | 30% | tracking exists | none yet |
| SH3 | Sharing acquires users | 3 | 20% | none | none yet |
| SH4 | Sharing accusations feels safe | 3 | 30% | disclosure framing | none yet |
| RE1 | Problem recurs → 2nd case | 2 | 30% | reasoning | none yet |
| RE2 | Value compounds with use | 3 | 25% | memory/recurrence built | none yet |
| RE3 | Becomes workflow not curiosity | 3 | 20% | none | none yet |
| RE4 | Retention survives per-scan cost | 3 | 30% | none | none yet |

**Update protocol**
1. Evidence enters ONLY from call notes (`N-###`) or tracker behaviors
   (column refs). No citation → no entry → no confidence change.
2. One call may move several rows; one row needs ≥2 independent sources
   before confidence moves more than ±10 points.
3. Contradicting evidence is never argued with in the ledger — it lands
   verbatim. Rebuttals don't exist here.
4. Friday: re-read every touched row, set trend arrows, update Tab 5.
5. A row crossing its 6C falsification line is **locked + flagged** to the
   gate — not edited, not rationalized.

---

## STEP 4 — THE CALL-ANALYSIS FRAMEWORK

Within 60 minutes of every call, 10 minutes by timer, BEFORE reading anything
else. Four boxes, appended to the call note:

**Box 1 — WHAT HAPPENED (facts only, ≤5 lines)**
Stage outcomes only: cold read result · own case Y/N · scan run Y/N + outcome
· WTP given Y/N · referrals. No adjectives. (If you can't fill this in 5
lines, the call lacked structure — note that too.)

**Box 2 — WHAT SURPRISED ME (mandatory, the highest-value box)**
What did they say/do that you did NOT predict? Surprise = information; it's
the only thing in the call that wasn't already in your head.
*Discipline rule:* three consecutive calls with "nothing surprised me" means
you are pitching, not listening — re-read the script before the next call.

**Box 3 — WHAT ASSUMPTIONS CHANGED (ledger discipline)**
`ledger-id → direction (↑/↓) → the verbatim/behavior that moved it → new conf.`
Rules: no entry without a citation · politeness moves nothing · a behavior
(own case, return, share) outweighs any quote · check explicitly: did they
demonstrate a false positive? If yes and it's the SECOND independent one →
F4: pause recruiting per the 6B exception.

**Box 4 — WHAT ACTION FOLLOWS (one owner: you; one due date each)**
Allowed actions: follow-up/booking · message or artifact change for the next
wave · targeting change · ops/config fix (Week-0 class) · bench refill ·
parking-lot entry. NOT allowed from a call: feature work, roadmap entries,
threshold changes. If the honest action is "nothing" — write "no action,"
which is a real decision, not a gap.

---

## STEP 5 — THE FOUNDER DECISION FRAMEWORK (graduated)

Four verbs, defined once:
- **CONTINUE** — keep executing the plan as-is.
- **REPOSITION** — change the *message*: wording, artifact choice, channel,
  framing, price-conversation order. Cheap, reversible, founder-level.
- **PIVOT** — change the *target*: ICP emphasis, segment, persona. (At the
  gate, a product-shape pivot exits to a CEO proposal — never a build inside
  Phase 6.)
- **STOP** — end the campaign (or the idea) under the 6B-D guards.

### At n = 5 (end of wave 1) — a PROCESS checkpoint, not a thesis checkpoint
Five conversations can tell you whether the *machine* works (do messages get
opened? do calls book? does the funnel survive contact?). They cannot tell
you anything about demand, trust, or WTP — any thesis conclusion at n=5 is
noise.
- **CONTINUE** (default): ≥1 reply or ≥2 report-opens — the machine functions.
- **REPOSITION**: 0–1 opens or 0 replies → change subject line/artifact/
  channel for wave 2; if a funnel break surfaced (signup, credits, email) →
  ops fix immediately.
- **PIVOT**: forbidden. **STOP**: forbidden — sole exception **F4** (2
  independent expert-demonstrated false positives already) → pause
  recruiting; trust-defect protocol.

### At n = 10 (waves 1–2 + first calls) — a DIRECTION checkpoint
- **CONTINUE**: ≥1 own case brought, OR ≥2 strong engagements (call done +
  clean cold read + a named case coming). On track for the gate.
- **REPOSITION**: opens healthy but calls don't convert to cases → the
  message promises the wrong thing; one artifact clearly outperforming →
  standardize on it; comprehension stalling at the same section in ≥3 cold
  reads → scripted explanation added to calls (copy itself stays frozen
  unless F-level).
- **PIVOT (within-campaign reallocation only)**: one segment holds ~all
  Signal-Score mass and another is dead after 2 full waves → reweight the
  remaining waves toward the live segment. Record it in WEEKLY. (Full ICP
  redefinition still waits for the gate.)
- **STOP**: still forbidden except F4. Special rule: **zero own cases at
  n=10 with otherwise good engagement → audit the LIST before the thesis**
  (are these actually hands-on practitioners? platform-fit real?). Demand
  verdicts wait for 25; sourcing-quality verdicts don't.

### At n = 25 (or week-4 timeout) — THE GATE (6B, verbatim thresholds)
- **CONTINUE**: S1 ≥5 own cases AND S3 ≥3 would-cite AND no unresolved F4,
  plus one of S5 ≥5 returning / S6 ≥3 WTP-with-budget → concentrate on the
  winning segment, pricing test, second cohort.
- **PIVOT (ICP)**: S1 = 2–4 with ≥70% signal mass in one segment (or an
  uninvited persona that kept appearing), or two segments dead while one
  replies >25% with ≥2 cases → rebuild the 25 in the winning segment, rerun.
- **REPOSITION (product-shape proposal)**: pain confirmed first-hand in ≥15
  conversations + engagement healthy + S1 <2 + the parking lot's `job_count`
  shows the SAME job ≥8 → write the pivot brief and take it to the CEO gate.
  Authorizes a proposal, never construction.
- **STOP**: 25 quality conversations across ≥2 segments + S1 <2 + no segment
  concentration + no consistent parking-lot job + S3 ≤1 + S6 = 0 + the
  funnel demonstrably worked (smoke passed, replies ≥10%, reports opened).
  Demand-side falsification only — F8 guard absolute (<15 quality
  conversations = the test never ran; extend, don't conclude).
- **Ambiguity between thresholds** resolves DOWN (a second, focused cohort)
  — never UP into building. "Almost validated" authorizes more validation,
  nothing else.

---

*Operating note: this OS converts conversations into evidence the same way
Omi converts scans into intelligence — observations appended verbatim,
confidence explicit, conclusions reserved for the corroborated gate. The
instruments are ready; their value starts at the first `sent_date`.*
