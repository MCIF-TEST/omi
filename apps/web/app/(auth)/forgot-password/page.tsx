import Link from 'next/link';
import { KeyRound } from 'lucide-react';
import { Card } from '@/components/ui/card';
import { ForgotPasswordForm } from './forgot-password-form';

export const metadata = { title: 'Reset password — OMISPHERE' };

export default function ForgotPasswordPage() {
  return (
    <Card gradient className="shadow-card-lg relative overflow-hidden">
      <div className="relative">
        <div className="inline-flex items-center gap-2 font-mono text-2xs tracking-[0.18em] text-accent uppercase mb-4">
          <KeyRound size={13} />
          Account recovery
        </div>
        <h1 className="text-2xl font-semibold text-fg tracking-tight mb-2">
          Forgot your password?
        </h1>
        <p className="text-sm text-fg-dim mb-7">
          Enter your email and we&apos;ll send a link to set a new one.
          Remembered it?{' '}
          <Link href="/login" className="text-accent hover:text-accent-2 transition-colors">
            Back to log in
          </Link>
          .
        </p>
        <ForgotPasswordForm />
      </div>
    </Card>
  );
}
