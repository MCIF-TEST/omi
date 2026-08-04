import Link from 'next/link';
import { ArrowRight, ArrowUpRight } from 'lucide-react';
import { Logo } from '@/components/shared/logo';
import { Reveal } from '@/components/shared/reveal';
import { ScorecardPreview } from '@/components/shared/scorecard-preview';
import { ScoreScale } from '@/components/shared/score-scale';
import { DemoScanForm } from './demo-scan-form';
import {
  TRIAL_CREDITS_LABEL, MONTHLY_CREDITS, SUBSCRIPTION_PRICE, PLAN_NAME,
} from '@/lib/plan';

/**
 * Pre-login front page.
 *
 * Second pass, aimed at authority rather than at removing template tells. What that changed:
 *
 *   · The headline described the product. It now states the premise the product rests on, and the
 *     description moves to the line under it, where description belongs. A headline that explains
 *     is a headline arguing for its own relevance.
 *   · The 0-to-100 score was mentioned only inside sentences. It now has its own chapter, at size,
 *     with the burden of proof each band demands. Publishing the burden is the strongest claim to
 *     seriousness available, and only a product that imposes one can make it.
 *   · The eight signals were a feature list. They are now the second chapter, carrying their
 *     internal engine keys, because the keys are real and reading like an instrument beats reading
 *     like marketing.
 *   · A chapter of refusals ("what it will not do") sits beside the claims. For a product that
 *     publishes scored judgements about named people, the limits ARE the credibility.
 *   · Sections were continuous and polite. They are now numbered chapters on alternating ground
 *     bands, separated by a 2px rule that starts hard at the left axis.
 *   · Copy cut roughly in half. Hedging and second explanations removed throughout.
 *
 * Palette, edges and display face are scoped under `.omi-landing` in globals.css. Nothing in the
 * signed-in app changes.
 *
 * No `overflow-hidden` on the root: it creates a scroll container that breaks the sticky header.
 * Horizontal containment is handled by `overflow-x: clip` on html/body in globals.css.
 */
