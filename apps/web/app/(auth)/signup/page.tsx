import Link from 'next/link';
import { Card, CardLabel, CardTitle } from '@/components/ui/card';
import { SignupForm } from './signup-form';

export const metadata = { title: 'Sign up — OMISPHERE' };

export default function SignupPage() {
  return (
    <Card>
      <CardLabel>Intelligence Access</CardLabel>
      <CardTitle>Create your account</CardTitle>

      <div className="mb-5 p-4 rounded-md border border-accent-dim bg-accent/[0.04]">
        <div className="flex items-baseline justify-between mb-1">
          <span className="text-2xl font-bold text-accent tracking-tight">
            $9.99<span className="text-xs text-fg-dim font-normal ml-0.5">/mo</span>
          </span>
          <span className="font-mono text-2xs tracking-[0.16em] text-fg-dim uppercase">
            20 scans / month
          </span>
        </div>
        <ul className="mt-2 space-y-1 text-sm text-fg">
          <li>· Full account + video + coordination scans</li>
          <li>· Per-account activity drilldown</li>
          <li>· Cancel anytime</li>
        </ul>
        <p className="mt-3 font-mono text-2xs tracking-wider text-accent">
          3 free trial scans. No card required.
        </p>
      </div>

      <SignupForm />

      <p className="mt-4 text-xs text-fg-mute leading-relaxed">
        By signing up you agree to OMISPHERE's{' '}
        <Link href="/terms" className="text-fg-dim hover:text-fg">Terms</Link>{' '}
        and{' '}
        <Link href="/privacy" className="text-fg-dim hover:text-fg">Privacy Policy</Link>.
        All output is probabilistic — never a definitive judgement about an account.
      </p>
      <p className="mt-3 text-sm text-fg-dim">
        Already have an account?{' '}
        <Link href="/login" className="text-accent hover:text-accent-2">
          Log in
        </Link>
        .
      </p>
    </Card>
  );
}
