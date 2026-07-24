import Link from 'next/link';
import {
  ShieldCheck, Gauge, MessagesSquare, Database,
  CheckCircle2, ArrowRight, Fingerprint, ScanLine,
  Link2, MousePointerClick,
} from 'lucide-react';
import { Logo } from '@/components/shared/logo';
import { Reveal } from '@/components/shared/reveal';
import { AnimatedNumber } from '@/components/shared/animated-number';
import { ScrollProgress } from '@/components/shared/scroll-progress';
import { HeroVisual } from '@/components/shared/hero-visual';
import { DemoScanForm } from './demo-scan-form';
import { TRIAL_CREDITS, MONTHLY_CREDITS } from '@/lib/plan';

export function LandingPage() {
  return (
    <div className="min-h-screen bg-bg-deep flex flex-col relative overflow-hidden">
      <ScrollProgress />

      {/* ── Nav ─────────────────────────────────────────────────── */}
      <header className="relative z-20 h-14 px-6 md:px-8 flex items-center justify-between border-b border-border-1/50 bg-bg-deep/95 backdrop-blur-sm sticky top-0">
        <Link href="/" aria-label="omisphere home">
          <Logo />
        </Link>
        {/* A cold visitor has two jobs here: start, or sign back in. Pricing and
            About live in the footer — a buying decision before the value moment
            is a detour. Both links go straight to Clerk. */}
        <nav className="flex items-center gap-5 font-mono text-2xs tracking-[0.14em] text-fg-mute">
          <Link href="/sign-in" className="hover:text-fg transition-colors">Log in</Link>
          <Link
            href="/sign-up"
            className="inline-flex items-center gap-1.5 btn-lamp text-[0.7rem] font-semibold px-3.5 py-1.5 rounded-md"
          >
            Start free
            <ArrowRight size={11} />
          </Link>
        </nav>
      </header>

      {/* ── Hero ────────────────────────────────────────────────── */}
      <section className="aurora relative z-10 px-6 md:px-8 pt-16 md:pt-20 pb-12 max-w-6xl mx-auto w-full">
        <div className="grid lg:grid-cols-[1fr_440px] gap-10 lg:gap-14 items-start">

          {/* Left: copy */}
          <div className="order-2 lg:order-1 lg:pt-4">
            <div
              className="inline-flex items-center gap-2 font-mono text-2xs tracking-[0.18em] text-accent-2 uppercase border border-accent/20 bg-accent/[0.06] px-3 py-1.5 rounded-sm mb-8"
              style={{ animation: 'fade-up 220ms cubic-bezier(0.16,1,0.3,1) both' }}
            >
              <span className="w-1.5 h-1.5 rounded-full bg-tier-low animate-pulse-dot" />
              Online Media Intelligence · Private beta
            </div>

            <h1
              className="display-alt font-semibold tracking-[-0.035em] leading-[0.94] mb-7"
              style={{
                fontSize: 'clamp(2.5rem, 5.4vw, 4.2rem)',
                animation: 'fade-up-lg 480ms cubic-bezier(0.16,1,0.3,1) both',
                animationDelay: '60ms',
              }}
            >
              See which accounts
              <br />
              are real — and which
              <br />
              were <span className="text-gradient">bought</span>.
            </h1>

            <p
              className="text-base text-fg-dim leading-relaxed max-w-[490px] mb-9"
              style={{ animation: 'fade-up-lg 480ms cubic-bezier(0.16,1,0.3,1) both', animationDelay: '100ms' }}
            >
              Paste a post from X or YouTube. OmiSphere pulls the comment section, you
              pick the accounts to check, and each one comes back with an OMI score and
              a plain-English read: a real person, or a bought account. Every verdict
              shows the behavioral evidence behind it.
            </p>

            <div
              className="flex items-center gap-3 flex-wrap mb-9"
              style={{ animation: 'fade-up-lg 480ms cubic-bezier(0.16,1,0.3,1) both', animationDelay: '150ms' }}
            >
              <Link
                href="/sign-up"
                className="inline-flex items-center gap-2 btn-lamp font-semibold px-6 py-2.5 rounded-lg text-sm"
              >
                Start free — {TRIAL_CREDITS} credits
                <ArrowRight size={14} />
              </Link>
              {/* The pinned featured-campaign token (cmp_ + campaign_key, seeded at
                  boot; held by test_stable_tokens_match_the_landing_page_contract so
                  a scheme change breaks loudly instead of dead-linking). A real,
                  disclosed case with its evidence, no account required. */}
              <a
                href="/rc/cmp_feat_cn_xinjiang"
                className="inline-flex items-center gap-2 border border-border-2 text-fg-dim font-medium px-5 py-2.5 rounded-lg hover:text-fg hover:border-border-hot transition-colors text-sm"
              >
                See a real case — no sign-up
              </a>
            </div>

            <div
              className="flex items-center gap-x-6 gap-y-2 flex-wrap font-mono text-2xs text-fg-faint tracking-wider"
              style={{ animation: 'fade-up-lg 480ms cubic-bezier(0.16,1,0.3,1) both', animationDelay: '200ms' }}
            >
              {[`${TRIAL_CREDITS} free credits, no card`, 'A plain-English reason on every score', 'X and YouTube'].map((t) => (
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
                { value: 8,    suffix: null, label: 'Behavioral signals', sub: 'read per account' },
                { value: 100,  suffix: null, label: 'OMI score', sub: '0 real · 100 bought' },
                { value: 2,    suffix: null, label: 'Platforms', sub: 'X · YouTube' },
                { value: null, suffix: 'Why', label: 'Every verdict', sub: 'explained in plain English' },
              ].map(({ value, suffix, label, sub }) => (
                <div key={label}>
                  <div className="display-alt text-3xl font-semibold text-fg mb-1 tabular-nums">
                    {value !== null ? <AnimatedNumber value={value} format={false} onView /> : suffix}
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
          <div className="border border-border-2 rounded-xl bg-bg-elev overflow-hidden">
            <div className="px-5 py-3 border-b border-border-1/60 flex items-center justify-between flex-wrap gap-2">
              <div className="flex items-center gap-3">
                <span className="flex gap-1.5" aria-hidden>
                  <span className="w-2 h-2 rounded-full bg-tier-high/55" />
                  <span className="w-2 h-2 rounded-full bg-tier-moderate/55" />
                  <span className="w-2 h-2 rounded-full bg-tier-low/55" />
                </span>
                <span className="font-mono text-2xs tracking-[0.16em] text-fg-mute uppercase">
                  Free X scan — no account
                </span>
              </div>
              <span className="font-mono text-2xs text-fg-faint tracking-wider">
                Up to 25 repliers · one per visitor
              </span>
            </div>
            <div className="p-6 md:p-8">
              <DemoScanForm />
            </div>
          </div>
        </Reveal>
      </section>

      {/* ── How it works ────────────────────────────────────────── */}
      <section className="relative z-10 px-6 md:px-8 pb-16 max-w-5xl mx-auto w-full">
        <Reveal className="mb-8">
          <p className="font-mono text-2xs tracking-[0.2em] text-fg-mute uppercase mb-2">How it works</p>
          <h2 className="display-alt text-2xl md:text-3xl font-semibold tracking-tight">
            A post goes in. Scored accounts come out.
          </h2>
        </Reveal>

        <div className="grid md:grid-cols-3 gap-4 relative">
          <div className="hidden md:block absolute top-[2.5rem] left-[calc(33%+0.75rem)] right-[calc(33%+0.75rem)] h-px bg-border-2" aria-hidden />

          {STEPS.map((s, i) => (
            <Reveal key={s.title} delay={i * 80} from="up">
              <div className="border border-border-1 rounded-xl p-5 bg-bg-elev card-interactive relative">
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

      {/* ── Capabilities ────────────────────────────────────────── */}
      <section className="relative z-10 px-6 md:px-8 pb-16 max-w-5xl mx-auto w-full">
        <Reveal className="mb-8">
          <p className="font-mono text-2xs tracking-[0.2em] text-fg-mute uppercase mb-2">What you get</p>
          <h2 className="display-alt text-2xl md:text-3xl font-semibold tracking-tight">
            Evidence first. Then an analyst explains it.
          </h2>
        </Reveal>

        <div className="border border-border-1 rounded-xl divide-y divide-border-1 overflow-hidden">
          {CAPABILITIES.map((cap) => (
            <Reveal key={cap.title} from="up">
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

      {/* ── Scope ───────────────────────────────────────────────── */}
      <section className="relative z-10 px-6 md:px-8 pb-12 max-w-5xl mx-auto w-full">
        <Reveal>
          <div className="rounded-xl border border-border-1 bg-bg-elev p-6">
            <p className="font-mono text-2xs tracking-[0.18em] uppercase text-fg-mute mb-3">Scope, plainly</p>
            <p className="text-sm text-fg-dim leading-relaxed">
              Today OmiSphere reads <span className="text-fg font-medium">X (Twitter)</span> and
              <span className="text-fg font-medium"> YouTube</span> — posts, videos, and the accounts
              that comment on them. The detection engine is platform-agnostic; Reddit and TikTok are
              next. We would rather ship two platforms with depth than four with stubs.
            </p>
          </div>
        </Reveal>
      </section>

      {/* ── CTA ─────────────────────────────────────────────────── */}
      <section className="relative z-10 px-6 md:px-8 py-20 max-w-3xl mx-auto w-full">
        <Reveal from="up">
          <div className="border-t border-border-1 pt-16 text-center">
            <p className="font-mono text-2xs tracking-[0.22em] text-fg-mute uppercase mb-5">
              Start your first scan
            </p>
            <h2 className="display-alt text-3xl md:text-4xl font-semibold tracking-tight mb-5">
              Find out who&apos;s real.
            </h2>
            <p className="text-sm text-fg-dim max-w-md mx-auto mb-8">
              ${'9.99'}/month · {MONTHLY_CREDITS} credits monthly · {TRIAL_CREDITS} free to start. Cancel anytime.
              Built for creators, brands, journalists, and platform-integrity teams.
            </p>
            <div className="flex items-center justify-center gap-4 flex-wrap">
              <Link
                href="/sign-up"
                className="inline-flex items-center gap-2 btn-lamp font-semibold px-7 py-2.5 rounded-lg"
              >
                Create your free account
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
    icon: <Gauge size={15} />,
    title: 'A per-account OMI score',
    body: 'Every account you check gets its own 0-to-100 score for how likely it is bought or inauthentic. No blanket verdict on the whole comment section — each account is judged on its own evidence.',
    tag: 'core',
  },
  {
    icon: <MessagesSquare size={15} />,
    title: 'A plain-English read on every account',
    body: 'The omi analyst reads the evidence and tells you, in a sentence or two, why an account looks real or bought. No jargon, no black box.',
    tag: null,
  },
  {
    icon: <ShieldCheck size={15} />,
    title: 'Eight behavioral signals',
    body: 'Posting cadence, repetition, writing tells, profile metadata, personal-voice rate, engagement farming, account history, and fingerprint memory. Computed, not guessed — fast and auditable.',
    tag: null,
  },
  {
    icon: <MousePointerClick size={15} />,
    title: 'Pick who to scan',
    body: 'OmiSphere pulls the whole comment section for free. You choose the accounts worth checking, and credits go only to the ones you select.',
    tag: null,
  },
  {
    icon: <Database size={15} />,
    title: 'A memory that sharpens with use',
    body: 'Every scan adds a behavioral fingerprint to the database. Later scans pull priors from what came before, so repeat offenders surface faster.',
    tag: null,
  },
  {
    icon: <Fingerprint size={15} />,
    title: 'The full evidence chain',
    body: 'Open any score to see the raw signals that drove it — the comment, the account metadata, the cadence. Every number shows its work.',
    tag: null,
  },
];

const STEPS = [
  {
    icon: <Link2 size={16} />,
    title: 'Paste a post',
    body: 'Drop in any X post or YouTube video. OmiSphere pulls its comment section — up to every account on the post.',
  },
  {
    icon: <MousePointerClick size={16} />,
    title: 'Pick the accounts',
    body: 'Read through the comments and select the ones you want checked. You spend credits only on the accounts you choose.',
  },
  {
    icon: <ScanLine size={16} />,
    title: 'Read each score',
    body: 'Each account comes back with a 0-to-100 OMI score and a plain-English reason: real person, or bought, and the evidence behind the call.',
  },
];
