import Link from 'next/link';
import { Logo } from '@/components/shared/logo';

export default function AuthLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-screen flex flex-col bg-bg-deep bg-grid">
      <header className="px-6 py-5">
        <Link href="/" aria-label="OMISPHERE home">
          <Logo />
        </Link>
      </header>
      <main className="flex-1 flex items-center justify-center px-6 py-10">
        <div className="w-full max-w-md">{children}</div>
      </main>
      <footer className="px-6 py-4 text-center font-mono text-2xs tracking-wider text-fg-mute uppercase">
        <Link href="/terms" className="hover:text-fg-dim">Terms</Link>
        <span className="mx-2">·</span>
        <Link href="/privacy" className="hover:text-fg-dim">Privacy</Link>
        <span className="mx-2">·</span>
        <Link href="/pricing" className="hover:text-fg-dim">Pricing</Link>
      </footer>
    </div>
  );
}
