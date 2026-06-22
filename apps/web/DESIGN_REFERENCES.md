# OmiSphere UI — Design References & Direction (V1)

> Source material lives in `references/` (Cursor, Airtable, Arc, Linear, Notion,
> Perplexity, Retool, Stripe, Vercel). **We reference strengths; we do not copy.**
> The current UI is already a coherent dark analyst system (`app/globals.css` +
> `tailwind.config.ts`), so this is a **confident evolution**, not a rebuild — we
> preserve the deep-black + electric-blue + tier identity and the ~18 working
> screens, and fold in the references' best ideas where they raise clarity,
> density, and *evidence-first* trust.

---

## 1. What each reference does best (and the one thing to steal)

| Reference | Theme | Core strength | Steal this for OmiSphere |
|---|---|---|---|
| **Linear** ⭐ | dark | Instrument-panel density: 4px grid, 4-step near-black surface stack, elevation via **inset 1px border + restrained shadow**, one rationed accent kept *separate* from status colors, Inter at 510/590 (not 700), mono IDs | The skeleton: dark layered surfaces + hairline elevation + accent-separate-from-semantics |
| **Retool** | dark | **Shadow-free luminance elevation** (cards = lighter/darker slabs); an explicit **motion spec** (easing + duration tiers; animate opacity/transform/color/border only) | A concrete, mechanical motion system + formalized no-shadow elevation |
| **Vercel** | light | Hairline-border layering, near-monochrome chrome, and a **defined code-syntax palette** (strings/props/keywords/errors) | An **evidence/JSON/log syntax palette** for rendering raw source data |
| **Stripe** | light | One electric accent does *all* functional work; **tabular numerals** (`tnum`); gradients atmospheric only | `tnum` everywhere data appears; accent discipline |
| **Airtable** | light | **Color-as-information-architecture**: each category owns a saturated hue acting as a chapter divider | **Per-cluster color identity** for narratives/campaigns/accounts (the standout idea) |
| **Notion** | mixed | Deliberate **dark-stage vs. lighter-reading-surface** split; tabular numerals; disciplined radius roles | A "command/overview" vs. "deep-evidence-reading" surface distinction |
| **Perplexity** | light | Total restraint — hierarchy from **weight + inversion + hairlines**, color reserved for true signal | Guardrail: don't add chrome; let type + surface carry hierarchy |
| **Cursor** | light | Ruthless color rationing (~95% achromatic), editorial single-weight type, mono reserved for code/IDs | Reserve chromatic color for confidence/evidence cues only |
| **Arc** | — | *(placeholder only — no tokens)* dark canvas, selective high-saturation accents, gradient-as-atmosphere | Atmospheric edge-gradient on hero moments (already partly present) |

## 2. Cross-cutting patterns (the consensus of the best)
1. **Rationed action accent, separated from semantics** — one accent for the primary action; a *separate* ramp for status/confidence so "high confidence" can never read as "click me."
2. **Elevation by surface-luminance + inset hairline borders, not drop shadows** — keeps deeply nested panels (campaign → cluster → evidence row) legible.
3. **Compact 4px-grid instrument density** — tight rows, disciplined 8/12/16/24 gaps.
4. **Mono for IDs/evidence; tabular numerals for all figures** — "raw fact" signalling + column-aligned scores.
5. **Color-coded clusters as information architecture** (Airtable) — navigate by hue, not just label.
6. **Weight + inversion as primary emphasis** — type does the work before color.
7. **A defined raw-data / syntax palette** — a coordination tool *must* show source evidence well.
8. **Concrete motion discipline** — motion confirms state changes (filter, drill-down, live update), no theatrics.

## 3. OmiSphere direction — preserve / refine / add

**Preserve (identity):** deep near-black surfaces, electric-blue action accent, the
tier ramp (green→amber→orange→red), Space Grotesk display / Inter body / JetBrains
Mono data, the `ease-omi` curve, glass/grain/grid textures, the topbar+sidebar shell.

