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
  high:     'bg-tier-high/10 border-tier-high/40 text-tier-high',
  unknown:  'bg-bg-elev border-border-2 text-fg-mute',
};

const SIZE: Record<NonNullable<TierBadgeProps['size']>, string> = {
  sm: 'text-2xs px-1.5 py-0.5',
  md: 'text-xs px-2 py-0.5',
  lg: 'text-xs px-3 py-1',
};

export function TierBadge({ tier, className, size = 'md' }: TierBadgeProps) {
  const key = (tier || 'unknown') as Tier | 'unknown';
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1 rounded-sm border font-mono uppercase tracking-wider',
        BG[key],
        SIZE[size],
        className,
      )}
    >
      {tier || 'unknown'}
    </span>
  );
}
