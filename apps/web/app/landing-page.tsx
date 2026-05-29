import Link from 'next/link';
import {
  ShieldAlert,
  Activity,
  Network,
  Database,
  CheckCircle2,
  ArrowRight,
  Cpu,
  Eye,
  GitBranch,
} from 'lucide-react';
import { Logo } from '@/components/shared/logo';
import { DemoScanForm } from './demo-scan-form';

export function LandingPage() {
  return (
    <div className="min-h-screen bg-bg-deep flex flex-col relative overflow-hidden grain">

      {/* Aurora blobs */}
      <div className="fixed inset-0 pointer-events-none overflow-hidden" aria-hidden>
        <div className="absolute top-[-15%] left-[15%] w-[700px] h-[600px] rounded-full bg-accent/[0.055] blur-[130px] animate-drift" />
        <div className="absolute bottom-[10%] right-[-8%] w-[500px] h-[500px] rounded-full bg-accent-2/[0.035] blur-[110px] animate-drift-slow" />
        <div className="absolute top-[55%] left-[-5%] w-[350px] h-[350px] rounded-full bg-tier-high/[0.025] blur-[90px] animate-float" style={{ animationDelay: '-3s' }} />
      </div>

      {/* Dot grid */}
      <div className="fixed inset-0 pointer-events-none dot-bg opacity-[0.28]" aria-hidden />

      {/* ── Nav ─────────────────────────────────────────────────── */}
      <header className="relative z-20 px-6 py-4 flex items-center justify-between border-b border-border-1/50 backdrop-blur-md bg-bg-deep/75 sticky top-0">
        <Link href="/" aria-label="OMISPHERE home">
          <Logo />
        </Link>
        <nav className="flex items-center gap-5 font-mono text-2xs tracking-[0.18em] text-fg-mute uppercase">
          <Link href="/pricing" className="hidden sm:block hover:text-fg-dim transition-colors">Pricing</Link>
          <Link href="/about" className="hidden sm:block hover:text-fg-dim transition-colors">About</Link>
          <Link href="/login" className="hover:text-fg-dim transition-colors">Log in</Link>
          <Link
            href="/signup"
            className="text-accent border border-accent/30 bg-accent/[0.07] px-3 py-1.5 rounded-sm hover:bg-accent/[0.13] hover:border-accent/50 transition-all"
          >
            Sign up
          </Link>
        </nav>
      </header>

      {/* ── Hero ────────────────────────────────────────────────── */}
      <section className="relative z-10 px-6 pt-24 pb-14 max-w-5xl mx-auto w-full">
        <div className="text-center space-y-7 mb-14">

          {/* Live pill */}
          <div className="inline-flex items-center gap-2.5 font-mono text-2xs tracking-[0.2em] text-accent uppercase border border-accent/20 bg-accent/[0.06] px-4 py-2 rounded-full">
            <span className="w-1.5 h-1.5 rounded-full bg-tier-low animate-pulse-dot" />
            YouTube Authenticity Intelligence · Beta
          </div>

          {/* Headline */}
          <h1 className="text-5xl md:text-6xl lg:text-7xl font-semibold tracking-tight leading-[1.06] text-fg">
            See who&apos;s{' '}
            <span className="text-shimmer">really</span>
            <br />behind the comments.
          </h1>

          {/* Sub */}
          <p className="text-lg md:text-xl text-fg-dim max-w-2xl mx-auto leading-relaxed">
            Paste any YouTube URL. OMISPHERE scores every commenter on eight
            independent signals, surfaces coordinated networks, and tracks
            narrative campaigns — probabilistic, with full evidence.
          </p>
        </div>

        {/* Demo card */}
        <div className="glass rounded-xl p-6 md:p-8 shadow-card-lg max-w-3xl mx-auto border-accent/[0.12]">
          <div className="flex items-center justify-between mb-5 flex-wrap gap-2">
            <div className="flex items-center gap-2">
              <span className="w-1.5 h-1.5 rounded-full bg-tier-low animate-pulse-dot" />
              <p className="font-mono text-2xs tracking-[0.18em] text-fg-mute uppercase">
                Try it now — no signup required
              </p>
            </div>
            <span className="font-mono text-2xs text-fg-faint tracking-wider">
              10 commenters · ~10 s · 1 free demo/day
            </span>
          </div>
          <DemoScanForm />
        </div>

        {/* Trust row */}
        <div className="mt-7 flex items-center justify-center gap-5 flex-wrap font-mono text-2xs text-fg-mute tracking-wider">
          {['No card required', 'Real scan on your URL', 'Never a verdict — always probabilistic'].map((t) => (
            <span key={t} className="flex items-center gap-1.5">
              <CheckCircle2 size={10} className="text-tier-low" />
              {t}
            </span>
          ))}
        </div>
      </section>

      {/* ── Stats row ───────────────────────────────────────────── */}
      <section className="relative z-10 px-6 pb-6 max-w-5xl mx-auto w-full">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          {[
            { value: '8',   label: 'Detection signals',  sub: 'per commenter' },
            { value: '3',   label: 'Coord. detectors',   sub: 'cross-account' },
            { value: '0',   label: 'LLMs in core path',  sub: 'pure heuristics' },
            { value: '∞',   label: 'Self-improving DB',  sub: 'every scan trains it' },
          ].map(({ value, label, sub }) => (
            <div
              key={label}
              className="p-4 rounded-lg border border-border-1 bg-bg-elev/50 text-center hover:border-border-hot transition-colors"
            >
              <div className="text-3xl font-semibold mono text-accent mb-0.5">{value}</div>
              <div className="font-mono text-2xs text-fg uppercase tracking-wider">{label}</div>
              <div className="font-mono text-2xs text-fg-faint mt-0.5">{sub}</div>
            </div>
          ))}
        </div>
      </section>

      {/* ── Features ────────────────────────────────────────────── */}
      <section className="relative z-10 px-6 py-16 max-w-5xl mx-auto w-full">
        <div className="text-center mb-12">
          <p className="font-mono text-2xs tracking-[0.2em] text-accent uppercase mb-3">
            Capabilities
          </p>
          <h2 className="text-2xl md:text-3xl font-semibold text-fg tracking-tight">
            Intelligence across every dimension
          </h2>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 stagger">
          <FeatureCard
            icon={<ShieldAlert size={20} />}
            title="Per-commenter detection"
            body="Each commenter scored on temporal cadence, semantic repetition, AI-writing tells, profile metadata, personal-voice rate, engagement farming, fingerprint memory, and coordination. Probabilistic with explicit evidence."
          />
          <FeatureCard
            icon={<Network size={20} />}
            title="Coordination clusters"
            body="Three cross-account detectors find groups acting together: temporal-semantic bursts (copy-paste within seconds), age cohorts (accounts created in the same week), and co-engagement (the same people on the same videos)."
          />
          <FeatureCard
            icon={<Activity size={20} />}
            title="Narrative tracking"
            body="Semantic clusters across all your scans. See which talking points are organic and which are being amplified by suspicious accounts — across every video you've ever scanned."
          />
          <FeatureCard
            icon={<Database size={20} />}
            title="Self-improving database"
            body="Every scan adds a behavioural fingerprint and persists coordination edges. Future scans pull priors from the growing set, so the engine sharpens the more you use it."
          />
          <FeatureCard
            icon={<Cpu size={20} />}
            title="Pure-signal engine"
            body="No LLMs in the core detection path — pure Python heuristics, embeddings, and graph algorithms. Fast, deterministic, and fully auditable. LLMs are reserved for optional report generation only."
          />
          <FeatureCard
            icon={<Eye size={20} />}
            title="Full evidence chain"
            body="Every score shows its work. Click any flag to see the raw signals that triggered it — timestamps, text matches, account metadata. No black boxes. Probabilistic reasoning, fully transparent."
          />
        </div>
      </section>

      {/* ── Scope block ─────────────────────────────────────────── */}
      <section className="relative z-10 px-6 pb-8 max-w-4xl mx-auto w-full">
        <div className="rounded-lg border border-border-1 bg-bg-elev/40 p-6 flex gap-4">
          <GitBranch size={16} className="text-fg-mute shrink-0 mt-0.5" />
          <div>
            <p className="font-mono text-2xs tracking-wider uppercase text-fg-mute mb-2">
              Scope, plainly
            </p>
            <p className="text-sm text-fg-dim leading-relaxed">
              Today OMISPHERE scans <span className="text-fg font-medium">YouTube</span> only — videos and channels.
              The detection engine is platform-agnostic; ingestion for X / Twitter, Reddit, and TikTok
              is on the roadmap. We&apos;d rather ship one platform with depth than four with stubs.
            </p>
          </div>
        </div>
      </section>

      {/* ── CTA ─────────────────────────────────────────────────── */}
      <section className="relative z-10 px-6 py-20 max-w-3xl mx-auto w-full text-center space-y-6">
        <h2 className="text-3xl md:text-4xl font-semibold text-fg tracking-tight leading-tight">
          Ready to see what&apos;s{' '}
          <span className="text-gradient">real?</span>
        </h2>
        <p className="text-lg text-fg-dim max-w-xl mx-auto">
          $9.99/month · 20 scans · 3 free on signup. Cancel anytime.
          Built for journalists, researchers, and platform integrity teams.
        </p>
        <div className="flex items-center justify-center gap-4 pt-2 flex-wrap">
          <Link
            href="/signup"
            className="inline-flex items-center gap-2 bg-accent text-bg-deep font-semibold px-8 py-3 rounded-sm hover:bg-accent-2 transition-all btn-glow"
          >
            Start free trial
            <ArrowRight size={16} />
          </Link>
          <Link
            href="/pricing"
            className="font-mono text-2xs tracking-wider uppercase text-fg-dim hover:text-fg transition-colors px-4 py-3"
          >
            See full pricing →
          </Link>
        </div>
      </section>

      {/* ── Footer ──────────────────────────────────────────────── */}
      <footer className="relative z-10 border-t border-border-1/50 px-6 py-8 mt-auto">
        <div className="max-w-5xl mx-auto flex items-center justify-between flex-wrap gap-4">
          <Logo />
          <p className="font-mono text-2xs tracking-wider text-fg-faint">
            Probabilistic Authenticity Intelligence
          </p>
          <div className="flex items-center gap-5 font-mono text-2xs text-fg-mute uppercase tracking-wider">
            <Link href="/terms"    className="hover:text-fg-dim transition-colors">Terms</Link>
            <Link href="/privacy"  className="hover:text-fg-dim transition-colors">Privacy</Link>
            <Link href="/pricing"  className="hover:text-fg-dim transition-colors">Pricing</Link>
            <Link href="/about"    className="hover:text-fg-dim transition-colors">About</Link>
          </div>
        </div>
      </footer>
    </div>
  );
}

function FeatureCard({
  icon,
  title,
  body,
}: {
  icon: React.ReactNode;
  title: string;
  body: string;
}) {
  return (
    <div className="group bg-bg-elev rounded-lg border border-border-1 p-6 card-interactive spotlight shadow-inner-top">
      <div className="flex items-center gap-3 mb-3">
        <div className="w-9 h-9 rounded-md bg-accent/[0.08] border border-accent/20 flex items-center justify-center text-accent group-hover:bg-accent/[0.13] transition-colors">
          {icon}
        </div>
        <h3 className="text-fg font-semibold">{title}</h3>
      </div>
      <p className="text-sm text-fg-dim leading-relaxed">{body}</p>
    </div>
  );
}
