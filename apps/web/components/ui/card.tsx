import { type HTMLAttributes, forwardRef } from 'react';
import { cn } from '@/lib/cn';

interface CardProps extends HTMLAttributes<HTMLDivElement> {
  /** Adds hover border brightening. */
  interactive?: boolean;
  /** Accent blue static border variant. */
  gradient?: boolean;
}

export const Card = forwardRef<HTMLDivElement, CardProps>(
  ({ className, interactive, gradient, ...props }, ref) => (
    <div
      ref={ref}
      className={cn(
        // surface-lit: every raised slab catches the room light on its top edge
        'rounded-xl p-6 surface-lit',
        gradient
          ? 'gradient-border'
          : 'bg-bg-elev border border-border-1',
        interactive && 'card-interactive',
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
      className={cn('text-[0.95rem] font-semibold text-fg tracking-[-0.01em] mb-2', className)}
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
        'text-2xs font-semibold tracking-[0.12em] text-fg-mute uppercase mb-3',
        className,
      )}
      {...props}
    />
  ),
);
CardLabel.displayName = 'CardLabel';
