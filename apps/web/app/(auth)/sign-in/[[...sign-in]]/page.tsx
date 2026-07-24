import Link from 'next/link';
import { SignIn } from '@clerk/nextjs';
import { AuthFormGate } from '@/components/shared/auth-form-gate';

export const metadata = { title: 'Sign in — OMISPHERE' };

// Clerk-hosted sign-in (Google, Apple, X, email/phone — whatever is enabled in the Clerk dashboard),
// dropped into the app's centered auth shell. Global theming lives in app/layout.tsx; the heading and
// the switch-to-sign-up link are ours so the page reads as part of the product, not a bolted-on widget.
//
// Loop guard runs CLIENT-side (AuthFormGate/useAuth), never via Clerk's <SignedIn>/<SignedOut> — those
// call auth() on the server and would throw here because this app runs no clerkMiddleware. The gate
// shows <SignIn> when signed out, and AuthBridge (recovery) when Clerk reports the visitor already
// signed in on this page (they were bounced here), so the form never loops back into the app.
export default function SignInPage() {
  return (
    <div className="w-full">
      <div className="mb-7 text-center">
        <h1 className="display text-2xl font-semibold tracking-tight text-fg mb-1.5">Welcome back</h1>
        <p className="text-sm text-fg-mute">Sign in to continue your investigations.</p>
      </div>

      <AuthFormGate>
        <SignIn signUpUrl="/sign-up" fallbackRedirectUrl="/investigate" />
        <p className="mt-6 text-center font-mono text-2xs tracking-wider text-fg-mute">
          New here?{' '}
          <Link href="/sign-up" className="text-accent-text hover:underline">
            Create a free account
          </Link>
        </p>
      </AuthFormGate>
    </div>
  );
}
