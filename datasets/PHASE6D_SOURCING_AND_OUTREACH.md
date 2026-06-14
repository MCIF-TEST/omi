# PHASE 6D — PROSPECT SOURCING & OUTREACH EXECUTION SYSTEM

> Sourcing and outreach only. No product work, no features, no validation
> theory. Goal: a ranked 25-person prospect list in under a week, and a
> day-by-day plan to start disciplined outreach. Anchor accounts named below
> are **sourcing nodes to mine**, not necessarily people to contact (celebrity
> hubs are on the 6B do-not-contact list — harvest their engaged community).

---

## STEP 1 — WHERE THESE PEOPLE ARE

### OSINT researchers / disinformation analysts
- **Communities:** Bellingcat Discord · r/OSINT · OSINT Curious · Trace Labs · Project Owl Discord · OSINT Combine community · the "Week in OSINT" reader circle.
- **Conferences:** EU DisinfoLab Annual Conference · Bellingcat workshops · ConINT · SANS OSINT Summit · DEF CON Recon Village + Misinformation Village · NATO StratCom COE events · GIJC (crossover).
- **Slack/Discord:** Bellingcat Discord (most active) · Trace Labs Slack/Discord · OSINT Curious Discord · Project Owl.
- **Forums:** r/OSINT · r/OSINTtools · the OSINT Framework community.
- **Newsletters (mine author + engaged readers):** Sector035 "Week in OSINT" · Dutch OSINT Guy · Bellingcat newsletter · EU DisinfoLab digest · DFRLab Dispatch · Conspirador Norteño's posts.
- **Organizations:** Bellingcat · DFRLab (Atlantic Council) · EU DisinfoLab · ASPI ICPC · Graphika · ISD (Institute for Strategic Dialogue) · Logically · Alethea · Recorded Future Insikt · Clemson Media Forensics Hub · UW Center for an Informed Public · Stanford Internet Observatory **diaspora** (wound down — find where alumni landed).
- **LinkedIn search pattern:**
  `("OSINT" OR "open-source intelligence" OR "disinformation" OR "influence operations" OR "information operations") AND ("analyst" OR "researcher" OR "investigator")` — then filter by the orgs above and by "Posted in last 30 days."
- **X/Bluesky search patterns:**
  - Live-case hunting: `(coordinated OR "bot network" OR astroturfing OR "inauthentic behavior" OR "sock puppet") (analysis OR investigation OR thread) min_faves:25 -filter:replies lang:en`
  - Hottest prospects (actively asking the question Omi answers): `("is this coordinated" OR "are these bots" OR "looks like a bot network" OR "coordinated inauthentic")`
  - Anchor-mining nodes (read their case threads, harvest practitioner repliers/QTs): @bellingcat · @DFRLab · @conspirator0 · @Shayan86 · @MarcOwenJones · @ZellaQuixote · @ASPI_ICPC · @disinfoeu · @Graphika.

### Investigative journalists (platform / influence beat)
- **Communities:** IRE (Investigative Reporters & Editors) · NICAR · Hacks/Hackers · ONA · GIJN (Global Investigative Journalism Network).
- **Conferences:** NICAR · IRE Conference · GIJC · ISOJ · ONA · Logan Symposium.
- **Slack:** News Nerdery · Hacks/Hackers · OpenNews/SRCCON circles.
- **Forums/listservs:** NICAR-L listserv (the big one) · IRE forums · MuckRock community.
- **Newsletters (mine author + bylines they cite):** Platformer (Casey Newton) · 404 Media · Garbage Day (Ryan Broderick) · User Mag (Taylor Lorenz) · Galaxy Brain (Charlie Warzel) · Nieman Lab · GIJN newsletter · Tech Policy Press.
- **Organizations (on-beat desks):** 404 Media (the sharpest fit — bot networks/platform manipulation) · The Markup · ProPublica · Wired · Bloomberg · NYT/WaPo tech-accountability desks · Rest of World · Coda Story · NBC disinfo-desk diaspora.
- **LinkedIn pattern:** `("investigative journalist" OR "reporter" OR "correspondent") AND ("disinformation" OR "misinformation" OR "platforms" OR "bots" OR "extremism")` — weaker channel; journalists live on X/Bluesky.
- **X/Bluesky patterns:**
  - Byline-mining nodes: @404mediaco (Koebler/Cox/Maiberg/Cole) · @CaseyNewton · @sheeraf · @rmac · @craigtimberg · @oneunderscore__.
  - Beat-finder: `(disinformation OR "bot network" OR "influence operation") (filter:links) min_faves:30` then check who's a reporter (bio + outlet).
  - Bluesky: search the "Journalism" and "Disinformation" starter packs — dense reporter migration.

