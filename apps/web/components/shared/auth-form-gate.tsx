'use client';

import { useAuth } from '@clerk/nextjs';
import { usePathname } from 'next/navigation';
import { Loader2 } from 'lucide-react';
import { AuthBridge } from './auth-bridge';

/**
 * Client-side auth gate for the sign-in / sign-up pages.
 *
 * We deliberately do NOT use Clerk's <SignedIn>/<SignedOut> here: those resolve auth state on the
 * SERVER via auth(), which requires clerkMiddleware — and this app runs no Clerk middleware (it can't
 * get the secret into the Edge runtime, see middleware.ts). Rendering them server-side throws
 * "auth() was called but Clerk can't detect usage of clerkMiddleware()", a server-side exception on
 * the whole page. useAuth() reads the browser's Clerk instance instead, so it works with no
 * middleware and never touches server auth — no SSR throw.
 *
 * Behavior mirrors the intended loop guard: show the sign-in/up form only when signed out; when Clerk
 * reports the visitor already signed in on an auth page (they were bounced here), render AuthBridge to
 * recover instead of letting the form silently redirect back into a loop.
 */
export function AuthFormGate({ children }: { children: React.ReactNode }) {
  const { isLoaded, isSignedIn } = useAuth();
  const pathname = usePathname();
  if (!isLoaded) {
    return (
      <div className="flex justify-center py-10" aria-busy>
        <Loader2 size={20} className="animate-spin text-accent" />
      </div>
    );
  }
  // Only engage the loop recovery on the BASE auth path. Clerk runs multi-step flows under sub-routes
  // — /sign-up/continue (collect required fields), /sign-in/sso-callback (OAuth return),
  // /sign-in/factor-two (MFA), email/phone verification — and on those the child <SignIn>/<SignUp>
  // MUST render to finish the flow. Hijacking a sub-route with AuthBridge would strand the user
  // mid-signup. So the recovery only triggers when the visitor is fully signed in AND sitting on the
  // plain /sign-in or /sign-up entry (the only place the redirect loop can form).
  const onBaseAuthPath = pathname === '/sign-in' || pathname === '/sign-up';
  if (isSignedIn && onBaseAuthPath) return <AuthBridge />;
  return <>{children}</>;
}
