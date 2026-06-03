# OmiSphere — Tier 2 Audit: Investigation Value

> Author: Claude (founder / product strategist / T&S + authenticity-intelligence
> analyst lens). Date: 2026-06-02. Branch: `claude/focused-turing-upy6c`.
> Scope: the **value** of investigations — quality, evidence, confidence,
> explainability, transparency, actionability, authenticity-intelligence,
> intelligence quality, dataset leverage. **Tier 1 (reliability/persistence/data
> integrity) is assumed complete.**
> Method: read the actual investigation *outputs* (report templates, LLM/template
> commentary, the synthesis/conclusion generators, the OmiScore envelope) + two
> focused evidence-gathering agents (user-facing value/actionability; intelligence
> quality + dataset leverage) + quantitative checks on real-shaped inputs. No
> implementation — this determines the highest-value work.

---

## Tier 2 Health Score: **48 / 100**
### "Investigation-grade exploration tool — not yet decision-grade intelligence."

| Dimension | Score | Verdict |
|---|---|---|
| Investigation quality | 5/10 | Rich to explore; suspicion-forward; over-asserts on thin coordination |
| Authenticity-analysis quality | 5/10 | Right *shape* (multidimensional OmiScore) but partly hollow — see Amplification |
| Evidence quality | 6/10 | Real per-detector evidence strings; exculpatory evidence hidden; amplification evidence absent |
| Confidence systems | 5/10 | Honest abstention is a plus; but point-estimates, no uncertainty band, overconfident coordination |
| Explainability | 6/10 | Above-average (`score_adjustments`, reasons, commentary) — but the balanced attribution is buried |
| Transparency | 5/10 | Supporting evidence ✓; contradicting/alternative ✗; uncertainty ✗ — the balanced data exists, isn't shown |
| Actionability | 3/10 | Investigations are analysis exercises; no watchlist/bulk/escalation/next-step/alerts |
| User understanding | 5/10 | Sees *what* was found, not *how sure*, *what lowered it*, or *what to do* |

**Brutally honest "valuable vs. interesting":** On a *typical* (organic) video, every
per-account detector correctly **abstains** — a 6-comment commenter yields confidence
**0.0** on temporal/voice/engagement/ai_writing and **0.15** on semantic — and no
coordination fires, so the result is "nothing flagged" and the user thinks *"interesting,
it didn't find much."* On a *genuinely coordinated* video the cross-account layer can
deliver a real *"I'd have missed this"* — but it currently over-asserts (3 accounts
posting similar text within 2 minutes → 80% / "coordinated campaign"), so the first time
a user spot-checks and finds three people who simply quoted the video, the trust is gone.
**Today the product mostly lands on "interesting," with genuine-value moments gated behind
coordination actually firing *and* the user trusting an unvalidated, overconfident
verdict.** The good news: most of the fix is surfacing balance the engine *already
computes* and being honest about what it doesn't measure.

---

## Audit findings

### Investigation review — what users learn / don't
**Learn:** an overall OmiScore + tier, coordination clusters (methods, member accounts,
evidence snippets), per-commenter probability/confidence/evidence, an intent label,
data-quality caveats, and (if saved) an analyst paragraph.
**Don't learn:** *how confident* the headline is (no band), *what lowered* suspicion (the
exculpatory "community" detector and the signed raises/lowers `contributions` are computed
but surfaced nowhere in the structured UI), *what else could explain* the behavior, or
*what to do next*.