### Trust & Safety professionals
- **Communities:** Integrity Institute (the core practitioner community) · Trust & Safety Professional Association (TSPA) · Marketplace Risk · Merchant Risk Council (fraud-adjacent).
- **Conferences:** **TrustCon** (the one) · Integrity Institute "Spotlight" · Marketplace Risk Management Summit · MRC Vegas (fraud).
- **Slack:** Integrity Institute member Slack · TSPA community · Marketplace Risk Slack.
- **Forums/newsletters:** "Everything in Moderation" (Ben Whitelaw — the T&S newsletter) · Integrity Institute "Integrity Insights" · Tech Policy Press.
- **Organizations (small/mid platforms — the buyable ones):** Discord · Reddit · Twitch · Patreon · Substack · Roblox · Nextdoor · Bumble/Match · marketplaces (Etsy, Poshmark, Mercari, OfferUp, Depop). **Avoid** X and Google/YouTube integrity teams (conflict/optics) and direct T&S vendors (ActiveFence, Cinder, Cove, Spectrum, Checkstep — competitors/partners).
- **LinkedIn pattern (strongest channel for T&S):**
  `("Trust and Safety" OR "Trust & Safety" OR "platform integrity" OR "content moderation") AND ("analyst" OR "investigator" OR "operations" OR "lead" OR "manager")` — exclude pure "policy" titles if you want hands-on queue people; filter to the platforms above.
- **X pattern:** weak; use LinkedIn. Mining nodes for the community: @integrityinst · @ben_whitelaw · @TSProfAssoc.

---

## STEP 2 — PROSPECT SOURCING PLAYBOOK (25 qualified in <1 week)

**Funnel math:** source **~100 raw candidates → qualify to ~40 → rank → take top 25 to contact, bench the next 15** as refill. (Low reply rates mean you contact all 25 and refill from the bench; the bench is non-negotiable.)

**"Qualified" = all five (from 6B):** right ICP · platform fit (their work is plausibly X/YouTube) · active (posted/published in ~90 days) · hands-on (does the work, not just manages/opines) · reachable (findable contact; warm path a plus) · **not** on a do-not-contact list.

**Raw-sourcing quotas (hit ~100):**
| Source method | Target raw | ICP skew |
|---|---|---|
| Anchor-account mining on X/Bluesky (repliers/QTs on real case threads) | 40 | mostly OSINT |
| LinkedIn org-roster mining (10 orgs × right titles) | 30 | OSINT + T&S |
| Byline mining (8 recent influence-op stories → authors + practitioners they quote) | 20 | journalists + OSINT |
| Community/member directories (Integrity Institute, TSPA, Bellingcat Discord actives) | 10 | T&S |

**The five sourcing moves, in order of yield:**
1. **Anchor mining (highest yield).** Open 5 anchor hubs' recent "is this coordinated?" threads → harvest the *practitioners* in replies/QTs (not the anchor). The people *answering* coordination questions in public are your warmest cold prospects.
2. **Hot-prospect search.** Run the "is this coordinated / are these bots" X search — anyone asking that question this week has the exact job-to-be-done live.
3. **Org-roster mining (LinkedIn).** 10 target orgs × the boolean title search → pull names with the right title + recent activity.
4. **Byline mining.** 8 recent bot-network/influence-op stories → the reporter byline + any practitioner quoted by name.
5. **Directory mining.** Integrity Institute / TSPA / community member lists for T&S.

