import Link from 'next/link';
import {
  ArrowRight, CheckCircle2, Database, Fingerprint, Gauge,
  MessagesSquare, MousePointerClick, Radar, ScanLine,
  ShieldCheck, Users,
} from 'lucide-react';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Logo } from '@/components/shared/logo';
import { Reveal } from '@/components/shared/reveal';
import { AnimatedNumber } from '@/components/shared/animated-number';
import { ScrollProgress } from '@/components/shared/scroll-progress';
import { HeroVisual } from '@/components/shared/hero-visual';
import { TierBadge } from '@/components/shared/tier-badge';
import { DemoScanForm } from './demo-scan-form';
import { TRIAL_CREDITS, MONTHLY_CREDITS, SUBSCRIPTION_PRICE } from '@/lib/plan';

/**
 * Pre-login front page.
 *
 * Deliberately built from the SAME grammar as the signed-in app rather than a separate marketing
 * language, so a visitor recognises the product the moment they log in:
 *
 *   · the page-header slab from /investigations (rounded-2xl bg-bg-elev, top accent hairline,
 *     blurred orbs, `.section-label` eyebrow, `.display` heading, mono meta row, action cluster)
 *   · `.display` (Inter) as the heading voice, the app's own. The old Space Grotesk
 *     `.display-alt` marketing voice was the single biggest visual tell that this page belonged
 *     to a different product.
 *   · figures in mono/tabular (`.stat-value`), because in this product a number is evidence
 *   · the real `Card` / `Button` / `TierBadge` primitives rather than lookalikes
 *   · blue compiles and purple analyzes, the color story of the investigate workspace
 *
 * No `overflow-hidden` on the root: it creates a scroll container that breaks the sticky header.
 * Horizontal containment is handled by `overflow-x: clip` on html/body in globals.css.
 */
