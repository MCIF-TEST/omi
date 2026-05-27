import Link from 'next/link';
import { Card, CardLabel, CardTitle } from '@/components/ui/card';
import { LoginForm } from './login-form';

export const metadata = { title: 'Log in — OMISPHERE' };

export default function LoginPage({
  searchParams,
}: {
  searchParams: { next?: string };
}) {
  return (
    <Card>
      <CardLabel>Intelligence Access</CardLabel>
      <CardTitle>Log in to OMISPHERE</CardTitle>
      <p className="text-sm text-fg-dim mb-6">
        Probabilistic detection of bots, AI engagement, and coordinated
        influence. New here?{' '}
        <Link href="/signup" className="text-accent hover:text-accent-2">
          Create an account
        </Link>
        .
      </p>
      <LoginForm next={searchParams.next} />
    </Card>
  );
}
