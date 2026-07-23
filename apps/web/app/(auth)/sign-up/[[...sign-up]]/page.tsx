import Link from 'next/link';
import { SignUp } from '@clerk/nextjs';
import { TRIAL_CREDITS } from '@/lib/plan';

export const metadata = { title: 'Create account — OMISPHERE' };

// Clerk-hosted sign-up (Google, Apple, X, email/phone — whatever is enabled in the Clerk dashboard),
// dropped into the app's centered auth shell. Global theming lives in app/layout.tsx; the heading and
// the switch-to-sign-in link are ours so the page reads as part of the product, not a bolted-on widget.
export default function SignUpPage() {
  return (
    <div className="w-full">
      <div className="mb-7 text-center">
        <h1 className="display text-2xl font-semibold tracking-tight text-fg mb-1.5">Create your account</h1>
        <p className="text-sm text-fg-mute">
          {TRIAL_CREDITS} free credits to start. No card required.
        </p>
      </div>

      <SignUp signInUrl="/sign-in" fallbackRedirectUrl="/investigate" />

      <p className="mt-6 text-center font-mono text-2xs tracking-wider text-fg-mute">
        Already have an account?{' '}
        <Link href="/sign-in" className="text-accent-text hover:underline">
          Sign in
        </Link>
      </p>
    </div>
  );
}
