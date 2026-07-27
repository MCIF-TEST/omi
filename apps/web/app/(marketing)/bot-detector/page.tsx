import type { Metadata } from 'next';
import Link from 'next/link';
import { headers } from 'next/headers';
import {
  Gauge, MessagesSquare, ShieldCheck, MousePointerClick, Database, Fingerprint, Radar, ArrowRight,
} from 'lucide-react';
import { Card, CardLabel } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { DemoScanForm } from '@/app/demo-scan-form';
import { TRIAL_CREDITS } from '@/lib/plan';
import { pageMetadata } from '@/lib/seo';

export const metadata: Metadata = pageMetadata({
  title: 'Bot Detector — Free Bot & Fake Engagement Checker',
  description:
    'A bot detector for X (Twitter) and YouTube that shows its evidence instead of a bare verdict. ' +
    'Score any commenter 0-100 across eight behavioral signals — free, no account required.',
  path: '/bot-detector',
});

const SIGNALS = [
  {
    icon: Gauge,
    title: 'Posting cadence',
    body: 'Intervals between an account\'s posts and comments. Machine-regular timing is a tell; a real person\'s activity is noisy.',
  },
  {
    icon: MessagesSquare,
    title: 'Message repetition',
    body: 'Near-duplicate phrasing reused across an account\'s own history, or echoed by other accounts in the same thread.',
  },
  {
    icon: ShieldCheck,
    title: 'Writing tells',
    body: 'Stylistic fingerprints — vocabulary, sentence shape, punctuation habits — that repeat suspiciously across supposedly unrelated accounts.',
  },
  {
    icon: Database,
    title: 'Profile metadata',
    body: 'Account age, follower/following balance, bio completeness, and other static facts an automated or bought account tends to skimp on.',
  },
  {
    icon: MousePointerClick,
    title: 'Personal-voice rate',
    body: 'How much of an account\'s history reads like first-person opinion versus generic, interchangeable filler.',
  },
  {
    icon: Radar,
    title: 'Engagement farming',
    body: 'Patterns consistent with reply-for-reply or like-for-like schemes rather than organic interest in the content.',
  },
  {
    icon: Fingerprint,
    title: 'Fingerprint memory',
    body: 'Every scan stores a behavioral fingerprint. An account flagged under one post still matches when it turns up under another, months later.',
  },
  {
    icon: ShieldCheck,
    title: 'Account history depth',
    body: 'Thin or newly created histories are scored as "not enough data" rather than silently treated as evidence either way.',
  },
];

const FAQ = [
  {
    q: 'What does a bot detector actually detect?',
    a: 'OMISPHERE looks for behavioral patterns consistent with automation, purchased engagement, or coordinated activity — mechanical posting cadence, repeated phrasing, thin account histories, and fingerprints shared with other accounts. It reports a 0-to-100 probability and the specific evidence behind it, not a yes/no label.',
  },
  {
    q: 'Can a bot detector be wrong?',
    a: 'Yes. No behavioral signal is proof by itself, which is why every score ships with its evidence for and against, a confidence band, and — when the account has too little history to judge — an explicit "not enough data" read instead of a guess.',
  },
  {
    q: 'Does a high score mean the account is definitely a bot?',
    a: 'No. A high score means several independent signals point the same way — for example, mechanically regular timing plus a fingerprint shared with other accounts in the same thread. It is a probability to investigate further, not an accusation.',
  },
  {
    q: 'Is this the same as a platform\'s own automated-account labels?',
    a: 'No. X and YouTube apply their own policy-based labels at the platform level. OMISPHERE runs an independent, evidence-based read on the specific accounts you choose to check, which is often the only signal available for accounts a platform hasn\'t (or won\'t) label itself.',
  },
];

