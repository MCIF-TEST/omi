import Link from 'next/link';
import { Card, CardLabel } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';

export const metadata = { title: 'Pricing — OMISPHERE' };

export default function PricingPage() {
  return (
    <div className="space-y-10">
      <header>
        <p className="font-mono text-2xs tracking-[0.18em] text-fg-mute uppercase mb-2">Pricing</p>
        <h1 className="text-3xl font-semibold text-fg tracking-tight">One plan. Cancel anytime.</h1>
        <p className="mt-3 text-fg-dim">
          YouTube comment intelligence — bots, AI engagement, and coordinated influence
          campaigns. Probabilistic. Every scan trains the OMISPHERE fingerprint database.
        </p>
      </header>

      <Card className="border-accent-dim bg-gradient-to-b from-accent/[0.06] to-transparent">
        <div className="flex items-baseline justify-between mb-6 flex-wrap gap-2">
          <span className="text-4xl font-bold text-accent tracking-tight">
            $9.99<span className="text-base text-fg-dim font-normal ml-1">/month</span>
          </span>
          <Badge variant="accent">20 scans / month</Badge>
        </div>
        <ul className="space-y-3 text-fg">
          <Feature>Full YouTube video scans — every commenter analysed across 8 detectors</Feature>
          <Feature>YouTube channel scans — single account drilldown with trend over time</Feature>
          <Feature>Cross-account coordination clusters (3 dedicated detectors)</Feature>
          <Feature>Per-commenter activity drilldown — see what flagged accounts actually wrote</Feature>
          <Feature>Saved investigations — shareable, exportable as Markdown / JSON / PDF</Feature>
          <Feature>Watchlist alerts — get notified when a channel&apos;s tier changes</Feature>
          <Feature>Self-improving fingerprint database — every scan trains the engine</Feature>
          <Feature>Cancel from your account at any time</Feature>
        </ul>
        <p className="mt-6 font-mono text-2xs tracking-wider text-accent uppercase">
          3 free trial scans on signup · no card required
        </p>
        <div className="mt-6">
          <Link href="/signup">
            <Button size="lg">Start free trial →</Button>
          </Link>
        </div>
      </Card>

      <section className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <Card>
          <CardLabel>What counts as a scan?</CardLabel>
          <p className="text-sm text-fg-dim leading-relaxed">
            Each YouTube video or channel URL you submit is one scan, regardless of
            how many commenters it covers. Re-scanning the same URL later costs an
            additional scan (it pulls fresh comments). Pulling additional batches
            of commenters on an existing investigation also costs one scan per batch.
          </p>
        </Card>
        <Card>
          <CardLabel>What about X / Twitter / Reddit / TikTok?</CardLabel>
          <p className="text-sm text-fg-dim leading-relaxed">
            Not yet. The detection engine is platform-agnostic; the missing piece is
            ingestion. X / Twitter is the next planned platform — pricing for X scans
            will reflect the higher API cost when it ships. We&apos;d rather give you
            one platform that works than four with stubs.
          </p>
        </Card>
        <Card>
          <CardLabel>What if YouTube&apos;s quota is exhausted?</CardLabel>
          <p className="text-sm text-fg-dim leading-relaxed">
            YouTube API quota is shared across the service. If today&apos;s quota is
            spent, new scans will return a friendly &ldquo;try again tomorrow&rdquo; error and
            no credit is charged. The service status pill in the top-right shows
            real-time scanning health.
          </p>
        </Card>
        <Card>
          <CardLabel>Beyond 20 scans / month?</CardLabel>
          <p className="text-sm text-fg-dim leading-relaxed">
            Reach out via the contact form — we can set up a higher-tier plan for
            research labs, brand-safety teams, and platform-integrity groups.
            Subscriptions are billed monthly; no annual lock-in.
          </p>
        </Card>
      </section>
    </div>
  );
}

function Feature({ children }: { children: React.ReactNode }) {
  return (
    <li className="flex items-start gap-3">
      <span className="text-accent mt-0.5">·</span>
      <span>{children}</span>
    </li>
  );
}
