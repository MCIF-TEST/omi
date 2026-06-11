# PHASE 6C — ASSUMPTION LEDGER & VALIDATION FRAMEWORK

> Validation-first. No features, no platforms, no redesigns. This is the
> truth-tracking instrument for the 25-user campaign. Confidence is rated
> honestly: with **zero real users to date**, "evidence supporting" is almost
> always internal reasoning or self-graded metrics — which is NOT user evidence.
> Saying so plainly is the point of the ledger.

**Confidence scale**
- **VERIFIED (~90%+)** — proven in code / observed fact.
- **PLAUSIBLE (~45–60%)** — reasoned, indirect support, no direct user data.
- **LOW (~20–35%)** — assumption; no evidence either way.
- **LIKELY-FALSE (<20%)** — structure or evidence suggests it's probably wrong.

Cross-reference to the Phase 6 plan's A1–A10 is noted per row.

---

## STEP 1 — THE OMI ASSUMPTION LEDGER

### OSINT researchers
| ID | Assumption | Confidence | Evidence supporting | Evidence missing | Falsified by |
|---|---|---|---|---|---|
| O1 | They have the "prove a cluster is coordinated" pain often enough to want a tool (≈A1) | LOW 30% | Public threads show the manual work exists; reasoning only | Any real OSINT researcher saying "yes, recurring, I'd use a tool" | <2 of 12 describe it as a current, recurring pain |
| O2 | They'll trust a tool's output instead of insisting on their own manual, reproducible analysis | LOW 25% | None | Whether show-your-work culture rejects a score | Repeated "I'd have to redo it myself anyway" |
| O3 | Their live cases are on X/YouTube (platform fit, ≈A3) | LOW 30% | Omi scans X/YouTube; some OSINT is there | Where their *current* cases actually live | Majority name Telegram/TikTok/cross-platform |
| O4 | They're reachable by a cold founder (not too senior/flooded) | PLAUSIBLE 45% | Mid-career analysts are active on Bluesky/X | Actual reply rate | <10% reply incl. warm paths (F2) |
| O5 | OSINT is the correct PRIMARY ICP (sharpest fit) | LOW 30% | Differentiator maps to their job; reasoning | Comparative pull vs. journalists/T&S | Another segment out-pulls OSINT on Signal Score |

### Journalists
| ID | Assumption | Confidence | Evidence supporting | Evidence missing | Falsified by |
|---|---|---|---|---|---|
| J1 | They need a defensible coordination call before publishing and lack tooling | PLAUSIBLE 45% | Real beat exists; no obvious incumbent tool | Whether they feel the gap acutely | "We just ask an academic / we don't run those stories" |
| J2 | They'd cite or rely on an automated tool's output in published work | LOW 20% | None | Editorial/sourcing norms on black-box tools | "My editor would never let me cite a startup's score" |
| J3 | The need recurs often enough to matter (not one story a year) | LOW 30% | Influence-op coverage is growing | Per-reporter frequency | Most treat it as rare/one-off |
| J4 | A shareable `/rc` report is the right format for them (≈A10) | PLAUSIBLE 40% | Editors want backup docs | Whether they want the verdict or the raw data | "I need the underlying data, not your conclusion" |

### Trust & Safety teams
| ID | Assumption | Confidence | Evidence supporting | Evidence missing | Falsified by |
|---|---|---|---|---|---|
| T1 | Their coordination problems have a PUBLIC X/YouTube footprint Omi can scan | LOW 25% | Some abuse is public | How much casework is private internal logs | "Our cases are in our own logs you can't see" |
| T2 | They can adopt an external SaaS tool (security/egress allows it) | LOW 30% | Small platforms use SaaS | Their infosec/data-egress constraints | "We can't send anything to an outside tool" |
| T3 | They hold budget and can buy without 9-month procurement | LOW 30% | Mid-size orgs buy tools | Real buying authority of the contact | Every interested lead stalls in procurement |
| T4 | Omi's evidence output fits casework/appeals workflows | PLAUSIBLE 40% | Markdown/JSON export exists | Whether it drops into their tooling | "Doesn't fit how we document cases" |

### Pricing
| ID | Assumption | Confidence | Evidence supporting | Evidence missing | Falsified by |
|---|---|---|---|---|---|
| P1 | $9.99/mo is appropriately priced/packaged for ≥1 ICP (≈A9) | LIKELY-FALSE 18% | A number was chosen | Any WTP data | WTP answers cluster far above or below; "that price makes it look like a toy" |
| P2 | Per-scan credits (X batch = 10) is an acceptable model | LOW 25% | Tracks API cost | Whether users accept metered pricing | "I can't predict my cost / I want unlimited or a seat" |
| P3 | Individuals will pay personally (not only orgs) | LOW 25% | None | Whether the passion ICP has any budget | OSINT/freelancers: "I only use free tools" |
| P4 | There is willingness to pay at all (commercial pull exists, ≈A9) | LOW 30% | None | One concrete number with a budget owner | Zero concrete WTP across 25 (F7) |