export default function BotDetectorPage() {
  const nonce = headers().get('x-nonce') ?? undefined;
  return (
    <article className="space-y-10">
      <script
        type="application/ld+json"
        nonce={nonce}
        dangerouslySetInnerHTML={{
          __html: JSON.stringify({
            '@context': 'https://schema.org',
            '@type': 'FAQPage',
            mainEntity: FAQ.map(({ q, a }) => ({
              '@type': 'Question',
              name: q,
              acceptedAnswer: { '@type': 'Answer', text: a },
            })),
          }),
        }}
      />

      <header>
        <span className="section-label mb-3">Bot detector</span>
        <h1 className="display text-3xl md:text-4xl font-semibold tracking-tight leading-tight mt-3">
          A bot detector that shows its <span className="text-brand">evidence</span>, not a verdict.
        </h1>
        <p className="mt-4 text-fg-dim leading-relaxed">
          Paste a post from X (Twitter) or a video from YouTube. OMISPHERE lists everyone who
          commented, you pick which accounts to check, and each one comes back scored 0-to-100 with
          the behavioral evidence — posting cadence, writing tells, profile metadata, and more —
          that produced the score. Never a bare &ldquo;bot&rdquo; label with nothing behind it.
        </p>
      </header>

      {/* Live tool — the same free X scan the front page runs, so this page IS the checker the
          query is looking for, not just an article about one. */}
      <div className="rounded-2xl border border-border-1 bg-bg-elev surface-lit overflow-hidden">
        <div className="px-4 md:px-5 py-3 border-b border-divider bg-bg/60 flex items-center justify-between flex-wrap gap-2">
          <span className="flex items-center gap-2 font-mono text-2xs tracking-[0.16em] uppercase text-accent-text">
            <Radar size={13} className="text-accent" aria-hidden />
            Free X bot check, no account
          </span>
          <span className="font-mono text-2xs text-fg-faint tracking-wider uppercase">
            Compile · select · analyze
          </span>
        </div>
        <div className="p-5 md:p-7">
          <DemoScanForm />
        </div>
      </div>

      <div>
        <span className="section-label mb-3">Eight behavioral signals</span>
        <p className="text-sm text-fg-dim leading-relaxed mt-2 mb-5">
          Every account gets its own read on its own evidence — never a blanket score for the whole
          comment section.
        </p>
        <div className="grid sm:grid-cols-2 gap-4 stagger">
          {SIGNALS.map(({ icon: Icon, title, body }) => (
            <Card key={title} interactive>
              <div className="flex gap-3">
                <div className="shrink-0 w-9 h-9 rounded-md bg-accent/[0.08] border border-accent/20 flex items-center justify-center text-accent">
                  <Icon size={16} />
                </div>
                <div>
                  <h2 className="text-sm font-semibold text-fg mb-1">{title}</h2>
                  <p className="text-sm text-fg-dim leading-relaxed">{body}</p>
                </div>
              </div>
            </Card>
          ))}
        </div>
      </div>

      <section className="grid gap-4 md:grid-cols-2">
        {FAQ.map(({ q, a }) => (
          <Card key={q} interactive>
            <CardLabel>{q}</CardLabel>
            <p className="text-sm text-fg-dim leading-relaxed">{a}</p>
          </Card>
        ))}
      </section>

      {/* Platform-specific tools + full-account CTA */}
      <Card className="text-center">
        <h2 className="text-base font-semibold text-fg mb-2">Checking one platform in particular?</h2>
        <p className="text-sm text-fg-dim leading-relaxed mb-5">
          <Link href="/twitter-bot-checker" className="text-accent hover:underline">
            X (Twitter) bot checker
          </Link>
          {' '}and{' '}
          <Link href="/youtube-bot-comments" className="text-accent hover:underline">
            YouTube bot comment detection
          </Link>
          {' '}each walk through the signals specific to that platform.
        </p>
        <Link href="/sign-up" className="inline-block">
          <Button size="lg">
            Start free with {TRIAL_CREDITS} credits
            <ArrowRight size={14} />
          </Button>
        </Link>
      </Card>
    </article>
  );
}
