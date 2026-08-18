import { type HTMLAttributes, type ReactNode, forwardRef } from 'react';
import { cn } from '@/lib/cn';

interface CardProps extends HTMLAttributes<HTMLDivElement> {
  /** Adds hover border brightening. */
  interactive?: boolean;
  /** Accent blue static border variant. */
  gradient?: boolean;
  /**
   * Drops the padding so a `CardHead` can sit flush against the frame.
   * A header bar has to touch its own border to read as a header; inside a
   * padded box it is just a bold line with a gap around it.
   */
  flush?: boolean;
  /**
   * Registration ticks at the four corners. Rationed on purpose: the primary
   * readout on a page, never every panel on it.
   */
  ticks?: boolean;
}

export const Card = forwardRef<HTMLDivElement, CardProps>(
  ({ className, interactive, gradient, flush, ticks, ...props }, ref) => (
    <div
      ref={ref}
      className={cn(
        // surface-lit: every raised slab catches the room light on its top edge
        'rounded-xl surface-lit',
        // 18px, down from 24. Density is most of the difference between a
        // console and a content page: at 24 a column of panels reads as a feed
        // of cards, because the gaps inside them compete with the gaps between.
        flush ? 'overflow-hidden' : 'p-[18px]',
        gradient
          ? 'gradient-border'
          : 'bg-bg-elev border border-border-1',
        interactive && 'card-interactive',
        ticks && 'tick-frame',
        className,
      )}
      {...props}
    />
  ),
);
Card.displayName = 'Card';

/**
 * The panel header bar: label hard left in the data voice, meta hard right,
 * hairline under, sitting on its own ground. Requires `flush` on the Card.
 *
 * This is the single biggest thing separating an instrument panel from a
 * card with a bold line at the top. A fixed 34px bar means a column of panels
 * lines up like a rack whatever their contents.
 */
export function CardHead({
  label,
  meta,
  children,
  className,
}: {
  label: ReactNode;
  /** Right-hand readout: a count, a status, an id. Kept short. */
  meta?: ReactNode;
  /** Controls. Sit beside the meta, right-aligned. */
  children?: ReactNode;
  className?: string;
}) {
  return (
    <div className={cn('panel-head', className)}>
      <span className="meta meta-hi truncate">{label}</span>
      {(meta || children) && (
        <span className="flex items-center gap-3 shrink-0">
          {meta && <span className="meta tabular">{meta}</span>}
          {children}
        </span>
      )}
    </div>
  );
}

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
      // The label voice is mono product-wide now: a uniform, tracked, uppercase
      // data label is what makes a screen read as instrumented. Sans small caps
      // read as a section title in a document.
      className={cn('meta meta-hi mb-3', className)}
      {...props}
    />
  ),
);
CardLabel.displayName = 'CardLabel';
