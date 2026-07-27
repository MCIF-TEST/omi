import type { Metadata } from 'next';
import Link from 'next/link';
import { headers } from 'next/headers';
import { Radar, Users, Network, MessagesSquare, ArrowRight } from 'lucide-react';
import { Card, CardLabel } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { DemoScanForm } from '@/app/demo-scan-form';
import { TRIAL_CREDITS } from '@/lib/plan';
import { pageMetadata } from '@/lib/seo';

export const metadata: Metadata = pageMetadata({
  title: 'Twitter Bot Checker — Check Any X Account for Bot Activity',
  description:
    'Free Twitter (X) bot checker. Paste any X post, pick the repliers to check, and see each ' +
    'account scored 0-100 for bot and bought-engagement activity — with the evidence, no account needed.',
  path: '/twitter-bot-checker',
});

const X_SIGNALS = [
  {
    icon: Radar,
    title: 'Reply timing',
    body: 'A cluster of replies landing seconds apart across many accounts is far more consistent with a scheduled amplification push than with organic, staggered attention.',
  },
  {
    icon: Network,
    title: 'Co-tag & co-engagement networks',
    body: 'Accounts that consistently reply to, retweet, or hashtag-amplify the same narrow set of posts as each other — a network the platform\'s own labels often miss.',
  },
  {
    icon: MessagesSquare,
    title: 'Style match across accounts',
    body: 'Shared vocabulary, sentence rhythm, or copy-pasted phrasing across supposedly unrelated handles is a discriminative signal, not a coincidence, once it repeats.',
  },
  {
    icon: Users,
    title: 'Follower / following imbalance',
    body: 'A thin, one-sided ratio combined with a sparse or templated bio — the profile shape a bought or freshly spun-up account tends to have.',
  },
];

const FAQ = [
  {
    q: 'How do I check if a Twitter/X account is a bot?',
    a: 'Paste the link to any post that account replied to below. OMISPHERE lists everyone who replied, you tick the account(s) to check, and it returns a 0-to-100 score with the specific evidence — timing, style, network — behind it. No sign-up needed for your first two checks.',
  },
  {
    q: 'Does this work on any X post, or only certain accounts?',
    a: 'Any public X (Twitter) post with replies. The free tier reads up to 25 repliers per post; a signed-in account can check up to 150 in one investigation.',
  },
  {
    q: 'What makes an X account look like a bot versus just very active?',
    a: 'Volume alone is not a signal. What moves the score is mechanically regular timing, phrasing that repeats across the account\'s own history or echoes other accounts, a thin/templated profile, and — most discriminative — a fingerprint or co-engagement pattern shared with other accounts replying to the same posts.',
  },
  {
    q: 'Can I check a whole thread at once instead of one account?',
    a: 'Yes — that\'s the default flow. Paste the post once, OMISPHERE compiles every replier for free, and you select as many of them as you want checked in a single pass.',
  },
];

export default function TwitterBotCheckerPage() {
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
        <span className="section-label mb-3">Twitter / X bot checker</span>
        <h1 className="display text-3xl md:text-4xl font-semibold tracking-tight leading-tight mt-3">
          Check any <span className="text-brand">X account</span> for bot or bought-engagement activity.
        </h1>
        <p className="mt-4 text-fg-dim leading-relaxed">
          Paste a post below. OMISPHERE lists every account that replied, you choose which ones to
          check, and each comes back scored 0-to-100 with the reply-timing, network, and writing
          evidence behind the number — free, no account required for your first two checks.
        </p>
      </header>

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
        <span className="section-label mb-3">What the X checker looks at</span>
        <div className="grid sm:grid-cols-2 gap-4 stagger mt-2">
          {X_SIGNALS.map(({ icon: Icon, title, body }) => (
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

      <Card className="text-center">
        <h2 className="text-base font-semibold text-fg mb-2">Need YouTube, or more than 25 accounts?</h2>
        <p className="text-sm text-fg-dim leading-relaxed mb-5">
          <Link href="/youtube-bot-comments" className="text-accent hover:underline">
            YouTube bot comment detection
          </Link>
          {' '}covers video comment sections. A free account raises the per-scan cap to 150 accounts
          across both platforms.
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
