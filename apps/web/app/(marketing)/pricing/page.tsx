import Link from 'next/link';
import { Check, Sparkles, Zap } from 'lucide-react';
import { Card, CardLabel } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { TRIAL_CREDITS } from '@/lib/plan';

export const metadata = { title: 'Pricing. OMISPHERE' };

const FEATURES = [
  'YouTube + X (Twitter) coordination intelligence. Videos, channels, accounts',
  'Six cross-account coordination detectors (fingerprint, co-engagement, co-tag, style, temporal-semantic, age-cohort)',
  'Corroboration-gated Campaign records. Durable, evolving, evidence-bearing',
  'Per-commenter activity drilldown. See what flagged accounts actually wrote',
  'Saved investigations. Shareable, exportable as Markdown / JSON / PDF',
  'Watchlist alerts. Get notified when a tracked channel\'s tier changes',
  'Cross-scan fingerprint memory, every scan adds priors for the next',
  'Cancel from your account at any time',
];

const FAQ = [
  {
    q: 'What does an investigation cost?',
    a: 'One credit per 50 commenters (on YouTube) or repliers (on X/Twitter) scanned, so a 50-account scan is 1 credit and a 150-account scan is 3. YouTube and X are priced the same. The exact cost is shown next to the Scan button before you run anything, and you are never charged if a scan fails. Re-scanning the same URL later, or pulling additional batches, costs the same per-50 rate again.',
  },
  {
    q: 'What about Reddit / TikTok / Instagram?',
    a: 'YouTube and X (Twitter) are live today. Reddit and TikTok are on the roadmap and require their own API access. The detection engine is platform-agnostic; the missing piece is ingestion. We\'d rather ship two platforms with depth than four with stubs.',
  },
  {
    q: 'What if YouTube\'s quota is exhausted?',
    a: 'YouTube API quota is shared across the service. If today\'s quota is spent, new scans will return a friendly "try again tomorrow" error and no credit is charged. The service status pill in the top-right shows real-time scanning health.',
  },
  {
    q: 'Beyond 20 scans / month?',
    a: 'Reach out via the contact form. We can set up a higher-tier plan for research labs, brand-safety teams, and platform-integrity groups. Subscriptions are billed monthly; no annual lock-in.',
  },
];

export default function PricingPage() {
  return (
    <div className="space-y-12">
      {/* Hero */}
      <header className="text-center max-w-2xl mx-auto">
        <div className="inline-flex items-center gap-2 font-mono text-2xs tracking-[0.2em] text-accent uppercase border border-accent/20 bg-accent/[0.06] px-4 py-1.5 rounded-full mb-5">
          <Sparkles size={11} />
          Pricing
        </div>
        <h1 className="display text-4xl md:text-5xl font-semibold tracking-tight leading-tight">
          One plan. <span className="text-brand">Cancel anytime.</span>
        </h1>
        <p className="mt-4 text-fg-dim leading-relaxed">
          YouTube comment intelligence. Bots, AI engagement, and coordinated
          influence campaigns. Probabilistic. Every scan trains the OMISPHERE
          fingerprint database.
        </p>
      </header>

      {/* Plan card */}
      <div className="max-w-2xl mx-auto">
        <Card gradient className="relative overflow-hidden shadow-card-lg">
          {/* corner glow */}

          <div className="relative">
            <div className="flex items-baseline justify-between mb-1 flex-wrap gap-2">
              <span className="stat-value text-5xl font-bold tracking-tight">
                <span className="text-brand">$9.99</span>
                <span className="text-base text-fg-dim font-normal ml-1.5">/month</span>
              </span>
              <span className="inline-flex items-center gap-1.5 font-mono text-2xs tracking-[0.16em] text-accent uppercase border border-accent/30 bg-accent/10 px-3 py-1.5 rounded-full">
                <Zap size={11} />
                20 scans / month
              </span>
            </div>

            <p className="font-mono text-2xs tracking-wider text-tier-low uppercase mb-6 flex items-center gap-1.5">
              <Sparkles size={11} />
              {TRIAL_CREDITS} free trial credits on signup · no card required
            </p>

            <ul className="space-y-3 mb-8">
              {FEATURES.map((f) => (
                <li key={f} className="flex items-start gap-3 text-sm text-fg">
                  <span className="shrink-0 mt-0.5 w-4 h-4 rounded-full bg-accent/15 border border-accent/30 flex items-center justify-center">
                    <Check size={10} className="text-accent" strokeWidth={3} />
                  </span>
                  <span>{f}</span>
                </li>
              ))}
            </ul>

            <Link href="/signup" className="block">
              <Button size="lg" className="w-full">
                Start free trial →
              </Button>
            </Link>
          </div>
        </Card>
      </div>

      {/* FAQ */}
      <section className="grid grid-cols-1 md:grid-cols-2 gap-4 max-w-3xl mx-auto">
        {FAQ.map(({ q, a }) => (
          <Card key={q} interactive>
            <CardLabel>{q}</CardLabel>
            <p className="text-sm text-fg-dim leading-relaxed">{a}</p>
          </Card>
        ))}
      </section>
    </div>
  );
}