### Evidence audit
Per-detector evidence strings carry real measured values ("posting cadence looks
mechanical," cosine/Jaccard counts) and are mostly understandable. Two findings rely on
**opaque or absent** evidence: (a) **amplification** — no evidence, because it measures
nothing real (below); (b) **coordination intent** — a single similarity cluster is
asserted as a "campaign" without showing why the innocent explanation was ruled out.

### Confidence audit
Confidence is a single scalar (weighted-evidence coverage), rendered as small secondary
text, never as a range. Uncertainty is **not** communicated at the verdict; alternative
explanations are **not** considered in output. The coordination confidence **floor of 0.75
for a single method** makes thin evidence look authoritative — confidence is *miscalibrated
upward* exactly where it matters most.

### Explainability audit
A non-technical user can read "why flagged" plus a plain-language calibration narrative —
better than most tools. But they **cannot** explain *why this confidence*, *what pulled the
score down*, or *what would make it benign*, because the balanced attribution lives only in
an expandable sub-panel and the optional LLM prose.

### Transparency audit
Supporting evidence: shown. Confidence: partial. **Contradicting evidence, uncertainty,
alternative explanations: not shown.** The engine already computes the balanced view —
GAP-06 signed `contributions`, a "community" detector that *lowers* suspicion, and
per-account LLM digests that explicitly include `lowered_suspicion … reflect them
honestly`. The gap is purely **presentation**.

### Authenticity-Intelligence audit
Structurally it is *more* than a bot detector — the OmiScore decomposes into
coordination / amplification / spam / ai-generation / authenticity dimensions with
evidence per dimension. But two dimensions are weak (amplification is a relabel;
ai-generation is correctly contextual-only), so today it behaves like a **coordination
detector wrapped in an authenticity-intelligence UI** — the multidimensional promise is
half-delivered.

### Actionability audit
Essentially none. After a verdict the user cannot add the flagged set to a watchlist,
bulk-action them, export an evidence pack, set an alert on future activity, or follow a
playbook. The verdict is stored and the thread ends. (Watchlist + alert infrastructure
*exists* in the backend but isn't wired to the investigation flow.)

### Intelligence-quality audit (confirmed quantitatively)

| Analysis | Verdict | The crux (evidence) |
|---|---|---|
| **Coordination** | **Genuine but overconfident** | Real graph: TF-IDF cosine + time-window union-find (`detection/coordination/*`). But score base 0.40 + single-method confidence floor 0.75 (`elevate.py`) → a 3-account / 2-min similarity (innocent: three people quoting the video) emits **0.80 prob / 0.75 conf** and routes to a "coordinated_campaign" intent (`scoring.py`). No 2nd-method corroboration required. |
| **Amplification** | **Weak — a re-label** | `amplification_probability = coordination·0.45 + engagement·0.35 + temporal·0.20` (`intelligence/signals.py`). **Zero reach data used.** `integrations/youtube.py` fetches `likeCount`/`replyCount`/`subscriberCount` then **discards** them — no detector reads them. No like-velocity, no time-to-engagement, no like/reply ratios. It is three behavioral detectors re-weighted and relabeled "artificial reach inflation." |
| **Narrative** | **Needs improvement** | `sentence-transformers` is **not installed** → `HashingEmbedder` fallback = **lexical near-duplicate** detection (`narrative/embeddings.py`), which "will NOT catch paraphrases." Worse, `inauthenticity_score` is **circular** — derived from member tiers produced by the single-account engine, which abstains on typical commenters → most real clusters score ~0 coordination regardless of content. |
| **Behavioral** | **Weak on real commenters** | Detector floors (temporal 8 posts; semantic ~20; voice 80 words/full-conf 800; engagement 5 posts/40 words; ai_writing 120/full-conf 600). A **typical 6-short-comment commenter → temporal/voice/engagement/ai_writing conf 0.00, semantic 0.15: all five abstain.** Honest (no false accusations) but contributes ~nothing single-account; all real signal is cross-account. |

### Dataset-leverage audit
The ML feature vector is built from **engine outputs** (`ml/features.py`,
`ml/public_import.py` runs each row through `analyze_account`), so text-less account rows
collapse the 16 detector dims to neutral (0.5, 0.0) — **the datasets' behavioral richness
never reaches the model.**

| Rank | Dataset | Rows | Best use | Capability | Status |
|---|---|---|---|---|---|
| 1 | `ai vs human text/ai_vs_human_text_2026.csv` | 2000 (1334/666) | Validation benchmark **now** (already wired in `ai_writing_benchmark.py`); train DistilBERT text head | AI-text | OK |
| 2 | `Fake…/…global_2.0…with_missing.xlsx` | 3000 (**1941/1059**, 24 cols) | Train tabular model; calibrate profile/handle thresholds | authenticity/behavioral | **Locked out** — `.xlsx` rejected by `discovery.py` |
| 3 | `Fake…/reddit_dead_internet…csv` | 500 (282/218; bot reply-delay **6s** vs human **1756s**) | Calibrate temporal/age thresholds; small benchmark | behavioral | OK but **lossy** — adapter drops reply_delay/karma |
| 4 | `activity_botscore.csv` | 11190 (continuous 0–1) | Calibrate bot-score→tier mapping | authenticity | Unsupported (no adapter) |
| 5 | `Fake…/real_users.csv`+`fake_users.csv` | 5000 | Tabular training volume | authenticity | OK but **degenerate** (median statuses/followers/friends = 0 both classes; no text) |
| 6 | `ai vs human text/ai_vs_human_text.csv` | 1000 | Archive | — | Synthetic-template poison ("This is an example of text generated by ChatGPT…") |
| 7 | `ai vs human text/ai_human_detection_v1.csv` | 686 | Archive after scrub | — | **Poison**: ~8% are API error strings labeled `ai` |
| 8 | `Fake…/fake_social_media.csv` | 3000 (**2993/7**) | Archive | — | 99.8% single-class — untrainable |
| 9 | `Fake…/bot_detection_data.csv` | 50000 | **Quarantine/delete** | — | **Random-label poison** (corr(label, every feature) ≈ 0.001); dodged today only by a label-column name miss |
| 10 | `article_discusses_claim` | 793 | Archive | — | Pickled DataFrame, wrong domain (fact-check), ignored by discovery |

- **#1 opportunity:** convert the balanced fsm `.xlsx` → CSV and **extend `features.py`** to
  carry its behavioral columns (similarity scores, follow/unfollow rate) — exactly the
  reach/spam signals the engine otherwise lacks. Pair with the already-wired
  `ai_vs_human_text_2026` benchmark for a real train+validate loop to wake the dormant
  scorer.
- **#1 gap:** **no real coordination ground truth exists.** Zero files match the
  `io_disclosure` adapter (which already exists and labels rows `political_coord`/`high`);
  `coordination_benchmark.py` validates against synthetic scenarios only. The product's one
  novel capability — and the entirely-derived amplification dimension — have no labeled
  real-world coordinated-campaign data to calibrate the 0.40 base / 0.75 floor against.
- **Secondary:** quarantine `bot_detection_data.csv` and scrub `ai_human_detection_v1.csv`
  before either touches a training run — both are active poison dodged today only by
  accident.

---

## Top 20 Tier-2 Weaknesses (ranked by impact on value & trust)

| # | Weakness | Audit area |
|---|---|---|
| 1 | **Amplification measures no real reach** — re-weight of 3 behavioral detectors relabeled "artificial amplification"; like/reply/subscriber data fetched then discarded | Authenticity intelligence |
| 2 | **Coordination over-asserts on thin evidence** (3 accounts/2-min → 80% / "campaign", no corroboration) — first false campaign destroys trust | Intelligence quality / trust |
| 3 | **No actionability** — no watchlist-from-investigation, bulk actions, escalation, next-step, or alerts-on-future-activity | Actionability |
| 4 | **Exculpatory "community"/lowers-suspicion signals surfaced nowhere** — product reads suspicion-only though the engine computes balance | Transparency |
| 5 | **No uncertainty band at the headline** — 74%@conf0.3 looks identical to 74%@conf0.9 | Confidence |
| 6 | **No alternative/benign explanations** in any output (only in code comments) | Transparency |
| 7 | **Single-account analysis blind to the modal commenter** — most videos get ~no per-account signal | Intelligence quality |
| 8 | **Narrative runs on lexical hashing by default** — misses paraphrased campaigns | Intelligence quality |
| 9 | **Narrative inauthenticity score is circular** — derived from abstaining single-account tiers | Intelligence quality |
| 10 | **Signed contributions hidden** (raises/lowers/impact) — only in an expandable sub-panel, not the main breakdown | Explainability |
| 11 | **Intent inference is brittle/overconfident** — keyword-matches its own evidence into accusatory categories from one detector | Trust |
| 12 | **No real coordination ground truth** — novel capability calibrated only on synthetic fixtures | Trust / validation |
| 13 | **Reports lack a "what to do / risk implications / recommended action" section** | Actionability |
| 14 | **`score_adjustments`/`weak_signals` read as calibration, not exculpation** — don't say whether an adjustment raised or lowered the score | Explainability |
| 15 | **Best account dataset locked out** (xlsx gate); richest behavioral columns discarded at the adapter boundary | Dataset leverage |
| 16 | **Commentary only post-save** — users mark verdicts without the most readable synthesis | Explainability / UX |
| 17 | **Poison datasets one rename from contaminating training** (random-label 50k set; error-string set) | Data integrity for intelligence |
| 18 | **Executive report truncates the flagged list** ("5 of 47") — stakeholders can't gauge scope | Communication |
| 19 | **The balanced story exists only in optional LLM prose** behind an API key (GAP-06), not the structured UI/report | Transparency |
| 20 | **Methodology in reports is a generic blurb** — the headline number isn't traceable to inputs in the shareable artifact | Explainability |

---

## Top 10 Highest-Leverage Improvements (ranked by expected user value)

1. **Surface the balanced verdict** — show what *raised and lowered* suspicion (signed
   contributions + the community detector) prominently, with the "why it could be benign"
   framing. Converts a suspicion tool into authenticity *intelligence*. *(Data already
   exists on the payload.)*
2. **Fix or reframe amplification** — ingest the reach signals already fetched
   (like-velocity, reply ratios, time-to-engagement) to make it real; until then, stop
   labeling it "artificial amplification." Honest > impressive.
3. **Calibrate coordination confidence** — require a 2nd corroborating method (or cap
   confidence) for thin clusters; present coordination as a range with the
   innocent-explanation caveat. Kills the trust-destroying false "campaign."
4. **Add a confidence/uncertainty band** to the headline verdict + explain tier cutoffs
   in-product.
5. **Add an actionability layer** — "add flagged to watchlist," "export evidence pack," "set
   alert on future activity," and a recommended next step per verdict. Turns *interesting*
   → *operational*.
6. **Add "alternative explanations / what would change this verdict"** to investigations and
   reports (the directive's investigation-quality standard).
7. **Surface commentary live in the workspace** and feed contributions/adjustments into it so
   the prose explains the balance, not just the suspicion.
8. **Acquire one real coordination ground-truth archive** (Twitter/X transparency — the
   `io_disclosure` adapter already exists) and calibrate coordination/amplification against
   reality.
9. **Unlock + leverage the balanced fsm dataset** (xlsx→CSV) and extend `features.py` to
   carry behavioral columns; quarantine the poison sets. Makes the dormant model worth
   waking.
10. **Make narrative real** — install sentence-transformers and decouple
    `inauthenticity_score` from the abstaining single-account tiers (or de-emphasize
    narrative until it is).

---

## Quick Wins (high impact, low effort)
- Surface signed contributions (raises/lowers) + the community signal in the **main**
  detector breakdown — the data is already on the payload.
- Add a confidence band / "low-confidence" badge to the headline + a one-line tier-cutoff
  explainer.
- **Reframe amplification copy** honestly (+ caveat) until real reach signals land.
- Require ≥2 coordination methods (or cap confidence) before the "campaign" intent label —
  a small scoring guard.
- Render commentary in the live workspace; include contributions in its digest.
- **Quarantine `bot_detection_data.csv` and scrub `ai_human_detection_v1.csv`** (prevent
  accidental training poison) — a manifest/`.gitignore` change.
- Convert the fsm `.xlsx` → CSV to unlock the best account dataset.
- Add "export evidence pack" + "add flagged to watchlist" buttons (watchlist infra exists).

## Deep Improvements (high impact, higher effort)
- A **real amplification detector** built on ingested reach/velocity signals.
- **Coordination calibration on a labeled IO archive** + corroboration requirements + range
  output.
- **Extend the feature contract** to capture dataset behavioral richness; wake the ML scorer
  on *validated real* data.
- **Semantic narrative** (sentence-transformers) + de-circularized inauthenticity +
  paraphrase-campaign detection.
- A full **"investigation answers the 9 questions"** redesign (evidence-for/against,
  alternatives, confidence, takeaway, action) across UI + report.
- A proper **operationalization layer** (watchlist/alerts/escalation/integrations).

---

## Recommended Tier-2 Execution Plan (ROI order)

- **Phase 1 — Surface the truth you already compute (days; highest ROI).** The quick wins:
  show the balanced raises/lowers + community signal, add the confidence band, reframe
  amplification honestly, add the coordination-corroboration guard, surface commentary live,
  quarantine poison + convert the fsm xlsx. *Biggest trust/understanding jump for the least
  effort, and it de-risks the dataset traps. Most of it is presentation of data that already
  exists.*
- **Phase 2 — Earn the trust (weeks; the core-value unlock).** Acquire one real coordination
  ground-truth archive; calibrate coordination/amplification; report real
  precision/recall/FPR; wake the dormant ML scorer on validated real data (fsm +
  `ai_vs_human_text_2026`) with an extended feature vector. *Converts "trust us" into a
  measured number — the thing that makes the product chargeable.*
- **Phase 3 — Make the intelligence real (weeks).** Real amplification (reach signals),
  semantic + de-circularized narrative, and the 9-question investigation redesign.
- **Phase 4 — Operationalize (ongoing).** Watchlist/alerts/export/escalation so findings
  become actions.

### The single highest-value move
**Phase 1's first item — surface what already exists** (the balanced, signed, exculpatory
attribution + a confidence band), paired with the **honest amplification reframe** and the
**coordination corroboration guard**. It is low-effort, it directly flips the product from
"suspicion scorer" toward "authenticity intelligence," and it removes the two findings most
likely to destroy trust the first time a user checks the work.
