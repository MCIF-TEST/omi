import Link from 'next/link';
import { ArrowRight, ArrowUpRight } from 'lucide-react';
import { Logo } from '@/components/shared/logo';
import { Reveal } from '@/components/shared/reveal';
import { ScorecardPreview } from '@/components/shared/scorecard-preview';
import { DemoScanForm } from './demo-scan-form';
import {
  TRIAL_CREDITS, TRIAL_CREDITS_LABEL, CREDIT_NOUN,
  MONTHLY_CREDITS, SUBSCRIPTION_PRICE, PLAN_NAME,
} from '@/lib/plan';

/**
 * Pre-login front page.
 *
 * Rebuilt to stop reading as a generated SaaS template. What that actually meant, concretely:
 *
 *   · The hero was a centred rounded slab with blurred colour orbs behind it and a force-directed
 *     node graph on the right. All three are house style for AI product demos, and the graph in
 *     particular illustrated nothing this product returns. The slab is gone (the hero now sits
 *     directly on the page ground), the orbs are gone, and the graph is replaced by
 *     `ScorecardPreview`, which shows the real shape of the output.
 *   · Everything was centred and evenly weighted, which is what makes a page feel machine-laid.
 *     The page now runs off a hard left axis with a numbered index rail, sections are deliberately
 *     unequal in width, and the closing block is left-aligned rather than centred.
 *   · Inter at every size read corporate and defaulted. Display type is now Archivo, set tight and
 *     heavy (`.display-hard`). Body copy stays Inter so the signed-in app still matches.
 *   · Soft blue pill buttons read friendly. Primary is now a bone slab with 2px corners.
 *
 * The colder palette, square edges and display face are all scoped under `.omi-landing` in
 * globals.css. Nothing in the signed-in app changes.
 *
 * No `overflow-hidden` on the root: it creates a scroll container that breaks the sticky header.
 * Horizontal containment is handled by `overflow-x: clip` on html/body in globals.css.
 */
