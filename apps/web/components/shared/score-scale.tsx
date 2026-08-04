/**
 * The 0-to-100 scale, rendered as the instrument face it is.
 *
 * The ranges sit INSIDE the bands, in near-black on the band colour, rather than as tick labels
 * underneath. That is the difference between a chart annotated with numbers and a gauge whose
 * numbers are part of it, and it is most of why this reads as an instrument.
 *
 * Bands and burdens are the real ones, from the engine's tier bounds and the analyst
 * constitution's score discipline: 50 and above needs two independent discriminative indicators,
 * 75 and above needs several converging plus a statable reason the innocent explanation fails.
 * Stating the burden publicly is the strongest claim to seriousness available, and it is only
 * available to a product that actually imposes one.
 *
 * The asymmetry note is not a disclaimer. A tool that assigns a number to a named person and does
 * not say which way it errs is hiding the only thing that makes the number trustworthy.
 *
 * Server-rendered, no JS. Near-black on every band clears 5.5:1 at the worst case (red).
 */

const BANDS = [
  {
    tier: 'low',
    range: '0-24',
    label: 'Low',
    burden: 'Behaves like a person.',
  },
  {
    tier: 'moderate',
    range: '25-49',
    label: 'Moderate',
    burden: 'Irregular. Not enough to name it.',
  },
  {
    tier: 'elevated',
    range: '50-74',
    label: 'Elevated',
    burden: 'Two independent indicators converge.',
  },
  {
    tier: 'high',
    range: '75-100',
    label: 'High',
    burden: 'Converging evidence. No innocent reading survives it.',
  },
] as const;

export function ScoreScale() {
  return (
    <div>
      <div
        className="flex h-16 w-full border border-border-2"
        role="img"
        aria-label="The OMI scale runs 0 to 100 in four bands: low 0 to 24, moderate 25 to 49, elevated 50 to 74, high 75 to 100."
      >
        {BANDS.map((b) => (
          <div
            key={b.tier}
            className="flex-1 flex items-center justify-center border-r-2 border-bg-deep last:border-r-0"
            style={{ background: `var(--tier-${b.tier})` }}
          >
            <span
              className="stat-value text-base sm:text-lg font-semibold tabular"
              style={{ color: '#010203' }}
            >
              {b.range}
            </span>
          </div>
        ))}
      </div>

      <dl className="grid grid-cols-2 lg:grid-cols-4 gap-px bg-border-1 border-x border-b border-border-1">
        {BANDS.map((b) => (
          <div key={b.tier} className="bg-bg-deep px-3.5 py-4">
            <dt
              className="font-mono text-[0.625rem] tracking-[0.18em] uppercase mb-2"
              style={{ color: `var(--tier-${b.tier})` }}
            >
              {b.label}
            </dt>
            <dd className="text-sm text-fg-dim leading-snug">{b.burden}</dd>
          </div>
        ))}
      </dl>

      {/* Which way the instrument errs, stated up front. */}
      <p className="mt-6 text-sm text-fg-mute leading-relaxed max-w-[62ch]">
        <span className="text-fg">The errors are not symmetric.</span> Calling a real person bought
        is the expensive mistake, because the reader cannot check it and one bad score discredits
        every other number beside it. On balanced evidence the engine returns the lower score.
      </p>
    </div>
  );
}
