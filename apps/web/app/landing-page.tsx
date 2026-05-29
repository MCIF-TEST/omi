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
} from 'lucide-react';
import { Logo } from '@/components/shared/logo';
import { Reveal } from '@/components/shared/reveal';
import { AnimatedNumber } from '@/components/shared/animated-number';
import { ScrollProgress } from '@/components/shared/scroll-progress';
import { DemoScanForm } from './demo-scan-form';

export function LandingPage() {
  return (
    <div className="min-h-screen bg-bg-deep flex flex-col relative overflow-hidden grain">
      <ScrollProgress />

      {/* ── Ambient spectral field ──────────────────────────────── */}
      <div className="fixed inset-0 pointer-events-none overflow-hidden" aria-hidden>
        <div className="absolute top-[-18%] left-[8%] w-[680px] h-[620px] rounded-full bg-accent/[0.10] blur-[150px] animate-drift" />
        <div className="absolute top-[8%] right-[-10%] w-[560px] h-[520px] rounded-full bg-coral/[0.06] blur-[140px] animate-drift-slow" />
        <div className="absolute bottom-[6%] left-[-6%] w-[420px] h-[420px] rounded-full bg-accent-2/[0.05] blur-[120px] animate-float" style={{ animationDelay: '-3s' }} />
      </div>
      <div className="fixed inset-0 pointer-events-none dot-bg opacity-[0.3]" aria-hidden />

      {/* ── Nav ─────────────────────────────────────────────────── */}
      <header className="relative z-20 px-6 py-4 flex items-center justify-between border-b border-border-1/40 backdrop-blur-xl bg-bg-deep/70 sticky top-0">
        <Link href="/" aria-label="omisphere home">
          <Logo />
        </Link>
        <nav className="flex items-center gap-1.5 sm:gap-2 font-mono text-2xs tracking-[0.16em] text-fg-mute uppercase">
          <Link href="/pricing" className="hidden sm:block px-3 py-1.5 rounded-full hover:text-fg hover:bg-bg-elev transition-colors">Pricing</Link>
          <Link href="/about" className="hidden sm:block px-3 py-1.5 rounded-full hover:text-fg hover:bg-bg-elev transition-colors">About</Link>
          <Link href="/login" className="px-3 py-1.5 rounded-full hover:text-fg hover:bg-bg-elev transition-colors">Log in</Link>
          <Link
            href="/signup"
            className="text-bg-deep bg-accent font-semibold px-4 py-1.5 rounded-full hover:bg-accent-2 transition-all btn-glow"
          >
            Sign up
          </Link>
        </nav>
      </header>

      {/* ── Hero ────────────────────────────────────────────────── */}
      <section className="relative z-10 px-6 pt-20 md:pt-28 pb-16 max-w-5xl mx-auto w-full text-center">
        <div className="inline-flex items-center gap-2.5 font-mono text-2xs tracking-[0.2em] text-accent-2 uppercase border border-accent/25 bg-accent/[0.07] px-4 py-2 rounded-full mb-8 animate-fade-up">
          <span className="w-1.5 h-1.5 rounded-full bg-tier-low animate-pulse-dot" />
          YouTube Authenticity Intelligence · Beta
        </div>

        <h1 className="display text-[3.25rem] leading-[0.98] sm:text-7xl lg:text-[5.5rem] font-semibold tracking-[-0.03em] mb-7">
          See who&apos;s{' '}
          <span className="text-shimmer">really</span>
          <br />
          behind the comments.
        </h1>

        <p className="text-lg md:text-xl text-fg-dim max-w-2xl mx-auto leading-relaxed mb-12">
          Paste any YouTube URL. OMISPHERE scores every commenter on eight
          independent signals, surfaces coordinated networks, and tracks
          narrative campaigns — probabilistic, with full evidence.
        </p>

        {/* Demo console */}
        <div className="gradient-border shadow-card-lg max-w-3xl mx-auto text-left p-6 md:p-8">
          <div className="flex items-center justify-between mb-5 flex-wrap gap-2">
            <div className="flex items-center gap-2.5">
              <span className="flex gap-1.5">
                <span className="w-2.5 h-2.5 rounded-full bg-tier-high/70" />
                <span className="w-2.5 h-2.5 rounded-full bg-tier-moderate/70" />
                <span className="w-2.5 h-2.5 rounded-full bg-tier-low/70" />
              </span>
              <p className="font-mono text-2xs tracking-[0.16em] text-fg-mute uppercase">
                live console — no signup
              </p>
            </div>
            <span className="font-mono text-2xs text-fg-faint tracking-wider">
              10 commenters · ~10s · 1 free/day
            </span>
          </div>
          <DemoScanForm />
        </div>

        <div className="mt-8 flex items-center justify-center gap-x-6 gap-y-2 flex-wrap font-mono text-2xs text-fg-mute tracking-wider">
          {['No card required', 'Real scan on your URL', 'Always probabilistic'].map((t) => (
            <span key={t} className="flex items-center gap-1.5">
              <CheckCircle2 size={11} className="text-tier-low" />
              {t}
            </span>
          ))}
        </div>
      </section>

      {/* ── Stat strip ──────────────────────────────────────────── */}
      <section className="relative z-10 px-6 pb-10 max-w-5xl mx-auto w-full">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-px rounded-2xl overflow-hidden border border-border-1 bg-border-1/60">
          {[
            { num: 8,    suffix: '',  label: 'Detection signals', sub: 'per commenter' },
            { num: 3,    suffix: '',  label: 'Coord. detectors',  sub: 'cross-account' },
            { num: 0,    suffix: '',  label: 'LLMs in core path',  sub: 'pure heuristics' },
            { num: null, suffix: '∞', label: 'Self-improving',     sub: 'every scan trains it' },
          ].map(({ num, suffix, label, sub }, i) => (
            <Reveal key={label} delay={i * 70} from="up" className="bg-bg-elev/80">
              <div className="group p-6 text-center spotlight h-full transition-colors hover:bg-bg-elev-2/60">
                <div className="display text-4xl font-semibold text-brand mb-1">
                  {num !== null ? <AnimatedNumber value={num} format={false} onView /> : suffix}
                </div>
                <div className="font-mono text-2xs text-fg uppercase tracking-wider">{label}</div>
                <div className="font-mono text-2xs text-fg-faint mt-0.5">{sub}</div>
              </div>
            </Reveal>
          ))}
        </div>
      </section>

      {/* ── Bento features ──────────────────────────────────────── */}
      <section className="relative z-10 px-6 py-16 max-w-5xl mx-auto w-full">
        <Reveal className="mb-12 max-w-2xl">
          <p className="font-mono text-2xs tracking-[0.2em] text-accent-2 uppercase mb-3">
            Capabilities
          </p>
          <h2 className="display text-3xl md:text-4xl font-semibold tracking-tight">
            Intelligence across every dimension
          </h2>
        </Reveal>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 auto-rows-fr">
          {FEATURES.map((f, i) => (
            <Reveal key={f.title} delay={(i % 3) * 80} from="up" className={f.span}>
              <FeatureCard {...f} />
            </Reveal>
          ))}
        </div>
      </section>

      {/* ── Scope ───────────────────────────────────────────────── */}
      <section className="relative z-10 px-6 pb-10 max-w-4xl mx-auto w-full">
        <Reveal className="glass rounded-2xl p-7">
          <p className="font-mono text-2xs tracking-[0.18em] uppercase text-accent-2 mb-3">
            Scope, plainly
          </p>
          <p className="text-base text-fg-dim leading-relaxed">
            Today OMISPHERE scans <span className="text-fg font-medium">YouTube</span> only — videos and channels.
            The detection engine is platform-agnostic; ingestion for X / Twitter, Reddit, and TikTok
            is on the roadmap. We&apos;d rather ship one platform with depth than four with stubs.
          </p>
        </Reveal>
      </section>

      {/* ── CTA ─────────────────────────────────────────────────── */}
      <section className="relative z-10 px-6 py-24 max-w-3xl mx-auto w-full text-center">
        <Reveal from="scale" className="space-y-7">
          <h2 className="display text-4xl md:text-5xl font-semibold tracking-[-0.02em] leading-[1.05]">
            Ready to see what&apos;s{' '}
            <span className="text-brand">real?</span>
          </h2>
          <p className="text-lg text-fg-dim max-w-xl mx-auto">
            $9.99/month · 20 scans · 3 free on signup. Cancel anytime.
            Built for journalists, researchers, and platform integrity teams.
          </p>
          <div className="flex items-center justify-center gap-4 pt-2 flex-wrap">
            <Link
              href="/signup"
              className="inline-flex items-center gap-2 bg-accent text-bg-deep font-semibold px-8 py-3.5 rounded-full hover:bg-accent-2 transition-all btn-glow"
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
        </Reveal>
      </section>

      {/* ── Footer ──────────────────────────────────────────────── */}
      <footer className="relative z-10 border-t border-border-1/40 px-6 py-9 mt-auto">
        <div className="max-w-5xl mx-auto flex items-center justify-between flex-wrap gap-4">
          <Logo />
          <p className="font-mono text-2xs tracking-wider text-fg-faint">
            Probabilistic Authenticity Intelligence
          </p>
          <div className="flex items-center gap-1.5 font-mono text-2xs text-fg-mute uppercase tracking-wider">
            {[['Terms', '/terms'], ['Privacy', '/privacy'], ['Pricing', '/pricing'], ['About', '/about']].map(([l, h]) => (
              <Link key={h} href={h} className="px-2.5 py-1 rounded-full hover:text-fg hover:bg-bg-elev transition-colors">{l}</Link>
            ))}
          </div>
        </div>
      </footer>
    </div>
  );
}

