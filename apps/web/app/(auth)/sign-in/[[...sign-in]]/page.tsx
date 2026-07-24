import Link from 'next/link';
import { SignIn, SignedIn, SignedOut } from '@clerk/nextjs';
import { AuthBridge } from '@/components/shared/auth-bridge';

export const metadata = { title: 'Sign in — OMISPHERE' };

// Clerk-hosted sign-in (Google, Apple, X, email/phone — whatever is enabled in the Clerk dashboard),
// dropped into the app's centered auth shell. Global theming lives in app/layout.tsx; the heading and
// the switch-to-sign-up link are ours so the page reads as part of the product, not a bolted-on widget.
//
// Loop guard: <SignIn> renders ONLY when the visitor is signed OUT. If Clerk reports them signed IN on
// this page, they were bounced here by the app's server guard (Clerk/server disagree about the session)
// — AuthBridge recovers instead of letting <SignIn> silently redirect back into an infinite loop.
export default function SignInPage() {
  return (
    <div className="w-full">
      <div className="mb-7 text-center">
        <h1 className="display text-2xl font-semibold tracking-tight text-fg mb-1.5">Welcome back</h1>
        <p className="text-sm text-fg-mute">Sign in to continue your investigations.</p>
      </div>

      <SignedOut>
        <SignIn signUpUrl="/sign-up" fallbackRedirectUrl="/investigate" />
        <p className="mt-6 text-center font-mono text-2xs tracking-wider text-fg-mute">
          New here?{' '}
          <Link href="/sign-up" className="text-accent-text hover:underline">
            Create a free account
          </Link>
        </p>
      </SignedOut>

      <SignedIn>
        <AuthBridge />
      </SignedIn>
    </div>
  );
}
