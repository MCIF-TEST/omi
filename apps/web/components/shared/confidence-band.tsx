'use client';

/**
 * ConfidenceBand — a verdict is a number AND its uncertainty, never a bare
 * point estimate. Plots the probability on a 0..1 track with an uncertainty
 * halo whose width grows as confidence falls: high confidence -> a sharp tick;
 * low confidence -> a wide band the investigator can SEE is tentative.
 *
 * `confidence` here is "data sufficiency" — how much evidence backed the
 * estimate (the mean of the detectors' self-reported confidence). It is a
 * surfacing of values the engine already computes, not a new score.
 */
export function ConfidenceBand({
  probability,
  confidence,
  label = 'Score with uncertainty band',
}: {
  probability: number;
  confidence: number;
  label?: string;
}) {
  const pCl = Math.min(1, Math.max(0, probability));
  const cCl = Math.min(1, Math.max(0, confidence));
  const halfWidth = Math.min(0.4, (1 - cCl) * 0.4);
  const left = Math.max(0, pCl - halfWidth);
  const right = Math.min(1, pCl + halfWidth);
  const bandPct = (right - left) * 100;
  const leftPct = left * 100;
  const tickPct = pCl * 100;
  const confLabel =
    cCl >= 0.7 ? 'high' : cCl >= 0.4 ? 'moderate' : 'low — thin evidence';

  return (
    <div>
      <div className="flex items-center justify-between font-mono text-2xs uppercase tracking-wider text-fg-mute mb-1.5">
        <span>{label}</span>
        <span title="How much data backed this estimate (mean detector confidence). Low confidence means the verdict is tentative — treat it cautiously, not as firm.">
          confidence: {Math.round(cCl * 100)}% ({confLabel})
        </span>
      </div>
      <div
        className="relative h-3 bg-bg-elev-2 border border-border-1 rounded-sm overflow-hidden"
        role="img"
        aria-label={`Probability ${Math.round(pCl * 100)}%, confidence ${Math.round(cCl * 100)}%`}
      >
        <div
          className="absolute top-0 bottom-0 bg-accent/25"
          style={{ left: `${leftPct}%`, width: `${bandPct}%` }}
        />
        <div
          className="absolute top-0 bottom-0 w-0.5 bg-accent"
          style={{ left: `calc(${tickPct}% - 1px)` }}
        />
      </div>
      <div className="mt-1 flex justify-between font-mono text-[0.55rem] uppercase tracking-wider text-fg-faint">
        <span>0% low</span>
        <span>50% moderate</span>
        <span>100% high</span>
      </div>
    </div>
  );
}
