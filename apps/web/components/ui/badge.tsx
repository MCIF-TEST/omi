import { type HTMLAttributes } from 'react';
import { cn } from '@/lib/cn';
import { tierBg } from '@/lib/format';
import { type Tier } from '@/lib/api';

interface BadgeProps extends HTMLAttributes<HTMLSpanElement> {
  variant?: 'tier' | 'neutral' | 'accent' | 'warn' | 'danger';
  tier?: Tier;
}

export function Badge({ variant = 'neutral', tier, className, children, ...props }: BadgeProps) {
  let classes = 'border border-border-2 bg-bg-elev text-fg-dim';
  if (variant === 'tier' && tier) {
    classes = tierBg(tier);
  } else if (variant === 'accent') {
    classes = 'border border-accent-dim bg-accent/10 text-accent';
  } else if (variant === 'warn') {
    classes = 'border border-warn/40 bg-warn/10 text-warn';
  } else if (variant === 'danger') {
    classes = 'border border-danger/50 bg-danger/10 text-danger';
  }
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1 px-2 py-0.5 rounded-sm',
        'font-mono text-2xs tracking-wider uppercase',
        classes,
        className,
      )}
      {...props}
    >
      {children}
    </span>
  );
}
