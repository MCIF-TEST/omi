import Link from 'next/link';
import { ArrowRight } from 'lucide-react';
import { PageMasthead, PageSection } from '@/components/shared/page-masthead';
import {
  TRIAL_CREDITS_LABEL, SUBSCRIPTION_PRICE, PLAN_NAME, MONTHLY_CREDITS,
} from '@/lib/plan';

export const metadata = { title: 'Pricing. OMISPHERE' };

/**
 * Rebuilt to the front page's grammar: left axis, mono labels, hard rules, bone action.
 *
 * The old page centred everything behind a blue pill eyebrow, put the price in a gradient card
 * with a rounded "20 SCANS / MONTH" chip beside it, and closed with a full-width blue button.
 * Read next to the front page it was plainly a different product.
 *
 * The unit language is also corrected throughout. The plan grants CREDITS, and one credit covers
 * up to 50 accounts, so "20 scans / month" was only true for scans of 50 accounts or fewer. A
 * pricing page that quietly overstates what a subscription buys is the one page you cannot afford
 * to have wrong.
 */

const INCLUDED = [
  'X and YouTube. Posts, videos, and the accounts that comment on them.',
  'Eight detection methods per account, each with its own score and the reason behind it.',
  'The full evidence chain. What an account wrote, its metadata, its posting cadence.',
  'Saved investigations, shareable, exportable as CSV, Markdown, JSON or PDF.',
  'Watchlist alerts when a tracked channel changes tier.',
  'Cross-scan fingerprint memory. Every scan sharpens the next.',
  'Cancel from your account at any time.',
];

const FAQ = [
  {
    q: 'What does an investigation cost?',
    a: 'One credit per 50 accounts scanned, so 50 accounts is 1 credit and 150 is 3. X and YouTube are priced the same. The exact cost is shown next to the Scan button before anything runs, and a failed scan is never charged.',
  },
  {
    q: 'Reddit, TikTok, Instagram?',
    a: 'X and YouTube are live. Reddit and TikTok arrive November 1st. The detection engine is platform-agnostic, so the missing piece is ingestion rather than detection.',
  },
  {
    q: 'What if the YouTube quota runs out?',
    a: 'YouTube API quota is shared across the service. If a day’s quota is spent, new scans return a plain "try again tomorrow" and no credit is charged. The status indicator in the top bar shows real-time scanning health.',
  },
  {
    q: `Beyond ${MONTHLY_CREDITS} credits a month?`,
    a: 'Get in touch. Higher-tier plans exist for research labs, brand-safety teams and platform-integrity groups. Billing is monthly, with no annual lock-in.',
  },
];

export default function PricingPage() {
  return (
    <div>
      <PageMasthead
        index="001"
        eyebrow="Pricing"
        title="One membership. Cancel anytime."
        lede="Compiling a comment section is free. Credits are spent only on the accounts you choose to scan."
      />

      {/* Price. The figure carries the section, so it is set at display scale in mono and given a
          hard edge rather than a card with a gradient behind it. */}
      <div className="border border-border-1">
        <div className="px-5 py-4 border-b border-border-1 bg-bg flex items-baseline justify-between gap-3 flex-wrap">
          <span className="meta meta-hi">{PLAN_NAME}</span>
          <span className="meta tabular">{MONTHLY_CREDITS} credits / month</span>
        </div>

        <div className="p-5 md:p-7">
          <div className="flex items-baseline gap-2.5 mb-1.5">
            <span className="stat-value text-5xl md:text-6xl text-fg">{SUBSCRIPTION_PRICE}</span>
            <span className="font-mono text-sm text-fg-mute">/ month</span>
          </div>
          <p className="font-mono text-[0.6875rem] tracking-wide text-fg-faint mb-7 max-w-[52ch]">
            {TRIAL_CREDITS_LABEL} on signup, no card. One credit covers up to 50 accounts.
          </p>

          <ul className="space-y-2.5 mb-8">
            {INCLUDED.map((f) => (
              <li key={f} className="flex gap-3 text-sm text-fg-dim leading-relaxed">
                <span className="mt-[0.45rem] h-px w-3 shrink-0 bg-border-hot" aria-hidden />
                <span className="min-w-0">{f}</span>
              </li>
            ))}
          </ul>

          <Link
            href="/sign-up"
            className="btn-lamp inline-flex items-center justify-center gap-2 h-11 px-6 text-[0.9375rem] focus-hard focus-visible:outline-none"
          >
            Create an account
            <ArrowRight size={15} />
          </Link>
        </div>
      </div>

      <PageSection label="Questions">
        <dl className="grid sm:grid-cols-2 gap-px bg-border-1 border border-border-1">
          {FAQ.map(({ q, a }, i) => (
            <div key={q} className="bg-bg-deep p-4 md:p-5">
              <div className="flex items-center gap-2.5 mb-2.5">
                <span className="meta tabular">Q{String(i + 1).padStart(2, '0')}</span>
                <span className="h-px flex-1 bg-border-1" aria-hidden />
              </div>
              <dt className="text-sm font-semibold text-fg mb-2">{q}</dt>
              <dd className="text-sm text-fg-mute leading-relaxed">{a}</dd>
            </div>
          ))}
        </dl>
      </PageSection>
    </div>
  );
}
