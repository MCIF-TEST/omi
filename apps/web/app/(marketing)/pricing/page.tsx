import Link from 'next/link';
import { ArrowRight } from 'lucide-react';
import { PageMasthead, PageSection } from '@/components/shared/page-masthead';
import {
  ACCOUNTS_PER_CREDIT,
  PLAN_TIERS,
  TOPUP_ACCOUNTS,
  TOPUP_CREDITS,
  TOPUP_PRICE,
  TRIAL_ACCOUNTS,
  TRIAL_CREDITS_LABEL,
  accountsFor,
} from '@/lib/plan';

export const metadata = { title: 'Pricing. OMISPHERE' };

/**
 * Three tiers, in the app's own grammar: left axis, mono labels, hard rules, no gradient cards.
 *
 * EVERY FIGURE IS DERIVED FROM lib/plan.ts. The page used to hardcode "20 scans / month", which was
 * only true for scans of 50 accounts or fewer, and "one credit covers up to 50 accounts", which
 * went stale the moment the rate moved. A pricing page that quietly overstates what a subscription
 * buys is the one page you cannot afford to have wrong, so nothing here is written out by hand.
 *
 * The per-account price is FLAT across the three tiers and that is deliberate rather than an
 * oversight: upstream cost is purely variable, so a volume discount would come out of margin rather
 * than out of fixed cost being spread. The bigger plans are worth more because of what they unlock,
 * and the page says so instead of implying a bulk rate that does not exist.
 */

const INCLUDED_EVERYWHERE = [
  'X and YouTube. Posts, videos, and the accounts that comment on them.',
  'A score, a tier and a written read for every account you scan.',
  'The full evidence chain. What an account wrote, its metadata, its posting cadence.',
  'Saved investigations, shareable, exportable as CSV, Markdown, JSON or PDF.',
  'Compiling a comment section is free. Credits are spent only on accounts you choose to scan.',
  'Cancel from your account at any time.',
];

const FAQ = [
  {
    q: 'What does a scan cost?',
    a: `One credit per ${ACCOUNTS_PER_CREDIT} accounts scanned, on every platform. The exact cost is shown next to the Scan button before anything runs, and a failed scan is never charged.`,
  },
  {
    q: 'What happens when I run out?',
    a: `Buy a credit pack at ${TOPUP_PRICE} a credit (${TOPUP_CREDITS} credits, ${TOPUP_ACCOUNTS.toLocaleString()} accounts) or move up a plan. Nothing you have already scanned is affected, and your work stays available either way.`,
  },
  {
    q: 'Why is there a monthly lookup limit?',
    a: 'Loading a comment section calls the platform, and those calls cost us money whether or not you scan anyone. The limit is what lets the plans be priced honestly instead of being underwritten by people who use them lightly. Every plan includes far more lookups than its credits can spend.',
  },
  {
    q: 'Reddit, TikTok, Instagram?',
    a: 'X and YouTube are live. Reddit is next. TikTok and Instagram are not planned: their APIs cannot return an account’s comment history, which is the evidence this product runs on.',
  },
  {
    q: 'Can I change plans?',
    a: 'Yes, from your account settings, and Stripe prorates the difference. Downgrading keeps everything you have already built: your investigations, graphs and exports stay readable.',
  },
];

export default function PricingPage() {
  return (
    <div>
      <PageMasthead
        index="001"
        eyebrow="Pricing"
        title="Three plans. Cancel anytime."
        lede={`Compiling a comment section is free. ${TRIAL_CREDITS_LABEL} on signup, no card, worth ${TRIAL_ACCOUNTS} accounts.`}
      />

      {/* The tiers. A grid of hard-edged panels rather than cards: the numbers are the subject. */}
      <div className="grid md:grid-cols-3 gap-px bg-border-1 border border-border-1">
        {PLAN_TIERS.map((tier, i) => (
          <div key={tier.slug} className="bg-bg-deep flex flex-col">
            <div className="px-5 py-4 border-b border-border-1 bg-bg flex items-baseline justify-between gap-3">
              <span className="meta meta-hi">{tier.name}</span>
              {i === 1 && <span className="meta tabular text-fg-faint">Most chosen</span>}
            </div>

            <div className="p-5 flex flex-col flex-1">
              <div className="flex items-baseline gap-2 mb-1.5">
                <span className="stat-value text-4xl text-fg">{tier.price}</span>
                <span className="font-mono text-xs text-fg-mute">/ month</span>
              </div>
              <p className="font-mono text-[0.6875rem] tracking-wide text-fg-faint mb-5 min-h-[2.5rem]">
                {tier.audience}
              </p>

              <dl className="border-t border-border-1 divide-y divide-border-1 mb-5">
                <Readout label="Accounts / month" value={accountsFor(tier).toLocaleString()} />
                <Readout label="Credits" value={String(tier.credits)} />
                <Readout label="Lookups / month" value={tier.callCeiling.toLocaleString()} />
              </dl>

              {tier.adds.length > 0 && (
                <ul className="space-y-2 mb-6">
                  {tier.adds.map((a) => (
                    <li key={a} className="flex gap-2.5 text-sm text-fg-dim leading-relaxed">
                      <span className="mt-[0.45rem] h-px w-3 shrink-0 bg-border-hot" aria-hidden />
                      <span className="min-w-0">{a}</span>
                    </li>
                  ))}
                </ul>
              )}

              <Link
                href={`/sign-up?plan=${tier.slug}`}
                className="btn-lamp mt-auto inline-flex items-center justify-center gap-2 h-11 px-5 text-[0.9375rem] focus-hard focus-visible:outline-none"
              >
                Start with {tier.name}
                <ArrowRight size={15} />
              </Link>
            </div>
          </div>
        ))}
      </div>

      <PageSection label="Every plan">
        <ul className="space-y-2.5">
          {INCLUDED_EVERYWHERE.map((f) => (
            <li key={f} className="flex gap-3 text-sm text-fg-dim leading-relaxed">
              <span className="mt-[0.45rem] h-px w-3 shrink-0 bg-border-hot" aria-hidden />
              <span className="min-w-0">{f}</span>
            </li>
          ))}
        </ul>
      </PageSection>

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

function Readout({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-baseline justify-between gap-3 py-2">
      <dt className="meta">{label}</dt>
      <dd className="font-mono text-sm text-fg tabular-nums">{value}</dd>
    </div>
  );
}
