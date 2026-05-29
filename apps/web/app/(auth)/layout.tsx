import Link from 'next/link';
import { Logo } from '@/components/shared/logo';

export default function AuthLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-screen flex flex-col bg-bg-deep grain">
      {/* Aurora */}
      <div className="fixed inset-0 pointer-events-none overflow-hidden" aria-hidden>
        <div className="absolute top-[-10%] left-[30%] w-[600px] h-[500px] rounded-full bg-accent/[0.055] blur-[130px]" />
      </div>
      <div className="fixed inset-0 pointer-events-none dot-bg opacity-[0.22]" aria-hidden />

      <header className="relative z-10 px-6 py-5">
        <Link href="/" aria-label="OMISPHERE home">
          <Logo />
        </Link>
      </header>

      <main className="relative z-10 flex-1 flex items-center justify-center px-6 py-10">
        <div className="w-full max-w-md">{children}</div>
      </main>

      <footer className="relative z-10 px-6 py-5 text-center font-mono text-2xs tracking-wider text-fg-faint uppercase">
        <Link href="/terms"    className="hover:text-fg-mute transition-colors">Terms</Link>
        <span className="mx-2 text-border-hot">·</span>
        <Link href="/privacy"  className="hover:text-fg-mute transition-colors">Privacy</Link>
        <span className="mx-2 text-border-hot">·</span>
        <Link href="/pricing"  className="hover:text-fg-mute transition-colors">Pricing</Link>
      </footer>
    </div>
  );
}