export function LandingPage() {
  return (
    <div className="omi-landing omi-landing-grid min-h-screen bg-bg-deep flex flex-col">
      {/* `ScrollProgress` deliberately removed: it painted the suspicion ramp across the top of the
          viewport as a rainbow hairline, spending a data legend on scroll position. Still used by
          the marketing layout, which is untouched. */}

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
        {/* ══ Hero ═══════════════════════════════════════════════════════════ */}
        <Shell className="pt-14 md:pt-24 pb-12 md:pb-20">
          <div className="flex items-center gap-3 mb-8">
            <span className="idx">001</span>
            <span className="h-px w-8 bg-border-hot" aria-hidden />
            <span className="font-mono text-[0.625rem] tracking-[0.18em] uppercase text-fg-mute">
              Private beta
            </span>
          </div>

          {/* States the premise rather than the feature set. The product description moves to the
              line below, which is where a reader looks for it anyway.

              Deliberately OUTSIDE the two-column grid and wider than the paragraph beneath it.
              Constrained to the copy column it broke into four lines with "leaves" stranded alone,
              and the only fix available there was shrinking the type, which works against the one
              thing this headline has to do. Breaking it out buys the width to set it in two lines
              at full size, and a headline running wider than its own body copy is a deliberate
              editorial device rather than an accident of the grid.

              52rem holds "Bought engagement" on one line at the clamp ceiling (measured at 804px),
              so the balanced break lands between the two phrases instead of mid-phrase. */}
          <h1
            className="display-hard text-fg mb-10 md:mb-12 max-w-[52rem]"
            style={{ fontSize: 'clamp(2.25rem, 7.4vw, 5.25rem)' }}
          >
            Bought engagement leaves a pattern.
          </h1>

          <div className="grid lg:grid-cols-12 gap-x-10 gap-y-12">
            <div className="lg:col-span-6 min-w-0">
              <p className="text-base text-fg-dim leading-relaxed max-w-[50ch] mb-9">
                Score every account in a comment section. Paste an X post or a YouTube video, pick
                the accounts, and read what each one is doing.
              </p>

              <div className="flex flex-col sm:flex-row sm:items-center gap-2.5 mb-6">
                {/* The free scan leads. It is the strongest thing on the page: a real result from
                    the real engine, with nothing asked in return. The credit offer is an incentive
                    to sign up, which is a weaker argument than a working demonstration. */}
                <a
                  href="#try"
                  className="btn-bone inline-flex items-center justify-center gap-2 h-12 px-6 text-[0.9375rem] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/60 focus-visible:ring-offset-2 focus-visible:ring-offset-bg-deep"
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

              <p className="font-mono text-[0.6875rem] leading-relaxed tracking-wide text-fg-faint">
                No account for the first scan. Signing up adds {TRIAL_CREDITS_LABEL}, no card.
              </p>
            </div>

            {/* Starts at column 8, leaving column 7 empty. The gap is the asymmetry: an even
                6/6 split would read as a template again. */}
            <div className="lg:col-span-5 lg:col-start-8 min-w-0">
              <ScorecardPreview />
            </div>
          </div>
        </Shell>

        {/* ══ 002 · The scale ════════════════════════════════════════════════ */}
        <Chapter
          n="002"
          band
          title="One number, per account."
          lede="Not a reading of the section. A judgement on each account, where the burden of proof rises with the score."
        >
          <ScoreScale />
        </Chapter>

        {/* ══ 003 · The signals ══════════════════════════════════════════════ */}
        <Chapter
          n="003"
          title="Eight signals."
          lede="Every account is read on all eight. A dimension with no evidence is left unscored, never counted as clean."
        >
          {/* Each item puts the numeral in its own grid column rather than padding the lines below
              it. The numeral's rendered width depends on the mono face and its tracking, so a
              hand-guessed indent is a hairline misalignment waiting to happen. */}
          <div className="grid sm:grid-cols-2 gap-px bg-border-1 border border-border-1">
            {SIGNALS.map((s, i) => (
              <div
                key={s.key}
                className="bg-bg-deep p-4 md:p-5 grid grid-cols-[1.75rem_1fr] items-baseline"
              >
                <span className="idx">{String(i + 1).padStart(2, '0')}</span>
                <div className="min-w-0">
                  <h3 className="text-[0.9375rem] font-semibold text-fg">{s.name}</h3>
                  {/* The engine's own field name. It is real and appears in output, which is worth
                      more to a sceptical reader than another sentence of description. */}
                  <div className="font-mono text-[0.625rem] tracking-[0.1em] text-accent-text/70 mt-1.5 mb-2">
                    {s.key}
                  </div>
                  <p className="text-sm text-fg-mute leading-relaxed">{s.body}</p>
                </div>
              </div>
            ))}
          </div>
        </Chapter>

        {/* ══ 004 · Method ═══════════════════════════════════════════════════ */}
        <Chapter n="004" band title="Paste. Pick. Score.">
          <div className="grid md:grid-cols-3 gap-px bg-border-1 border border-border-1">
            {STEPS.map((s, i) => (
              <div key={s.title} className="h-full bg-bg p-5 md:p-6">
                <div className="idx mb-4">{String(i + 1).padStart(2, '0')}</div>
                <h3 className="display-hard-sm text-lg text-fg mb-2.5">{s.title}</h3>
                <p className="text-sm text-fg-mute leading-relaxed">{s.body}</p>
              </div>
            ))}
          </div>
        </Chapter>

        {/* ══ 005 · The free scan ════════════════════════════════════════════ */}
        <Chapter
          n="005"
          id="try"
          title="Run one now."
          lede="The real engine, up to 25 accounts, no account needed."
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
        </Chapter>

        {/* ══ 006 · The discipline ═══════════════════════════════════════════
            Claims and refusals set against each other. For a product that
            publishes scored judgements about named people, the limits are not
            a caveat, they are the reason to trust the numbers. */}
        <Chapter
          n="006"
          band
          title="What it does. What it refuses."
          lede="A false positive is a real person wrongly accused, and one bad score discredits every other number on the page."
        >
          <div className="grid lg:grid-cols-2 gap-px bg-border-1 border border-border-1">
            <div className="bg-bg p-5 md:p-7">
              <div className="font-mono text-[0.625rem] tracking-[0.18em] uppercase text-fg-mute mb-5">
                Does
              </div>
              <ul className="space-y-3.5">
                {DOES.map((t) => (
                  <li key={t} className="flex gap-3 text-sm text-fg-dim leading-relaxed">
                    <span className="mt-[0.4rem] h-1 w-3 shrink-0 bg-tier-low" aria-hidden />
                    <span className="min-w-0">{t}</span>
                  </li>
                ))}
              </ul>
            </div>
            <div className="bg-bg p-5 md:p-7">
              <div className="font-mono text-[0.625rem] tracking-[0.18em] uppercase text-fg-mute mb-5">
                Refuses
              </div>
              <ul className="space-y-3.5">
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
            <div className="bg-bg-deep p-5 md:p-7">
              <div className="font-mono text-[0.625rem] tracking-[0.18em] uppercase text-fg-faint mb-4">
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
            <div className="bg-bg-deep p-5 md:p-7">
              <div className="font-mono text-[0.625rem] tracking-[0.18em] uppercase text-fg-faint mb-4">
                Price
              </div>
              <div className="flex items-baseline gap-2 mb-3">
                <span className="stat-value text-4xl text-fg">{SUBSCRIPTION_PRICE}</span>
                <span className="font-mono text-xs text-fg-mute">/ month</span>
              </div>
              <p className="text-sm text-fg-dim leading-relaxed">
                {PLAN_NAME}. {MONTHLY_CREDITS} credits a month, one credit per 50 accounts. Cancel
                whenever.
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
        </Chapter>

        {/* ══ Close ══════════════════════════════════════════════════════════ */}
        <Shell className="pt-20 md:pt-28 pb-20 md:pb-28">
          <hr className="rule-chapter mb-12" />
          <div className="grid lg:grid-cols-12 gap-x-10 gap-y-8 items-end">
            <div className="lg:col-span-8 min-w-0">
              <div className="idx mb-6">008</div>
              <h2
                className="display-hard text-fg mb-6"
                style={{ fontSize: 'clamp(2rem, 5.4vw, 3.75rem)' }}
              >
                Most of it is real. Some of it is not.
              </h2>
              <p className="text-[0.9375rem] text-fg-dim leading-relaxed max-w-[48ch]">
                Creators, brands, journalists, platform-integrity teams. First scan is free and
                needs no account.
              </p>
            </div>
            <div className="lg:col-span-4 flex flex-col sm:flex-row lg:justify-end gap-2.5">
              <a
                href="#try"
                className="btn-bone inline-flex items-center justify-center gap-2 h-12 px-6 text-[0.9375rem] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/60 focus-visible:ring-offset-2 focus-visible:ring-offset-bg-deep"
              >
                Run a scan
                <ArrowRight size={15} />
              </a>
            </div>
          </div>
        </Shell>
      </main>

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
 * A numbered chapter.
 *
 * Two devices carry the separation the old page lacked. `band` puts every other chapter on a
 * raised full-bleed ground, so a boundary is felt before it is read, and the large numeral sits in
 * the left rail in the border colour, reading as structure rather than as a value.
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
      <div className="px-4 md:px-8 max-w-6xl mx-auto w-full py-16 md:py-24">
        {/* A band already declares itself with its own ground and edges; a rule on top of that is
            two separators doing one job. */}
        {!band && <hr className="rule-chapter mb-10" />}

        <div className="md:grid md:grid-cols-[4.5rem_1fr] md:gap-x-6">
          <div className="chapter text-2xl md:text-[1.75rem] mb-4 md:mb-0 md:pt-1">{n}</div>
          <div className="min-w-0">
            <h2
              className="display-hard-sm text-fg"
              style={{ fontSize: 'clamp(1.65rem, 3.4vw, 2.5rem)' }}
            >
              {title}
            </h2>
            {lede && (
              <p className="text-[0.9375rem] text-fg-dim leading-relaxed mt-4 max-w-[58ch]">
                {lede}
              </p>
            )}
          </div>
        </div>

        <div className="md:pl-24 mt-9 md:mt-11">{children}</div>
      </div>
    </section>
  );
}

