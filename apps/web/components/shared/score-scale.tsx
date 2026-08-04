/**
 * The 0-to-100 scale, rendered as the instrument face it actually is.
 *
 * The score is the product's single output and it was previously mentioned only in passing, inside
 * sentences. Given a section of its own, at size, it does two things at once: it tells a visitor
 * exactly what the number means, and it makes clear that the number is a judgement with thresholds
 * behind it rather than a friendly percentage.
 *
 * The bands and the evidence each one demands are the real ones, taken from the engine's tier
 * bounds and the analyst constitution's score discipline (50 and above needs two independent
 * discriminative indicators; 75 and above needs several converging plus a statable reason the
 * innocent explanation fails). Stating the burden of proof publicly is the strongest possible
 * claim to seriousness, and it is only available to a product that actually imposes one.
 *
 * Server-rendered, no JS.
 */

const BANDS = [
  {
    tier: 'low',
    range: '0-24',
    label: 'Low',
    burden: 'Reads like a person.',
  },
  {
    tier: 'moderate',
    range: '25-49',
    label: 'Moderate',
    burden: 'Something is off. Not enough to name it.',
  },
  {
    tier: 'elevated',
    range: '50-74',
    label: 'Elevated',
    burden: 'Two independent indicators, converging.',
  },
  {
    tier: 'high',
    range: '75-100',
    label: 'High',
    burden: 'Several converge, and the innocent explanation fails.',
  },
] as const;

export function ScoreScale() {
  return (
    <div>
      {/* The bar. Four equal quarters, hard edges, no rounding: this is a scale, not a meter. */}
      <div className="flex h-11 w-full border border-border-1" role="img" aria-label="The OMI scale runs 0 to 100 in four bands: low 0 to 24, moderate 25 to 49, elevated 50 to 74, high 75 to 100.">
        {BANDS.map((b) => (
          <div
            key={b.tier}
            className="flex-1 border-r border-bg-deep last:border-r-0"
            style={{ background: `var(--tier-${b.tier})` }}
          />
        ))}
      </div>

      {/* Ticks. Sit directly under the band boundaries they mark, so the numbers belong to the
          scale rather than floating beneath it. */}
      <div className="flex mt-2" aria-hidden>
        {['0', '25', '50', '75'].map((n) => (
          <div key={n} className="flex-1 border-l border-border-2 pl-2">
            <span className="stat-value text-xs text-fg-mute tabular">{n}</span>
          </div>
        ))}
        <div className="border-l border-border-2 pl-2">
          <span className="stat-value text-xs text-fg-mute tabular">100</span>
        </div>
      </div>

      {/* The burden of proof for each band. */}
      <dl className="grid sm:grid-cols-2 lg:grid-cols-4 gap-px bg-border-1 border border-border-1 mt-8">
        {BANDS.map((b) => (
          <div key={b.tier} className="bg-bg-deep p-4 md:p-5">
            <dt className="flex items-baseline gap-2 mb-2.5">
              <span
                className="h-2.5 w-2.5 shrink-0 translate-y-px"
                style={{ background: `var(--tier-${b.tier})` }}
                aria-hidden
              />
              <span className="font-mono text-[0.625rem] tracking-[0.16em] uppercase text-fg">
                {b.label}
              </span>
              <span className="stat-value text-[0.625rem] text-fg-faint tabular ml-auto">
                {b.range}
              </span>
            </dt>
            <dd className="text-sm text-fg-mute leading-relaxed">{b.burden}</dd>
          </div>
        ))}
      </dl>
    </div>
  );
}