const FEATURES = [
  {
    icon: <ShieldAlert size={22} />,
    title: 'Per-commenter detection',
    body: 'Each commenter scored on temporal cadence, semantic repetition, AI-writing tells, profile metadata, personal-voice rate, engagement farming, fingerprint memory, and coordination. Probabilistic with explicit evidence.',
    span: 'md:col-span-2',
  },
  {
    icon: <Network size={22} />,
    title: 'Coordination clusters',
    body: 'Three cross-account detectors find groups acting together: temporal-semantic bursts, age cohorts, and co-engagement.',
    span: '',
  },
  {
    icon: <Activity size={22} />,
    title: 'Narrative tracking',
    body: 'Semantic clusters across all your scans. See which talking points are organic and which are amplified.',
    span: '',
  },
  {
    icon: <Database size={22} />,
    title: 'Self-improving database',
    body: 'Every scan adds a behavioural fingerprint and persists coordination edges. Future scans pull priors from the growing set, so the engine sharpens the more you use it.',
    span: 'md:col-span-2',
  },
  {
    icon: <Cpu size={22} />,
    title: 'Pure-signal engine',
    body: 'No LLMs in the core path — pure Python heuristics, embeddings, and graph algorithms. Fast, deterministic, auditable.',
    span: '',
  },
  {
    icon: <Eye size={22} />,
    title: 'Full evidence chain',
    body: 'Every score shows its work. Click any flag to see the raw signals that triggered it. No black boxes.',
    span: 'md:col-span-2',
  },
];

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
    <div className="group h-full bg-bg-elev rounded-2xl border border-border-1 p-6 card-interactive spotlight shadow-inner-top">
      <div className="w-11 h-11 rounded-xl bg-accent/[0.1] border border-accent/25 flex items-center justify-center text-accent-2 mb-4 group-hover:scale-110 group-hover:bg-accent/[0.16] transition-all duration-300">
        {icon}
      </div>
      <h3 className="text-lg font-semibold text-fg mb-2">{title}</h3>
      <p className="text-sm text-fg-dim leading-relaxed">{body}</p>
    </div>
  );
}
