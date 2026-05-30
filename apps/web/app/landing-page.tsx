import Link from 'next/link';
import {
  ShieldAlert, Activity, Network, Database,
  CheckCircle2, ArrowRight, Cpu, Eye,
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

      {/* ── Nav ─────────────────────────────────────────────────── */}
      <header className="relative z-20 h-14 px-6 md:px-8 flex items-center justify-between border-b border-border-1/50 bg-bg-deep/95 backdrop-blur-sm sticky top-0">
        <Link href="/" aria-label="omisphere home">
          <Logo />
        </Link>
        <nav className="flex items-center gap-5 font-mono text-2xs tracking-[0.14em] text-fg-mute">
          <Link href="/pricing" className="hidden sm:block hover:text-fg transition-colors">Pricing</Link>
          <Link href="/about"   className="hidden sm:block hover:text-fg transition-colors">About</Link>
          <span className="hidden sm:block w-px h-3.5 bg-border-2" aria-hidden />
          <Link href="/login"   className="hover:text-fg transition-colors">Log in</Link>
          <Link
            href="/signup"
            className="inline-flex items-center gap-1.5 bg-accent text-bg-deep text-[0.7rem] font-semibold px-3.5 py-1.5 rounded-sm hover:bg-accent-2 transition-colors"
          >
            Sign up
            <ArrowRight size={11} />
          </Link>
        </nav>
      </header>

      {/* ── Hero ────────────────────────────────────────────────── */}
      <section className="relative z-10 px-6 md:px-8 pt-16 md:pt-20 pb-12 max-w-6xl mx-auto w-full">
        <div className="grid lg:grid-cols-[1fr_440px] gap-10 lg:gap-14 items-start">

          {/* Left: copy */}
          <div className="order-2 lg:order-1 lg:pt-4">
            <div
              className="inline-flex items-center gap-2 font-mono text-2xs tracking-[0.18em] text-accent-2 uppercase border border-accent/20 bg-accent/[0.06] px-3 py-1.5 rounded-sm mb-8"
              style={{ animation: 'fade-up 220ms cubic-bezier(0.16,1,0.3,1) both' }}
            >
              <span className="w-1.5 h-1.5 rounded-full bg-tier-low animate-pulse-dot" />
              Online Media Intelligence · Beta
            </div>

            <h1
              className="display font-semibold tracking-[-0.03em] leading-[0.92] mb-7"
              style={{
                fontSize: 'clamp(2.6rem, 5.5vw, 4.4rem)',
                animation: 'fade-up-lg 480ms cubic-bezier(0.16,1,0.3,1) both',
                animationDelay: '60ms',
              }}
            >
              Detect coordinated
              <br />
              <span className="text-gradient">influence</span>
              <br />
              at scale.
            </h1>

            <p
              className="text-base text-fg-dim leading-relaxed max-w-[480px] mb-9"
              style={{ animation: 'fade-up-lg 480ms cubic-bezier(0.16,1,0.3,1) both', animationDelay: '100ms' }}
            >
              Probabilistic intelligence on YouTube comment sections. Score every
              commenter across 8 independent signals, surface coordination networks,
              and track narrative campaigns — with full evidence chains.
            </p>

            <div
              className="flex items-center gap-3 flex-wrap mb-9"
              style={{ animation: 'fade-up-lg 480ms cubic-bezier(0.16,1,0.3,1) both', animationDelay: '150ms' }}
            >
              <Link
                href="/signup"
                className="inline-flex items-center gap-2 bg-accent text-bg-deep font-semibold px-6 py-2.5 rounded-sm hover:bg-accent-2 transition-colors text-sm btn-glow"
              >
                Begin investigating
                <ArrowRight size={14} />
              </Link>
              <Link
                href="/pricing"
                className="font-mono text-2xs tracking-wider text-fg-mute hover:text-fg-dim transition-colors"
              >
                View pricing →
              </Link>
            </div>

            <div
              className="flex items-center gap-6 flex-wrap font-mono text-2xs text-fg-faint tracking-wider"
              style={{ animation: 'fade-up-lg 480ms cubic-bezier(0.16,1,0.3,1) both', animationDelay: '200ms' }}
            >
              {['3 free scans', 'No credit card', 'Always probabilistic'].map((t) => (
                <span key={t} className="flex items-center gap-1.5">
                  <CheckCircle2 size={10} className="text-tier-low shrink-0" />
                  {t}
                </span>
              ))}
            </div>
          </div>

          {/* Right: visualization */}
          <div className="order-1 lg:order-2">
            <HeroVisual />
          </div>
        </div>
      </section>

      {/* ── Stats strip ─────────────────────────────────────────── */}
      <section className="relative z-10 px-6 md:px-8 pb-14 max-w-6xl mx-auto w-full">
        <Reveal from="up">
          <div className="border-y border-border-1 py-7">
            <div className="grid grid-cols-2 md:grid-cols-4 gap-8">
              {[
                { value: 8,    label: 'Detection signals', sub: 'per commenter' },
                { value: 3,    label: 'Coord. detectors',  sub: 'cross-account' },
                { value: 0,    label: 'LLMs in core path', sub: 'pure heuristics' },
                { value: null, suffix: '∞', label: 'Self-improving', sub: 'every scan trains it' },
              ].map(({ value, suffix, label, sub }) => (
                <div key={label}>
                  <div className="display text-3xl font-semibold text-fg mb-1 tabular-nums">
                    {value !== null ? <AnimatedNumber value={value!} format={false} onView /> : suffix}
                  </div>
                  <div className="font-mono text-2xs text-fg-dim uppercase tracking-wider">{label}</div>
                  <div className="font-mono text-2xs text-fg-faint mt-0.5">{sub}</div>
                </div>
              ))}
            </div>
          </div>
        </Reveal>
      </section>

      {/* ── Demo console ────────────────────────────────────────── */}
      <section className="relative z-10 px-6 md:px-8 pb-16 max-w-5xl mx-auto w-full">
        <Reveal from="up">
          <div className="border border-border-2 rounded-sm bg-bg-elev">
            <div className="px-5 py-3 border-b border-border-1/60 flex items-center justify-between flex-wrap gap-2">
              <div className="flex items-center gap-3">
                <span className="flex gap-1.5" aria-hidden>
                  <span className="w-2 h-2 rounded-full bg-tier-high/55" />
                  <span className="w-2 h-2 rounded-full bg-tier-moderate/55" />
                  <span className="w-2 h-2 rounded-full bg-tier-low/55" />
                </span>
                <span className="font-mono text-2xs tracking-[0.16em] text-fg-mute uppercase">
                  Live console · no account required
                </span>
              </div>
              <span className="font-mono text-2xs text-fg-faint tracking-wider">
                10 commenters · ≈10 s · 1 free / day
              </span>
            </div>
            <div className="p-6 md:p-8">
              <DemoScanForm />
            </div>
          </div>
        </Reveal>
      </section>

      {/* ── Capabilities ────────────────────────────────────────── */}
      <section className="relative z-10 px-6 md:px-8 pb-16 max-w-5xl mx-auto w-full">
        <Reveal className="mb-8">
          <p className="font-mono text-2xs tracking-[0.2em] text-fg-mute uppercase mb-2">Capabilities</p>
          <h2 className="display text-2xl md:text-3xl font-semibold tracking-tight">
            Intelligence across every dimension
          </h2>
        </Reveal>

        <div className="border border-border-1 rounded-sm divide-y divide-border-1">
          {CAPABILITIES.map((cap, i) => (
            <Reveal key={cap.title} delay={i * 55} from="up">
              <div className="group flex gap-4 p-5 hover:bg-bg-elev/50 transition-colors">
                <div className="shrink-0 w-8 h-8 border border-border-2 rounded-sm flex items-center justify-center text-fg-mute group-hover:text-accent group-hover:border-accent/35 transition-colors mt-0.5">
                  {cap.icon}
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-baseline gap-3 mb-1 flex-wrap">
                    <span className="text-sm font-semibold text-fg">{cap.title}</span>
                    {cap.tag && (
                      <span className="font-mono text-[0.6rem] tracking-[0.12em] uppercase text-fg-faint border border-border-2 px-1.5 py-0.5 rounded-sm">
                        {cap.tag}
                      </span>
                    )}
                  </div>
                  <p className="text-sm text-fg-dim leading-relaxed">{cap.body}</p>
                </div>
              </div>
            </Reveal>
          ))}
        </div>
      </section>

      {/* ── How it works ────────────────────────────────────────── */}
      <section className="relative z-10 px-6 md:px-8 pb-16 max-w-5xl mx-auto w-full">
        <Reveal className="mb-8">
          <p className="font-mono text-2xs tracking-[0.2em] text-fg-mute uppercase mb-2">How it works</p>
          <h2 className="display text-2xl md:text-3xl font-semibold tracking-tight">
            From URL to insight in seconds
          </h2>
        </Reveal>

        <div className="grid md:grid-cols-3 gap-4 relative">
          <div className="hidden md:block absolute top-[2.5rem] left-[calc(33%+0.75rem)] right-[calc(33%+0.75rem)] h-px bg-border-2" aria-hidden />

          {STEPS.map((s, i) => (
            <Reveal key={s.title} delay={i * 80} from="up">
              <div className="border border-border-1 rounded-sm p-5 bg-bg-elev shadow-inner-top card-interactive relative">
                <div className="absolute -top-2.5 left-5 font-mono text-[0.6rem] tracking-[0.16em] text-fg-faint uppercase bg-bg-deep border border-border-1 px-2 py-0.5">
                  {String(i + 1).padStart(2, '0')}
                </div>
                <div className="w-9 h-9 border border-border-2 rounded-sm flex items-center justify-center text-fg-mute mb-4 mt-1">
                  {s.icon}
                </div>
                <h3 className="text-sm font-semibold text-fg mb-2">{s.title}</h3>
                <p className="text-sm text-fg-dim leading-relaxed">{s.body}</p>
              </div>
            </Reveal>
          ))}
        </div>
      </section>

      {/* ── Scope ───────────────────────────────────────────────── */}
      <section className="relative z-10 px-6 md:px-8 pb-12 max-w-5xl mx-auto w-full">
        <Reveal>
          <div className="border border-border-1 rounded-sm p-6">
            <p className="font-mono text-2xs tracking-[0.18em] uppercase text-fg-mute mb-3">Scope, plainly</p>
            <p className="text-sm text-fg-dim leading-relaxed">
              Today OMISPHERE scans <span className="text-fg font-medium">YouTube</span> only — videos and channels.
              The detection engine is platform-agnostic; ingestion for X&nbsp;/&nbsp;Twitter, Reddit, and TikTok
              is on the roadmap. We&apos;d rather ship one platform with depth than four with stubs.
            </p>
          </div>
        </Reveal>
      </section>

      {/* ── CTA ─────────────────────────────────────────────────── */}
      <section className="relative z-10 px-6 md:px-8 py-20 max-w-3xl mx-auto w-full">
        <Reveal from="up">
          <div className="border-t border-border-1 pt-16 text-center">
            <p className="font-mono text-2xs tracking-[0.22em] text-fg-mute uppercase mb-5">
              Start your investigation
            </p>
            <h2 className="display text-3xl md:text-4xl font-semibold tracking-tight mb-5">
              See what&apos;s real.
            </h2>
            <p className="text-sm text-fg-dim max-w-md mx-auto mb-8">
              $9.99/month · 20 scans · 3 free on signup. Cancel anytime.
              Built for journalists, researchers, and platform integrity teams.
            </p>
            <div className="flex items-center justify-center gap-4 flex-wrap">
              <Link
                href="/signup"
                className="inline-flex items-center gap-2 bg-accent text-bg-deep font-semibold px-7 py-2.5 rounded-sm hover:bg-accent-2 transition-colors btn-glow"
              >
                Begin investigating
                <ArrowRight size={14} />
              </Link>
              <Link
                href="/pricing"
                className="font-mono text-2xs tracking-wider text-fg-mute hover:text-fg-dim transition-colors"
              >
                See full pricing →
              </Link>
            </div>
          </div>
        </Reveal>
      </section>

      {/* ── Footer ──────────────────────────────────────────────── */}
      <footer className="relative z-10 border-t border-border-1/40 px-6 md:px-8 py-8 mt-auto">
        <div className="max-w-5xl mx-auto flex items-center justify-between flex-wrap gap-4">
          <Logo />
          <p className="font-mono text-2xs tracking-wider text-fg-faint">Online Media Intelligence</p>
          <div className="flex items-center gap-px font-mono text-2xs text-fg-mute tracking-wider">
            {[['Terms', '/terms'], ['Privacy', '/privacy'], ['Pricing', '/pricing'], ['About', '/about']].map(([l, h]) => (
              <Link key={h} href={h} className="px-2.5 py-1 hover:text-fg transition-colors">{l}</Link>
            ))}
          </div>
        </div>
      </footer>
    </div>
  );
}

