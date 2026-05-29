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
  ScanSearch,
  BarChart3,
  Brain,
  ShieldCheck,
  Zap,
  Lock,
  TrendingUp,
} from 'lucide-react';
import { Logo } from '@/components/shared/logo';
import { Reveal } from '@/components/shared/reveal';
import { AnimatedNumber } from '@/components/shared/animated-number';
import { ScrollProgress } from '@/components/shared/scroll-progress';
import { HeroVisual } from '@/components/shared/hero-visual';
import { DemoScanForm } from './demo-scan-form';

export function LandingPage() {
  return (
    <div className="min-h-screen bg-bg-deep flex flex-col relative overflow-hidden grain">
      <ScrollProgress />

      {/* ── Ambient spectral field ──────────────────────────────── */}
      <div className="fixed inset-0 pointer-events-none overflow-hidden" aria-hidden>
        <div className="absolute top-[-18%] left-[8%] w-[680px] h-[620px] rounded-full bg-accent/[0.09] blur-[160px] animate-drift" />
        <div className="absolute top-[5%] right-[-10%] w-[560px] h-[520px] rounded-full bg-violet/[0.06] blur-[140px] animate-drift-slow" />
        <div className="absolute bottom-[4%] left-[-6%] w-[420px] h-[420px] rounded-full bg-accent-2/[0.04] blur-[120px] animate-float" style={{ animationDelay: '-3s' }} />
      </div>
      <div className="fixed inset-0 pointer-events-none dot-bg opacity-[0.28]" aria-hidden />

      {/* ── Nav ─────────────────────────────────────────────────── */}
      <header className="relative z-20 px-6 py-4 flex items-center justify-between border-b border-border-1/40 backdrop-blur-xl bg-bg-deep/70 sticky top-0">
        <Link href="/" aria-label="omisphere home">
          <Logo />
        </Link>
        <nav className="flex items-center gap-1.5 sm:gap-2 font-mono text-2xs tracking-[0.16em] text-fg-mute uppercase">
          <Link href="/pricing" className="hidden sm:block px-3 py-1.5 rounded-full hover:text-fg hover:bg-bg-elev transition-colors">Pricing</Link>
          <Link href="/about"   className="hidden sm:block px-3 py-1.5 rounded-full hover:text-fg hover:bg-bg-elev transition-colors">About</Link>
          <Link href="/login"   className="px-3 py-1.5 rounded-full hover:text-fg hover:bg-bg-elev transition-colors">Log in</Link>
          <Link
            href="/signup"
            className="text-bg-deep bg-accent font-semibold px-4 py-1.5 rounded-full hover:bg-accent-2 transition-all btn-glow"
          >
            Sign up
          </Link>
        </nav>
      </header>

      {/* ── Hero ────────────────────────────────────────────────── */}
      <section className="relative z-10 px-6 pt-16 md:pt-24 pb-8 max-w-6xl mx-auto w-full">
        <div className="grid lg:grid-cols-2 gap-10 lg:gap-16 items-center">

          {/* Left: copy */}
          <div className="order-2 lg:order-1">
            <div
              className="inline-flex items-center gap-2.5 font-mono text-2xs tracking-[0.2em] text-accent-2 uppercase border border-accent/25 bg-accent/[0.07] px-4 py-2 rounded-full mb-8"
              style={{ animation: 'fade-up 240ms cubic-bezier(0.16,1,0.3,1) both' }}
            >
              <span className="w-1.5 h-1.5 rounded-full bg-tier-low animate-pulse-dot" />
              Online Media Intelligence · Beta
            </div>

            <h1
              className="display font-semibold tracking-[-0.035em] leading-[0.94] mb-7"
              style={{
                fontSize: 'clamp(2.8rem, 6vw, 4.75rem)',
                animation: 'fade-up-lg 520ms cubic-bezier(0.16,1,0.3,1) both',
                animationDelay: '60ms',
              }}
            >
              See who&apos;s{' '}
              <span className="text-shimmer">really</span>
              <br />
              behind the{' '}
              <br className="hidden sm:block" />
              <span className="text-gradient">comments.</span>
            </h1>

            <p
              className="text-lg text-fg-dim leading-relaxed max-w-lg mb-10"
              style={{ animation: 'fade-up-lg 520ms cubic-bezier(0.16,1,0.3,1) both', animationDelay: '120ms' }}
            >
              Paste any YouTube URL. OMISPHERE scores every commenter on eight
              independent signals, surfaces coordinated networks, and tracks
              narrative campaigns — probabilistic, with full evidence.
            </p>

            <div
              className="flex items-center gap-4 flex-wrap mb-8"
              style={{ animation: 'fade-up-lg 520ms cubic-bezier(0.16,1,0.3,1) both', animationDelay: '180ms' }}
            >
              <Link
                href="/signup"
                className="inline-flex items-center gap-2 bg-accent text-bg-deep font-semibold px-7 py-3.5 rounded-full hover:bg-accent-2 transition-all btn-glow text-[0.95rem]"
              >
                Start free trial
                <ArrowRight size={16} />
              </Link>
              <Link
                href="/pricing"
                className="font-mono text-2xs tracking-wider uppercase text-fg-dim hover:text-fg transition-colors px-2 py-3.5"
              >
                See pricing →
              </Link>
            </div>

            <div
              className="flex items-center gap-x-6 gap-y-2 flex-wrap font-mono text-2xs text-fg-mute tracking-wider"
              style={{ animation: 'fade-up-lg 520ms cubic-bezier(0.16,1,0.3,1) both', animationDelay: '230ms' }}
            >
              {['No card required', 'Real scan on your URL', 'Always probabilistic'].map((t) => (
                <span key={t} className="flex items-center gap-1.5">
                  <CheckCircle2 size={11} className="text-tier-low" />
                  {t}
                </span>
              ))}
            </div>
          </div>

          {/* Right: visualization */}
          <div className="order-1 lg:order-2 flex justify-center lg:justify-end">
            <HeroVisual />
          </div>
        </div>
      </section>

      {/* ── Demo console ────────────────────────────────────────── */}
      <section className="relative z-10 px-6 py-10 max-w-5xl mx-auto w-full">
        <Reveal from="up">
          <div className="gradient-border shadow-card-lg">
            <div className="p-6 md:p-8">
              <div className="flex items-center justify-between mb-6 flex-wrap gap-2">
                <div className="flex items-center gap-2.5">
                  <span className="flex gap-1.5">
                    <span className="w-2.5 h-2.5 rounded-full bg-tier-high/75" />
                    <span className="w-2.5 h-2.5 rounded-full bg-tier-moderate/75" />
                    <span className="w-2.5 h-2.5 rounded-full bg-tier-low/75" />
                  </span>
                  <p className="font-mono text-2xs tracking-[0.18em] text-fg-mute uppercase">
                    live console — no signup required
                  </p>
                </div>
                <span className="font-mono text-2xs text-fg-faint tracking-wider">
                  10 commenters · ~10s · 1 free / day
                </span>
              </div>
              <DemoScanForm />
            </div>
          </div>
        </Reveal>
      </section>

      {/* ── Stat strip ──────────────────────────────────────────── */}
      <section className="relative z-10 px-6 pb-12 max-w-5xl mx-auto w-full">
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

      {/* ── Four pillars ────────────────────────────────────────── */}
      <section className="relative z-10 px-6 pb-14 max-w-5xl mx-auto w-full">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-5">
          {PILLARS.map((p, i) => (
            <Reveal key={p.label} delay={i * 80} from="up">
              <div className="group flex flex-col items-center text-center gap-3 py-1">
                <div className="relative w-14 h-14 rounded-2xl border border-border-2 bg-bg-elev flex items-center justify-center text-accent-2 group-hover:border-accent/40 group-hover:shadow-glow-sm transition-all duration-300">
                  <span className="absolute inset-0 rounded-2xl bg-accent/[0.06] opacity-0 group-hover:opacity-100 transition-opacity" />
                  <span className="relative">{p.icon}</span>
                </div>
                <div>
                  <div className="font-mono text-2xs tracking-[0.18em] uppercase text-fg">{p.label}</div>
                  <div className="text-xs text-fg-mute mt-1 max-w-[16ch] mx-auto leading-snug">{p.sub}</div>
                </div>
              </div>
            </Reveal>
          ))}
        </div>
      </section>

      {/* ── How it works ────────────────────────────────────────── */}
      <section className="relative z-10 px-6 py-16 max-w-5xl mx-auto w-full">
        <Reveal className="mb-12 text-center">
          <p className="font-mono text-2xs tracking-[0.2em] text-accent-2 uppercase mb-3">How it works</p>
          <h2 className="display text-3xl md:text-4xl font-semibold tracking-tight">
            From URL to insight in seconds
          </h2>
        </Reveal>

        <div className="grid md:grid-cols-3 gap-5 md:gap-6 relative">
          {/* Connector line (desktop) */}
          <div className="hidden md:block absolute top-[3.5rem] left-[calc(33%+1rem)] right-[calc(33%+1rem)] h-px bg-gradient-to-r from-accent/40 to-violet/40" aria-hidden />

          {STEPS.map((s, i) => (
            <Reveal key={s.title} delay={i * 100} from="up">
              <div className="group relative bg-bg-elev border border-border-1 rounded-2xl p-6 spotlight card-interactive shadow-inner-top text-center">
                <div className="inline-flex items-center justify-center w-12 h-12 rounded-xl bg-bg-elev-2 border border-border-2 text-accent mb-4 group-hover:border-accent/50 group-hover:bg-accent/[0.08] transition-all duration-300 relative z-10">
                  {s.icon}
                </div>
                <div className="absolute -top-3 -right-2 font-mono text-[0.55rem] tracking-[0.18em] text-fg-faint uppercase bg-bg-deep border border-border-1 px-2 py-0.5 rounded-full">
                  step {i + 1}
                </div>
                <h3 className="text-base font-semibold text-fg mb-2">{s.title}</h3>
                <p className="text-sm text-fg-dim leading-relaxed">{s.body}</p>
              </div>
            </Reveal>
          ))}
        </div>
      </section>

      {/* ── Bento features ──────────────────────────────────────── */}
      <section className="relative z-10 px-6 pb-16 max-w-5xl mx-auto w-full">
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
          <h2 className="display text-4xl md:text-5xl font-semibold tracking-[-0.025em] leading-[1.05]">
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
            Online Media Intelligence
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

const PILLARS = [
  { icon: <ScanSearch size={22} />, label: 'Detect',        sub: 'Bots, AI, coordination' },
  { icon: <BarChart3 size={22} />,  label: 'Analyze',       sub: 'Eight independent signals' },
  { icon: <Brain size={22} />,      label: 'Understand',    sub: 'Narratives & networks' },
  { icon: <ShieldCheck size={22} />,label: 'Protect Truth', sub: 'Evidence, not verdicts' },
];

const STEPS = [
  {
    icon: <Zap size={20} />,
    title: 'Paste a YouTube URL',
    body: 'Any video or channel URL. OMISPHERE pulls the top commenters immediately with no preprocessing required.',
  },
  {
    icon: <TrendingUp size={20} />,
    title: 'Engine scores each commenter',
    body: 'Eight independent signals run in parallel: temporal cadence, semantic repetition, AI-writing tells, profile metadata, and more.',
  },
  {
    icon: <Lock size={20} />,
    title: 'Review the evidence',
    body: 'Every score shows its work. Click any flag to see the raw signals. Save investigations and track narratives over time.',
  },
];

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
      <div className="w-11 h-11 rounded-xl bg-accent/[0.10] border border-accent/25 flex items-center justify-center text-accent-2 mb-4 group-hover:scale-110 group-hover:bg-accent/[0.16] transition-all duration-300">
        {icon}
      </div>
      <h3 className="text-lg font-semibold text-fg mb-2">{title}</h3>
      <p className="text-sm text-fg-dim leading-relaxed">{body}</p>
    </div>
  );
}
