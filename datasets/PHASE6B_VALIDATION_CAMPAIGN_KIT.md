# PHASE 6B — VALIDATION CAMPAIGN KIT

> Execution system only. No code, no features, no redesigns. Product is frozen
> for validation. Grounded in the audited site: two seeded featured campaigns
> (both real state-actor disclosure archives, scored by the real engine),
> public report routes `/rc/{token}` and `/r/{token}`, landing CTA already
> pointing at the Xinjiang report.

---

## STEP 1 — ARTIFACT SELECTION (from the live-site audit)

### What exists to choose from (verified)
| Artifact | URL | What it is |
|---|---|---|
| Russia · GRU (Dec 2020 disclosure) | `/rc/cmp_feat_ru_gru_202012` | 16-member GRU network from Twitter's official state-actor disclosure; Omi re-derives the coordination **from behavior alone** (fingerprints + amplification network), never from the disclosure label. Score 1.0. |
| China · Xinjiang (CNHU disclosure) | `/rc/cmp_feat_cn_xinjiang` | 41-member PRC operation amplifying Xinjiang narratives; **three independent methods agree** — corroborated, not a lone-bot guess. Score 0.9991. |
| Landing page | `/` | Marketing surface; primary CTA → the Xinjiang report; pricing ($9.99/mo · 20 scans · 3 free) visible. |
| Signup | `/signup` | Asks for commitment before showing value. |

### The default first artifact: a public report URL, never a marketing page
Send the **`/rc/...` public campaign report link, bare** — no deck, no
screenshots, no landing page.
Why: it renders logged-out with zero friction; it carries the first-view
"how to read this" guidance; it shows evidence AND counter-evidence (the
differentiator we're testing); opening it is **tracked** (deduped
`public_report_view`), so "sent → opened" is measurable per wave; and a
marketing page triggers the being-sold-to reflex in exactly the skeptical
experts we're recruiting. Screenshots would kill both the click and the
measurement. The landing page is the *second* page — they reach it themselves
via the logo if interested, where signup and pricing live.

### Per-ICP defaults (override only for domain match)
- **OSINT researchers (A) → GRU report** (`/rc/cmp_feat_ru_gru_202012`).
  The canonical, instantly-recognized case in this community — and it's a
  **ground-truth challenge**: they know the answer from the disclosure, so the
  pitch is "we re-derived this from behavior alone — check our work." 16
  members is one sitting's read. *Override:* China-watchers get Xinjiang.
- **Journalists (B) → Xinjiang report** (`/rc/cmp_feat_cn_xinjiang`).
  A named, newsworthy operation with scale (41 accounts) and a clean editorial
  hook: "three independent methods agree" maps directly to corroboration
  standards a standards desk understands. *Override:* Russia-beat reporters
  get GRU. (Consistent bonus: cold web traffic from the landing CTA already
  lands here.)
- **Trust & Safety (C) → GRU report** (`/rc/cmp_feat_ru_gru_202012`).
  The 16-member cluster reads like a realistic case file (a ban-wave-sized
  network), and the conversation angle is casework: evidence + counter-evidence
  + Markdown export = appeal-proof documentation. *Override:* if their abuse
  surface is narrative/brigading at scale, Xinjiang.

### First page per ICP (exact)
| ICP | First page they should see |
|---|---|
| Journalists | `/rc/cmp_feat_cn_xinjiang` |
| OSINT researchers | `/rc/cmp_feat_ru_gru_202012` |
| Trust & Safety | `/rc/cmp_feat_ru_gru_202012` |

**Honest limitation + optional play:** both artifacts are X-platform
state-actor cases. For a T&S prospect in commerce/review-fraud they may feel
distant. Permitted mitigation (uses the product, builds nothing): during
Week 0 the founder may run ONE real scan on a commercially-flavored public
case and mint its `/r/{token}` report as a supplementary artifact. Optional —
the two featured reports remain the defaults.
**Week-0 tie-in:** verify BOTH featured URLs render logged-out in production
before wave 1.

---

## STEP 2 — FIRST-WAVE TARGET PROFILES

### A. OSINT researcher (12 of 25)
- **Ideal seniority:** mid-career practitioner, 2–8 years doing network /
  influence-op analysis. Senior enough to have live cases; junior enough to
  still do the work themselves.
