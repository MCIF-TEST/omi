import { PageMasthead, PageSection } from '@/components/shared/page-masthead';

export const metadata = { title: 'About' };

/**
 * Rebuilt to the front page's grammar, and corrected.
 *
 * Two claims on this page had gone stale and were contradicting the rest of the site:
 *
 *   · "Today OMISPHERE scans YouTube only" with "X / Twitter ingestion is the next platform on the
 *     roadmap", directly under a roadmap block on the same page marking X as live.
 *   · "no LLM calls in the per-scan path. Pure Python heuristics" was true when the engine scored
 *     every dimension itself. The eight per-signal readings and the written verdict now come from
 *     the analyst model, with the deterministic engine still producing the OMI score underneath.
 *
 * The honest version is also the stronger one, so it is stated plainly below: a deterministic
 * engine computes the number, a model explains it, and the model's prose is checked back against
 * the evidence rather than trusted.
 */

const SECTIONS = [
  {
    title: 'What this is not',
    body: (
      <>
        Not a binary bot classifier. Every result is a probability with an evidence chain attached.
        The product never asserts that an account is a bot, that anyone was paid, or that a rule was
        broken. It reports which observable patterns an account&apos;s public behaviour resembles,
        and shows the patterns.
      </>
    ),
  },
  {
    title: 'How a score is made',
    body: (
      <>
        A deterministic engine computes the 0-to-100 OMI score from public behaviour: posting
        intervals, text reuse, follower and following ratios, history depth. The analyst model then
        reads the same evidence, scores the eight detection methods, and writes the verdict. The two
        are separate on purpose, so the number does not depend on a model&apos;s mood.
      </>
    ),
  },
  {
    title: 'The prose is checked, not trusted',
    body: (
      <>
        Every quotation the analyst attributes to an account is matched against what that account
        actually posted, and every figure it states is recomputed from the account&apos;s real
        metadata. A verdict that fails those checks is withheld rather than published. Asking a
        model to be careful is not a control.
      </>
    ),
  },
  {
    title: 'Fingerprints accumulate',
    body: (
      <>
        Every scan stores a behavioral fingerprint, so an account checked in March still matches
        when it appears under a different post in July. The set sharpens with use.
      </>
    ),
  },
  {
    title: 'Who it is for',
    body: (
      <>
        Researchers, journalists, brand-safety teams, and platform-integrity professionals. It is
        not a tool for harassing individuals. Probabilistic patterns are not proof, and the product
        says so on every report it produces.
      </>
    ),
  },
];

const ROADMAP = [
  { platform: 'X', state: 'live', detail: 'Per-account scoring, fingerprinting, posting-history analysis' },
  { platform: 'YouTube', state: 'live', detail: 'Full comment analysis, per-account scoring, channel intelligence' },
  { platform: 'Reddit', state: 'next', detail: 'Thread and comment analysis, karma and account age' },
];

export default function AboutPage() {
  return (
    <article>
      <PageMasthead
        index="001"
        eyebrow="About"
        title="Purpose-built detection. Not a wrapper around a chatbot."
        lede="OmiSphere scores the accounts in a comment section on how closely each one resembles bought, farmed or automated behaviour. Every finding carries its confidence, the evidence for it, the evidence against it, and a plain English reason."
      />

      <div className="border border-border-1 divide-y divide-divider">
        {SECTIONS.map(({ title, body }, i) => (
          <div
            key={title}
            className="grid grid-cols-[1.75rem_1fr] sm:grid-cols-[1.75rem_13rem_1fr] gap-x-4 sm:gap-x-8 gap-y-1.5 px-4 py-4"
          >
            <span className="idx pt-0.5">{String(i + 1).padStart(2, '0')}</span>
            <h2 className="text-sm font-semibold text-fg">{title}</h2>
            <div className="col-start-2 sm:col-start-3 text-sm text-fg-mute leading-relaxed min-w-0">
              {body}
            </div>
          </div>
        ))}
      </div>

      <PageSection label="Platform roadmap">
        <dl className="border border-border-1 divide-y divide-divider">
          {ROADMAP.map(({ platform, state, detail }) => (
            <div
              key={platform}
              className="grid grid-cols-[1fr_auto] sm:grid-cols-[7rem_1fr_auto] gap-x-4 gap-y-1 px-4 py-3.5 items-baseline"
            >
              <dt className="text-sm font-semibold text-fg">{platform}</dt>
              <dd className="col-span-2 sm:col-span-1 sm:col-start-2 text-sm text-fg-mute leading-relaxed min-w-0 order-last sm:order-none">
                {detail}
              </dd>
              <span
                className="font-mono text-[0.625rem] tracking-[0.14em] uppercase tabular"
                style={{ color: state === 'live' ? 'var(--tier-low)' : 'var(--text-faint)' }}
              >
                {state}
              </span>
            </div>
          ))}
        </dl>
      </PageSection>
    </article>
  );
}
