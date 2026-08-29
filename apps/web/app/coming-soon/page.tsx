import Link from 'next/link';
import { WaitlistForm } from '@/components/shared/waitlist-form';
import { LAUNCH_DATE_LABEL } from '@/lib/launch';

export const metadata = {
  title: 'Coming soon',
  description: 'Social media intelligence. Welcome to the transparency layer of the internet.',
};

/**
 * Where everybody lands until launch.
 *
 * Built from the product's own grammar rather than a marketing template: the same near-black ground,
 * the mono eyebrow with its blue tick, Archivo at display scale, hard edges, no gradient and no
 * glow. Somebody arriving from a campaign should recognise this page when they come back to the
 * real product, which is the entire job of a coming-soon page beyond collecting the address.
 *
 * NOTHING HERE IS ESTIMATED OR INFLATED. No counter of people already waiting, no countdown, no
 * "spots remaining". This is a product whose central claim is that it can tell you when engagement
 * is manufactured; inventing a number on its own front door would be the cheapest possible way to
 * undercut that, and it only takes one screenshot.
 */
export default function ComingSoonPage() {
  return (
    <main className="min-h-[100dvh] flex flex-col justify-center px-5 py-16">
      <div className="w-full max-w-2xl mx-auto">
        <div className="flex items-center gap-2.5 mb-7">
          <span className="w-2 h-2 bg-accent shrink-0" aria-hidden />
          <span className="font-mono text-[0.625rem] tracking-[0.18em] uppercase text-fg-faint">
            OmiSphere
          </span>
          <span className="h-px flex-1 bg-border-1" aria-hidden />
          <span className="font-mono text-[0.625rem] tracking-[0.18em] uppercase text-fg-faint tabular-nums">
            {LAUNCH_DATE_LABEL}
          </span>
        </div>

        <h1 className="display-hard text-[clamp(2.5rem,9vw,4.5rem)] leading-[0.95] tracking-[-0.02em] text-fg mb-5">
          Coming soon
        </h1>

        <p className="font-mono text-xs tracking-[0.16em] uppercase text-accent-text mb-5">
          Social media intelligence
        </p>

        <p className="text-lg text-fg-dim leading-relaxed max-w-[46ch] mb-10">
          Welcome to the transparency layer of the internet.
        </p>

        <div className="border-t border-border-hot pt-7">
          <p className="text-sm text-fg-mute leading-relaxed max-w-[52ch] mb-4">
            OmiSphere opens on {LAUNCH_DATE_LABEL}. Leave your email and we will send you one
            message the moment it does. That is the only email the waitlist sends.
          </p>
          <WaitlistForm source="coming_soon" />
        </div>

        <p className="mt-12 font-mono text-2xs tracking-wider uppercase text-fg-faint">
          <Link href="/accuracy" className="hover:text-fg-mute transition-colors">
            What the scores mean
          </Link>
          <span className="mx-2.5 text-border-1" aria-hidden>
            /
          </span>
          <Link href="/privacy" className="hover:text-fg-mute transition-colors">
            Privacy
          </Link>
        </p>
      </div>
    </main>
  );
}