### Activation
| ID | Assumption | Confidence | Evidence supporting | Evidence missing | Falsified by |
|---|---|---|---|---|---|
| AC1 | A cold expert understands the report in ~60s (≈A6) | LOW 35% | Phase 5 added guidance (untested on humans) | Any real cold-read | ≥50% stall/misread (F3) |
| AC2 | Demo-impressed converts to "I'll run my own case" (≈A8) | LOW 25% | None | The view→own-scan conversion | High views, near-zero own scans |
| AC3 | A stranger can self-serve signup→scan→report unaided (≈A2) | PLAUSIBLE 50% | Flows exist and pass tests | Any non-founder completing it | A smoke-test outsider needs help |
| AC4 | The trial allowance lets them reach the value moment | **LIKELY-FALSE 10%** | — | — | **Already structurally false: 3 trial credits < 10 for an X batch. True only after the Week-0 env fix.** |
| AC5 | The featured X state-actor artifact is relevant enough to trigger "run mine" | LOW 30% | They're real, recognizable cases | Whether it maps to their domain | "Interesting, but unrelated to my work" |
| AC6 | Fetching holds up on real targets, not just fixtures (≈A7) | LOW 30% | Engine works on fixtures; reaper/refund exists | Real-target completion rate; twitterapi.io reliability | >40% of real scans end scan_incomplete (F5) |

### Trust
| ID | Assumption | Confidence | Evidence supporting | Evidence missing | Falsified by |
|---|---|---|---|---|---|
| TR1 | Counter-evidence framing BUILDS trust (not reads as hedging) (≈A5) | LOW 30% | Design principle; coherent thesis | Any expert reaction | Experts call it "wishy-washy"/skip the against-section |
| TR2 | Detection quality holds on real adversarial data (≈A4) | LOW 25% | FPR 0.000 **on our own curated controls only**; corroboration gate | Behavior on messy real cases | ≥2 experts demonstrate false positives on their own cases (F4) |
| TR3 | Experts will stake their reputation on a tool they didn't build | LOW 25% | None | Whether they'll cede judgment for a public accusation | "I'd never put my name on someone else's score" |
| TR4 | "Evidence, not verdicts" is what users want (vs. a confident yes/no) | PLAUSIBLE 40% | Aligns with researcher rigor | Whether they actually prefer it | Users demand a definitive call and dismiss nuance |

### Sharing
| ID | Assumption | Confidence | Evidence supporting | Evidence missing | Falsified by |
|---|---|---|---|---|---|
| SH1 | Users will mint and share reports (≈A10) | LOW 30% | Share + public-report infra exists | Any real mint by a non-founder | Nobody mints across 25 |
| SH2 | Shared reports get READ by recipients (not just minted) | LOW 30% | Deduped view tracking exists | Minted→viewed conversion | Views ≈ sender only |
| SH3 | Sharing drives new-user acquisition (a viral loop) | LOW 20% | None | Whether a viewer becomes a user | Reads happen, signups don't follow |
| SH4 | Publicly naming accounts "coordinated" is reputationally safe enough to share | LOW 30% | Disclosure-archive framing is defensible | Legal/ethical hesitation in practice | "I'd never share something accusing named accounts" |

### Retention
| ID | Assumption | Confidence | Evidence supporting | Evidence missing | Falsified by |
|---|---|---|---|---|---|
| RE1 | The problem recurs, so users come back for a 2nd case | LOW 30% | Reasoning about the beat | Any real 2nd-scan | <5 run a 2nd scan in wk2 (weak S5) |
| RE2 | Value compounds (memory/recurrence creates lock-in) | LOW 25% | Memory + recurrence are built | Whether users run enough to feel it | Users never reach multi-scan depth |
| RE3 | Omi becomes part of their workflow vs. a one-time curiosity | LOW 20% | None | Habitual/repeat usage | One scan, then silence |
| RE4 | Retention isn't killed by per-scan cost/quota friction | LOW 30% | — | Whether cost deters re-use | "Stopped because each run costs me" |

---

## STEP 2 — RANK BY EXISTENTIAL RISK

### Tier 1 — EXISTENTIAL (false ⇒ no company)
- **O1 / demand core (A1)** — if target users don't have the pain acutely, nothing else matters.
- **TR2 — detection holds on real data (A4)** — in a category that publicly *accuses* accounts, a demonstrated false positive doesn't just disappoint, it does reputational harm. Wrong is worse than useless here.
- **TR3 + TR1 — experts will trust/cede to the tool, and the counter-evidence framing earns that trust** — the entire value proposition. Demand without trust = admiration without adoption.
- **O3 / T1 — platform fit** — if real cases aren't on X/YouTube, the product can't even be *tried*, so every other signal reads as a false negative.
- **AC4 — trial reaches the value moment** — currently structurally false (3<10). Existential *for the test itself*: an unfixed funnel makes the whole campaign measure nothing. (Fixable in Week 0 with one env var — existential only if ignored.)

