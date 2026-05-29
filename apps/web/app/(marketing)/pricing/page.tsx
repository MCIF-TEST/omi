import Link from 'next/link';
import { Check, Sparkles, Zap } from 'lucide-react';
import { Card, CardLabel } from '@/components/ui/card';
import { Button } from '@/components/ui/button';

export const metadata = { title: 'Pricing — OMISPHERE' };

const FEATURES = [
  'Full YouTube video scans — every commenter analysed across 8 detectors',
  'YouTube channel scans — single account drilldown with trend over time',
  'Cross-account coordination clusters (3 dedicated detectors)',
  'Per-commenter activity drilldown — see what flagged accounts actually wrote',
  'Saved investigations — shareable, exportable as Markdown / JSON / PDF',
  'Watchlist alerts — get notified when a channel\'s tier changes',
  'Self-improving fingerprint database — every scan trains the engine',
  'Cancel from your account at any time',
];

const FAQ = [
  {
    q: 'What counts as a scan?',
    a: 'Each YouTube video or channel URL you submit is one scan, regardless of how many commenters it covers. Re-scanning the same URL later costs an additional scan (it pulls fresh comments). Pulling additional batches of commenters on an existing investigation also costs one scan per batch.',
  },
  {
    q: 'What about X / Twitter / Reddit / TikTok?',
    a: 'Not yet. The detection engine is platform-agnostic; the missing piece is ingestion. X / Twitter is the next planned platform — pricing for X scans will reflect the higher API cost when it ships. We\'d rather give you one platform that works than four with stubs.',
  },
  {
    q: 'What if YouTube\'s quota is exhausted?',
    a: 'YouTube API quota is shared across the service. If today\'s quota is spent, new scans will return a friendly "try again tomorrow" error and no credit is charged. The service status pill in the top-right shows real-time scanning health.',
  },
  {
    q: 'Beyond 20 scans / month?',
    a: 'Reach out via the contact form — we can set up a higher-tier plan for research labs, brand-safety teams, and platform-integrity groups. Subscriptions are billed monthly; no annual lock-in.',
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
        <h1 className="text-4xl md:text-5xl font-semibold tracking-tight leading-tight">
          One plan. <span className="text-brand">Cancel anytime.</span>
        </h1>
        <p className="mt-4 text-fg-dim leading-relaxed">
          YouTube comment intelligence — bots, AI engagement, and coordinated
          influence campaigns. Probabilistic. Every scan trains the OMISPHERE
          fingerprint database.
        </p>
      </header>

      {/* Plan card */}
      <div className="max-w-2xl mx-auto">
        <Card gradient className="relative overflow-hidden shadow-card-lg">
          {/* corner glow */}
          <div className="absolute -top-16 -right-16 w-48 h-48 rounded-full bg-accent/[0.08] blur-3xl pointer-events-none" aria-hidden />

          <div className="relative">
            <div className="flex items-baseline justify-between mb-1 flex-wrap gap-2">
              <span className="text-5xl font-bold tracking-tight">
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
              3 free trial scans on signup · no card required
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