/**
 * The eight dimensions, in the canonical order of `COMPREHENSIVE_SIGNAL_NAMES` on the API side.
 * The `key` is the engine's own field name and appears in real output, which is why it is shown:
 * a reader who checks will find it, and that is worth more than another line of description.
 */
const SIGNALS = [
  { key: 'temporal', name: 'Posting rhythm', body: 'When it posts. Whether the cadence is lived-in or scheduled.' },
  { key: 'semantic', name: 'Content repetition', body: 'The same phrasing recurring across posts that should differ.' },
  { key: 'ai_writing', name: 'Machine-written prose', body: 'Markers of generated text, weighed against people who simply write well.' },
  { key: 'profile', name: 'Profile coherence', body: 'Whether the bio, name, join date and activity describe one account.' },
  { key: 'voice', name: 'Personal voice', body: 'Anything specific to a person, or only interchangeable copy.' },
  { key: 'engagement', name: 'Engagement farming', body: 'Reply and follow patterns that chase reach, not conversation.' },
  { key: 'account_maturity', name: 'Account maturity', body: 'Age and history depth, read as context. Never as the case.' },
  { key: 'history_authenticity', name: 'History authenticity', body: 'A real timeline, or one recently assembled.' },
];

const DOES = [
  'Scores each account on its own evidence, so a busy section does not drag a real person up with it.',
  'Quotes what an account wrote. If it cannot be quoted, it is not claimed.',
  'Shows the evidence behind every score: the comment, the metadata, the cadence.',
  'Carries a behavioral fingerprint between scans, so an account matches when it turns up again.',
  'Lists every account it scored, not only the ones it flagged.',
  'Charges only for the accounts you tick. Compiling the section is free.',
];

const REFUSES = [
  'Name who runs an account.',
  'Say money changed hands.',
  'Call a score proof of anything.',
  'Read fluent or formal writing as machine writing.',
  "Hold a new account's age against it on its own.",
  'Score a dimension it collected no evidence for.',
];

const STEPS = [
  {
    title: 'Paste a post',
    body: 'An X post or a YouTube video. The comment section is compiled free of charge.',
  },
  {
    title: 'Pick the accounts',
    body: 'Tick the ones worth checking. Credits go only to those.',
  },
  {
    title: 'Read the scores',
    body: 'A 0-to-100 reading each, a written verdict, and the signals behind both.',
  },
];