export function LandingPage() {
  return (
    <div className="min-h-screen bg-bg-deep flex flex-col">
      <ScrollProgress />

      {/* ── Chrome ───────────────────────────────────────────────────────────
          Mirrors the app topbar: 14 units tall, sticky, `glass` surface on a
          hairline, with the same mono telemetry pills. */}
      <header className="sticky top-0 z-30 h-14 shrink-0 border-b border-border-1 glass px-4 md:px-6 flex items-center gap-3 min-w-0">
        <Link
          href="/"
          aria-label="OMISPHERE home"
          className="shrink min-w-0 overflow-hidden rounded-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/50"
        >
          <Logo size="sm" />
        </Link>

        <div className="hidden lg:flex items-center gap-2.5 font-mono text-2xs text-fg-mute tracking-wider shrink-0 ml-2">
          <span className="inline-flex items-center gap-1.5 h-7 px-2.5 rounded-md border border-border-1 bg-bg-elev/60">
            <span className="w-1.5 h-1.5 rounded-full bg-tier-low" aria-hidden />
            <span>SIGNALS</span>
            <span className="text-fg-dim tabular">8</span>
          </span>
          <span className="inline-flex items-center gap-1.5 h-7 px-2.5 rounded-md border border-border-1 bg-bg-elev/60">
            <span>SOURCES</span>
            <span className="text-fg-dim tabular">2</span>
          </span>
        </div>

        <nav className="flex items-center gap-2 ml-auto shrink-0">
          <Link
            href="/sign-in"
            className="font-mono text-2xs tracking-[0.14em] uppercase text-fg-mute hover:text-fg transition-colors px-3 py-2 rounded-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/50"
          >
            Log in
          </Link>
          <Link href="/sign-up">
            <Button size="sm" className="btn-glow">
              Start free
              <ArrowRight size={12} />
            </Button>
          </Link>
        </nav>
      </header>

      <main className="flex-1">
        {/* ── Hero ─────────────────────────────────────────────────────────
            The /investigations page header, at hero scale. */}
        <Shell className="pt-6 md:pt-8">
          <div className="aurora relative overflow-hidden rounded-2xl border border-border-1 bg-bg-elev px-5 py-7 md:px-8 md:py-10">
            <span
              className="absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-accent/50 to-transparent"
              aria-hidden
            />
            <span
              className="pointer-events-none absolute -right-12 -top-12 h-52 w-52 rounded-full bg-violet/15 blur-3xl"
              aria-hidden
            />
            <span
              className="pointer-events-none absolute -left-10 bottom-0 h-36 w-36 rounded-full bg-accent/10 blur-2xl"
              aria-hidden
            />

            <div className="relative grid lg:grid-cols-[1fr_380px] gap-8 lg:gap-12 items-center">
              {/* Copy leads in DOM order, so on a phone (single column) the headline is the first
                  thing on screen and the visual follows it. The old layout floated the globe above
                  the copy, which pushed the value proposition below the fold on a 390px screen. */}
              <div className="min-w-0">
                {/* `.section-label` already carries a blue tick and is `flex-wrap: wrap`, so a long
                    label plus an icon orphaned the tick onto its own line at 390px. The label stays
                    short and the beta status rides alongside in its own span, which wraps as one
                    piece. */}
                <div className="flex items-center gap-2.5 flex-wrap">
                  <span className="section-label">Online media intelligence</span>
                  <span className="font-mono text-2xs tracking-wider uppercase text-accent-text">
                    Private beta
                  </span>
                </div>

                <h1
                  className="display font-semibold text-fg tracking-[-0.03em] leading-[1.02] mt-4 mb-5"
                  style={{ fontSize: 'clamp(2.1rem, 4.6vw, 3.4rem)' }}
                >
                  Score every account in a comment section.
                </h1>

                <p className="text-base text-fg-dim leading-relaxed max-w-[52ch] mb-7">
                  Paste an X post or a YouTube video. OmiSphere lists everyone who commented, you
                  pick which accounts to check, and each one comes back with a 0-to-100 score plus
                  the behavioral evidence behind it.
                </p>

                <div className="flex items-center gap-3 flex-wrap mb-7">
                  <Link href="/sign-up">
                    <Button size="lg" className="btn-glow">
                      <ScanLine size={15} />
                      Start free with {TRIAL_CREDITS} credits
                    </Button>
                  </Link>
                  {/* The free scan below is the second call to action: it is the strongest one on
                      the page (no signup, real result), so the button jumps to it rather than
                      competing with it. */}
                  <a href="#try">
                    <Button size="lg" variant="secondary">
                      Try a free scan
                      <ArrowRight size={14} />
                    </Button>
                  </a>
                </div>

                <ul className="flex items-center gap-x-5 gap-y-2 flex-wrap font-mono text-2xs text-fg-mute tracking-wider">
                  {[
                    `${TRIAL_CREDITS} free credits, no card`,
                    'A written read on every account',
                    'X and YouTube',
                  ].map((t) => (
                    <li key={t} className="flex items-center gap-1.5">
                      <CheckCircle2 size={10} className="text-tier-low shrink-0" aria-hidden />
                      {t}
                    </li>
                  ))}
                </ul>
              </div>

              {/* Inset on phones: the visual's floating verdict chips are positioned off its own
                  edges, so at full bleed the widest one ran into the slab's clip boundary. */}
              <div className="px-6 sm:px-0">
                <HeroVisual />
              </div>
            </div>
          </div>
        </Shell>

        {/* ── Signal tiles ─────────────────────────────────────────────────
            Figures in mono/tabular, the way the app renders evidence. */}
        <Shell className="pt-4">
          <Reveal from="up">
            <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
              {TILES.map(({ figure, animate, label, sub }) => (
                <div
                  key={label}
                  className="rounded-xl border border-border-1 bg-bg-elev surface-lit px-4 py-4"
                >
                  <div className="stat-value text-2xl text-fg mb-2">
                    {animate ? <AnimatedNumber value={animate} format={false} onView /> : figure}
                  </div>
                  <div className="font-mono text-2xs text-fg-dim uppercase tracking-wider">
                    {label}
                  </div>
                  <div className="font-mono text-2xs text-fg-faint mt-0.5">{sub}</div>
                </div>
              ))}
            </div>
          </Reveal>
        </Shell>

        {/* ── Live workspace ───────────────────────────────────────────────
            The free scan, framed like the investigate workspace panel. The id is the target of
            the hero's secondary call to action. */}
        <Shell id="try" className="pt-14">
          <Reveal className="mb-5">
            <SectionHeading
              eyebrow="Intelligence · Workspace"
              icon={<Radar size={11} className="text-accent" />}
              title="Run a scan right now"
              lede="The same engine the signed-in workspace runs. One free analysis per visitor, up to 25 accounts, no account needed."
            />
          </Reveal>

          <Reveal from="up">
            <div className="rounded-2xl border border-border-1 bg-bg-elev surface-lit overflow-hidden">
              <div className="px-4 md:px-5 py-3 border-b border-divider bg-bg/60 flex items-center justify-between flex-wrap gap-2">
                <span className="flex items-center gap-2 font-mono text-2xs tracking-[0.16em] uppercase text-accent-text">
                  <Radar size={13} className="text-accent" aria-hidden />
                  Free X scan, no account
                </span>
                <span className="font-mono text-2xs text-fg-faint tracking-wider uppercase">
                  Compile · select · analyze
                </span>
              </div>
              <div className="p-5 md:p-7">
                <DemoScanForm />
              </div>
            </div>
          </Reveal>
        </Shell>

        {/* ── How a scan runs ──────────────────────────────────────────────── */}
        <Shell className="pt-14">
          <Reveal className="mb-5">
            <SectionHeading
              eyebrow="Method"
              icon={<ScanLine size={11} className="text-accent" />}
              title="Three steps from a link to a scored account."
            />
          </Reveal>

          <div className="grid md:grid-cols-3 gap-3">
            {STEPS.map((s, i) => (
              <Reveal key={s.title} delay={i * 70} from="up">
                <Card interactive className="relative h-full p-5">
                  <span className="absolute -top-2.5 left-5 font-mono text-[0.6rem] tracking-[0.16em] text-fg-faint uppercase bg-bg-deep border border-border-1 rounded px-2 py-0.5">
                    {String(i + 1).padStart(2, '0')}
                  </span>
                  <span className="grid place-items-center w-9 h-9 rounded-lg border border-border-2 bg-bg-elev-2 text-accent-text mb-4 mt-1">
                    {s.icon}
                  </span>
                  <h3 className="text-sm font-semibold text-fg mb-2">{s.title}</h3>
                  <p className="text-sm text-fg-dim leading-relaxed">{s.body}</p>
                </Card>
              </Reveal>
            ))}
          </div>
        </Shell>

        {/* ── What you get ─────────────────────────────────────────────────── */}
        <Shell className="pt-14">
          <Reveal className="mb-5">
            <SectionHeading
              eyebrow="What you get"
              icon={<Gauge size={11} className="text-accent" />}
              title="The evidence behind every score."
            />
          </Reveal>

          <Reveal from="up">
            <div className="rounded-2xl border border-border-1 bg-bg-elev surface-lit divide-y divide-divider overflow-hidden">
              {CAPABILITIES.map((cap) => (
                <div key={cap.title} className="group flex gap-4 p-5 hover:bg-bg-elev-2 transition-colors">
                  <span className="shrink-0 grid place-items-center w-8 h-8 mt-0.5 rounded-lg border border-border-2 bg-bg-elev-2 text-fg-mute group-hover:text-accent-text group-hover:border-border-hot transition-colors">
                    {cap.icon}
                  </span>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-baseline gap-2.5 mb-1 flex-wrap">
                      <h3 className="text-sm font-semibold text-fg">{cap.title}</h3>
                      {cap.tag && (
                        <span className="font-mono text-[0.6rem] tracking-[0.12em] uppercase text-fg-faint border border-border-2 rounded px-1.5 py-0.5">
                          {cap.tag}
                        </span>
                      )}
                    </div>
                    <p className="text-sm text-fg-dim leading-relaxed">{cap.body}</p>
                  </div>
                </div>
              ))}
            </div>
          </Reveal>
        </Shell>

        {/* ── Scope ────────────────────────────────────────────────────────── */}
        <Shell className="pt-14">
          <Reveal from="up">
            <Card className="p-5 md:p-6">
              <span className="section-label">Scope</span>
              <p className="text-sm text-fg-dim leading-relaxed mt-3">
                OmiSphere reads <span className="text-fg font-medium">X (Twitter)</span> and{' '}
                <span className="text-fg font-medium">YouTube</span> today: posts, videos, and the
                accounts that comment on them. <span className="text-fg font-medium">Reddit</span> and{' '}
                <span className="text-fg font-medium">TikTok</span> arrive November 1st: the
                detection engine is already platform-agnostic, so they need an ingestion adapter
                rather than new detection work.
              </p>
            </Card>
          </Reveal>
        </Shell>

        {/* ── Close ────────────────────────────────────────────────────────── */}
        <Shell className="py-20">
          <Reveal from="up">
            <div className="border-t border-border-1 pt-14 text-center">
              <span className="section-label justify-center">Start your first scan</span>
              <h2 className="display text-3xl md:text-4xl font-semibold text-fg tracking-[-0.025em] mt-4 mb-4">
                Find out who&apos;s real.
              </h2>
              <p className="text-sm text-fg-dim max-w-lg mx-auto leading-relaxed mb-8">
                {SUBSCRIPTION_PRICE} a month buys {MONTHLY_CREDITS} credits. {TRIAL_CREDITS} are free to start,
                no card. Cancel whenever you like. Built for creators, brands, journalists, and
                platform-integrity teams.
              </p>
              <div className="flex items-center justify-center gap-3 flex-wrap">
                <Link href="/sign-up">
                  <Button size="lg" className="btn-glow">
                    Create your free account
                    <ArrowRight size={14} />
                  </Button>
                </Link>
                <Link
                  href="/pricing"
                  className="font-mono text-2xs tracking-wider uppercase text-fg-mute hover:text-fg-dim transition-colors px-3 py-2 rounded-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/50"
                >
                  See full pricing
                </Link>
              </div>
            </div>
          </Reveal>
        </Shell>
      </main>

      {/* ── Footer ─────────────────────────────────────────────────────────── */}
      <footer className="border-t border-border-1/60 px-4 md:px-6 py-8">
        <div className="max-w-6xl mx-auto flex items-center justify-between flex-wrap gap-4">
          <Logo size="sm" />
          <p className="font-mono text-2xs tracking-wider uppercase text-fg-faint">
            Online media intelligence
          </p>
          <div className="flex items-center gap-px font-mono text-2xs text-fg-mute tracking-wider uppercase">
            {[['Terms', '/terms'], ['Privacy', '/privacy'], ['Pricing', '/pricing'], ['About', '/about']].map(
              ([label, href]) => (
                <Link
                  key={href}
                  href={href}
                  className="px-2.5 py-1.5 rounded hover:text-fg transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/50"
                >
                  {label}
                </Link>
              ),
            )}
          </div>
        </div>
      </footer>
    </div>
  );
}