export function LandingPage() {
  return (
    <div className="omi-landing omi-landing-grid min-h-screen bg-bg-deep flex flex-col">
      {/* `ScrollProgress` deliberately removed. Its own docstring called it "pure decoration", and
          it painted the suspicion ramp (green to amber to red) across the top of the viewport as a
          rainbow hairline. That ramp is a data legend for probability meters, so spending it on
          scroll position both drains the meaning it carries elsewhere and reads as exactly the
          decorative flourish this page is trying to shed. Scroll position already has an indicator:
          the scrollbar. Still used by the marketing layout, which is untouched. */}

      {/* ── Chrome ───────────────────────────────────────────────────────────
          Square, solid, hairline. The mono telemetry pills are gone: they were
          decoration dressed as data, and they competed with the headline. */}
      {/* Fully opaque, not 95%. A partly transparent bar lets type scroll under it as a ghost,
          which is the soft translucent register this page is moving away from. */}
      <header className="sticky top-0 z-30 h-14 shrink-0 border-b border-border-1 bg-bg-deep px-4 md:px-8 flex items-center gap-3 min-w-0">
        <Link
          href="/"
          aria-label="OMISPHERE home"
          className="shrink min-w-0 overflow-hidden focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/50"
        >
          <Logo size="sm" />
        </Link>

        <span className="hidden md:block ml-4 font-mono text-[0.625rem] tracking-[0.18em] uppercase text-fg-faint">
          Online media intelligence
        </span>

        <nav className="flex items-center gap-1.5 ml-auto shrink-0">
          <Link
            href="/sign-in"
            className="font-mono text-[0.625rem] tracking-[0.16em] uppercase text-fg-mute hover:text-fg transition-colors px-3 py-2 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/50"
          >
            Log in
          </Link>
          <Link
            href="/sign-up"
            className="btn-bone inline-flex items-center gap-1.5 h-8 px-3.5 font-mono text-[0.625rem] tracking-[0.14em] uppercase focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/60 focus-visible:ring-offset-2 focus-visible:ring-offset-bg-deep"
          >
            Start free
            <ArrowRight size={11} />
          </Link>
        </nav>
      </header>

      <main className="flex-1">
        {/* ══ Hero ═══════════════════════════════════════════════════════════
            No card, no orbs, no centring. The headline sits on the page ground
            and runs to a hard left axis, and the readout is pushed DOWN rather
            than vertically centred against it, which is where most of the
            asymmetry comes from. */}
        <Shell className="pt-12 md:pt-20 pb-10 md:pb-14">
          <div className="grid lg:grid-cols-12 gap-x-10 gap-y-12">
            <div className="lg:col-span-7 min-w-0">
              <div className="flex items-center gap-3 mb-7">
                <span className="idx">001</span>
                <span className="h-px w-8 bg-border-hot" aria-hidden />
                <span className="font-mono text-[0.625rem] tracking-[0.18em] uppercase text-fg-mute">
                  Private beta
                </span>
              </div>

              <h1
                className="display-hard text-fg mb-7"
                style={{ fontSize: 'clamp(2.35rem, 6.4vw, 4.75rem)' }}
              >
                Score every account in a comment section.
              </h1>

              <p className="text-[0.9375rem] text-fg-dim leading-relaxed max-w-[54ch] mb-9">
                Paste an X post or a YouTube video. OmiSphere lists everyone who commented, you
                pick which accounts to check, and each one comes back with a 0-to-100 score plus
                the behavioral evidence behind it.
              </p>

              {/* Stacks on narrow screens rather than sitting beside the copy column, which is
                  what collapses a flexible text column to two characters per line. */}
              <div className="flex flex-col sm:flex-row sm:items-center gap-2.5 mb-8">
                <Link
                  href="/sign-up"
                  className="btn-bone inline-flex items-center justify-center gap-2 h-12 px-6 text-[0.9375rem] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/60 focus-visible:ring-offset-2 focus-visible:ring-offset-bg-deep"
                >
                  Start free with {TRIAL_CREDITS} {CREDIT_NOUN}
                  <ArrowRight size={15} />
                </Link>
                {/* The free scan below is the stronger offer (no signup, real result), so this
                    jumps to it instead of competing with it. */}
                <a
                  href="#try"
                  className="btn-hard inline-flex items-center justify-center gap-2 h-12 px-6 text-[0.9375rem] font-medium focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/60 focus-visible:ring-offset-2 focus-visible:ring-offset-bg-deep"
                >
                  Run one now, no account
                </a>
              </div>

              <p className="font-mono text-[0.6875rem] leading-relaxed tracking-wide text-fg-faint max-w-[46ch]">
                {TRIAL_CREDITS_LABEL}, no card. A written read on every account. X and YouTube.
              </p>
            </div>

            {/* Pushed down against the headline on desktop. Deliberately not centred. */}
            <div className="lg:col-span-5 lg:pt-24 min-w-0">
              <ScorecardPreview />
            </div>
          </div>
        </Shell>

        {/* ══ 002 · Method ═══════════════════════════════════════════════════
            Three steps as a numbered sequence on one rule, not three identical
            cards. Cards made the steps look like unordered options. */}
        <Section index="002" title="Paste. Pick. Score.">
          <div className="grid md:grid-cols-3 gap-px bg-border-1 border border-border-1">
            {STEPS.map((s, i) => (
              <Reveal key={s.title} delay={i * 60} from="up">
                <div className="h-full bg-bg-deep p-5 md:p-6">
                  <div className="idx mb-4">{String(i + 1).padStart(2, '0')}</div>
                  <h3 className="display-hard-sm text-lg text-fg mb-2.5">{s.title}</h3>
                  <p className="text-sm text-fg-dim leading-relaxed">{s.body}</p>
                </div>
              </Reveal>
            ))}
          </div>
        </Section>

        {/* ══ 003 · The free scan ════════════════════════════════════════════ */}
        <Section
          index="003"
          title="Run a scan right now."
          lede="The same engine the signed-in workspace runs. One free analysis per visitor, up to 25 accounts, no account needed."
          id="try"
        >
          <Reveal from="up">
            <div className="border border-border-1 bg-bg-elev">
              <div className="px-4 md:px-5 py-3 border-b border-border-1 bg-bg flex items-center justify-between flex-wrap gap-2">
                <span className="font-mono text-[0.625rem] tracking-[0.18em] uppercase text-fg-mute">
                  Free X scan
                </span>
                <span className="font-mono text-[0.625rem] tracking-[0.14em] uppercase text-fg-faint">
                  Compile · select · analyze
                </span>
              </div>
              <div className="p-5 md:p-7">
                <DemoScanForm />
              </div>
            </div>
          </Reveal>
        </Section>

        {/* ══ 004 · The eight signals ════════════════════════════════════════
            Given their own section and numbered. They were previously one
            bullet inside a feature list, which buried the most specific and
            least imitable thing on the page. */}
        <Section
          index="004"
          title="Eight behavioral signals."
          lede="Every account is read on the same eight dimensions. Each returns its own score with the reason behind it, and a dimension with no evidence is left unscored rather than counted as clean."
        >
          <div className="grid sm:grid-cols-2 gap-px bg-border-1 border border-border-1">
            {SIGNALS.map((s, i) => (
              <div key={s.name} className="bg-bg-deep p-4 md:p-5 flex gap-4">
                <span className="idx pt-0.5 shrink-0">{String(i + 1).padStart(2, '0')}</span>
                <div className="min-w-0">
                  <h3 className="text-sm font-semibold text-fg mb-1">{s.name}</h3>
                  <p className="text-sm text-fg-mute leading-relaxed">{s.body}</p>
                </div>
              </div>
            ))}
          </div>
        </Section>

        {/* ══ 005 · What the score rests on ══════════════════════════════════
            Asymmetric on purpose: a narrow claim column against a wider
            evidence column, rather than an even split. */}
        <Section index="005" title="A score you can check.">
          <div className="grid lg:grid-cols-12 gap-x-10 gap-y-8">
            {/* Sticky, so the claim stays beside the list it governs. Without it the narrow column
                holds two lines against six rows and the asymmetry stops reading as composition and
                starts reading as a column somebody forgot to fill. */}
            <div className="lg:col-span-4 lg:sticky lg:top-24 lg:self-start">
              <p className="text-[0.9375rem] text-fg-dim leading-relaxed">
                The results get posted publicly, about named real accounts. So every reading has to
                survive someone checking it.
              </p>
            </div>
            <div className="lg:col-span-8 divide-y divide-divider border-t border-border-1">
              {CAPABILITIES.map((cap) => (
                <div key={cap.title} className="py-4 md:py-5 flex flex-col sm:flex-row sm:gap-6 gap-1.5">
                  <h3 className="text-sm font-semibold text-fg sm:w-52 sm:shrink-0">{cap.title}</h3>
                  <p className="text-sm text-fg-mute leading-relaxed min-w-0">{cap.body}</p>
                </div>
              ))}
            </div>
          </div>
        </Section>

        {/* ══ 006 · Scope and pricing ════════════════════════════════════════ */}
        <Section index="006" title="Scope and price.">
          <div className="grid md:grid-cols-2 gap-px bg-border-1 border border-border-1">
            <div className="bg-bg-deep p-5 md:p-7">
              <div className="font-mono text-[0.625rem] tracking-[0.18em] uppercase text-fg-faint mb-4">
                Sources
              </div>
              <p className="text-sm text-fg-dim leading-relaxed">
                <span className="text-fg font-medium">X (Twitter)</span> and{' '}
                <span className="text-fg font-medium">YouTube</span> today: posts, videos, and the
                accounts that comment on them. <span className="text-fg font-medium">Reddit</span>{' '}
                and <span className="text-fg font-medium">TikTok</span> arrive November 1st. The
                detection engine is already platform-agnostic, so they need an ingestion adapter
                rather than new detection work.
              </p>
            </div>
            <div className="bg-bg-deep p-5 md:p-7">
              <div className="font-mono text-[0.625rem] tracking-[0.18em] uppercase text-fg-faint mb-4">
                Price
              </div>
              <div className="flex items-baseline gap-2 mb-3">
                <span className="stat-value text-3xl text-fg">{SUBSCRIPTION_PRICE}</span>
                <span className="font-mono text-xs text-fg-mute">/ month</span>
              </div>
              <p className="text-sm text-fg-dim leading-relaxed">
                {PLAN_NAME} buys {MONTHLY_CREDITS} credits a month, and one credit covers up to 50
                accounts. You start with {TRIAL_CREDITS_LABEL} and no card. Cancel whenever you
                like.
              </p>
              <Link
                href="/pricing"
                className="inline-flex items-center gap-1.5 mt-4 font-mono text-[0.625rem] tracking-[0.16em] uppercase text-fg-mute hover:text-fg transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/50"
              >
                Full pricing
                <ArrowUpRight size={11} />
              </Link>
            </div>
          </div>
        </Section>

        {/* ══ Close ══════════════════════════════════════════════════════════
            Left-aligned. A centred closing block was one of the strongest
            template tells on the old page. */}
        <Shell className="pt-16 md:pt-24 pb-20 md:pb-28">
          <Reveal from="up">
            <hr className="rule-hard mb-10" />
            <div className="grid lg:grid-cols-12 gap-x-10 gap-y-8 items-end">
              <div className="lg:col-span-7 min-w-0">
                <div className="idx mb-5">007</div>
                <h2
                  className="display-hard text-fg mb-5"
                  style={{ fontSize: 'clamp(2rem, 5vw, 3.5rem)' }}
                >
                  Find out who is real.
                </h2>
                <p className="text-[0.9375rem] text-fg-dim leading-relaxed max-w-[50ch]">
                  Built for creators, brands, journalists, and platform-integrity teams. Start with{' '}
                  {TRIAL_CREDITS_LABEL} and no card.
                </p>
              </div>
              <div className="lg:col-span-5 flex flex-col sm:flex-row lg:justify-end gap-2.5">
                <Link
                  href="/sign-up"
                  className="btn-bone inline-flex items-center justify-center gap-2 h-12 px-6 text-[0.9375rem] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/60 focus-visible:ring-offset-2 focus-visible:ring-offset-bg-deep"
                >
                  Create your free account
                  <ArrowRight size={15} />
                </Link>
              </div>
            </div>
          </Reveal>
        </Shell>
      </main>

      {/* ── Footer ─────────────────────────────────────────────────────────── */}
      <footer className="border-t border-border-1 px-4 md:px-8 py-8">
        <div className="max-w-6xl mx-auto flex flex-col sm:flex-row sm:items-center justify-between gap-5">
          <div className="flex items-center gap-4 min-w-0">
            <Logo size="sm" />
            <span className="font-mono text-[0.625rem] tracking-[0.16em] uppercase text-fg-faint">
              Online media intelligence
            </span>
          </div>
          <div className="flex items-center flex-wrap gap-x-1 gap-y-1 font-mono text-[0.625rem] text-fg-mute tracking-[0.14em] uppercase">
            {[['Terms', '/terms'], ['Privacy', '/privacy'], ['Accuracy', '/accuracy'], ['Pricing', '/pricing'], ['About', '/about']].map(
              ([label, href]) => (
                <Link
                  key={href}
                  href={href}
                  className="px-2.5 py-1.5 hover:text-fg transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/50"
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

/** One gutter, one measure, every section. */
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
    <section id={id} className={`px-4 md:px-8 max-w-6xl mx-auto w-full ${className}`}>
      {children}
    </section>
  );
}

/**
 * Section frame. The numeral sits in its own left rail on desktop, which is what gives the page a
 * single hard vertical axis instead of a stack of centred blocks. On a phone the rail would eat a
 * quarter of the width for a three-character label, so it collapses inline above the heading.
 */
function Section({
  index,
  title,
  lede,
  id,
  children,
}: {
  index: string;
  title: string;
  lede?: string;
  id?: string;
  children: React.ReactNode;
}) {
  return (
    <Shell id={id} className="pt-16 md:pt-24">
      <Reveal className="mb-8">
        <hr className="rule-hard mb-7" />
        <div className="md:grid md:grid-cols-[4.5rem_1fr] md:gap-x-6">
          <div className="idx mb-3 md:mb-0 md:pt-1.5">{index}</div>
          <div className="min-w-0">
            <h2
              className="display-hard-sm text-fg"
              style={{ fontSize: 'clamp(1.5rem, 3vw, 2.125rem)' }}
            >
              {title}
            </h2>
            {lede && (
              <p className="text-sm text-fg-dim leading-relaxed mt-3 max-w-[62ch]">{lede}</p>
            )}
          </div>
        </div>
      </Reveal>
      {/* 6rem, matching the heading column exactly: the rail is 4.5rem and the gap is 1.5rem, so
          anything else leaves the heading and its content on two different left edges. It was
          5.5rem, an 8px disagreement, which is small enough to pass unnoticed and precisely the
          kind of thing that reads as carelessness without a viewer being able to name it. */}
      <div className="md:pl-24">{children}</div>
    </Shell>
  );
}

/**
 * The eight dimensions the model scores, in the canonical order used by `COMPREHENSIVE_SIGNAL_NAMES`
 * on the API side. Named in plain English here: the internal keys (temporal, ai_writing,
 * history_authenticity) are precise but tell a visitor nothing.
 */
const SIGNALS = [
  { name: 'Posting rhythm', body: 'When the account posts, and whether the cadence looks lived-in or scheduled.' },
  { name: 'Content repetition', body: 'Whether the same phrasing and structure recur across posts that should differ.' },
  { name: 'Machine-written prose', body: 'Markers of generated text, weighed against people who simply write formally.' },
  { name: 'Profile coherence', body: 'Whether the bio, name, join date and activity describe one consistent account.' },
  { name: 'Personal voice', body: 'Whether anything specific to a person is present, or only interchangeable copy.' },
  { name: 'Engagement farming', body: 'Reply and follow patterns that chase reach rather than conversation.' },
  { name: 'Account maturity', body: 'Age and history depth, read as context rather than as an accusation on its own.' },
  { name: 'History authenticity', body: 'Whether the account past reads as a real timeline or as recently assembled.' },
];

const CAPABILITIES = [
  {
    title: 'Scored one at a time',
    body:
      'Every account gets its own 0-to-100 reading, judged on its own evidence rather than on a blanket read of the section. A busy section does not drag a real person up with it.',
  },
  {
    title: 'A written verdict',
    body:
      'The Omi analyst works through the evidence and explains, in a few sentences, why an account looks genuine or bought. Claims about what someone wrote carry the quote.',
  },
  {
    title: 'You choose who to scan',
    body:
      'OmiSphere lists the whole comment section for free. Credits go only to the accounts you tick.',
  },
  {
    title: 'Fingerprints carry between scans',
    body:
      'Each scan stores a behavioral fingerprint, so an account you checked in March still matches when it turns up under a different post in July.',
  },
  {
    title: 'The full evidence chain',
    body:
      'Open any score to see what produced it: the comment, the account metadata, the posting cadence.',
  },
  {
    title: 'A low score is a result',
    body:
      'Most of a comment section is real, and the report says so. Every account scanned is listed, not only the ones that were flagged.',
  },
];

const STEPS = [
  {
    title: 'Paste a post',
    body:
      'Drop in an X post or a YouTube video. OmiSphere reads the comment section and lists who commented, free of charge.',
  },
  {
    title: 'Pick the accounts',
    body:
      'Read the comments and tick the accounts worth checking. Credits go only to the ones you select.',
  },
  {
    title: 'Read the scores',
    body:
      'Each account returns a 0-to-100 OMI score, a written verdict, and the signals that produced both.',
  },
];
