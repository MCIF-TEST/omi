import Link from 'next/link';
import { Logo } from '@/components/shared/logo';
import { ScrollProgress } from '@/components/shared/scroll-progress';

export default function MarketingLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-screen flex flex-col bg-bg-deep grain">
      <ScrollProgress />

      {/* `justify-between` with no wrap let the nav crowd straight into the wordmark below ~400px —
          "SPHERE" ran into "PRICING" and "Log in" / "Sign up" split mid-word. `flex-wrap` plus
          `shrink-0` + `whitespace-nowrap` on every nav item lets the row drop to a second line on a
          narrow phone instead of compressing text into itself. */}
      <header className="relative z-10 px-4 sm:px-6 py-4 flex flex-wrap items-center justify-between gap-x-4 gap-y-2 border-b border-border-1/60 backdrop-blur-sm bg-bg-deep/80 sticky top-0">
        <Link href="/" aria-label="OMISPHERE home" className="shrink-0">
          <Logo size="sm" />
        </Link>
        <nav className="flex items-center flex-wrap gap-x-4 gap-y-1.5 font-mono text-2xs tracking-[0.18em] text-fg-mute uppercase">
          <Link href="/pricing" className="whitespace-nowrap hover:text-fg-dim transition-colors">Pricing</Link>
          <Link href="/about"   className="whitespace-nowrap hover:text-fg-dim transition-colors">About</Link>
          <Link href="/login"   className="whitespace-nowrap hover:text-fg-dim transition-colors">Log in</Link>
          <Link
            href="/signup"
            className="whitespace-nowrap shrink-0 text-accent border border-accent/30 bg-accent/[0.07] px-3 py-1.5 rounded-md hover:bg-accent/[0.13] hover:border-accent/50 transition-all"
          >
            Sign up
          </Link>
        </nav>
      </header>

      <main className="aurora relative z-10 flex-1 max-w-3xl mx-auto w-full px-6 py-12">
        {children}
      </main>

      <footer className="relative z-10 border-t border-border-1/50 px-6 py-6 mt-12 text-center">
        <div className="flex items-center justify-center gap-x-4 gap-y-1.5 flex-wrap font-mono text-2xs tracking-wider text-fg-mute uppercase mb-3">
          <Link href="/bot-detector" className="hover:text-fg-dim transition-colors">Bot detector</Link>
          <Link href="/twitter-bot-checker" className="hover:text-fg-dim transition-colors">X bot checker</Link>
          <Link href="/youtube-bot-comments" className="hover:text-fg-dim transition-colors">YouTube bot comments</Link>
        </div>
        <p className="font-mono text-2xs tracking-wider text-fg-faint uppercase">
          OMISPHERE · Probabilistic Authenticity Intelligence
        </p>
      </footer>
    </div>
  );
}