**Tooling (lightweight, founder-run):** the 6A tracker spreadsheet · LinkedIn (Sales Navigator 1-month free trial for the boolean filters) · X advanced search (free) · email-finding via outlet contact pages / personal sites / Hunter.io free tier. Nothing else.

**Warm-path overlay (do this last, on the qualified ~40):** for each, check LinkedIn "How you're connected" and mutual follows. Tag `warm` / `2nd-degree` / `cold`. Warm paths jump the queue regardless of raw score.

**De-dupe + qualify pass:** drop anyone hitting a 6B red flag or do-not-contact rule (score 0, remove). What survives, you rank in Step 3.

---

## STEP 3 — RANKING SYSTEM (scoring 100 prospects)

**Auto-disqualify first (remove, don't score):** celebrity/director-tier · no activity in 12 months · platform-unsupported with no public X/YouTube work · pure policy/management (no hands-on) · vendor/competitor · platform-you-scan insider · anyone you'd also pitch for press.

**Fit Score — 100 points, all from observable signals:**
| Dimension | Pts | How to score from public signal |
|---|---|---|
| **Active case now** | 0–30 | Publicly worked a coordination case ≤90d = 30 · ≤12mo = 15 · older/none = 0 |
| **Platform fit** | 0–25 | Work clearly X/YouTube = 25 · mixed = 12 · unsupported-leaning = 0 |
| **ICP sharpness** | 0–20 | OSINT-A = 20 · Journalist-B = 14 · T&S-C = 10 |
| **Reachability** | 0–15 | Warm intro available = 15 · 2nd-degree = 8 · cold but contact findable = 3 |
| **Reach/influence** | 0–10 | Would their adoption pull peers? high = 10 · some = 5 · solo = 2 |

**Prioritization procedure:**
1. Score all ~100; drop disqualifies.
2. Sort descending by Fit Score.
3. **Enforce composition** on the top cut: 12 A / 8 B / 5 C = the 25 contact list. (If a segment lacks enough ≥ threshold, that shortfall is itself a sourcing signal — note it, don't pad with juniors.)
4. **Bench** the next ~15 by score for refill.
5. **Tie-breakers (in order):** warm path > active-case recency > a *currently live* public case > higher reach.
6. **Assign to waves of 5**, each wave spread across A/B/C so every wave tests all three segments (see Step 4).

---

## STEP 4 — WAVE 1: THE FIRST 5 TARGET PROFILES

Not names — the five highest-fit archetypes, composed **3 A / 1 B / 1 C** to
over-index the sharpest ICP while testing all three in wave 1. Match real
sourced prospects to these slots.

**Profile 1 — "The live-thread coordination poster" (OSINT / A)**
- *Signals:* posted an "is this network coordinated?" thread on X/Bluesky in the last 2–4 weeks; shows account screenshots; mid-career, not a celebrity.
- *Why wave 1:* the job-to-be-done is **live right now** — highest-intent prospect that exists.
- *Artifact:* GRU report (`/rc/cmp_feat_ru_gru_202012`). *Channel:* public reply or DM. *Warm path:* usually cold but high-intent.

**Profile 2 — "The small-lab disinfo analyst" (OSINT / A)**
- *Signals:* analyst/fellow at a 2–50-person lab (DFRLab/EU DisinfoLab/ISD/ASPI-tier); recent published network analysis on X.
- *Why wave 1:* recurring professional need + credible validator; reachable via org email/LinkedIn.
- *Artifact:* GRU report. *Channel:* warm intro > personal email. *Warm path:* prioritize anyone 2nd-degree.

**Profile 3 — "The YouTube-comment-ecosystem researcher" (OSINT / A)**
- *Signals:* studies comment manipulation / engagement rings on YouTube specifically.
- *Why wave 1:* perfect platform fit **and** cheap to serve (YouTube scans = 1 credit), so they can run several real cases without hitting cost friction.
- *Artifact:* offer to run their own YouTube case immediately. *Channel:* DM/email. 

**Profile 4 — "The influence-op beat reporter at a digital-native outlet" (Journalist / B)**
- *Signals:* byline on a recent bot-network/platform-manipulation story (404 Media / The Markup / Wired tier); active on X/Bluesky.
- *Why wave 1:* tests the journalist trust+citation question early with the most on-beat reporter type.
- *Artifact:* Xinjiang report (`/rc/cmp_feat_cn_xinjiang`). *Channel:* DM referencing their story, or email.

**Profile 5 — "The hands-on integrity analyst at a mid platform" (T&S / C)**
- *Signals:* "Trust & Safety / Platform Integrity Analyst" at a 50–2000-person platform with a public abuse surface (community app, marketplace, creator platform); Integrity Institute or TSPA member.
- *Why wave 1:* tests the buyable ICP and the casework angle; LinkedIn-reachable.
- *Artifact:* GRU report (case-file framing). *Channel:* LinkedIn/email. *Warm path:* Integrity Institute/TSPA mutual.

---

## STEP 5 — OUTREACH EXECUTION PLAN (Day 1–7)

Sources the full ranked 25 within the week and **begins** disciplined outreach
in waves of 5 (2–3 days apart, per 6B). It does **not** fire all 25 in 7 days —
that would burn the list and violate the adapt-between-waves rule. Waves 3–5
land in week 2. The 15-minute daily discipline (6B) runs every day from Day 4.

**Day 1 — Setup + sourcing sprint 1**
- Build the tracker (6A schema); start the LinkedIn Sales Navigator trial.
- Lock the "qualified" filter and the disqualify list at the top of the sheet.
- Anchor-mine + hot-prospect search on X/Bluesky → **40 raw OSINT candidates**.
- *Output:* 40 raw rows.

**Day 2 — Sourcing sprint 2 (hit ~100 raw)**
- LinkedIn org-roster mining (10 orgs) → ~30 · byline mining (8 stories) → ~20 · community directories → ~10.
- *Output:* ~100 raw candidates total.

**Day 3 — Qualify, rank, build lists, draft Wave 1**
- Qualify ~100 → ~40; run warm-path overlay; score with the Step-3 rubric.
- Sort, enforce 12/8/5 → **the 25**; bench the next 15.
- Assign waves; fill the **Wave 1 five** against the Step-4 profiles.
- Write 5 personalized messages (6A skeletons; reference each person's specific work). Pre-send check: both `/rc` artifacts load logged-out; calls have pre-grantable credits ready.
- *Output:* ranked 25 + bench 15 + 5 ready-to-send messages.

**Day 4 — Send Wave 1**
- Fire the 5 (warm intros requested first where a path exists; otherwise DM/email/public reply per profile). Log `sent` + timestamp.
- Start the 15-min daily from here on.
- *Output:* 5 contacted.

**Day 5 — Manage Wave 1 + prep Wave 2**
- Reply to any Wave 1 response within 24h; book interested people (offer two concrete times); pre-grant their credits.
- Draft Wave 2's 5 personalized messages (adapt wording from anything Wave 1 taught you).
- *Output:* Wave 1 managed; Wave 2 drafted.

**Day 6 — Send Wave 2**
- Fire the next 5. Log. Continue 24h replies + booking. First calls may occur — run the 6A interview script; never name a price; credits pre-granted.
- *Output:* 10 contacted cumulative.

**Day 7 — Wave 1 follow-ups + week review + schedule week 2**
- Wave 1 follow-up (T+3d from Day 4): one nudge each, different artifact/angle, to non-responders (max 2 touches ever).
- Refill: replace any Wave 1 hard "no"/disqualify from the bench.
- Quick review: sent / replied / opened (`q3.public_report_views`) / calls booked. Note message changes for week 2.
- Schedule week 2: Wave 3 (Day 9), Wave 4 (Day 11), Wave 5 (Day 13); Wave 2 follow-up Day 9; keep booking and running calls.
- *Output:* follow-ups out, list refilled, week-2 calendar set.

**End-of-week-1 state:** ranked 25 sourced + 15 benched · 10 contacted in two waves · Wave 1 followed up · calls being booked/run · week-2 waves scheduled. The list is built and the machine is running without burning it.
