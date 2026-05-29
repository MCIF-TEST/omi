import { Suspense } from 'react';
import Link from 'next/link';
import { Sparkles, Zap, Check } from 'lucide-react';
import { Card } from '@/components/ui/card';
import { SignupForm } from './signup-form';

export const metadata = { title: 'Sign up — OMISPHERE' };

export default function SignupPage() {
  return (
    <Card gradient className="shadow-card-lg relative overflow-hidden">
      <div className="absolute -top-12 -left-12 w-40 h-40 rounded-full bg-violet/[0.06] blur-3xl pointer-events-none" aria-hidden />
      <div className="relative">
        <div className="inline-flex items-center gap-2 font-mono text-2xs tracking-[0.18em] text-accent uppercase mb-4">
          <Sparkles size={13} />
          Intelligence Access
        </div>
        <h1 className="text-2xl font-semibold text-fg tracking-tight mb-5">
          Create your account
        </h1>

        {/* Plan highlight */}
        <div className="mb-6 p-4 rounded-lg border border-accent/25 bg-accent/[0.04]">
          <div className="flex items-baseline justify-between mb-2">
            <span className="text-2xl font-bold tracking-tight">
              <span className="text-brand">$9.99</span>
              <span className="text-xs text-fg-dim font-normal ml-0.5">/mo</span>
            </span>
            <span className="inline-flex items-center gap-1 font-mono text-2xs tracking-[0.16em] text-fg-dim uppercase">
              <Zap size={10} className="text-accent" />
              20 scans / month
            </span>
          </div>
          <ul className="space-y-1.5 text-sm text-fg">
            {['Full account + video + coordination scans', 'Per-account activity drilldown', 'Cancel anytime'].map((f) => (
              <li key={f} className="flex items-center gap-2">
                <Check size={12} className="text-accent shrink-0" strokeWidth={3} />
                {f}
              </li>
            ))}
          </ul>
          <p className="mt-3 font-mono text-2xs tracking-wider text-tier-low flex items-center gap-1.5">
            <Sparkles size={10} />
            3 free trial scans. No card required.
          </p>
        </div>

        <Suspense fallback={<div className="h-48 animate-pulse bg-bg-elev rounded-sm" />}>
          <SignupForm />
        </Suspense>

        <p className="mt-4 text-xs text-fg-mute leading-relaxed">
          By signing up you agree to OMISPHERE&apos;s{' '}
          <Link href="/terms" className="text-fg-dim hover:text-fg transition-colors">Terms</Link>{' '}
          and{' '}
          <Link href="/privacy" className="text-fg-dim hover:text-fg transition-colors">Privacy Policy</Link>.
          All output is probabilistic — never a definitive judgement about an account.
        </p>
        <p className="mt-3 text-sm text-fg-dim">
          Already have an account?{' '}
          <Link href="/login" className="text-accent hover:text-accent-2 transition-colors">
            Log in
          </Link>
          .
        </p>
      </div>
    </Card>
  );
}
