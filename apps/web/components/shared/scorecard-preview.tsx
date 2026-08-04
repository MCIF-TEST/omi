import { type Tier } from '@/lib/api';

/**
 * The hero's visual, and a deliberate replacement for the node-graph that sat here before.
 *
 * A force-directed network of glowing dots is the house style of every AI product demo, and worse,
 * it is not what this product returns. OmiSphere returns a per-account score with evidence behind
 * it, so the honest illustration is the readout itself: handles, numbers, tiers, signal coverage.
 * It doubles as the clearest possible statement of what a customer gets, which a decorative graph
 * could never do.
 *
 * Marked SAMPLE, with handles that are obviously placeholders. This product publishes scored claims
 * about real named people, so an illustration that could be mistaken for a real reading of a real
 * account is not a thing to ship, even on a marketing page.
 *
 * Server-rendered, no JS, no animation: the numbers are the point.
 */

type Row = {
  handle: string;
  score: number;
  tier: Tier;
  /** Signals that returned a reading, out of the eight. Nulls are honest here too. */
  read: number;
};

/**
 * Scores and tiers agree with the real bands (`TIER_TITLE` in tier-badge.tsx, mirroring the
 * backend `_tier_for`): LOW under 25, MODERATE 25 to 50, ELEVATED 50 to 75, HIGH 75 and above.
 * A sample whose own numbers contradicted the product's scale would be the exact kind of detail
 * that gives a page away.
 */
const ROWS: Row[] = [
  { handle: '@user_8812049', score: 91, tier: 'high', read: 8 },
  { handle: '@dailygrowthhq', score: 78, tier: 'high', read: 7 },
  { handle: '@marcus_reeve', score: 44, tier: 'moderate', read: 6 },
  { handle: '@k_okonkwo', score: 12, tier: 'low', read: 8 },
  { handle: '@thefilmroom', score: 9, tier: 'low', read: 5 },
];

/** Tier counts across the whole sample section, not just the rows shown. */
const SPREAD: { tier: Tier; count: number }[] = [
  { tier: 'low', count: 16 },
  { tier: 'moderate', count: 5 },
  { tier: 'elevated', count: 2 },
  { tier: 'high', count: 2 },
];

const TOTAL = SPREAD.reduce((n, s) => n + s.count, 0);

export function ScorecardPreview() {
  return (
    <figure className="border border-border-1 bg-bg-elev" style={{ borderRadius: 2 }}>
      {/* Header. Reads as an instrument label, not a card title. */}
      <div className="flex items-center justify-between gap-3 px-3.5 py-2.5 border-b border-border-1 bg-bg">
        <span className="font-mono text-[0.625rem] tracking-[0.18em] uppercase text-fg-mute">
          Sample readout
        </span>
        <span className="font-mono text-[0.625rem] tracking-[0.14em] uppercase text-fg-faint tabular">
          {TOTAL} accounts
        </span>
      </div>

      {/* Column heads. Tiny, so the table below can stay quiet. */}
      <div className="grid grid-cols-[1.75rem_1fr_auto] gap-3 px-3.5 pt-3 pb-1.5 font-mono text-[0.5625rem] tracking-[0.16em] uppercase text-fg-faint">
        <span aria-hidden />
        <span>Account</span>
        <span className="text-right">Omi</span>
      </div>

      <table className="w-full border-collapse">
        <caption className="sr-only">
          Sample OmiSphere output: five accounts with their 0 to 100 OMI score and suspicion tier.
        </caption>
        <thead className="sr-only">
          <tr>
            <th scope="col">Rank</th>
            <th scope="col">Account</th>
            <th scope="col">OMI score</th>
          </tr>
        </thead>
        <tbody>
          {ROWS.map((r, i) => {
            return (
              <tr key={r.handle} className="border-t border-divider first:border-t-0">
                {/* Top-aligned with a nudge onto the handle's baseline. Middle alignment floats
                    the numeral between the handle and the signal ticks, which on a phone (where
                    the row is taller) leaves it attached to neither. */}
                <td className="w-7 pl-3.5 py-2.5 align-top">
                  <span className="idx tabular block pt-[3px]">
                    {String(i + 1).padStart(2, '0')}
                  </span>
                </td>

                <td className="py-2.5 pr-3 align-middle min-w-0">
                  <div className="font-mono text-xs text-fg-dim truncate">{r.handle}</div>
                  {/* Signal coverage. Eight ticks, filled for the dimensions that returned a
                      reading. A dimension with no evidence is left empty rather than shown as a
                      low score, which is the same distinction the product makes everywhere. */}
                  <div className="flex items-center gap-[3px] mt-1.5" aria-hidden>
                    {Array.from({ length: 8 }).map((_, s) => (
                      <span
                        key={s}
                        className="h-[3px] w-3"
                        style={{
                          background:
                            s < r.read ? `var(--tier-${r.tier})` : 'var(--border-2)',
                          opacity: s < r.read ? 0.75 : 1,
                        }}
                      />
                    ))}
                    <span className="idx ml-1.5 normal-case tracking-normal">
                      {r.read}/8
                    </span>
                  </div>
                </td>

                <td className="py-2.5 pr-3.5 align-middle text-right whitespace-nowrap">
                  <div
                    className="stat-value text-xl tabular"
                    style={{ color: `var(--tier-${r.tier})` }}
                  >
                    {r.score}
                  </div>
                  <div className="font-mono text-[0.5625rem] tracking-[0.14em] uppercase text-fg-faint mt-0.5">
                    {r.tier}
                  </div>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>

      {/* Spread. The reassuring half of the product: most of a section comes back clean, and
          the page should say so rather than implying everything gets flagged. */}
      <div className="px-3.5 pt-3 pb-3.5 border-t border-border-1">
        <div className="flex items-center justify-between gap-3 mb-2">
          <span className="font-mono text-[0.5625rem] tracking-[0.16em] uppercase text-fg-faint">
            Spread
          </span>
          <span className="font-mono text-[0.5625rem] tracking-[0.14em] uppercase text-fg-faint tabular">
            {SPREAD[0].count} of {TOTAL} clean
          </span>
        </div>
        <div className="flex h-1.5 w-full overflow-hidden" style={{ borderRadius: 1 }}>
          {SPREAD.map((s) => (
            <span
              key={s.tier}
              style={{
                width: `${(s.count / TOTAL) * 100}%`,
                background: `var(--tier-${s.tier})`,
              }}
            />
          ))}
        </div>
      </div>

      <figcaption className="sr-only">
        Illustrative sample of OmiSphere output. The handles shown are placeholders and are not real
        accounts or real readings.
      </figcaption>
    </figure>
  );
}
