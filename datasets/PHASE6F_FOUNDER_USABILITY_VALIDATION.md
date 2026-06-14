# PHASE 6F — FOUNDER USABILITY VALIDATION SYSTEM

> Converts the founder's personal use of Omi into evidence — while preventing
> that evidence from becoming product direction on its own. Operational only:
> no features, no UI proposals, no roadmap. Built on Omi's own trust
> architecture: **evidence, not verdicts**; a single signal can't drive a
> maximal verdict; confidence is explicit; conclusions wait for corroboration.

## The premise this system is built to resist

The founder is, for usability purposes, the **worst possible test subject** and
the **best possible one** at the same time — and the two cancel unless kept
strictly apart:

- **High authority** only where the observation is *measurable against ground
  truth*: detection quality on cases where the founder already knows the answer
  (false positives/negatives), and structural blockers that are objectively
  true, not perceptual (e.g. the trial-credit wall). These map to Omi's
  precision discipline — measure FPR on known controls.
- **Near-zero authority** everywhere the observation depends on being a *naive
  user*: comprehension, activation, "is this confusing," first-run friction.
  Familiarity makes the founder blind to exactly what stops a newcomer.

So the governing law of 6F: **founder-observation value is inversely
proportional to how much the observation depends on not already knowing Omi.**
And the hard guard, carried from Phase 6C's most-dangerous-assumption finding:
**dogfooding cannot reopen code during the validation window.** The only thing
that does is the 25-user F4 trust defect. Heavy self-use feels like progress
and emits an endless stream of "improvements"; this system exists to absorb that
stream, not act on it.

**The four sanctioned uses of founder dogfooding (everything else is bias to
quarantine):** (1) generate real `/rc` artifacts to send prospects; (2) catch
detection errors on known-ground-truth cases; (3) confirm structural funnel
blockers; (4) build fluency to run live demos in calls.

---

## STEP 1 — THE FOUNDER USAGE REPORT (per session)

Filed after every working session. Capture **observation separately from
interpretation**, and **expectation before outcome** — the gap between them is
the unit of evidence (an "expectation violation"), not the feeling about it.

```
FUR-____   Date ____   Session length __min
Real case? Y/N   Ground truth known? Y/N (decides if trust obs are gradeable)
Artifact produced? /rc or /r link (for outreach reuse) ____

TASK ATTEMPTED (one concrete job, in JTBD terms):
EXPECTATION (write BEFORE acting — what I expected to happen/see):
ACTUAL OUTCOME (facts: completed? time-to-result? result state?):
EXPECTATION VIOLATIONS (where actual ≠ expected, each as OBS):

FRICTION POINTS (each):
- OBS (what happened, factual):
- Did it BLOCK / SLOW / neither:
- NAIVE-USER CHECK (mandatory): did I rely on prior product knowledge to get
  through (or to not notice)?  Y/N
- Did I value/notice this only because I'm a domain expert?  Y/N

TRUST REACTIONS (only gradeable if ground truth known):
- The output vs. what I know to be true:
- Any false positive / false negative (exactly what + the known truth):
- Reaction to the evidence-against section:

EMOTIONAL REACTIONS (quarantined by default — see Step 2):
- Powerful / awkward / delighted / irritated — verbatim, no fix proposed:

SURPRISES (mandatory): what did Omi do that I did NOT predict?

OBS vs INT line for the session:
- Happened: ___      I think it means (clearly mine, not fact): ___
```

Rule: a Usage Report **never** contains a proposed fix, UI idea, or "I should
build X." Those are interpretation; if one appears, it is logged as a
preference (Step 2), not an action.

---

## STEP 2 — EVIDENCE CLASSIFICATION SYSTEM

Every observation is sorted into exactly one category. Each carries a fixed
**founder authority** that the founder cannot raise by feeling strongly.

