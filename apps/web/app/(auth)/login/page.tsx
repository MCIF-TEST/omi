import Link from 'next/link';
import { ShieldCheck } from 'lucide-react';
import { Card } from '@/components/ui/card';
import { LoginForm } from './login-form';

export const metadata = { title: 'Log in — OMISPHERE' };

export default function LoginPage({
  searchParams,
}: {
  searchParams: { next?: string };
}) {
  return (
    <Card gradient className="shadow-card-lg relative overflow-hidden">
      <div className="relative">
        <div className="inline-flex items-center gap-2 font-mono text-2xs tracking-[0.18em] text-accent uppercase mb-4">
          <ShieldCheck size={13} />
          Intelligence Access
        </div>
        <h1 className="text-2xl font-semibold text-fg tracking-tight mb-2">
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