/** One gutter, one measure, every section: the app's content column. */
function Shell({
  children,
  className = '',
  id,
}: {
  children: React.ReactNode;
  className?: string;
  id?: string;
}) {
  return (
    <section id={id} className={`px-4 md:px-6 max-w-6xl mx-auto w-full ${className}`}>
      {children}
    </section>
  );
}

/** The app's page-header grammar: `.section-label` eyebrow over a `.display` heading. */
function SectionHeading({
  eyebrow,
  icon,
  title,
  lede,
}: {
  eyebrow: string;
  icon?: React.ReactNode;
  title: string;
  lede?: string;
}) {
  return (
    <div className="min-w-0">
      <span className="section-label inline-flex items-center gap-1.5">
        {icon}
        {eyebrow}
      </span>
      <h2 className="display text-xl md:text-2xl font-semibold text-fg tracking-tight mt-3">
        {title}
      </h2>
      {lede && <p className="text-sm text-fg-dim leading-relaxed mt-2 max-w-2xl">{lede}</p>}
    </div>
  );
}

const TILES = [
  { animate: 8, figure: null, label: 'Behavioral signals', sub: 'read per account' },
  { animate: null, figure: '0-100', label: 'OMI score', sub: 'per account, not per post' },
  { animate: 2, figure: null, label: 'Sources', sub: 'X and YouTube' },
  { animate: 25, figure: null, label: 'Free scan cap', sub: 'accounts, no account needed' },
] as const;

