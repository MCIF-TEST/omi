import Link from 'next/link';
import { redirect } from 'next/navigation';
import { ShieldCheck } from 'lucide-react';
import { Card } from '@/components/ui/card';
import { getCurrentUser } from '@/lib/auth';
import { LoginForm } from './login-form';

export const metadata = { title: 'Log in — OMISPHERE' };

export default async function LoginPage({
  searchParams,
}: {
  searchParams: { next?: string };
}) {
  // Already-authenticated users skip the form — but only on a VALIDATED
  // session (the API resolved the cookie to a real user). A stale cookie
  // must land here and see the form, never bounce (see middleware.ts —
  // an existence-only bounce here is what caused the /login <-> /dashboard
  // redirect loop).
  const user = await getCurrentUser();
  if (user) {
    // Only honor same-origin paths from ?next= (no protocol-relative or
    // absolute URLs) so this can never become an open redirect.
    const next = searchParams.next;
    const safeNext = next && next.startsWith('/') && !next.startsWith('//') ? next : '/dashboard';
    redirect(safeNext);
  }

  return (
    <Card gradient className="shadow-card-lg relative overflow-hidden">
      <div className="relative">
        <div className="inline-flex items-center gap-2 font-mono text-2xs tracking-[0.18em] text-accent uppercase mb-4">
          <ShieldCheck size={13} />
          Intelligence Access
        </div>
        <h1 className="display text-2xl font-semibold text-fg tracking-tight mb-2">
          Welcome back
        </h1>
        <p className="text-sm text-fg-dim mb-7">
          Probabilistic detection of bots, AI engagement, and coordinated
          influence. New here?{' '}
          <Link href="/signup" className="text-accent hover:text-accent-2 transition-colors">
            Create an account
          </Link>
          .
        </p>
        <LoginForm next={searchParams.next} />
      </div>
    </Card>
  );
}
