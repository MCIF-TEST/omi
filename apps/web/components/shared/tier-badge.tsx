import { cn } from '@/lib/cn';
import { type Tier } from '@/lib/api';

interface TierBadgeProps {
  tier: Tier | null | undefined;
  className?: string;
  size?: 'sm' | 'md' | 'lg';
}

const BG: Record<Tier | 'unknown', string> = {
  low:      'bg-tier-low/10 border-tier-low/40 text-tier-low',
  moderate: 'bg-tier-moderate/10 border-tier-moderate/40 text-tier-moderate',
  elevated: 'bg-tier-elevated/10 border-tier-elevated/40 text-tier-elevated',
  high:     'bg-tier-high/10 border-tier-high/40 text-tier-high shadow-glow-danger',
  unknown:  'bg-bg-elev border-border-2 text-fg-mute',
};

const DOT: Record<Tier | 'unknown', string> = {
  low:      'bg-tier-low',
  moderate: 'bg-tier-moderate',
  elevated: 'bg-tier-elevated',
  high:     'bg-tier-high',
  unknown:  'bg-fg-mute',
};

const SIZE: Record<NonNullable<TierBadgeProps['size']>, string> = {
  sm: 'text-2xs px-1.5 py-0.5',
  md: 'text-xs px-2 py-0.5',
  lg: 'text-xs px-3 py-1',
};

// Numeric meaning of each tier — must mirror the backend `_tier_for` bands
// (LOW <0.25, MODERATE <0.50, ELEVATED <0.75, HIGH ≥0.75). Surfaced as a
// title so the scale travels with the badge everywhere it appears, letting a
// journalist or analyst interpret (and cite) the label without reading code.
const TIER_TITLE: Record<Tier | 'unknown', string> = {
  low: 'LOW — under 25% modeled probability of inauthentic / coordinated behavior.',
  moderate: 'MODERATE — 25–50% modeled probability of inauthentic / coordinated behavior.',
  elevated: 'ELEVATED — 50–75% modeled probability of inauthentic / coordinated behavior.',
  high: 'HIGH — 75% or higher modeled probability of inauthentic / coordinated behavior.',
  unknown: 'Not enough data to assign a tier.',
};
const TIER_SCALE =
  ' Scale: LOW <25 · MODERATE 25–50 · ELEVATED 50–75 · HIGH ≥75 (percent). ' +
  'A probability with uncertainty — not a verdict.';

export function TierBadge({ tier, className, size = 'md' }: TierBadgeProps) {
  const key = (tier || 'unknown') as Tier | 'unknown';
  return (
    <span
      title={TIER_TITLE[key] + (key === 'unknown' ? '' : TIER_SCALE)}
      className={cn(
        'inline-flex items-center gap-1.5 rounded-full border font-mono uppercase tracking-wider',
        BG[key],
        SIZE[size],
        className,
      )}
    >
      {/* status-dot: the dot EMITS its color (tiny glow) — a status light, not paint */}
      <span
        className={cn(
          'w-1.5 h-1.5 rounded-full shrink-0 status-dot',
          DOT[key],
          key === 'high' && 'animate-pulse-dot',
        )}
      />
      {tier || 'unknown'}
    </span>
  );
}
