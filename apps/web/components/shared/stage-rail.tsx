import { type ReactNode } from 'react';
import { cn } from '@/lib/cn';

/**
 * A numbered stage in a workflow, and the rail that labels one.
 *
 * WHY THIS EXISTS. `/netdetect` was four panels stacked in a column with nothing saying which came
 * first, what any of them was for, or that they were steps in one job rather than four unrelated
 * readouts. An operator arriving at it could tell what each panel showed and not what to do. That
 * is the difference between a debug console wired to endpoints and a tool.
 *
 * The job here has a real order and it is worth stating: run the detector over a scan, review what
 * it found, and keep the operations you confirmed. Each stage says what it is for in one sentence,
 * because a numeral with no explanation is decoration pretending to be a filing system, which is
 * the same rule `SECTION_INDEX` already follows.
 *
 * NOT A WIZARD. Nothing is gated and nothing is disabled: an operator who wants to read the
 * catalogue without running anything should just read it. The numbering describes the work, it does
 * not sequence the interface.
 */
export function Stage({
  n,
  title,
  lede,
  children,
  className,
}: {
  /** Position in the workflow. One-based, because it is read by a person, not indexed by code. */
  n: number;
  title: string;
  /** What this stage is for, in one sentence. Never omit it: see the note above. */
  lede: string;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={cn('space-y-3', className)} aria-labelledby={`stage-${n}`}>
      <div className="flex items-start gap-3">
        {/* The numeral sits on the rail rather than inside the panel, so the panels below stay
            interchangeable and a stage can hold more than one of them. */}
        <span
          aria-hidden
          className={cn(
            'mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-sm',
            'border border-border-1 font-mono text-2xs tabular-nums text-fg-mute',
          )}
        >
          {n}
        </span>
        <div className="min-w-0">
          <h2 id={`stage-${n}`} className="display-hard-sm text-base leading-tight">
            {title}
          </h2>
          <p className="mt-0.5 text-xs text-fg-dim">{lede}</p>
        </div>
      </div>
      <div className="space-y-4 sm:pl-9">{children}</div>
    </section>
  );
}