| Category | What it is | Founder authority | Qualifies | Disqualifies | Min bar to leave MONITOR |
|---|---|---|---|---|---|
| **Usability** | Friction completing a task (controls, errors, nav) | **LOW** (familiarity bias) | A genuine **blocker** the fluent founder still couldn't reason past | "Annoying"/"I'd prefer" with task completed | ≥1 real user hits the same thing |
| **Workflow** | Whether the *sequence* matches how the job is actually done | **MED-HIGH on domain shape**, LOW on learnability | A JTBD-shape gap (a step the investigator workflow needs and the flow omits/forces) | Button placement, ordering taste | Domain logic + ≥1 user confirming the missing step |
| **Trust** | Does the output earn belief; FP/FN; evidence-against quality | **HIGH — only on known ground truth** | A graded error on a case whose truth the founder knows | Any trust claim on an unknown-truth case | Reproduced on a known case (fast-track; see Step 5) |
| **Activation** | The path to first value / magic moment | **NEAR-ZERO** (can't un-know the product) | A **structural** funnel blocker (objective, not perceptual) | Any perceptual "a new user would get this" | User cold-read evidence — founder cannot self-supply |
| **Retention** | Do I come back; does value compound | **LOW + contaminated** (returns for builder/validator reasons) | Only the **negative**: "I avoided Omi and used X for a real task" | "I keep using it" (invalid — not a user's reason) | A real user's return behavior, never the founder's |
| **Founder-preference-only** | Taste, polish, "I'd have designed it differently" | **ZERO for product decisions** | — | — | Independent user demand (then it re-files as a real category) |

Strict rules:
1. **Trust on unknown-truth cases is uncategorizable — discard it.** Without
   ground truth the founder's "this looks wrong/right" is opinion.
2. **Activation and comprehension observations from the founder are presumed
   invalid** and may only ever reach VALIDATE-WITH-USERS, never ROADMAP, on
   founder evidence alone.
3. **A usability blocker that stops even the fluent founder is high-signal**
   (it cleared the familiarity bar) — but a usability *annoyance* is the
   noisiest data in the system and defaults to preference.
4. When in doubt between a real category and preference, **file as
   preference.** False-quarantining a real issue costs a delay; false-promoting
   a preference corrupts product direction. Asymmetric — fail toward quarantine.

---

## STEP 3 — FOUNDER BIAS FILTERS

Run every observation through this sequence **before** it enters the ledger as
anything but raw. The questions are diagnostic and ordered; the first "yes"
routes it.

1. **Impact gate.** Did it block the task, change the outcome, or change trust?
   **No → Founder-preference / Perfectionism. Stop.**
2. **Perfectionism filter.** Is it about polish/consistency with no task or
   trust impact? **Yes → quarantine (ignore).** (Test: would the outcome or the
   user's belief differ if it were "fixed"? If no — perfectionism.)
3. **Expertise-bias filter.** Does *valuing* this require domain expertise the
   target user (per the 6B ICP profiles) lacks? **Yes → expertise-bias
   quarantine** until ≥N independent users ask for it. (Test: "I need the raw
   correlation matrix" — a median OSINT prospect wouldn't ask → quarantine.)
4. **Familiarity-bias filter (catches false *negatives*).** Did I use prior
   product knowledge to get through this step — or to *not notice* a problem?
   **Yes → the founder verdict is VOID; flag for user comprehension testing
   regardless of founder comfort.** (This is why "it's clear to me" can never
   close a comprehension question. Inverse positive: if even the fluent founder
   tripped, mark severity up — it's probably severe for newcomers.)
5. **Frequency filter.** Did it reproduce across ≥3 sessions, or is it a single
   event? **One-off + non-blocking → MONITOR only, never act.** (Frequency is
   recorded as a ratio — sessions-seen / sessions-attempted — so a founder who
   runs the same path 40 times can't inflate it.)
6. **Survivor = candidate real problem.** Blocked/slowed a task **and** is
   plausibly worse for a naive user **and** reproduced → eligible for the
   escalation framework (Step 5). Even here, founder evidence alone caps at
   VALIDATE-WITH-USERS.

Bias-flag tags recorded on every observation: `{expertise | familiarity |
perfectionism | one-off | none}`. An observation may carry several.

---

## STEP 4 — THE FOUNDER OBSERVATION LEDGER

Append-only, mirroring Omi's campaign-observation model: new evidence appends,
aggregates recompute, **a prior reading is never fed back as truth.** One row
per distinct observation; sessions add evidence to existing rows rather than
spawning duplicates.

**Columns:**
`obs_id (FO-001…) | date_first | category (Step 2) | description (OBS, factual) |
severity (blocker / major / minor / cosmetic) | frequency (seen/attempted ratio) |
founder_authority (fixed by category: high/med/low/zero) | bias_flags (Step 3) |
supporting_evidence (FUR-### sessions + any user N-### corroboration) |
contradicting_evidence (sessions it didn't occur; users who didn't hit it) |
confidence (Low/Med/High) | status (Step 5) | last_updated`

**Confidence rule (precision discipline applied to the founder):**
`confidence = founder_authority(category) × frequency_ratio × user_corroboration`.
- **Zero user corroboration caps confidence at LOW** for every category except
  *trust-on-known-ground-truth* and *structural-blocker*, no matter how strongly
  the founder rates severity. One signal cannot drive a maximal verdict — the
  same gate Omi puts on a lone detector, now on a lone founder.
- Contradicting evidence (a session where it didn't happen, a user who sailed
  past it) lands verbatim beside the supporting; it is never argued away.
- A trust observation that reproduces on a second independent known-truth case
  is the only founder-only path to HIGH confidence — because it is *measured*,
  not felt.

---

## STEP 5 — SIGNAL ESCALATION FRAMEWORK

Four states, with evidence thresholds. **Founder opinion alone never reaches
ROADMAP.** Transitions are earned by evidence, not by re-reading the same
observation more intensely.

| State | Meaning | Entry threshold | May consume |
|---|---|---|---|
| **IGNORE** | Logged for the record, no action | Preference-only · perfectionism (no task/trust impact) · one-off non-blocking · expertise-bias with 0 users | nothing |
| **MONITOR** | Plausibly real, unconfirmed | Survived bias filters but founder-only, frequency <3, no user mention | nothing (watch only) |
| **VALIDATE-WITH-USERS** | Worth a deliberate user probe | **Any of:** (a) trust/detection error reproduced on a **known-ground-truth** case; (b) blocker/major with frequency ratio ≥ "≥3 sessions or ≥50% of attempts"; (c) ≥1 *spontaneous* user mention already | a line in the interview script / a watch-item in cold reads |
| **ROADMAP-CANDIDATE** | Eligible to be *proposed at the n=25 gate* | **Real-user corroboration at gate strength:** ≥3 independent target users hit the same issue (parking-lot `job_count` ≥3), **OR** a confirmed **F4** trust defect (≥2 independent expert-demonstrated false positives) | a proposal at the gate — **not a build** |

Hard guards:
1. **0 user corroboration → cannot be ROADMAP-CANDIDATE, ever**, regardless of
   founder severity — with one carve-out: a **structural funnel blocker** that
   is objectively true (e.g. trial credits < an X-batch) is an **ops fix in the
   Week-0 class**, handled as configuration, never as a roadmap feature.
2. **ROADMAP-CANDIDATE ≠ build.** During the validation window it means
   "carried to the gate as a proposal." The only mid-window code path remains
   the F4 trust-defect protocol (pause / fix / resume).
3. **The founder's vote is worth at most one unit** in any roadmap case and can
   never be the majority of the evidence. A roadmap case that is mostly founder
   observation is, by definition, not ready.
4. Escalation is reversible: an observation that fails to recur or that users
   sail past is **demoted** (Med→Low, Validate→Monitor) on the same evidence
   rules. Demotion is as routine as promotion.

---

## STEP 6 — THE WEEKLY FOUNDER REVIEW RITUAL

Folded into the existing Friday review (6A/6C/6E) so there is **one** ritual,
not two. Time-boxed; it produces evidence, never decisions — decisions live at
the gate.

1. **Gather** the week's Founder Usage Reports (FUR-###).
2. **Filter** each raw observation through Step 3 → assign category + bias flags.
   (Most should route to preference/ignore — that is a *healthy* week.)
3. **Fold into the ledger:** update existing FO rows' frequency ratios and
   append supporting/contradicting from this week's sessions; create new rows
   only for genuinely new observations. Never duplicate; never overwrite history.
4. **Cross-reference against the USER evidence ledger (6E)** — the single most
   important step. For each escalated founder observation: did a real user this
   week corroborate or contradict it? Update `user_corroboration` and recompute
   confidence. This cross-check is the mechanism that stops founder bias from
   becoming direction.
5. **Re-run escalation states** (Step 5): promote only where the threshold is
   met by *evidence*; demote anything that didn't recur or that users bypassed.
6. **Bias-health audit (mandatory metric):**
   - % of this week's observations resting in preference/ignore (healthy: the
     majority).
   - **Founder-originated ROADMAP-CANDIDATEs with zero user corroboration —
     must be exactly 0.** Any non-zero is a bias alarm: the founder is steering
     by opinion; freeze and re-read this document.
   - Count of code changes made from founder usage this window — **must be 0**
     unless an F4 fired. Non-zero without F4 = the 6C failure mode is live.
7. **One-line state** into the WEEKLY tab: "Founder usage this week produced
   __ artifacts, __ measured trust findings, __ user-corroborated signals, and
   __ quarantined preferences."

Brutal honesty, stated once and kept visible: this entire apparatus exists
because *using Omi heavily is the most comfortable way to avoid the scary work
of putting it in front of strangers.* The system makes dogfooding **safe** —
it harvests the two things founder use legitimately produces (outreach artifacts
and measured detection findings) and quarantines everything else. If, at the
gate, the founder observation ledger has driven product direction more than the
25 real users have, 6F has failed at its only job — and the most dangerous
assumption from Phase 6C will have won.

---

*Operating note: the founder is now subject to the same evidentiary standard
Omi imposes on its own detectors — observe, append, surface confidence and
counter-evidence, and reserve the verdict for corroboration. Founder experience
becomes one more evidence stream, never a privileged one.*