### Tier 2 — SERIOUS (false ⇒ major pivot, not instant death)
- P4 / P1 — willingness to pay exists, at a workable price/packaging.
- AC1 / AC2 / AC3 — comprehension, demo→own-case conversion, self-serve funnel.
- AC6 — fetch reliability on real targets.
- J2 / T2 / T3 — journalists will cite; T&S can adopt and buy.
- RE1 — the problem recurs.
- SH2 — shares actually get read.

### Tier 3 — OPTIMIZATION (false ⇒ tune, don't pivot)
- O5 — which ICP is primary (this is *what the campaign discovers*, not a bet to defend).
- SH3 / SH1 / SH4 — viral loop, mint rate, share comfort.
- RE2 / RE3 / RE4 — compounding, habit, cost-friction on retention.
- AC5 / P2 / P3 / J3 / J4 / O2 / O4 / T4 / TR4 — packaging and segment-shape details that refine the offer once Tier 1 clears.

---

## STEP 3 — THE VALIDATION SCOREBOARD

Per assumption: the event that **proves** (strong support), **weakens** (partial negative), **falsifies** (kill it). Scored from tracker behaviors + `/v1/admin/learning`, never from compliments.

| ID | PROVES (↑↑) | WEAKENS (↓) | FALSIFIES (✗) |
|---|---|---|---|
| O1 | ≥5 OSINT bring a real case | Interest but no case offered | <2 of 12 call it a current pain |
| O2 | Runs Omi's output into real work | "Useful as a second opinion only" | "I'd redo it manually regardless" |
| O3 | Their case is X/YouTube | Case is mixed-platform | Case is Telegram/TikTok-only |
| O4 | >25% OSINT reply | 10–25% reply | <10% reply incl. warm |
| O5 | OSINT holds top Signal-Score mass | Tied with another segment | Another segment clearly out-pulls |
| J1 | "Yes, before publishing, recurring" | "Occasionally" | "We don't run those stories" |
| J2 | Cites/relies on it in a piece | Uses as a lead, not a source | "Editor would never allow it" |
| J3 | Multiple cases on their beat | One a quarter | One a year or less |
| J4 | Shares the `/rc` report onward | Wants it but reformatted | "Need raw data, not a verdict" |
| T1 | Brings a public-footprint case | Partial public signal | "All our cases are private logs" |
| T2 | Opens/uses it on real data | Interested, infosec-blocked pending | "Can't use external tools at all" |
| T3 | Names budget + path to buy | "Would need approval" | Procurement dead-ends every time |
| T4 | Exports into casework | Manual copy needed | "Doesn't fit our documentation" |
| P1 | WTP near/above $9.99 with budget | WTP exists but vague | "Price makes it look like a toy" / orders of magnitude off |
| P2 | Accepts credit model | Wants different metering | "Won't adopt metered pricing" |
| P3 | An individual pays personally | "My org might" | "Only if it's free for me" |
| P4 | ≥3 concrete WTP + budget owner | 1–2 soft numbers | Zero concrete across 25 (F7) |
| AC1 | ≥70% correct cold read in 60s | 50–70% partial | ≥50% stall/misread (F3) |
| AC2 | ≥40% of openers run own scan | 20–40% | High views, near-zero scans |
| AC3 | Outsider completes unaided | Minor hand-holding | Needs founder to get through |
| AC4 | Trial reaches value post-fix | — | Wall still blocks an X batch |
| AC5 | Artifact prompts "run mine" | Mild interest | "Unrelated to my work" |
| AC6 | <20% scans incomplete | 20–40% | >40% incomplete (F5) |
| TR1 | Unprompted "the against-section makes me trust it" | Neutral on it | "Reads as hedging" / skips it |
| TR2 | ≥1 confirmed true finding, no FP | Minor disputed edge case | ≥2 experts show FPs on own cases (F4) |
| TR3 | Would put their name on it | "As support only" | "Never cede that judgment" |
| TR4 | Prefers evidence to a yes/no | Wants both | Demands a verdict, dismisses nuance |
| SH1 | Mints a share unprompted | Mints only when asked | Never mints |
| SH2 | Shared link read by others | Read by 1 | Views ≈ sender only |
| SH3 | A viewer signs up | Viewer engages, no signup | Reads, zero downstream |
| SH4 | Shares publicly without hesitation | Shares privately only | "Won't share named accusations" |
| RE1 | ≥5 run a 2nd case unprompted | A few nudged returns | One scan then silence |
| RE2 | Runs many, cites compounding value | Runs a handful | Never reaches depth |
| RE3 | Returns weekly without nudge | Returns when prompted | No repeat usage |
| RE4 | Re-runs despite cost | Slows on cost | "Stopped — too costly per run" |

