import Link from 'next/link';
import { ArrowRight, ScanLine } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { TRIAL_CREDITS_LABEL } from '@/lib/plan';

/**
 * The funnel on a shared report.
 *
 * Someone is reading a report about a post they care about, which is the highest-intent moment this
 * product gets. Three placements, because a long report scrolls past a single one: a strip under the
 * top bar, a sticky rail on wide screens, and a full block at the end.
 *
 * Every one carries the share token to /sign-up?claim=<token>, which is what lets the report they
 * are reading follow them into their own archive after they sign up. Drop the token and the funnel
 * still converts but lands them on an empty dashboard with no idea which post they came from.
 *
 * All three are `no-print`: the report doubles as an exportable document, and a signup pitch inside
 * a PDF someone is using as evidence undermines the thing that made it credible.
 */
function href(token: string): string {
  return `/sign-up?claim=${encodeURIComponent(token)}`;
}

const HEADLINE = 'Scan more comments on this post';

/** What this report leaves out, as a number, or null when the total was never recorded. */
export interface Coverage {
  scanned: number;
  available: number | null;
  readCount: number | null;
}

/**
 * "checked 25 of 312" is the whole argument for signing up, and it is checkable.
 *
 * Returns null rather than a vaguer sentence when the total is missing or not actually larger than
 * the scanned count: a report that covered everything has no gap to sell, and saying otherwise would
 * be the one kind of dishonesty this page cannot afford.
 */
function gapLine(c: Coverage): string | null {
  if (!c.available || c.available <= c.scanned) return null;
  const rest = c.available - c.scanned;
  return `This report checked ${c.scanned.toLocaleString()} of the ${c.available.toLocaleString()} accounts that commented. ${rest.toLocaleString()} have not been looked at.`;
}

/** Real social proof, hidden below a threshold because a low number reads as "nobody cares". */
function readLine(c: Coverage): string | null {
  if (!c.readCount || c.readCount < 25) return null;
  return `Read ${c.readCount.toLocaleString()} times`;
}

/** Thin strip directly under the report's top bar. Seen before any scrolling happens. */
export function ScanMoreStrip({ token, coverage }: { token: string; coverage: Coverage }) {
  const gap = gapLine(coverage);
  return (
    <div className="no-print border-b border-accent/25 bg-accent/[0.06]">
      <div className="max-w-5xl mx-auto px-6 py-2.5 flex items-center gap-3 flex-wrap">
        <ScanLine size={14} className="text-accent shrink-0" aria-hidden />
        <p className="text-sm text-fg flex-1 min-w-0">
          <span className="font-medium">{HEADLINE}.</span>{' '}
          <span className="text-fg-dim">
            {gap ?? 'This report covers only the accounts the author picked.'}
          </span>
        </p>
        <Link href={href(token)} className="shrink-0">
          <Button size="sm">
            Scan this post
            <ArrowRight size={12} />
          </Button>
        </Link>
      </div>
    </div>
  );
}

/**
 * Sticky rail, wide screens only. Hidden below xl because there is no room beside the article and
 * stacking it would just repeat the strip above.
 */
export function ScanMoreRail({ token, coverage }: { token: string; coverage: Coverage }) {
  const gap = gapLine(coverage);
  const reads = readLine(coverage);
  const rest = coverage.available ? coverage.available - coverage.scanned : 0;
  return (
    <aside className="no-print hidden xl:block">
      <div className="sticky top-24 rounded-lg border border-border-1 bg-bg-elev p-4">
        <span className="section-label">Your turn</span>
        {rest > 0 && (
          <p className="stat-value text-3xl text-fg tabular-nums mt-2.5 leading-none">
            {rest.toLocaleString()}
          </p>
        )}
        <p className="display text-base font-semibold text-fg tracking-tight mt-2.5 leading-snug">
          {rest > 0 ? 'accounts nobody has checked' : HEADLINE}
        </p>
        <p className="text-xs text-fg-dim leading-relaxed mt-2">
          {gap
            ? 'Each one comes back with a 0-to-100 score and the evidence behind it.'
            : 'Check the accounts this report left out. Each one comes back with a 0-to-100 score and the evidence behind it.'}
        </p>
        {reads && (
          <p className="font-mono text-2xs tracking-wider uppercase text-fg-faint mt-2.5">
            {reads}
          </p>
        )}
        <Link href={href(token)} className="block mt-4">
          <Button className="w-full" size="sm">
            Scan this post
            <ArrowRight size={12} />
          </Button>
        </Link>
        <p className="font-mono text-2xs tracking-wider uppercase text-fg-faint mt-2.5 leading-relaxed">
          {TRIAL_CREDITS_LABEL} on signup, no card
        </p>
      </div>
    </aside>
  );
}

/** The closing block, at the end of the report where a reader has finished and is deciding. */
export function ScanMoreFooter({ token, coverage }: { token: string; coverage: Coverage }) {
  const gap = gapLine(coverage);
  return (
    <section className="no-print rounded-lg border border-accent/30 bg-accent/[0.05] p-6 md:p-7">
      <span className="section-label">Your turn</span>
      <h2 className="display text-xl md:text-2xl font-semibold text-fg tracking-tight mt-3 mb-2">
        {HEADLINE}
      </h2>
      <p className="text-sm text-fg-dim leading-relaxed max-w-xl mb-5">
        {gap ? `${gap} ` : 'This report covers only the accounts its author chose to check. '}
        Sign up and this investigation is saved to your account, so you can pick the rest of the
        comment section and see who else is real.
      </p>
      {/* Stacks on mobile: a shrink-0 button beside flex-1 text collapses the text column. */}
      <div className="flex flex-col sm:flex-row sm:items-center gap-3">
        <Link href={href(token)}>
          <Button size="lg">
            <ScanLine size={15} />
            Scan more comments
          </Button>
        </Link>
        <p className="font-mono text-2xs tracking-wider uppercase text-fg-mute leading-relaxed">
          {TRIAL_CREDITS_LABEL} on signup, no card required
        </p>
      </div>
    </section>
  );
}
