import Link from 'next/link';
import { Logo } from '@/components/shared/logo';

// Private surface (auth screens): never indexable. The root layout opts the site IN to indexing
// (it was site-wide noindex, left from the private beta), so anything non-public opts back OUT here.
export const metadata = { robots: { index: false, follow: false } };

/**
 * Auth shell (sign-in, sign-up, password reset).
 *
 * The form is the only thing on the screen, so the shell's job is to stay out of its way and to
 * look like the same product the visitor just came from. Same header height and hairline as the
 * front page, same mono footer, same near-black ground.
 *
 * The form stays centred here, unlike every other surface: there is one object on the page and no
 * hierarchy to express, so a left axis would be a rule followed for its own sake. It is nudged
 * above the optical centre, because a block placed at true centre reads as sitting low.
 */
export default function AuthLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="rule-grid min-h-screen flex flex-col bg-bg-deep">
      <header className="h-14 shrink-0 border-b border-border-1 px-4 md:px-8 flex items-center">
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
      </header>

      <main className="flex-1 flex items-center justify-center px-4 py-10 md:pb-24">
        <div className="w-full max-w-md">{children}</div>
      </main>

      <footer className="border-t border-border-1 px-4 md:px-8 py-6">
        <div className="flex items-center justify-center flex-wrap gap-x-1 gap-y-1 font-mono text-[0.625rem] text-fg-mute tracking-[0.14em] uppercase">
          {[['Terms', '/terms'], ['Privacy', '/privacy'], ['Accuracy', '/accuracy'], ['Pricing', '/pricing']].map(
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
      </footer>
    </div>
  );
}
