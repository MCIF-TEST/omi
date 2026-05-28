import Link from 'next/link';
import {
  ShieldAlert,
  Activity,
  Network,
  Database,
  CheckCircle2,
  ArrowRight,
} from 'lucide-react';
import { Logo } from '@/components/shared/logo';
import { DemoScanForm } from './demo-scan-form';

export function LandingPage() {
  return (
    <div className="min-h-screen bg-bg-deep flex flex-col">
      {/* Nav */}
      <header className="px-6 py-5 flex items-center justify-between border-b border-border-1">
        <Link href="/" aria-label="OMISPHERE home">
          <Logo />
        </Link>
        <nav className="flex items-center gap-6 font-mono text-2xs tracking-[0.18em] text-fg-mute uppercase">
          <Link href="/pricing" className="hover:text-fg-dim transition-colors">Pricing</Link>
          <Link href="/about" className="hover:text-fg-dim transition-colors">About</Link>
          <Link href="/login" className="hover:text-fg-dim transition-colors">Log in</Link>
          <Link
            href="/signup"
            className="text-accent border border-accent-dim bg-accent/[0.05] px-3 py-1 rounded-sm hover:bg-accent/10 transition-colors"
          >
            Sign up
          </Link>
        </nav>
      </header>

      {/* Hero */}
      <section className="px-6 pt-16 pb-12 max-w-5xl mx-auto w-full">
        <div className="space-y-6 text-center mb-12">
          <p className="font-mono text-2xs tracking-[0.18em] text-accent uppercase">
            YouTube authenticity intelligence · beta
          </p>
          <h1 className="text-4xl md:text-5xl font-semibold text-fg tracking-tight leading-tight max-w-3xl mx-auto">
            See who's <span className="text-accent">really</span> behind the comments.
          </h1>
          <p className="text-base md:text-lg text-fg-dim max-w-2xl mx-auto leading-relaxed">
            Paste a YouTube video or channel URL. OMISPHERE scores every commenter on
            eight independent signals, surfaces coordinated networks, and tracks
            narrative campaigns across every scan. Probabilistic — never a verdict.
          </p>
        </div>

        {/* Demo form */}
        <div className="bg-bg-elev border border-border-1 rounded-lg p-6 md:p-8 shadow-xl">
          <div className="flex items-center justify-between mb-4 flex-wrap gap-2">
            <p className="font-mono text-2xs tracking-[0.18em] text-fg-mute uppercase">
              Try it now — no signup
            </p>
            <span className="font-mono text-2xs text-fg-faint tracking-wider">
              · 10 commenters · ~10 seconds · 1 free demo per day
            </span>
          </div>
          <DemoScanForm />
        </div>

        {/* Trust row */}
        <div className="mt-6 flex items-center justify-center gap-2 font-mono text-2xs text-fg-mute tracking-wider">
          <CheckCircle2 size={11} className="text-tier-low" />
          No card · no signup · runs a real scan
        </div>
      </section>

      {/* Value props */}
      <section className="px-6 py-16 max-w-5xl mx-auto w-full grid grid-cols-1 md:grid-cols-2 gap-4">
        <ValueCard
          icon={<ShieldAlert size={18} />}
          title="Per-commenter detection"
          body="Each commenter scored on temporal cadence, semantic repetition, AI-writing tells, profile metadata, personal-voice rate, engagement farming, fingerprint memory, and coordination. Probabilistic, with explicit evidence."
        />
        <ValueCard
          icon={<Network size={18} />}
          title="Coordination clusters"
          body="Three cross-account detectors find groups acting together: temporal-semantic bursts (copy-paste within seconds), age cohorts (accounts created in the same week), and co-engagement (the same people on the same videos)."
        />
        <ValueCard
          icon={<Activity size={18} />}
          title="Narrative tracking"
          body="Semantic clusters across all your scans. See which talking points are organic and which are being amplified by suspicious accounts — across every video you've ever scanned."
        />
        <ValueCard
          icon={<Database size={18} />}
          title="Self-improving database"
          body="Every scan adds a behavioural fingerprint and persists coordination edges. Future scans pull priors from the growing set, so the engine sharpens the more you use it."
        />
      </section>

      {/* Honest scope block */}
      <section className="px-6 pb-4 max-w-3xl mx-auto w-full">
        <div className="bg-bg-elev/40 border border-border-1 rounded-md p-5 text-sm text-fg-dim leading-relaxed">
          <p className="font-mono text-2xs tracking-wider uppercase text-fg-mute mb-2">
            Scope, plainly
          </p>
          <p>
            Today OMISPHERE scans <span className="text-fg">YouTube</span> only —
            videos and channels. The detection engine is platform-agnostic;
            ingestion for X / Twitter, Reddit, and TikTok is on the roadmap and
            depends on those APIs being financially reasonable. We&apos;d rather ship
            one platform with depth than four platforms with stubs.
          </p>
        </div>
      </section>

      {/* CTA */}
      <section className="px-6 py-16 max-w-3xl mx-auto w-full text-center space-y-4">
        <h2 className="text-2xl font-semibold text-fg tracking-tight">
          $9.99/month · 20 scans · 3 free on signup
        </h2>
        <p className="text-fg-dim">Cancel anytime. Self-serve. Built for journalists, researchers, and platform integrity teams.</p>
        <div className="flex items-center justify-center gap-3 pt-2">
          <Link
            href="/signup"
            className="inline-flex items-center gap-2 bg-accent text-bg-deep font-medium px-5 py-2.5 rounded-sm hover:bg-accent-2 transition-colors"
          >
            Start free trial
            <ArrowRight size={14} />
          </Link>
          <Link
            href="/pricing"
            className="font-mono text-2xs tracking-wider uppercase text-fg-dim hover:text-fg transition-colors px-4 py-2"
          >
            See full pricing →
          </Link>
        </div>
      </section>

      <footer className="border-t border-border-1 px-6 py-6 mt-auto text-center font-mono text-2xs tracking-wider text-fg-mute uppercase">
        OMISPHERE · Probabilistic Authenticity Intelligence
      </footer>
    </div>
  );
}

function ValueCard({
  icon,
  title,
  body,
}: {
  icon: React.ReactNode;
  title: string;
  body: string;
}) {
  return (
    <div className="bg-bg-elev border border-border-1 rounded-md p-5">
      <div className="flex items-center gap-2 mb-2 text-accent">
        {icon}
        <h3 className="text-fg font-medium">{title}</h3>
      </div>
      <p className="text-sm text-fg-dim leading-relaxed">{body}</p>
    </div>
  );
}
