import { type ReactNode } from 'react';
import { cn } from '@/lib/cn';

/**
 * The workspace page header.
 *
 * Eight routes had each hand-rolled the same twenty-line slab (rounded panel,
 * accent hairline across the top, `.section-label` eyebrow, display h1, lede,
 * a status cluster on the right) and they had already drifted: different
 * paddings, different heading margins, three spellings of the right-hand
 * readout, and `/investigate` with no slab at all. One component fixes the
 * drift and is also where the authority treatment lands once instead of eight
 * times.
 *
 * What it adds over the copies it replaces: a section numeral and a rule, which
 * is the dossier grammar the public pages are built on and which stopped dead
 * at the login boundary. The workspace is the half of this product that
 * actually is a filing system.
 */
export function ConsoleHeader({
  index,
  eyebrow,
  title,
  lede,
  readout,
  children,
  className,
}: {
  /** Two-digit section number. Use `SECTION_INDEX` so the numerals cannot drift. */
  index?: string;
  /** Where this page sits: "Operations · Live intelligence". */
  eyebrow: string;
  title: string;
  lede?: ReactNode;
  /** Right-hand status cluster: a live lamp, a count, a filter. */
  readout?: ReactNode;
  /** Actions, below the lede. */
  children?: ReactNode;
  className?: string;
}) {
  return (
    <header
      className={cn(
        'relative overflow-hidden rounded-xl border border-border-1 bg-bg-elev tick-frame',
        'px-5 py-5 md:px-6',
        className,
      )}
    >
      {/* The identity hairline. A 1px rule, not a fill: the design language
          allows a gradient as a LINE and nowhere else. */}
      <span className="absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-accent/50 to-transparent" />

      <div className="relative flex items-start justify-between gap-4 flex-wrap">
        <div className="min-w-0">
          <div className="flex items-center gap-2.5 min-w-0">
            {index && <span className="meta meta-hi tabular shrink-0">{index}</span>}
            <span className="h-px w-6 bg-border-hot shrink-0" aria-hidden />
            <span className="meta truncate">{eyebrow}</span>
          </div>
          <h1 className="display-hard-sm text-[1.75rem] md:text-[2rem] text-fg mt-2.5">{title}</h1>
          {lede && (
            <p className="mt-2 text-sm text-fg-dim max-w-2xl leading-relaxed">{lede}</p>
          )}
        </div>
        {readout && <div className="flex items-center gap-3 shrink-0">{readout}</div>}
      </div>
      {children && <div className="relative mt-4">{children}</div>}
    </header>
  );
}

/**
 * Section numerals, in the sidebar's own order.
 *
 * Declared once so a page cannot invent its own number and two pages cannot
 * claim the same one. A numeral that does not correspond to anything is
 * decoration pretending to be a filing system, which is worse than no numeral.
 */
export const SECTION_INDEX = {
  '/investigate':    '01',
  '/investigations': '02',
  '/graph':          '03',
  '/narratives':     '04',
  '/monitoring':     '05',
  '/disputes':       '06',
  '/netdetect':      '13',
  '/settings':       '07',
  '/search':         '08',
  '/accounts':       '09',
  '/content':        '10',
  '/channels':       '11',
  '/bulk':           '12',
} as const;
