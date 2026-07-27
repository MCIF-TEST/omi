import type { Metadata } from 'next';
import Link from 'next/link';
import { headers } from 'next/headers';
import { MessagesSquare, Gauge, Users, Fingerprint, ArrowRight, Sparkles } from 'lucide-react';
import { Card, CardLabel } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { TRIAL_CREDITS } from '@/lib/plan';
import { pageMetadata } from '@/lib/seo';

export const metadata: Metadata = pageMetadata({
  title: 'YouTube Bot Comments — Detect Fake & Bought Comments',
  description:
    'Detect bot and bought comments on any YouTube video or channel. Score each commenter 0-100 ' +
    'across posting cadence, repetition, and cross-account fingerprint signals, with evidence attached.',
  path: '/youtube-bot-comments',
});

const YT_SIGNALS = [
  {
    icon: MessagesSquare,
    title: 'Templated praise',
    body: 'Generic, interchangeable comments ("Amazing content!! 🔥") repeated near-verbatim across many accounts under the same video is a classic engagement-farm pattern.',
  },
  {
    icon: Gauge,
    title: 'Posting cadence across videos',
    body: 'An account commenting on a channel\'s uploads at mechanically regular intervals — rather than the clustered, uneven timing a subscriber who actually watches would show.',
  },
  {
    icon: Users,
    title: 'Thin channel history',
    body: 'A commenting account with little to no content of its own and a sparse subscription history — scored as "not enough data" rather than assumed either way.',
  },
  {
    icon: Fingerprint,
    title: 'Cross-account fingerprints',
    body: 'The same behavioral fingerprint showing up under unrelated videos and channels is the strongest signal a comment farm produces, and the one OMISPHERE\'s memory is built to catch.',
  },
];

const FAQ = [
  {
    q: 'How can I tell if YouTube comments are bots or bought?',
    a: 'Look past the comment text alone: mechanically regular posting timing, near-identical phrasing repeated across many accounts, thin or brand-new channel histories, and a fingerprint shared with commenters on unrelated videos are what actually discriminate a comment farm from real engagement. OMISPHERE scores each commenting account 0-to-100 on exactly these signals.',
  },
  {
    q: 'Can I check comments on any YouTube video?',
    a: 'Yes — paste a video or channel link once signed in, and OMISPHERE lists everyone who commented (or a channel\'s recent commenters) so you can select who to score. YouTube and X (Twitter) are priced the same, one credit per 50 accounts.',
  },
  {
    q: 'Does a lot of comments mean an account is a bot?',
    a: 'No. Comment volume by itself is not a signal — the score comes from cadence, repetition, profile depth, and fingerprint matches across accounts, never from how often an account posts alone.',
  },
  {
    q: 'Is there a free way to try this on YouTube?',
    a: 'The no-login free scan currently covers X (Twitter) only, capped at 25 accounts. A free account extends to YouTube with 3 free trial credits and no card required — enough for a full 150-account channel or video scan.',
  },
];

export default function YoutubeBotCommentsPage() {
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
        <span className="section-label mb-3">YouTube bot comments</span>
        <h1 className="display text-3xl md:text-4xl font-semibold tracking-tight leading-tight mt-3">
          Spot <span className="text-brand">bot and bought comments</span> on any YouTube video.
        </h1>
        <p className="mt-4 text-fg-dim leading-relaxed">
          Comment farms rarely look identical to each other, but their behavior repeats: mechanically
          timed posting, near-duplicate phrasing, thin channel histories, and fingerprints shared with
          commenters on completely different videos. OMISPHERE scores each commenting account 0-to-100
          against those signals, with the evidence attached to every score.
        </p>
      </header>

      <div>
        <span className="section-label mb-3">What the YouTube checker looks at</span>
        <div className="grid sm:grid-cols-2 gap-4 stagger mt-2">
          {YT_SIGNALS.map(({ icon: Icon, title, body }) => (
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

      {/* No embedded free tool here: the no-login demo is X-only. Framed honestly rather than
          bolting on a form that would error on a YouTube link. */}
      <Card gradient className="text-center">
        <div className="inline-flex items-center gap-2 font-mono text-2xs tracking-[0.2em] text-accent uppercase border border-accent/20 bg-accent/[0.06] px-4 py-1.5 rounded-full mb-4">
          <Sparkles size={11} />
          {TRIAL_CREDITS} free credits, no card
        </div>
        <h2 className="text-base font-semibold text-fg mb-2">Run your first YouTube scan</h2>
        <p className="text-sm text-fg-dim leading-relaxed mb-5 max-w-lg mx-auto">
          The no-login free scan on this site covers X (Twitter) only. A free account unlocks YouTube
          video and channel scans — up to 150 accounts, priced the same as X.
        </p>
        <Link href="/sign-up" className="inline-block">
          <Button size="lg">
            Start free with {TRIAL_CREDITS} credits
            <ArrowRight size={14} />
          </Button>
        </Link>
      </Card>

      <section className="grid gap-4 md:grid-cols-2">
        {FAQ.map(({ q, a }) => (
          <Card key={q} interactive>
            <CardLabel>{q}</CardLabel>
            <p className="text-sm text-fg-dim leading-relaxed">{a}</p>
          </Card>
        ))}
      </section>

      <Card className="text-center">
        <h2 className="text-base font-semibold text-fg mb-2">Checking an X (Twitter) post instead?</h2>
        <p className="text-sm text-fg-dim leading-relaxed mb-5">
          <Link href="/twitter-bot-checker" className="text-accent hover:underline">
            Try the free X bot checker
          </Link>
          {' '}— no account needed for your first two checks.
        </p>
      </Card>
    </article>
  );
}