const CAPABILITIES = [
  {
    icon: <Gauge size={15} />,
    title: 'A score for each account',
    body:
      'Every account you check gets its own 0-to-100 reading on how likely it was bought or automated. OmiSphere judges each one on its own evidence rather than on a blanket read of the section.',
    tag: 'core',
  },
  {
    icon: <MessagesSquare size={15} />,
    title: 'A written read from the analyst',
    body:
      'The Omi analyst works through the evidence and explains, in a sentence or two, why an account looks genuine or bought.',
    tag: null,
  },
  {
    icon: <ShieldCheck size={15} />,
    title: 'Eight behavioral signals',
    body:
      'Posting cadence, message repetition, writing tells, profile metadata, personal-voice rate, engagement farming, account history, and fingerprint memory. Each one is a number you can audit.',
    tag: null,
  },
  {
    icon: <MousePointerClick size={15} />,
    title: 'You choose who to scan',
    body:
      'OmiSphere lists the whole comment section for free. Credits go only to the accounts you tick.',
    tag: null,
  },
  {
    icon: <Database size={15} />,
    title: 'Fingerprints carry between scans',
    body:
      'Each scan stores a behavioral fingerprint, so an account you checked in March still matches when it turns up under a different post in July.',
    tag: null,
  },
  {
    icon: <Fingerprint size={15} />,
    title: 'The full evidence chain',
    body:
      'Open any score to see what produced it: the comment, the account metadata, the posting cadence.',
    tag: null,
  },
];

const STEPS = [
  {
    icon: <ScanLine size={16} />,
    title: 'Paste a post',
    body:
      'Drop in an X post or a YouTube video. OmiSphere reads the comment section and lists who commented, free of charge.',
  },
  {
    icon: <MousePointerClick size={16} />,
    title: 'Pick the accounts',
    body:
      'Read the comments and tick the accounts worth checking. Credits go only to the ones you select.',
  },
  {
    icon: <Radar size={16} />,
    title: 'Read the scores',
    body:
      'Each account returns a 0-to-100 OMI score, a written verdict, and the signals that produced both.',
  },
];
