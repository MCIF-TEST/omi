import Link from 'next/link';
import { Logo } from '@/components/shared/logo';

export default function MarketingLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-screen flex flex-col bg-bg-deep grain">
      {/* Subtle aurora */}
      <div className="fixed inset-0 pointer-events-none overflow-hidden" aria-hidden>
        <div className="absolute top-[-20%] left-[20%] w-[500px] h-[500px] rounded-full bg-accent/[0.04] blur-[120px]" />
      </div>
      <div className="fixed inset-0 pointer-events-none dot-bg opacity-[0.18]" aria-hidden />

      <header className="relative z-10 px-6 py-4 flex items-center justify-between border-b border-border-1/60 backdrop-blur-sm bg-bg-deep/80 sticky top-0">
        <Link href="/" aria-label="OMISPHERE home">
          <Logo />
        </Link>
        <nav className="flex items-center gap-5 font-mono text-2xs tracking-[0.18em] text-fg-mute uppercase">
          <Link href="/pricing" className="hover:text-fg-dim transition-colors">Pricing</Link>
          <Link href="/about"   className="hover:text-fg-dim transition-colors">About</Link>
          <Link href="/login"   className="hover:text-fg-dim transition-colors">Log in</Link>
          <Link
            href="/signup"
            className="text-accent border border-accent/30 bg-accent/[0.07] px-3 py-1.5 rounded-sm hover:bg-accent/[0.13] hover:border-accent/50 transition-all"
          >
            Sign up
          </Link>
        </nav>
      </header>

      <main className="relative z-10 flex-1 max-w-3xl mx-auto w-full px-6 py-12">
        {children}
      </main>

      <footer className="relative z-10 border-t border-border-1/50 px-6 py-6 mt-12 text-center font-mono text-2xs tracking-wider text-fg-faint uppercase">
        OMISPHERE · Probabilistic Authenticity Intelligence
      </footer>
    </div>
  );
}
