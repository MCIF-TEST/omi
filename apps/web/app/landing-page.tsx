import Link from 'next/link';
import { ArrowRight, ArrowUpRight } from 'lucide-react';
import { Logo } from '@/components/shared/logo';
import { Reveal } from '@/components/shared/reveal';
import { ScorecardPreview } from '@/components/shared/scorecard-preview';
import { ScoreScale } from '@/components/shared/score-scale';
import { DemoScanForm } from './demo-scan-form';
import {
  TRIAL_CREDITS, CREDIT_NOUN, MONTHLY_CREDITS, SUBSCRIPTION_PRICE, PLAN_NAME,
} from '@/lib/plan';

/**
 * Pre-login front page.
 *
 * Third pass, aimed at reading as a forensic instrument rather than a product page:
 *
 *   · The headline states a fact about the reader's own feed instead of a premise about the
 *     market. It no longer explains anything.
 *   · The trial is presented as an access line, in mono, beside the scan cap. Framed as terms of
 *     entry rather than an offer, because an incentive undercuts the claim that the tool is worth
 *     using on its own.
 *   · The score chapter leads with the word judgement and closes with which way the engine errs.
 *     A tool that assigns a number to a named person and will not say where it is biased is
 *     hiding the only thing that makes the number worth anything.
 *   · The signals became a detection table: index, method, engine field, what it reads. A table
 *     is the honest form for eight parallel measurements, and it is denser than eight cards.
 *   · Contrast raised throughout: near-black ground, pure white primary text, the mid-grey steps
 *     pulled up so body copy stops receding.
 *   · Section padding cut by a third and copy cut again. The page is shorter than the previous
 *     pass while carrying more.
 *
 * The palette, edges and display face that started here now live in `:root` and the Tailwind
 * radius scale, so the whole product reads as one instrument. What is still page-local is the
 * chapter grammar (`.chapter`, `.band`, `.rule-chapter`), which the marketing pages reuse.
 *
 * No `overflow-hidden` on the root: it creates a scroll container that breaks the sticky header.
 * Horizontal containment is handled by `overflow-x: clip` on html/body in globals.css.
 */
