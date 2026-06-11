# PHASE 6G — VALIDATION INTELLIGENCE SYSTEM

> The synthesis layer above every 6A–6F instrument. Its job: convert founder
> observations, interviews, outreach results, activation/retention metrics,
> WTP answers, and both evidence ledgers into **decision-quality intelligence**
> — without letting noise, anecdotes, emotion, or the most recent conversation
> dominate judgment.
>
> **Design spine:** this is Omi's own detection architecture applied to the
> company. The engine never lets a lone supporting detector produce a maximal
> verdict (corroboration gate, supporting ceiling 0.49); it discounts
> correlated signals so shared evidence isn't double-counted (decorrelation);
> it appends observations and recomputes rather than persisting verdicts.
> Phase 6G imposes exactly those rules on validation evidence. The company is
> scanned by the same epistemics as a comment section.

---

## STEP 1 — THE VALIDATION EVIDENCE HIERARCHY

Two classes first — the load-bearing distinction:

- **SUPPORTING evidence = words.** Opinions, quotes, enthusiasm, founder
  impressions. Cheap to produce, socially contaminated.
- **DISCRIMINATIVE evidence = behaviors.** Things done, especially **costly**
  things (time spent, reputation staked, money offered, social capital spent).

**The ceiling rule (Omi's SUPPORTING_CEILING, applied to the company):**
*no amount of supporting evidence alone can cross a decision threshold.* Words
can ceiling at "probe this with users" — never higher. Every decision verb
requires at least one discriminative item.

| Rank | Evidence type | Class | Weight | Decision authority (max it can influence) |
|---|---|---|---|---|
| 1 | Founder opinion / preference | supporting | 0 | nothing (quarantine, 6F) |
| 2 | Founder observation, bias-filtered (6F) | supporting | 0.5 | an interview probe |
| 2★ | Founder **measured** trust finding (graded FP/FN on known ground truth) | discriminative | 4 | trust-defect protocol input (F4 path) |
| 3 | Single user quote / compliment | supporting | 1 | log only |
| 4 | Repeated independent user quotes (same point, ≥3 independent sources) | supporting | 2 | interview probe; message tweak candidate |
| 5 | Single user behavior (opened report → ran **own case**) | discriminative | 3 | ledger confidence movement |
| 6 | Repeated behavior, same user (returns unprompted) | discriminative | 4 | ledger + wave reallocation input |
| 7 | Repeated behavior **across** users (≥3 independent users, same behavior) | discriminative | 5 | gate input with named weight |
| 8 | Costly behavior: share that gets **read** / public citation / referral (spends their reputation) | discriminative-costly | 6–7 | gate input, strong |
| 9 | WTP with named budget owner | discriminative-costly | 6 | gate input (S6) |
| 10 | **Actual payment** · sustained retention (weeks, unprompted) | discriminative-costly | 8 | the strongest single input any decision can have |

**The decorrelation rule (no double-counting):** evidence items sharing an
origin are ONE source — same person saying it twice, three quotes from one
conversation, or three prospects from the same Discord echoing each other
within days. *Independence = different person + ideally different recruitment
channel.* When correlated items stack, count the strongest and discount the
rest — exactly as the engine discounts `temporal`+`engagement` reading the
same cadence.

---

## STEP 2 — SIGNAL vs NOISE FRAMEWORK (exact thresholds)

| Level | Definition (exact) | What it may do |
|---|---|---|
| **NOISE** | 1 source, OR supporting-only, OR fails independence (echo/correlated), OR founder-only non-measured | logged, nothing else |
| **WEAK signal** | 2 independent supporting sources, OR 1 discriminative instance | monitor; may add one interview probe |
| **MEDIUM signal** | ≥3 independent sources with ≥1 discriminative, OR 2 independent discriminative instances | may change message/artifact/channel (reposition-level); moves a ledger row ±1 confidence step |
| **STRONG signal** | ≥3 **independent discriminative** instances, OR ≥5 independent sources incl. ≥2 discriminative | may reallocate waves within campaign; becomes a named gate input |
| **DECISIVE signal** | a **pre-registered threshold** is hit: S1≥5 · S3≥3 · S6≥3 · F1–F8 · ≥70% segment concentration with ≥2 behaviors · F4 (2 independent expert-demonstrated FPs) | the only class that may drive a decision verb — and only at its scheduled review (sole exception: F4 pauses immediately) |

Hard consequences: nothing below MEDIUM may change anything you *do*; nothing
below DECISIVE may change what you *decide*. A finding that can't state its
level is NOISE by default.

---

## STEP 3 — CONTRADICTORY EVIDENCE PROTOCOL

Contradiction is information, never annoyance. Both sides land append-only in
the ledger (the engine never deletes an observation); then apply the
tie-breaks **in this order**:

1. **Behavior beats words — including the same person's words.** "Love it" +
   never returned → the non-return is the truth; the interview becomes a
   *hypothesis about why* behavior diverged, probed next call. Never let a
   quote overrule an action.
2. **Users disagree within a segment → segment further, don't average.**
   Disagreement usually hides a variable (case type, platform, seniority,
   org size). Write the discriminating hypothesis and add one probe to the
   next calls. If no variable is found, the position backed by the higher
   evidence class wins; if classes tie, it stays OPEN (an honest unresolved
   row outranks a forced resolution).
3. **Segments disagree → that is not a contradiction, it's ICP selection
   data.** Feed O5/segment-concentration. NEVER blend segments into an
   average — the gate decides per-segment. (Averaging a hot segment with a
   dead one manufactures lukewarm nonsense.)
4. **Interview enthusiasm contradicts WTP** ("amazing!" + no number, no
   budget owner) → not a contradiction: enthusiasm is supporting, the WTP
   answer is the costlier signal. Record as "value claimed, commercial pull
   unproven." Enthusiasm may never fill the WTP blank.
5. **Founder observation contradicts users → users win, full stop** — with
   ONE carve-out: founder **measured** ground truth (a graded FP/FN) beats
   user *opinion about correctness*, because measurement beats impression.
   But it never beats user *behavior about adoption*: the output can be
   correct AND unwanted — those answer different questions (precision vs.
   demand), and both verdicts stand.
6. **Resolution mechanism when order 1–5 doesn't settle it:** design the
   smallest discriminating test (one probe question, one artifact A/B in the
   next wave), pre-register what each outcome would mean, and leave the row
   OPEN until it lands. Forbidden: resolving by founder preference, recency,
   or whoever was most articulate.

---

## STEP 4 — THE DECISION EVIDENCE LADDER

Minimum evidence per verb. A decision that cannot cite its evidence rows and
their classes is **void** — intuition is not an input, it is a hypothesis
generator for probes.

| Verb | Minimum evidence required | Timing |
|---|---|---|
| **CONTINUE** (default state) | none to keep going during the campaign; **past the gate** requires DECISIVE: S1≥5 + S3≥3 + no unresolved F4 + (S5≥5 or S6≥3) | gate |
| **REPOSITION** (message/artifact/channel — cheap, reversible) | MEDIUM signal: ≥3 independent same-point sources with ≥1 behavior, or a full-wave pattern (e.g. 0–1 opens across 5 sends; one artifact outperforming across ≥2 waves) | weekly review |
| **PIVOT — within-campaign reallocation** (reweight remaining waves) | STRONG: one segment holds ~all behavioral signal mass AND another is dead after **2 complete waves** | weekly review, n≥10 |
| **PIVOT — full ICP redefinition** | DECISIVE at gate: S1=2–4 with ≥70% signal-mass concentration (≥2 behaviors in the winning segment), or two segments dead (<10% reply) while one replies >25% with ≥2 cases | gate |
| **PIVOT — product shape (proposal only)** | DECISIVE at gate: pain confirmed first-hand in ≥15 quality conversations + engagement healthy + S1<2 + parking-lot `job_count` ≥8 on the SAME job | gate → CEO proposal, never a build |
| **STOP** | DECISIVE at gate with every guard: 25 quality conversations across ≥2 segments + S1<2 + no concentration + no consistent job + S3≤1 + S6=0 + **funnel demonstrably worked** + F8 satisfied (≥15 quality convos actually happened) | gate only |

Ambiguity between rungs resolves **DOWN** (more validation: a probe, a second
cohort) — never UP (never into building). One non-decision is also on the
ladder: **F4 trust defect** (2 independent expert-demonstrated FPs) = pause
recruiting + fix + resume; it is the only mid-campaign action above
REPOSITION, and it is not a strategy change.

---

## STEP 5 — VALIDATION DASHBOARD SPECIFICATION (decision dashboard, weekly)

Seven numbers. Each exists because it changes a specific decision; anything
that changes no decision is not on the board.

| # | Metric | Why it matters | Decision it drives |
|---|---|---|---|
| 1 | **Real cases brought (cumulative)** | the only direct demand measurement (S1) | the entire gate: <2 → stop/pivot territory; ≥5 → continue |
| 2 | **Own-scan rate among report-openers** | separates "no demand" from "broken funnel" | fix funnel vs. question thesis |
| 3 | **Trust net** = unprompted would-cites − expert-demonstrated FPs | trust is the kill-variable in an accusation product | net-negative or 2 FPs → F4 pause (the only code path) |
| 4 | **WTP-with-budget count (+ any actual payment)** | "interesting" vs. "a business" | S6 gate input; pricing test design |
| 5 | **Segment signal concentration** (% of behavioral signal mass by ICP) | tells you WHO the customer is even when totals are thin | pivot-ICP vs. stop; wave reallocation |
| 6 | **Process health: quality conversations vs. plan + reply rate per wave** | distinguishes founder-execution failure from demand failure (F2/F8) | fix recruiting vs. read results |
| 7 | **Evidence-class mix**: % of this week's ledger updates that are behavioral | a words-only week means you collected compliments, not validation | redesign next wave's calls toward behavioral closes |

**Vanity metrics — explicitly ignored:** signups · page views · social
followers/likes · demo report views *alone* (without scan conversion) ·
founder's own scan count · number of documents/plans written · parking-lot
size (it's a queue, not a score) · conversations *attempted* (only quality
conversations count) · test counts/uptime (ops, not validation) · press or
HN interest. None of these may appear in a decision memo as evidence.

---

## STEP 6 — THE ANTI-PANIC FRAMEWORK

Stabilization rules — each one mechanical, because in the moment judgment is
exactly what's compromised:

1. **The 24-hour rule.** No system change (message, targeting, threshold,
   ledger move >1 step) within 24h of any single call or event. Log same-day,
   decide at the scheduled review. *Decisions are scheduled; evidence is
   continuous.*
2. **Single-event damping.** One event moves one ledger row at most one
   confidence step, and can trigger no verb (Step 4 minimums make this
   structural). The sole exception is F4's *second* independent FP — and even
   that triggers a pre-defined protocol, not a judgment call.
3. **The rejection budget (pre-registered).** With 25 contacted, EXPECT
   ~15–20 no/silence and several rough calls. Rejections inside budget are
   the process working, not the thesis failing. One brutal interview = one
   row. Five consecutive silences = check message/venue against F2 — a
   *process* review, never a thesis review.
4. **The enthusiast rule.** One excited user changes nothing by themselves:
   enthusiasm is supporting-class (Rank 3) until they DO something costly.
   A champion is not a market; expansion (segment, positioning, roadmap)
   needs gate-level evidence like everything else.
5. **The feature-request rule.** Every request → parking lot with its
   underlying job. Requests for *different* jobs never sum. Roadmap
   consideration starts at `job_count` ≥3 (probe) and ≥8 (gate proposal).
   One request — including from your favorite user — is Rank-3 noise.
6. **The recency guard.** Reviews read the ledger **sorted by evidence
   weight, never by date**. Before proposing any change, mandatory re-read of
   the 3 strongest items that CONTRADICT it. The last conversation gets no
   privileged seat.
7. **The abandonment guard.** STOP exists only at the gate with every guard
   met (Step 4). A terrible week cannot end the campaign; only completed
   evidence can. Symmetrically: a great week cannot skip the gate either.
8. **One-way-door cooling.** Any hard-to-reverse act (public launch, public
   shutdown announcement, abandoning a segment permanently) requires: the
   monthly review + a written memo + 48 hours + one outside reader.
9. **Emotion is logged, not acted on.** The 6F emotional field exists so
   feelings have somewhere to go that isn't the steering wheel. A decision
   memo containing "I feel/I'm worried/I'm excited" as a load-bearing clause
   is void by definition.

---

## STEP 7 — THE MONTHLY VALIDATION REVIEW

One sitting (~2–3h), once per month or at the n=25 gate, whichever first.
Produces exactly one output: **CONTINUE · REPOSITION · PIVOT · STOP.**
The order of operations is the anti-bias mechanism — do not reorder it.

**0. Pre-commitment re-read (before touching any data).** Re-read the
pre-registered thresholds (6B §E/F, Step 4 ladder) and last month's memo's
"what would change this decision." Thresholds are loaded before evidence so
evidence can't quietly bend them.

**1. Evidence assembly (the pack — no pack, no review).**
S1–S6 finals · F1–F8 flags · dashboard 7 with 4-week trends · per-segment
signal table · parking-lot `job_count` table · evidence-class mix · and
**balanced verbatims: the 5 strongest positive AND the 5 strongest negative**
(forced symmetry — cherry-picking is structurally blocked).

**2. Falsification pass FIRST.** For each Tier-1 assumption (O1, O3/T1, TR1,
TR2, TR3, AC4): read the **contradicting column before the supporting one**
and write one sentence: "the strongest evidence this is FALSE is ___."
Only then read support. (Anti-confirmation ordering, mandatory.)

**3. Signal classification.** Every candidate finding gets a Step-2 level.
Findings below STRONG are noted and excluded from decision inputs. Apply
decorrelation: collapse correlated sources before counting.

**4. Ladder application.** Test each verb's Step-4 minimums against the
surviving DECISIVE/STRONG inputs. Eliminate verbs whose minimums fail. If
more than one survives, apply 6B precedence; if genuinely between rungs,
resolve DOWN (a probe or focused second cohort *is* a CONTINUE-variant, not
a new verb).

**5. Anti-panic audit.** Check the proposed verb against Step 6: is any
input a single event, a recency artifact, an enthusiast, or an emotion
clause? Strike those inputs and re-test the minimums.

**6. The decision memo (one page, binding until next review):**
```
MONTH __ DECISION: CONTINUE / REPOSITION / PIVOT / STOP
Evidence cited: [ledger rows + class + level for each]
Verbs eliminated and why (minimums failed): ...
The strongest evidence AGAINST this decision: ...
What would change this decision next month (pre-registered falsifiers): ...
Actions authorized (within the verb's scope only): ...
```
A memo missing the "strongest evidence against" line is invalid.

**7. Outside read (recommended, 15 min).** One no-stakes outsider reads the
memo with a single mandate: point at any sentence and ask "where's the
evidence for that?" Unanswerable sentences get cut, and if the decision
depended on them, the review reruns step 4.

**8. Close.** File the memo, update the WEEKLY tab's monthly line, calendar
the next review. The decision binds until then — no relitigating mid-month
except a DECISIVE signal (in practice: F4, or a pre-registered threshold
landing).

*Month 1's expected honest output is "CONTINUE — campaign in progress,
evidence accumulating"; the review's real teeth arrive with the gate. Running
it monthly from the start builds the habit before the stakes.*

---

*Closing note: 6A–6F built the instruments; 6G is the aggregator above them —
and it is deliberately the same aggregator Omi itself uses: supporting
evidence ceilinged, lone signals gated, correlated sources discounted,
observations appended not overwritten, and the verdict reserved for
corroboration at a scheduled gate. If the company holds itself to the
engine's standard of evidence, the engine's standard of evidence is probably
right for the company.*
