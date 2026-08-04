import Link from 'next/link';
import { ArrowRight } from 'lucide-react';
import { Logo } from '@/components/shared/logo';

/**
 * Marketing shell (about, accuracy, pricing, privacy, terms).
 *
 * Header and footer are deliberately the same objects as the front page's, not lookalikes: a
 * visitor moving from / to /accuracy should not be able to tell they crossed a route boundary.
 * That was not true before, when this shell ran a translucent blurred bar, a pill-shaped signup
 * button, an accent-tinted nav and a centred single-line footer.
 *
 * `grain` and `aurora` are gone from the markup rather than left as inert classes. Both are no-ops
 * in globals.css today, and a class that looks like it does something but does not is a trap for
 * whoever reads this next.
 */
export default function MarketingLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="rule-grid min-h-screen flex flex-col bg-bg-deep">
      <header className="sticky top-0 z-30 h-14 shrink-0 border-b border-border-1 bg-bg-deep px-4 md:px-8 flex items-center gap-3 min-w-0">
        <Link
          href="/"
          aria-label="OMISPHERE home"
          className="shrink min-w-0 overflow-hidden focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/50"
        >
          <Logo size="sm" />
        </Link>

        <nav className="flex items-center gap-0.5 sm:gap-1.5 ml-auto shrink-0 font-mono text-[0.625rem] tracking-[0.16em] uppercase">
          {[['Pricing', '/pricing'], ['Accuracy', '/accuracy'], ['About', '/about']].map(
            ([label, href]) => (
              <Link
                key={href}
                href={href}
                className="hidden sm:block text-fg-mute hover:text-fg transition-colors px-2.5 py-2 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/50"
              >
                {label}
              </Link>
            ),
          )}
          <Link
            href="/sign-in"
            className="text-fg-mute hover:text-fg transition-colors px-2.5 py-2 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/50"
          >
            Log in
          </Link>
          <Link
            href="/sign-up"
            className="btn-bone inline-flex items-center gap-1.5 h-8 px-3.5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/60 focus-visible:ring-offset-2 focus-visible:ring-offset-bg-deep"
          >
            Start free
            <ArrowRight size={11} />
          </Link>
        </nav>
      </header>

      {/* Two nested constraints, doing two different jobs.

          The outer one is max-w-6xl, matching the front page's Shell, so the left edge of the
          content lands on the same pixel here as it does on /. A max-w-3xl column centred in the
          viewport put it at 368px against the front page's 176px, and that jump is visible the
          instant anyone clicks between the two.

          The inner one is the reading measure, left-anchored rather than centred: 1152px of prose
          would be unreadable, but the fix is a narrower column, not a re-centred one. */}
      <main className="flex-1 w-full max-w-6xl mx-auto px-4 md:px-8 py-12 md:py-16">
        <div className="max-w-3xl">{children}</div>
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