export function LandingPage() {
  return (
    <div className="omi-landing rule-grid min-h-screen bg-bg-deep flex flex-col">
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
            className="btn-lamp inline-flex items-center gap-1.5 h-8 px-3.5 font-mono text-[0.625rem] tracking-[0.14em] uppercase focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/60 focus-visible:ring-offset-2 focus-visible:ring-offset-bg-deep"
          >
            Start free
            <ArrowRight size={11} />
          </Link>
        </nav>
      </header>

      <main className="flex-1">
        {/* ══ Hero ═══════════════════════════════════════════════════════════ */}
        <Shell className="pt-12 md:pt-20 pb-10 md:pb-16">
          <div className="flex items-center gap-3 mb-7">
            <span className="idx">001</span>
            <span className="h-px w-8 bg-border-hot" aria-hidden />
            <span className="font-mono text-[0.625rem] tracking-[0.18em] uppercase text-fg-mute">
              Private beta
            </span>
          </div>

          {/* Sits outside the two-column grid and runs wider than the paragraph beneath it. Inside
              the copy column this breaks into four ragged lines, and the only fix available there
              is shrinking the type, which works against the one thing a headline has to do.
              52rem holds the first phrase on one line at the clamp ceiling, so the balanced break
              lands between phrases rather than mid-phrase. */}
          <h1
            className="display-hard text-fg mb-9 md:mb-11 max-w-[52rem]"
            style={{ fontSize: 'clamp(2.25rem, 7.4vw, 5.25rem)' }}
          >
            Not everyone in that thread is real.
          </h1>

          <div className="grid lg:grid-cols-12 gap-x-10 gap-y-10">
            <div className="lg:col-span-6 min-w-0">
              <p className="text-base text-fg-dim leading-relaxed max-w-[48ch] mb-8">
                OmiSphere scores every account in a comment section, 0 to 100, with the evidence
                behind each call.
              </p>

              <div className="flex flex-col sm:flex-row sm:items-center gap-2.5 mb-7">
                {/* The free scan leads. A working demonstration is a stronger argument than an
                    incentive, and it asks nothing in return. */}
                <a
                  href="#try"
                  className="btn-lamp inline-flex items-center justify-center gap-2 h-12 px-6 text-[0.9375rem] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/60 focus-visible:ring-offset-2 focus-visible:ring-offset-bg-deep"
                >
                  Run a scan
                  <ArrowRight size={15} />
                </a>
                <Link
                  href="/sign-up"
                  className="btn-hard inline-flex items-center justify-center gap-2 h-12 px-6 text-[0.9375rem] font-medium focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/60 focus-visible:ring-offset-2 focus-visible:ring-offset-bg-deep"
                >
                  Create an account
                </Link>
              </div>

              {/* Terms of entry, not an offer. Set as a two-row access line in mono so the trial
                  reads as the cap on a controlled surface rather than as a marketing hook. */}
              <dl className="border border-border-1 divide-y divide-divider font-mono text-[0.6875rem] tracking-wide max-w-[26rem]">
                <div className="flex items-baseline gap-4 px-3.5 py-2.5">
                  <dt className="text-fg-faint uppercase tracking-[0.14em] w-[5.5rem] shrink-0">
                    Anonymous
                  </dt>
                  <dd className="text-fg-mute min-w-0">One scan, 25 accounts, no account</dd>
                </div>
                <div className="flex items-baseline gap-4 px-3.5 py-2.5">
                  <dt className="text-fg-faint uppercase tracking-[0.14em] w-[5.5rem] shrink-0">
                    Registered
                  </dt>
                  <dd className="text-fg-mute min-w-0">
                    {TRIAL_CREDITS} {CREDIT_NOUN}, no card
                  </dd>
                </div>
              </dl>
            </div>

            {/* Starts at column 8, leaving column 7 empty. The gap is the asymmetry; an even split
                would read as a template again. */}
            <div className="lg:col-span-5 lg:col-start-8 min-w-0">
              <ScorecardPreview />
            </div>
          </div>
        </Shell>

        {/* ══ 002 · The score ════════════════════════════════════════════════ */}
        <Chapter
          n="002"
          band
          title="The score is a judgement."
          lede="Not a reading of the section. Each account, on its own evidence, against a burden of proof that rises with the number."
        >
          <ScoreScale />
        </Chapter>

        {/* ══ 003 · Detection methods ════════════════════════════════════════
            A table, because eight parallel measurements are tabular data and
            pretending otherwise costs both density and credibility. */}
        <Chapter
          n="003"
          title="Eight detection methods."
          lede="Every account is read on all eight. A method that collected no evidence returns null, never zero."
        >
          <div className="border border-border-1">
            <div className="grid grid-cols-[1.75rem_1fr] sm:grid-cols-[1.75rem_13rem_1fr] gap-x-4 sm:gap-x-8 px-4 py-2.5 bg-bg border-b border-border-1 font-mono text-[0.5625rem] tracking-[0.18em] uppercase text-fg-faint">
              <span>#</span>
              <span>Method</span>
              <span className="hidden sm:block">Reads</span>
            </div>

            {SIGNALS.map((s, i) => (
              <div
                key={s.key}
                className="grid grid-cols-[1.75rem_1fr] sm:grid-cols-[1.75rem_13rem_1fr] gap-x-4 sm:gap-x-8 gap-y-1.5 px-4 py-3.5 border-t border-divider first:border-t-0"
              >
                <span className="idx pt-0.5">{String(i + 1).padStart(2, '0')}</span>
                <div className="min-w-0">
                  <div className="text-sm font-semibold text-fg">{s.name}</div>
                  {/* The engine's own field name. It appears in real output, so a sceptical reader
                      can check it, which is worth more than another line of description. */}
                  <div className="font-mono text-[0.625rem] tracking-[0.08em] text-accent-text/75 mt-1">
                    {s.key}
                  </div>
                </div>
                <p className="col-start-2 sm:col-start-3 text-sm text-fg-mute leading-relaxed min-w-0">
                  {s.body}
                </p>
              </div>
            ))}
          </div>
        </Chapter>

        {/* ══ 004 · Method ═══════════════════════════════════════════════════ */}
        <Chapter n="004" band title="Paste. Pick. Score.">
          <div className="grid md:grid-cols-3 gap-px bg-border-1 border border-border-1">
            {STEPS.map((s, i) => (
              <div key={s.title} className="h-full bg-bg p-5">
                <div className="idx mb-3.5">{String(i + 1).padStart(2, '0')}</div>
                <h3 className="display-hard-sm text-lg text-fg mb-2">{s.title}</h3>
                <p className="text-sm text-fg-mute leading-relaxed">{s.body}</p>
              </div>
            ))}
          </div>
        </Chapter>

        {/* ══ 005 · The free scan ════════════════════════════════════════════ */}
        <Chapter n="005" id="try" title="Run one now." lede="Real engine. 25 accounts. No account.">
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
        </Chapter>

        {/* ══ 006 · The discipline ═══════════════════════════════════════════ */}
        <Chapter
          n="006"
          band
          title="What it does. What it refuses."
          lede="A false positive is a real person wrongly accused, and one bad score discredits every number beside it."
        >
          <div className="grid lg:grid-cols-2 gap-px bg-border-1 border border-border-1">
            <div className="bg-bg p-5 md:p-6">
              <div className="font-mono text-[0.625rem] tracking-[0.18em] uppercase text-fg-mute mb-4">
                Does
              </div>
              <ul className="space-y-3">
                {DOES.map((t) => (
                  <li key={t} className="flex gap-3 text-sm text-fg-dim leading-relaxed">
                    <span className="mt-[0.4rem] h-1 w-3 shrink-0 bg-tier-low" aria-hidden />
                    <span className="min-w-0">{t}</span>
                  </li>
                ))}
              </ul>
            </div>
            <div className="bg-bg p-5 md:p-6">
              <div className="font-mono text-[0.625rem] tracking-[0.18em] uppercase text-fg-mute mb-4">
                Refuses
              </div>
              <ul className="space-y-3">
                {REFUSES.map((t) => (
                  <li key={t} className="flex gap-3 text-sm text-fg-dim leading-relaxed">
                    <span className="mt-[0.4rem] h-1 w-3 shrink-0 bg-tier-high" aria-hidden />
                    <span className="min-w-0">{t}</span>
                  </li>
                ))}
              </ul>
            </div>
          </div>
        </Chapter>

        {/* ══ 007 · Scope and price ══════════════════════════════════════════ */}
        <Chapter n="007" title="Scope and price.">
          <div className="grid md:grid-cols-2 gap-px bg-border-1 border border-border-1">
            <div className="bg-bg-deep p-5 md:p-6">
              <div className="font-mono text-[0.625rem] tracking-[0.18em] uppercase text-fg-faint mb-3.5">
                Sources
              </div>
              <p className="text-sm text-fg-dim leading-relaxed">
                <span className="text-fg font-medium">X</span> and{' '}
                <span className="text-fg font-medium">YouTube</span> today.{' '}
                <span className="text-fg font-medium">Reddit</span> and{' '}
                <span className="text-fg font-medium">TikTok</span> November 1st. The engine is
                platform-agnostic, so those need an ingestion adapter, not new detection work.
              </p>
            </div>
            <div className="bg-bg-deep p-5 md:p-6">
              <div className="font-mono text-[0.625rem] tracking-[0.18em] uppercase text-fg-faint mb-3.5">
                Price
              </div>
              <div className="flex items-baseline gap-2 mb-2.5">
                <span className="stat-value text-4xl text-fg">{SUBSCRIPTION_PRICE}</span>
                <span className="font-mono text-xs text-fg-mute">/ month</span>
              </div>
              <p className="text-sm text-fg-dim leading-relaxed">
                {PLAN_NAME}. {MONTHLY_CREDITS} credits a month, one credit per 50 accounts.
              </p>
              <Link
                href="/pricing"
                className="inline-flex items-center gap-1.5 mt-3.5 font-mono text-[0.625rem] tracking-[0.16em] uppercase text-fg-mute hover:text-fg transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/50"
              >
                Full pricing
                <ArrowUpRight size={11} />
              </Link>
            </div>
          </div>
        </Chapter>

        {/* ══ Close ══════════════════════════════════════════════════════════ */}
        <Shell className="pt-16 md:pt-24 pb-16 md:pb-24">
          <hr className="rule-chapter mb-10" />
          <div className="grid lg:grid-cols-12 gap-x-10 gap-y-8 items-end">
            <div className="lg:col-span-8 min-w-0">
              <div className="idx mb-5">008</div>
              <h2
                className="display-hard text-fg mb-5"
                style={{ fontSize: 'clamp(2rem, 5.4vw, 3.75rem)' }}
              >
                Most of it is real. Some of it is not.
              </h2>
              <p className="text-[0.9375rem] text-fg-dim leading-relaxed max-w-[42ch]">
                Go and find out which is which.
              </p>
            </div>
            <div className="lg:col-span-4 flex flex-col sm:flex-row lg:justify-end gap-2.5">
              <a
                href="#try"
                className="btn-lamp inline-flex items-center justify-center gap-2 h-12 px-6 text-[0.9375rem] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/60 focus-visible:ring-offset-2 focus-visible:ring-offset-bg-deep"
              >
                Run a scan
                <ArrowRight size={15} />
              </a>
            </div>
          </div>
        </Shell>
      </main>

      <footer className="border-t border-border-1 px-4 md:px-8 py-7">
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
 * A numbered chapter.
 *
 * `band` puts every other chapter on a raised full-bleed ground, so a boundary is felt before it
 * is read, and the large numeral sits in the left rail in the border colour, reading as structure
 * rather than as a value.
 *
 * The rail is 4.5rem with a 1.5rem gap, so content must offset by exactly 6rem to share the
 * heading's left edge. Anything else leaves the page on two axes.
 */
function Chapter({
  n,
  title,
  lede,
  id,
  band = false,
  children,
}: {
  n: string;
  title: string;
  lede?: string;
  id?: string;
  band?: boolean;
  children: React.ReactNode;
}) {
  return (
    <section id={id} className={band ? 'band' : ''}>
      <div className="px-4 md:px-8 max-w-6xl mx-auto w-full py-12 md:py-16">
        {/* A band already declares itself with its own ground and edges; a rule on top of that is
            two separators doing one job. */}
        {!band && <hr className="rule-chapter mb-8" />}

        <div className="md:grid md:grid-cols-[4.5rem_1fr] md:gap-x-6">
          <div className="chapter text-2xl md:text-[1.75rem] mb-3.5 md:mb-0 md:pt-1">{n}</div>
          <div className="min-w-0">
            <h2
              className="display-hard-sm text-fg"
              style={{ fontSize: 'clamp(1.65rem, 3.4vw, 2.5rem)' }}
            >
              {title}
            </h2>
            {lede && (
              <p className="text-[0.9375rem] text-fg-dim leading-relaxed mt-3 max-w-[56ch]">
                {lede}
              </p>
            )}
          </div>
        </div>

        <div className="md:pl-24 mt-7 md:mt-9">{children}</div>
      </div>
    </section>
  );
}

/**
 * The eight dimensions, in the canonical order of `COMPREHENSIVE_SIGNAL_NAMES` on the API side.
 * `key` is the engine's own field name and appears in real output, which is why it is shown.
 */
const SIGNALS = [
  { key: 'temporal', name: 'Posting rhythm', body: 'Interval distribution across the account history. Machine cadence against a human day.' },
  { key: 'semantic', name: 'Content repetition', body: 'Phrase and structure reuse across posts that should not resemble each other.' },
  { key: 'ai_writing', name: 'Machine-written prose', body: 'Generation markers, discounted for people who simply write formally or in a second language.' },
  { key: 'profile', name: 'Profile coherence', body: 'Whether bio, display name, join date and activity describe one account or several.' },
  { key: 'voice', name: 'Personal voice', body: 'Presence of anything specific to a person, against interchangeable copy.' },
  { key: 'engagement', name: 'Engagement farming', body: 'Reply and follow topology that chases reach rather than conversation.' },
  { key: 'account_maturity', name: 'Account maturity', body: 'Age and history depth, read as context. Never sufficient on its own.' },
  { key: 'history_authenticity', name: 'History authenticity', body: 'Whether the timeline accumulated or was assembled.' },
];

const DOES = [
  'Scores each account on its own evidence. A busy section does not drag a real person up with it.',
  'Quotes what an account wrote. If it cannot be quoted, it is not claimed.',
  'Shows what produced every score: the comment, the metadata, the cadence.',
  'Carries a behavioral fingerprint between scans. An account matches when it turns up again.',
  'Lists every account it scored, not only the ones it flagged.',
  'Charges for the accounts you tick. Compiling the section is free.',
];

const REFUSES = [
  'Name who runs an account.',
  'Say money changed hands.',
  'Call a score proof of anything.',
  'Read fluent or formal writing as machine writing.',
  "Hold a new account's age against it on its own.",
  'Score a method that collected no evidence.',
];

const STEPS = [
  {
    title: 'Paste a post',
    body: 'An X post or a YouTube video. The comment section compiles free.',
  },
  {
    title: 'Pick the accounts',
    body: 'Tick the ones worth checking. Credits go only to those.',
  },
  {
    title: 'Read the scores',
    body: 'A 0-to-100 reading each, a written verdict, and the methods behind both.',
  },
];
