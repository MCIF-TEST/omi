import { cn } from '@/lib/cn';
import { type Tier } from '@/lib/api';

interface ProbabilityBarProps {
  value: number;            // 0..1
  tier?: Tier | null;
  className?: string;
  showLabel?: boolean;
  size?: 'sm' | 'md';
  /**
   * Hide the tier graduations. Only for bars that are NOT on the 0-100 OMI
   * scale, where marks at 25/50/75 would claim boundaries that do not exist.
   */
  ungraduated?: boolean;
}

const FILL: Record<Tier, string> = {
  low:      'bg-tier-low',
  moderate: 'bg-tier-moderate',
  elevated: 'bg-tier-elevated',
  high:     'bg-tier-high',
};

/**
 * The linear score meter.
 *
 * Graduated and square, not a stadium fill. The three marks are the real tier
 * boundaries (25 / 50 / 75), the same ones `ScoreScale` names, so a reader can
 * see WHERE a score sits rather than only how full the bar is: 46 and 54 are a
 * band apart and as an unmarked rounded fill they were eight pixels apart and
 * looked identical.
 */
export function ProbabilityBar({
  value, tier, className, showLabel = true, size = 'md', ungraduated = false,
}: ProbabilityBarProps) {
  const pct = Math.max(0, Math.min(100, Math.round(value * 100)));
  const fill = tier ? FILL[tier] : 'bg-accent';
  const h = size === 'sm' ? 'h-1.5' : 'h-2.5';
  return (
    <div className={cn('flex items-center gap-2', className)}>
      <div className={cn('relative flex-1 bg-bg-inset rounded-[1px] overflow-hidden border border-border-1', h)}>
        <div
          className={cn('bar-fill h-full transition-[width] duration-700 ease-omi', fill)}
          style={{ width: `${Math.max(2, pct)}%` }}
        />
        {!ungraduated && (
          <span className="absolute inset-0 pointer-events-none" aria-hidden>
            {[25, 50, 75].map((m) => (
              <span
                key={m}
                className="absolute top-0 bottom-0 w-px bg-bg-deep/70"
                style={{ left: `${m}%` }}
              />
            ))}
          </span>
        )}
      </div>
      {showLabel && (
        <span className="font-mono text-xs text-fg-dim tabular w-9 text-right">{pct}%</span>
      )}
    </div>
  );
}