---

## STEP 4 — THE FOUNDER REALITY DASHBOARD (only 5 things, every Friday)

If you read nothing else, read these five. Each is a behavior, not a vanity
metric; each drives a specific decision at the gate.

1. **Real cases brought — cumulative.** *(O1/A1 — the one number.)*
   *Why:* the only direct test of demand; everything else is leading
   indicators of it. *Drives:* the entire gate — <2 trends toward Shut-down/
   Pivot, ≥5 toward Continue.

2. **Own-case scan rate among report-openers.** *(AC2/S2.)*
   *Why:* separates "cool demo" from real pull and isolates whether a low #1
   is a *demand* failure (they don't care) or a *funnel* failure (they
   couldn't). *Drives:* fix the funnel vs. question the thesis.

3. **Trust ledger this week: # unprompted "would-cite" MINUS # expert-shown
   false positives.** *(TR1/TR2/TR3 — A4/A5.)*
   *Why:* trust is the make-or-break in an accusation product; one
   demonstrated FP can outweigh several would-cites. *Drives:* a net-negative
   or any F4 pauses recruiting and is the ONLY thing that re-opens code.

4. **Concrete WTP answers with a named budget owner — count.** *(P4/S6.)*
   *Why:* distinguishes "interesting" from "a business"; the budget *owner*
   matters as much as the number (reachable payer?). *Drives:* business-model
   viability; informs Continue's pricing test vs. a commercial pivot.

5. **Segment concentration of Signal Score (which ICP is pulling).** *(O5.)*
   *Why:* tells you *who* the customer is even when the aggregate is thin —
   the difference between Shut-down and Pivot-ICP. *Drives:* B) Pivot-ICP, and
   which segment a second cohort is drawn from.

Everything else (signups, views, uptime, social) is explicitly off this board.

---

## STEP 5 — THE SINGLE MOST DANGEROUS ASSUMPTION

**Not protecting feelings. Evidence from every phase.**

The most dangerous assumption is **not** any single row above. It is the
meta-assumption the founder's *behavior across all phases* reveals:

> **"The path to traction runs through the product — if I build it well enough
> and prepare thoroughly enough, validation will follow."**

The ledger's deadliest *product* row is **TR3 — that professional skeptics
(OSINT researchers, journalists) will cede judgment on a public accusation to
a tool they didn't build.** There is a strong structural reason it may be
false: these users' entire credibility rests on doing and showing the analysis
*themselves*; a verdict-producing tool — however well-hedged — may be admired
and never adopted. That is the most dangerous assumption *inside the product*.

But the most dangerous assumption *the founder holds* is bigger and it is the
reason TR3 is still at 25% confidence this late:

**Across Phases 0–5 the response to uncertainty was to build** — 24 API
modules, ~32 pages, billing, referrals, watchlists, a monitoring scheduler,
bulk scans, a graph, narratives, an ML track, an LLM layer. **Across Phases 6,
6A, 6B, 6C the response to uncertainty has been to plan** — a master plan, a
founder plan, an operating manual, a campaign kit, and now this ledger. Five
polished planning artifacts. **Real users contacted: zero. Real cases brought:
zero. Times Omi has been told "no" by a target user: zero.**

A startup that has never been rejected has never been tested. Every metric the
founder is proud of is self-graded on curated data. The one concrete blocker
that would stop a real user cold — the 3-credits-vs-10-for-an-X-batch wall —
has now been documented in three consecutive phases and, as far as the repo
shows, **still isn't fixed, because no one is in production to hit it.**

The danger is precise: **planning feels like progress and is being used to
avoid the one act that can falsify the thesis** — putting the product in front
of a stranger who can say no. Building was the comfort zone in Phases 0–5;
planning is the comfort zone in Phase 6. The frameworks are genuinely good —
which is exactly what makes them seductive. They will all be worth nothing on
the Friday a real OSINT researcher reads a report and says "interesting, but I'd
redo it myself."

I am complicit in this: each phase I have produced another excellent document,
because it is easy to consume and feels like momentum. So the ruthless thing to
say is that **no further framework from me changes the answer.** This ledger is
the last preparation artifact that should be written before contact. The single
highest-value action available to Omi right now is not in this file — it is to
complete the Week-0 checklist (starting with the credit-wall env fix) and send
**wave one**. Until a stranger has been given the chance to reject Omi, the
company has learned nothing — and the most dangerous belief is that it has.
