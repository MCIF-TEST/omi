import Link from 'next/link';
import { Logo } from '@/components/shared/logo';

export default function MarketingLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-screen flex flex-col bg-bg-deep">
      <header className="px-6 py-5 flex items-center justify-between border-b border-border-1">
        <Link href="/" aria-label="OMISPHERE home">
          <Logo />
        </Link>
        <nav className="flex items-center gap-6 font-mono text-2xs tracking-[0.18em] text-fg-mute uppercase">
          <Link href="/pricing" className="hover:text-fg-dim">Pricing</Link>
          <Link href="/about" className="hover:text-fg-dim">About</Link>
          <Link href="/login" className="hover:text-fg-dim">Log in</Link>
          <Link
            href="/signup"
            className="text-accent border border-accent-dim bg-accent/[0.05] px-3 py-1 rounded-sm hover:bg-accent/10"
          >
            Sign up
          </Link>
        </nav>
      </header>
      <main className="flex-1 max-w-3xl mx-auto w-full px-6 py-12">{children}</main>
      <footer className="border-t border-border-1 px-6 py-6 mt-12 text-center font-mono text-2xs tracking-wider text-fg-mute uppercase">
        OMISPHERE · Probabilistic Authenticity Intelligence
      </footer>
    </div>
  );
}