- **Ideal role:** analyst or fellow at a disinfo lab / think tank; independent
  researcher with a public investigation record; data-journalist crossover.
- **Ideal organization size:** small labs and think tanks (2–50) or
  independent. Big-org analysts have internal tooling and procurement walls.
- **Ideal platform focus:** X-native network investigations (what Omi scans);
  YouTube comment-ecosystem researchers are gold (scans cost 1 credit).
- **Red flags:** geolocation/imagery-only OSINT (wrong sub-discipline);
  "OSINT influencer" posting tool lists but no investigations; nothing
  published in 12+ months; fully anonymous with no verifiable work (their
  feedback can't be weighted).
- **Who NOT to contact:** field celebrities and lab directors (Bellingcat /
  DFRLab leadership — flooded inboxes, and one skeptical public quote-tweet
  ends the quiet validation window early); aggregate-level academics with no
  live cases; anyone mid-public-feud or doxxing-adjacent; state-affiliated
  researchers (OPSEC + optics).

### B. Investigative journalist (8 of 25)
- **Ideal seniority:** staff reporter or established freelancer, 3–10 years,
  with ≥1 shipped bot-network / influence-op story.
- **Ideal role:** misinformation / platforms / tech-accountability beat;
  data journalist on an investigations desk.
- **Ideal organization size:** mid-size digital outlets and nonprofit
  newsrooms (10–200 editorial). Top national desks have verification
  partnerships; tiny blogs have no standards desk — and the standards-desk
  test is exactly the trust signal we want.
- **Ideal platform focus:** recurring coverage of X/YouTube manipulation, not
  a one-off story.
- **Red flags:** opinion writers on disinfo (no original investigation);
  hot-take aggregators; reporters who only quote other researchers' findings
  (they can't evaluate evidence quality — possible future customers, weak
  validators).
- **Who NOT to contact:** editors-in-chief (wrong altitude — recruit the
  reporter, not the masthead); journalists publicly campaigning against
  AI/automated tools in journalism (wave-2 robustness test at best, not
  first-25); **anyone you would simultaneously pitch for press coverage** —
  never mix "cover my startup" with "use my tool"; it contaminates both the
  validation and the future story.

### C. Trust & Safety professional (5 of 25)
- **Ideal seniority:** senior analyst / team lead, 3–10 years, still
  hands-on in the queue (not pure management).
- **Ideal role:** integrity analyst, platform-abuse investigator, fraud/abuse
  ops, T&S threat-intel.
- **Ideal organization size:** small/mid platforms or marketplaces
  (~50–2000 employees; T&S team 2–20). Big enough to have a real abuse
  problem, small enough to lack Meta-scale tooling and to adopt SaaS without
  nine months of procurement.
- **Ideal platform focus:** abuse surface with a **public X/YouTube
  footprint** — brand brigading, comment-section manipulation, coordinated
  harassment of their users. (Honest fit note: much T&S casework lives in
  private internal logs Omi can't see; the fit is the public-footprint
  subset. Surface this in the call; don't oversell.)
- **Red flags:** policy-only roles (write rules, never touch cases);
  perpetual vendor-evaluators (love demos, never buy); orgs whose security
  posture blocks opening external tools at all.
- **Who NOT to contact:** integrity teams at the platforms Omi scans
  (X, Google/YouTube — conflict + ToS optics) or at direct competitors;
  between-jobs T&S folks as *validation* rows (no live queue = no behavior;
  log the candid ones as advisors, not among the 25).

---

## STEP 3 — FOUNDER DASHBOARD: THE 15-MINUTE DAILY

One sitting, same time daily. Anything not listed is out of bounds today.

### Minutes 0–3 — read exactly three numbers (`GET /v1/admin/learning`)
1. `q3.public_report_views` — did yesterday's sends get **opened**?
2. `q1` successful own scans / activations — did anyone **scan**?
3. `q5.wtp_answers` — any new **verbatims**?
Daily deltas only. Everything else in the payload is Friday's job.

### Minutes 3–6 — tracker triage
- New replies → update status, paste verbatim.
- Anyone interested >72h without a booked call → flag.
- Follow-ups due today (T+3d) and closes due (T+10d) → list.
- Calls tomorrow → confirm credits are pre-granted.

### Minutes 6–12 — act, strictly in this order
1. **Reply to every prospect reply** (24h SLA — this outranks everything).
2. Book/confirm calls (offer two concrete times, today+2 max).
3. Send due follow-ups (cap 2 per prospect, then terminal status + refill).
4. New outreach **only if** the active wave has unsent slots — wave
   discipline beats volume.
5. Pre-grant credits for tomorrow's calls.

### Minutes 12–15 — log one line
Daily-log tab: `date | sent | replies | opens | own-scans | 1 verbatim (if any)`.
If all zeros: add two new qualified prospects to the queue instead. That's
the whole entry.

### Ignore completely (every day)
- Total signups, page views, social metrics, follower counts.
- Uptime/infra dashboards — unless a **user** reports breakage.
- Q2 (return) and Q4 (trust-proxy) aggregates — weekly numbers; daily
  movement at N<25 is noise.
- Feature ideas (parking lot exists), the codebase, the roadmap.
- Re-checking the learning endpoint more than once a day. Obsessive
  refreshing at this N is reading tea leaves; the daily check is enough.

---

## STEP 4 — FOUNDER BIAS PREVENTION

### The top 10 ways to accidentally invalidate this PMF process

1. **Leading the witness.** Questions that contain the desired answer
   ("doesn't the counter-evidence make it more trustworthy?") manufacture
   agreement. *Prevention:* interview script is verbatim; banned phrases:
   "would you use", "do you like", "isn't it", "wouldn't it help".
2. **Rescuing the demo.** Explaining a section the prospect misread during
   the cold read erases the finding forever. *Prevention:* say-aloud
   protocol = founder silence; every stall/misread logged as A6 data.
3. **Sampling friendlies.** Filling the 25 with friends-of-friends who will
   be kind, or only contacting people who seem pre-warm. *Prevention:* list
   built by Fit Score BEFORE outreach; composition 12/8/5 enforced;
   declines and no-replies are recorded data, not embarrassments.
4. **Politeness-as-demand.** "This is cool, I'd definitely use it" is a
   social nicety, not a signal. *Prevention:* only behaviors score —
   own-case run, return, share-that-got-read, named budget owner.
   Compliments are logged with a Signal Score of 0.
5. **Retreating into building.** The repo is comfortable; rejection isn't.
   *Prevention:* product frozen; parking lot for every ask; only an F4
   trust-defect (≥2 independent experts) re-opens code. Weekly audit line:
   hours on outreach vs hours in the repo — repo > 0 without an F4 is a
   violation by definition.
6. **Cherry-picked logging.** Quoting praise verbatim, paraphrasing
   criticism. *Prevention:* weekly review rule — sections "confused" and
   "assumptions weaker" must have ≥ as many evidence-backed entries as
   "loved"/"stronger", or carry an explicit "none found despite N
   conversations" (which at N>3 is itself a red flag to investigate).
7. **Moving the goalposts after seeing data.** "2 real cases is basically
   5." *Prevention:* thresholds are pre-committed in writing (Phase 6 §E/F +
   the Gate below). Changing one requires writing, in the weekly review:
   "I am changing a threshold after seeing the data because ___."
8. **Demo-impressedness counted as pull.** High featured-report views feel
   like traction; they aren't (A8). *Prevention:* views and own-case scans
   are reported as separate lines, always; views never appear in the
   "validation" column.
9. **Price anchoring.** Naming $9.99 before they price their own pain caps
   every WTP answer at your number. *Prevention:* WTP question order is
   fixed (their spend → their hours → their band + budget owner); founder
   never says a price first in an interview.
10. **Wrong-N conclusions.** Declaring victory or death at n=6, or counting
    25 *attempts* as 25 conversations. *Prevention:* "quality conversation"
    is defined (call completed + cold read done + real-case close asked);
    the Gate fires only at 25 quality conversations or the week-4 timeout.

### The recurring checklist

**Before every call:**
- [ ] Script open; banned-phrase list visible.
- [ ] I have NOT told this person what the tool "should" do for them.
- [ ] Credits pre-granted so "run yours now" needs no founder action.
- [ ] I will not name a price.

**During every call:**
- [ ] Cold read happened in silence; stalls logged, not rescued.
- [ ] Asked trust-most / trust-least, not "do you trust it?"
- [ ] Asked "case on your desk right now?" — the behavioral close.
- [ ] If shown a false positive: "what tells you it's wrong?" — never argued.

**After every call (same day):**
- [ ] Verbatims pasted, not paraphrased.
- [ ] Signal Score updated from behaviors only.
- [ ] Feature asks → parking lot with the underlying job, not the solution.

**Every Friday:**
- [ ] Negative sections at least as full as positive ones (or flagged).
- [ ] No threshold changed silently.
- [ ] Outreach-hours ≥ repo-hours (repo should be 0 absent an F4).
- [ ] Views reported separately from own-case scans.

---

## STEP 5 — THE PMF DECISION GATE

**Fires at:** 25 quality conversations, or end of week 4 — whichever first.
**Quality conversation =** completed call + cold read done + real-case close
asked. (F8 guard: if fewer than 15 quality conversations happened, the only
permitted decision is "extend one week, fix recruiting" — you may NOT
conclude shut-down from a test that never ran.)

**Evidence pack required before deciding (no memo, no decision):**
S1–S6 finals · F1–F8 flags · per-segment signal table (Signal Score mass by
ICP) · parking-lot frequency table (same-job asks counted) · ≥10 verbatims ·
funnel (sent→opened→call→activated). Decision is a one-page memo citing it.

### A) CONTINUE — concentrate and deepen
**All of:**
- S1 ≥ 5 own-case scans, AND
- S3 ≥ 3 unprompted would-cite/defend, AND
- no unresolved F4 (trust defect), AND
- at least one of: S5 ≥ 5 returning users · S6 ≥ 3 WTP-with-budget-owner.
**Action:** declare the winning segment; second cohort of 25 drawn ONLY from
it; pricing/packaging test (A9). Feature work still gated: parking lot must
show the same job ≥5 times before anything is built.

### B) PIVOT ICP — the pull is real but lives somewhere else
**Pattern (any of):**
- S1 = 2–4 AND ≥70% of total Signal Score mass concentrated in one segment
  (or in an untargeted adjacent persona who kept showing up — e.g.
  brand-safety, academic labs), OR
- two segments dead (reply <10%, no cases) while one segment replies >25%
  with ≥2 cases, OR
- F6 fired overall, BUT the YouTube/X-native sub-population converted at
  ≥40% of its conversations to own-case scans.
**Action:** redefine the ICP around where the signal concentrated; rebuild
the 25-list in that segment; rerun the campaign. Recruiting pivot — zero
build.

### C) PIVOT PRODUCT — right people, real pain, wrong shape
**All of:**
- ≥15 quality conversations confirm the pain first-hand (they describe hours
  lost and current hacks — not hypotheticals), AND
- engagement was healthy (reports opened, cold reads mostly clean — so it's
  not a comprehension or funnel failure), AND
- S1 < 2 own-case scans despite that, AND
- the parking lot shows the SAME missing job-to-be-done named independently
  by ≥8 of 25 (e.g. "right evidence, wrong container — I need it inside my
  case system" / "I need the raw data, not the verdict").
**Action:** write the pivot brief (the consistent ask, verbatims, who said
it) and bring it to the CEO gate for Phase 7 scoping. This outcome
*authorizes a proposal*, not construction — no building inside Phase 6.

### D) SHUT DOWN THE IDEA — the thesis is falsified
**All of (the falsification must be demand-side, not execution-side):**
- 25 quality conversations across ≥2 segments, AND
- S1 < 2 own-case scans, AND
- no segment concentration (no segment holds ≥50% of a thin signal), AND
- no consistent missing-job in the parking lot (asks scattered or
  contradictory — distinguishes D from C), AND
- S3 ≤ 1 would-cite AND S6 = 0 WTP-with-budget, AND
- the funnel demonstrably worked: Week-0 smoke tests passed, reply rate
  ≥10%, reports were opened. (We reached real target users with a working
  product, and they did not pull.)
**Action:** post-mortem memo from the tracker evidence; archive the
campaign. The engine remains an asset — any repositioning is a NEW thesis
decided after a deliberate break, not a rationalization written the same
week.

### Precedence and ambiguity rules
- D's guards are absolute: no shut-down on a broken funnel or an unrun test.
- C beats B when the same-job evidence spans ≥2 segments; B beats C when
  signal concentrates by WHO rather than by WHAT.
- Between thresholds (e.g. S1 = 3–4 with weak trust): the default is **B or
  a second focused cohort — more validation**. Ambiguity always resolves
  DOWN (validate more), never UP (build more). "Almost validated" is not a
  build authorization.
