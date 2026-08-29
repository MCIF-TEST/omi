import Link from 'next/link';
import { SignUp } from '@clerk/nextjs';
import { TRIAL_CREDITS_LABEL } from '@/lib/plan';
import { AuthFormGate } from '@/components/shared/auth-form-gate';
import { RememberClaim } from './remember-claim';

export const metadata = { title: 'Create account' };

// Clerk-hosted sign-up (Google, Apple, X, email/phone. Whatever is enabled in the Clerk dashboard),
// dropped into the app's centered auth shell. Loop guard runs CLIENT-side via AuthFormGate (useAuth),
// never Clerk's <SignedIn>/<SignedOut>, those call auth() server-side and would throw here because
// this app runs no clerkMiddleware.
export default function SignUpPage({
  searchParams,
}: {
  searchParams: { claim?: string };
}) {
  // Funnel: the visitor came from someone's shared report, and that report should follow them in.
  //
  // Two carriers on purpose. `fallbackRedirectUrl` is the happy path, but Clerk runs multi-step
  // sign-ups across its own sub-routes (/sign-up/continue, email verification, an OAuth round trip)
  // and a query param does not reliably survive all of them. RememberClaim mirrors the token into
  // sessionStorage so /welcome can recover it either way. Losing it drops a converting visitor on an
  // empty dashboard with no idea which post they came from, which is the whole failure this avoids.
  const claim = typeof searchParams.claim === 'string' ? searchParams.claim : '';
  const afterSignUp = claim ? `/welcome?claim=${encodeURIComponent(claim)}` : '/investigate';

  return (
    <div className="w-full">
      {claim && <RememberClaim token={claim} />}
      <div className="mb-7 text-center">
        <h1 className="display-hard-sm text-2xl text-fg mb-1.5">
          {claim ? 'Create your account to scan this post' : 'Create your account'}
        </h1>
        <p className="text-sm text-fg-mute">
          {claim
            ? `The report you were reading gets saved to your account. ${TRIAL_CREDITS_LABEL} to start, no card.`
            : `${TRIAL_CREDITS_LABEL} to start. No card required.`}
        </p>
      </div>

      <AuthFormGate>
        <SignUp signInUrl="/sign-in" fallbackRedirectUrl={afterSignUp} />
        <p className="mt-6 text-center font-mono text-2xs tracking-wider text-fg-mute">
          Already have an account?{' '}
          <Link
            href={claim ? `/sign-in?claim=${encodeURIComponent(claim)}` : '/sign-in'}
            className="text-accent-text hover:underline"
          >
            Sign in
          </Link>
        </p>
      </AuthFormGate>
    </div>
  );
}
