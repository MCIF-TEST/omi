import Link from 'next/link';
import { Logo } from '@/components/shared/logo';

// Private surface (auth screens): never indexable. The root layout now opts the site IN to indexing (it was
// site-wide noindex, left from the private beta), so anything non-public must opt back OUT here.
export const metadata = { robots: { index: false, follow: false } };

export default function AuthLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-screen flex flex-col bg-bg-deep grain">
      <header className="relative z-10 px-6 py-5 border-b border-border-1/40">
        <Link href="/" aria-label="OMISPHERE home">
          <Logo tagline />
        </Link>
      </header>

      <main className="aurora relative z-10 flex-1 flex items-center justify-center px-6 py-10">
        <div className="w-full max-w-md">{children}</div>
      </main>

      <footer className="relative z-10 px-6 py-5 text-center font-mono text-2xs tracking-wider text-fg-faint uppercase">
        <Link href="/terms"   className="hover:text-fg-mute transition-colors">Terms</Link>
        <Link href="/accuracy" className="hover:text-fg-mute transition-colors">Accuracy</Link>
        <span className="mx-2 text-border-hot">·</span>
        <Link href="/privacy" className="hover:text-fg-mute transition-colors">Privacy</Link>
        <span className="mx-2 text-border-hot">·</span>
        <Link href="/pricing" className="hover:text-fg-mute transition-colors">Pricing</Link>
      </footer>
    </div>
  );
}
