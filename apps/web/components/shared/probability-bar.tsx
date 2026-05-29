import { cn } from '@/lib/cn';
import { type Tier } from '@/lib/api';

interface ProbabilityBarProps {
  value: number;            // 0..1
  tier?: Tier | null;
  className?: string;
  showLabel?: boolean;
  size?: 'sm' | 'md';
}

const FILL: Record<Tier, string> = {
  low:      'bg-tier-low',
  moderate: 'bg-tier-moderate',
  elevated: 'bg-tier-elevated',
  high:     'bg-tier-high',
};

export function ProbabilityBar({
  value, tier, className, showLabel = true, size = 'md',
}: ProbabilityBarProps) {
  const pct = Math.max(0, Math.min(100, Math.round(value * 100)));
  const fill = tier ? FILL[tier] : 'bg-accent';
  const h = size === 'sm' ? 'h-1' : 'h-1.5';
  return (
    <div className={cn('flex items-center gap-2', className)}>
      <div className={cn('flex-1 bg-bg rounded-full overflow-hidden ring-1 ring-border-1/60', h)}>
        <div
          className={cn('bar-fill h-full rounded-full transition-all duration-700 ease-omi', fill)}
          style={{ width: `${Math.max(2, pct)}%` }}
        />
      </div>
      {showLabel && (
        <span className="font-mono text-xs text-fg-dim mono w-9 text-right">{pct}%</span>
      )}
    </div>
  );
}
