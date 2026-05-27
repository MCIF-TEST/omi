import { type HTMLAttributes, forwardRef } from 'react';
import { cn } from '@/lib/cn';

export const Card = forwardRef<HTMLDivElement, HTMLAttributes<HTMLDivElement>>(
  ({ className, ...props }, ref) => (
    <div
      ref={ref}
      className={cn(
        'bg-bg-elev border border-border-1 rounded-md p-6',
        className,
      )}
      {...props}
    />
  ),
);
Card.displayName = 'Card';

export const CardTitle = forwardRef<HTMLHeadingElement, HTMLAttributes<HTMLHeadingElement>>(
  ({ className, ...props }, ref) => (
    <h3
      ref={ref}
      className={cn('text-lg font-semibold text-fg tracking-tight mb-2', className)}
      {...props}
    />
  ),
);
CardTitle.displayName = 'CardTitle';

export const CardLabel = forwardRef<HTMLDivElement, HTMLAttributes<HTMLDivElement>>(
  ({ className, ...props }, ref) => (
    <div
      ref={ref}
      className={cn(
        'font-mono text-2xs tracking-[0.18em] text-fg-mute uppercase mb-3',
        className,
      )}
      {...props}
    />
  ),
);
CardLabel.displayName = 'CardLabel';
