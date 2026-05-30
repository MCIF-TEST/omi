import Link from 'next/link';
import { KeyRound } from 'lucide-react';
import { Card } from '@/components/ui/card';
import { ResetPasswordForm } from './reset-password-form';

export const metadata = { title: 'Set a new password — OMISPHERE' };

export default function ResetPasswordPage({
  searchParams,
}: {
  searchParams: { token?: string };
}) {
  const token = (searchParams.token || '').trim();

  return (
    <Card gradient className="shadow-card-lg relative overflow-hidden">
      <div className="absolute -top-12 -right-12 w-40 h-40 rounded-full bg-accent/[0.07] blur-3xl pointer-events-none" aria-hidden />
      <div className="relative">
        <div className="inline-flex items-center gap-2 font-mono text-2xs tracking-[0.18em] text-accent uppercase mb-4">
          <KeyRound size={13} />
          Account recovery
        </div>
        <h1 className="text-2xl font-semibold text-fg tracking-tight mb-2">
          Set a new password
        </h1>
        {token ? (
          <>
            <p className="text-sm text-fg-dim mb-7">
              Choose a new password for your account. It must be at least 8
              characters.
            </p>
            <ResetPasswordForm token={token} />
          </>
        ) : (
          <p className="text-sm text-fg-dim">
            This reset link is missing its token. Request a fresh one from the{' '}
            <Link href="/forgot-password" className="text-accent hover:text-accent-2 transition-colors">
              forgot-password page
            </Link>
            .
          </p>
        )}
      </div>
    </Card>
  );
}
