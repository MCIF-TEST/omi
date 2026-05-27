# OMISPHERE — Design System

A futuristic intelligence-terminal aesthetic: dark, deliberate, calm. Not a
cyberpunk Hollywood UI. The reference points are Bloomberg Terminal,
Palantir Gotham, Mapbox Studio — interfaces that pack dense information
without feeling cluttered.

---

## Tokens

### Color

```css
:root {
  /* Surfaces */
  --bg-deep:      #030611;   /* page background */
  --bg:           #060a16;   /* default surface */
  --bg-elev:      #0b1124;   /* elevated cards */
  --bg-elev-2:    #111a30;   /* nested panels */

  /* Borders */
  --border:       #161e34;
  --border-2:     #1f2a48;
  --border-hot:   #2e3f6f;   /* active/selected */

  /* Text */
  --text:         #e7ecf5;   /* primary */
  --text-dim:     #a3afca;   /* secondary */
  --text-mute:    #6b7894;   /* labels, metadata */
  --text-faint:   #3a4664;   /* disabled */

  /* Accents — use sparingly */
  --accent:       #22d3ee;   /* primary action / active */
  --accent-2:     #67e8f9;   /* hover */
  --accent-dim:   #0e7490;   /* subdued accent (borders, backgrounds) */

  /* Status */
  --tier-low:       #10b981;
  --tier-moderate:  #f59e0b;
  --tier-elevated:  #fb923c;
  --tier-high:      #ef4444;

  --ok:           var(--tier-low);
  --warn:         var(--tier-moderate);
  --danger:       var(--tier-high);

  /* Graph cluster palette (rotates by cluster id) */
  --graph-1: #22d3ee;
  --graph-2: #a78bfa;
  --graph-3: #f472b6;
  --graph-4: #fb923c;
  --graph-5: #facc15;
  --graph-6: #34d399;
}
```

### Typography

| Token | Family | Use |
|-------|--------|-----|
| `--font-sans` | Inter | All narrative + UI text |
| `--font-mono` | JetBrains Mono | IDs, scores, timestamps, data tables |

Scale (rem):

| Token | Size | Use |
|-------|------|-----|
| `--text-xs`  | 0.75 | Metadata, chips |
| `--text-sm`  | 0.875 | Secondary text |
| `--text-base` | 1.0 | Body |
| `--text-lg`  | 1.125 | Card headings |
| `--text-xl`  | 1.375 | Section headings |
| `--text-2xl` | 1.875 | Page titles |
| `--text-3xl` | 2.5 | Hero numbers (probability, big counts) |

### Spacing

Tailwind defaults — 4 px scale. Use `gap-*` and `space-*` rather than
margin where possible.

### Radii

Sharp by default (`radius: 4px`). The aesthetic is precise, not rounded.
Modal corners and avatars go to `8px` max.

### Motion

| Property | Value |
|----------|-------|
| `--ease` | cubic-bezier(0.16, 1, 0.3, 1) |
| `--dur-fast` | 120ms |
| `--dur` | 200ms |
| `--dur-slow` | 400ms |

Use motion for **state transitions** (entering, expanding, focusing).
Never for decoration.

---

## Component primitives

Located in `apps/web/components/ui/`. Hand-rolled, not auto-installed
via `npx shadcn`, but follow the shadcn philosophy: unstyled headless
primitives + thin theming layer.

### Phase 1 set

| Component | Purpose |
|-----------|---------|
| `Button` | Primary, secondary, ghost, danger variants. Sm / md / lg sizes. |
| `Input` | Text inputs; matches design tokens. |
| `Label` | Form labels (mono, small, uppercase letter-spacing). |
| `Card` | Surface container with optional title + footer. |
| `Badge` | Tier pills, intent pills, status indicators. |
| `Pill` | Smaller than Badge; metadata chips. |
| `Tabs` | Horizontal tab strip. |
| `Dialog` | Modal overlay. |
| `Sheet` | Slide-over panel (right side). |
| `Skeleton` | Loading placeholders. |
| `AppShell` | Layout wrapper: top bar + sidebar + main. |

### Phase 5+ set

| Component | Purpose |
|-----------|---------|
| `GraphCanvas` | Cytoscape wrapper with themed nodes/edges. |
| `Timeline` | Vertical scrollable activity feed. |
| `DataTable` | Sortable, filterable, column-resizable table. |
| `Probability` | The big-number display with tier coloring. |
| `Evidence` | Collapsible evidence chain. |
| `Heatmap` | Time-grid intensity map. |
| `CommandPalette` | Cmd+K jump-to-anything. |

---

## Layout patterns

**App shell**

```
┌─────────────────────────────────────────────────────┐
│ Top bar: brand · search · credits · account         │
├──────┬──────────────────────────────────────────────┤
│      │                                              │
│ Side │  Main content (page-specific)                │
│ nav  │                                              │
│      │                                              │
└──────┴──────────────────────────────────────────────┘
```

* Top bar: 56 px, sticky, dark + 1 px bottom border
* Sidebar: 240 px on desktop, collapsible to icons on smaller screens,
  hidden on mobile (replaced by hamburger drawer)
* Main: max-width 1440 px, padded 24 px

**Investigation workspace** (Phase 5)

Three-pane layout — list / graph / detail. Each pane is resizable.

**Marketing pages** (`/pricing`, `/about`)

Single-column, max-width 720 px, generous spacing. No sidebar.

---

## Iconography

* Primary set: **Lucide React** (open source, consistent, weight-tunable).
* Stroke 1.5 px, 16 / 20 / 24 px sizes.
* No emoji in product UI.

---

## Voice + microcopy

Probabilistic, calm, evidence-bearing:

* Good: "Patterns consistent with synthetic engagement."
* Bad: "This account is a bot."

* Good: "Out of credits — subscribe to continue."
* Bad: "Payment required."

* Good: "3 free trial scans on signup. No card required."
* Bad: "Start your free trial now!"

No exclamation marks anywhere in product UI.

---

## Accessibility

* All interactive elements keyboard-reachable.
* Focus states visible (2 px accent outline, never `outline: none`).
* Color contrast ≥ 4.5:1 for body text, ≥ 3:1 for large text.
* Screen-reader labels on icon-only buttons.
* Cmd+K palette is the universal escape hatch.

---

## What to avoid

* Gradients in product chrome (gradients ok on graph nodes only).
* Drop shadows deeper than `0 8px 24px rgba(0,0,0,0.4)`.
* Heavy borders on every element — pick borders OR background tone, not both.
* Monospace in body text.
* Emoji.
* Heavy patterns / grid backgrounds outside the marketing pages.
