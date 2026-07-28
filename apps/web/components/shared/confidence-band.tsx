'use client';

import { cn } from '@/lib/cn';

/**
 * ConfidenceBand, a verdict is a number AND its uncertainty, never a bare
 * point estimate. Plots the probability on a 0..1 track with an uncertainty
 * halo whose width grows as confidence falls: high confidence -> a sharp tick;
 * low confidence -> a wide band the investigator can SEE is tentative.
 *
 * `confidence` here is "data sufficiency". How much evidence backed the
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
  // Confidence reads as DESATURATION (not a tier hue, which would collide with the
  // probability colour): high = crisp/opaque, low = faint + muted label.
  const confLabel =
    cCl >= 0.7 ? 'high' : cCl >= 0.4 ? 'moderate' : 'low, thin evidence';
  const confText =
    cCl >= 0.7 ? 'text-fg' : cCl >= 0.4 ? 'text-fg-dim' : 'text-confidence-weak';
  const bandOpacity = 0.14 + cCl * 0.22; // 0.14 (tentative) → 0.36 (firm)

  return (
    <div>
      <div className="flex items-center justify-between font-mono text-2xs uppercase tracking-[0.18em] text-fg-mute mb-1.5">
        <span>{label}</span>
        <span
          className={cn('tabular', confText)}
          title="How much data backed this estimate (mean detector confidence). Low confidence means the verdict is tentative. Treat it cautiously, not as firm."
        >
          confidence {Math.round(cCl * 100)}% · {confLabel}
        </span>
      </div>
      <div
        className="relative h-3 bg-bg-inset inset-hairline rounded-md overflow-hidden"
        role="img"
        aria-label={`Probability ${Math.round(pCl * 100)}%, confidence ${Math.round(cCl * 100)}%`}
      >
        <div
          className="absolute top-0 bottom-0 bg-accent rounded-sm"
          style={{ left: `${leftPct}%`, width: `${bandPct}%`, opacity: bandOpacity }}
        />
        <div
          className="absolute top-0 bottom-0 w-[3px] bg-accent rounded-full shadow-glow-sm"
          style={{ left: `calc(${tickPct}% - 1.5px)` }}
        />
      </div>
      <div className="mt-1 flex justify-between font-mono text-[0.55rem] uppercase tracking-[0.18em] text-fg-faint tabular">
        <span>0%</span>
        <span>50%</span>
        <span>100%</span>
      </div>
    </div>
  );
}