const CAPABILITIES = [
  {
    icon: <ShieldAlert size={15} />,
    title: 'Per-commenter detection',
    body: 'Each commenter scored on temporal cadence, semantic repetition, AI-writing tells, profile metadata, personal-voice rate, engagement farming, fingerprint memory, and coordination. Probabilistic with explicit evidence.',
    tag: 'core',
  },
  {
    icon: <Network size={15} />,
    title: 'Coordination mapping',
    body: 'Three cross-account detectors find groups acting together: temporal-semantic bursts, age cohorts, and co-engagement patterns across multiple videos.',
    tag: null,
  },
  {
    icon: <Activity size={15} />,
    title: 'Narrative tracking',
    body: 'Semantic clusters across all your scans surface which talking points are organic and which are amplified campaigns.',
    tag: null,
  },
  {
    icon: <Database size={15} />,
    title: 'Behavioral fingerprint database',
    body: 'Every scan adds a behavioral fingerprint and persists coordination edges. Future scans pull priors from the growing dataset — the engine sharpens with use.',
    tag: null,
  },
  {
    icon: <Cpu size={15} />,
    title: 'Pure-signal engine',
    body: 'No LLMs in the core detection path. Pure Python heuristics, embeddings, and graph algorithms. Fast, deterministic, auditable.',
    tag: 'no llm',
  },
  {
    icon: <Eye size={15} />,
    title: 'Full evidence chain',
    body: 'Every score shows its work. Click any flag to see the raw signals that triggered it. No black boxes, no unexplained verdicts.',
    tag: null,
  },
];

const STEPS = [
  {
    icon: <ArrowRight size={16} />,
    title: 'Paste a YouTube URL',
    body: 'Any video or channel URL. OMISPHERE pulls the top commenters immediately — no preprocessing required.',
  },
  {
    icon: <Activity size={16} />,
    title: 'Engine scores each commenter',
    body: 'Eight independent signals run in parallel: temporal cadence, semantic repetition, AI-writing tells, profile metadata, and more.',
  },
  {
    icon: <Eye size={16} />,
    title: 'Review the evidence',
    body: 'Every score shows its work. Save investigations and track narratives over time. Share or export to PDF.',
  },
];
