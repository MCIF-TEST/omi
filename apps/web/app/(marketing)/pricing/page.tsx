import Link from 'next/link';
import { Card, CardLabel, CardTitle } from '@/components/ui/card';
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
          Probabilistic detection of bots, AI engagement, and coordinated influence campaigns.
          Every scan trains the OMISPHERE database — it sharpens with every use.
        </p>
      </header>

      <Card className="border-accent-dim bg-gradient-to-b from-accent/[0.06] to-transparent">
        <div className="flex items-baseline justify-between mb-6">
          <span className="text-4xl font-bold text-accent tracking-tight">
            $9.99<span className="text-base text-fg-dim font-normal ml-1">/month</span>
          </span>
          <Badge variant="accent">20 scans / month</Badge>
        </div>
        <ul className="space-y-3 text-fg">
          <Feature>Comprehensive YouTube account, video, and coordination scans</Feature>
          <Feature>Per-account activity drilldown — see what flagged accounts actually wrote</Feature>
          <Feature>Cross-account coordination clusters (5 detectors)</Feature>
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

      <section>
        <CardLabel>What about X / Reddit / TikTok?</CardLabel>
        <p className="text-fg-dim leading-relaxed">
          Coming. They have different API costs — X is expensive, Reddit is cheap. The
          credit system already supports per-platform weighting, so X scans will cost
          more credits than YouTube scans when they ship.
        </p>
      </section>

      <section>
        <CardLabel>Beyond 20 scans / month?</CardLabel>
        <p className="text-fg-dim leading-relaxed">
          Reach out — we can set up a higher-tier plan. Subscriptions are billed monthly;
          no annual lock-in.
        </p>
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
