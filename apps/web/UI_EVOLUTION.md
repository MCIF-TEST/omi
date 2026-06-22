# OmiSphere UI Evolution V1 — Product Design Transformation

> Living record of the complete UI transformation toward **"the intelligence layer
> for online authenticity."** Frontend/design only — no backend, scoring, API, DB,
> or ML changes. Every increment is `typecheck` + `next build` verified.

Design references (`/references/`) are **taste guidance only** — principles, not
clones: Linear (clarity/density/hierarchy), Perplexity (evidence/reasoning/
citations), Arc (workspace/contextual panels), Vercel (premium polish), Stripe
(trust/onboarding). The identity is uniquely OmiSphere.

---

## A. UI audit summary (current state → problems)

The pre-existing UI was already competent (coherent dark theme, custom primitives,
~18 screens) but read as a *capable tool*, not a *premium intelligence platform*:

1. **Amateur tells:** uniform mono-uppercase labels everywhere (HUD cosplay),
   blue-tinted near-black that felt "gamer HUD" rather than premium, glow/grain
   used decoratively, 8px radius + inner-shimmer cards that looked templated.
2. **Friction:** search/command buried as a small top-right link; nav active-state
   was a thin bar with low presence; inputs were mono and cramped.
3. **Weak hierarchy:** stats, labels, and body text competed at similar weights;
   little use of scale/whitespace to lead the eye; cards all looked equally important.
4. **Components needing replacement:** badges (sharp chips), inputs (mono/glow),
   dialogs (hard shadow), tables (card-grids where tables belong), score displays
   (numbers without reasoning), empty/loading states (generic).
5. **Confusing workflows:** the verdict surfaces showed a score but buried the
   *why* (evidence/contributions/confidence the engine already computes).
6. **Mission mismatch:** felt like a social-analytics dashboard, not an OSINT /
   intelligence command center. Violet (a brand color) was unused.

## B. Design decisions (the OmiSphere identity system)

- **Canvas:** refined **neutral obsidian** (premium, legible at density) — not
  blue-black. Chroma is reserved for *signal*.
- **Identity = electric blue → violet.** Blue = primary action / authenticity;
  **violet = AI reasoning / coordination.** Expressed as a signature
  `--grad-brand` gradient (nav indicator, section ticks, gradient-border panels,
  aurora headers, score rings) — restrained, never wallpaper.
- **Atmosphere, not decoration:** a subtle `.aurora` blue+violet field on headers/
  hero; `glow-violet` / `glow-brand` shadows for elevated intelligence surfaces.
- **Evidence is the spine.** Every analytical screen must answer: *What happened?
  Why does Omi believe it? What evidence? How confident? What next?* Confidence
  reads as **desaturation** (`confidence-*`), separate from the probability tiers.
- **Type:** Space Grotesk (display, tight tracking) for headings + stat values;
  Inter (body); JetBrains Mono reserved for data/IDs/labels — no longer the body voice.
- **Motion tiers:** `--dur-hover/panel/view` with `ease-omi` (organic) + `ease-mech`
  (mechanical reveals) — motion confirms state, never decorates.
- **Cluster-as-color:** persistent `cluster-1..8` hues so analysts navigate
  campaigns/narratives by hue across views.

## C. Components redesigned (running)

| Component | Change | Status |
|---|---|---|
| Color system / tokens | neutral obsidian + blue→violet identity, gradient, aurora, glows, confidence + cluster + evidence palettes | ✅ |
| Button | sentence-case, refined variants | ✅ |
| Card | flat hairline, 12px radius, dropped HUD shimmer | ✅ |
| Badge | pill (rounded-full), neutral surface | ✅ |
| Input / Label | modern sans + soft accent ring focus | ✅ |
| Dialog | 12px panel + premium overlay shadow | ✅ |
| Sidebar | intelligence workspace: aurora brand header, gradient section ticks, blue→violet active indicator, live "engine online" status | ✅ |
| Topbar | command-center bar: prominent ⌘K command trigger, telemetry chips | ✅ |
| ConfidenceBand | desaturation-based confidence | ✅ |
| Tables / data grids | compact, sortable, tnum, sticky headers | ⏳ |
| Score displays (OmiScore) | score + contributing signals + confidence + evidence trail | ⏳ |
| Timelines / charts | evidence timelines, spread/activity viz | ⏳ |
| Empty / loading states | teaching empty states, layout-matched skeletons | ⏳ |
| Command palette / sheets / tooltips | popups polish | ⏳ |

## D. Pages improved (running)

- ✅ **App shell (all authenticated pages)** — new frame via sidebar + topbar + tokens.
- ⏳ Dashboard (intelligence workspace), Investigate workspace, Investigation detail,
  Campaigns list/detail, Narratives list/detail, Account detail, Graph, Reports,
  Content DB, Monitoring, Settings, Landing, Auth.

## E. Before / after (so far)

- **Before:** blue-tinted HUD, mono-uppercase everywhere, thin nav bar, buried
  search, sharp templated cards, decorative glow/grain.
- **After:** premium neutral-obsidian canvas with a deliberate blue→violet
  intelligence signature; aurora-tinted workspace shell; a real command bar;
  pill badges, soft-ring inputs, gradient-bordered intelligence panels, and
  confidence rendered as honest desaturation. The frame already reads as a
  different, more serious product.

## F. Remaining design recommendations (roadmap, moat-first)

1. **OmiScore as reasoning** — never a bare number: ring + contributing signals
   (signed contributions) + confidence band + "what raised / lowered" + evidence
   trail. Make this the template for every verdict.
2. **Investigation workspace** — Perplexity-style two-pane: verdict "stage" +
   calm evidence reading surface; provenance on every figure.
3. **Cluster-color everywhere** — campaigns/narratives/graph share hue identity.
4. **Graph as hero** — cluster-colored nodes, edge=corroboration, focus + "why
   linked" drawer.
5. **Reports = intelligence briefings** — structured, citable, briefing-grade.
6. **Dense tables + evidence-syntax blocks** for source data.
7. **States + motion pass** — teaching empties, layout skeletons, list/drawer motion.
8. **Mobile + a11y sweep** — contrast, hit targets, reduced-motion (partly done).