**Refine (close the gaps the audit found):**
- **Elevation discipline** — formalize a 5-level surface stack + a single inset-hairline elevation convention (today only `card-interactive` brightens on hover; make affordance consistent).
- **Accent vs. semantics** — make blue the *only* action accent; keep tier/confidence colors strictly for evidence/status (no overlap), so the UI reads as calibrated certainty, not verdict.
- **Buttons** — soften the utilitarian mono-uppercase primary; tone glow on secondary/ghost.
- **Numerals** — enable `tnum` on all scores, counts, dates (scannable evidence tables).
- **Spacing/radius** — consolidate to a 4px scale + 3-tier radius (4 / 6 / 10–12 + pill).
- **Motion** — adopt explicit tiers (≈0.2–0.3s hover/state, 0.4s panel/drawer, 0.6s view) animating opacity/transform/color/border only.

**Add (new, high-value for coordination intelligence):**
- **Cluster-identity palette** — a curated, desaturated-for-dark hue set assigned persistently per narrative/campaign/account cluster, so graph + tables + detail views cross-reference by color (Airtable's idea, applied to coordination).
- **Confidence / uncertainty ramp** — a dedicated scale where **uncertainty reads as desaturation**, separate from the action accent (directly serves evidence-not-verdict).
- **Evidence-syntax palette** — defined colors for rendering raw evidence (handles, IDs, timestamps, JSON, diffs, transcripts) — first-class, not an afterthought.

## 4. Token evolution map (current → proposed)
| Concept | Current | Proposed evolution |
|---|---|---|
| Surfaces | `--bg-deep/bg/elev/elev-2` (4) | add `--bg-elev-3` (inputs/active rows); document each level's role |
| Elevation | mixed (shadows + borders) | **inset hairline first**; drop-shadow only for true overlays (menus/modals/drawers) |
| Action accent | `--accent` blue (+ violet for logo) | unchanged, but enforced as the *only* action color |
| Status/confidence | tier colors double as status | dedicated **confidence ramp** (high emerald · med amber · low = neutral/desaturated) distinct from action accent |
| Cluster identity | — | **new** palette: terracotta · sapphire · forest · violet · marigold · teal (desaturated for dark) |
| Evidence/code | — | **new** syntax palette (string/key/number/error/meta) for raw-data rendering |
| Numerals | default | `font-feature-settings: 'tnum'` on data |
| Radius | 3/4/6/8/12/16 | 3-tier: `4` (tags/inputs) · `6` (buttons/cards/rows) · `10–12` (panels/modals) · `9999` |
| Motion | `ease-omi`, ad-hoc durations | keep curve; add duration tiers (hover/panel/view) as tokens |

## 5. Component refinements (incremental, behind the tokens)
Button (soften primary, calmer ghost/secondary) · Card (one consistent hover/elevation) ·
Badge/TierBadge (confidence-ramp aware) · Table/row (compact, `tnum`, hover) ·
Cluster chip (new — colored dot + label) · Evidence/JSON viewer (new — syntax palette) ·
ConfidenceBand / uncertainty surfacing (lean on desaturation) · Inputs (clearer focus/states).

## 6. Rollout plan (validate before sweeping)
1. **Foundation** — evolve tokens in `globals.css` + `tailwind.config.ts` (surfaces, elevation convention, confidence ramp, cluster palette, evidence palette, `tnum`, radius/motion tiers). Backward-compatible (keep existing token names; add new ones).
2. **Flagship screen** — apply to **one** high-value, evidence-dense view (recommended: the **Campaign detail** or **Investigation/account verdict**) to prove the language on something real. `npm run typecheck` gate.
3. **Primitives** — refine Button/Card/Badge/Table + add Cluster chip + Evidence viewer.
4. **Sweep** — roll across remaining screens screen-by-screen, each typecheck-clean.

Each step is reviewable and reversible; nothing ships until `apps/web` typechecks.

---

*Status: direction proposed — awaiting go before writing UI code. References are
analyzed strengths, adapted originally to OmiSphere's coordination-intelligence
purpose; no design was copied.*
