'use client';

import { useAuth } from '@clerk/nextjs';
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
  if (!isLoaded) {
    return (
      <div className="flex justify-center py-10" aria-busy>
        <Loader2 size={20} className="animate-spin text-accent" />
      </div>
    );
  }
  if (isSignedIn) return <AuthBridge />;
  return <>{children}</>;
}
