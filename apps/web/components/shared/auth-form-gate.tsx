'use client';

import { useEffect, useState } from 'react';
import { useAuth } from '@clerk/nextjs';
import { usePathname } from 'next/navigation';
import { Loader2, TriangleAlert } from 'lucide-react';
import { AuthBridge } from './auth-bridge';
import { clerkFrontendApiHost } from '@/lib/clerk-origin';

// How long to wait for Clerk's script before saying something. Generous: a cold cache on a slow
// connection is a few seconds, and a false alarm on a page that was about to work is its own bug.
const LOAD_TIMEOUT_MS = 12_000;

/**
 * Why the form did not load. Three causes with three different remedies, and the previous message
 * offered one sentence covering all of them, which is the same failure as an analyst floor with no
 * reason: the reader is told something went wrong and given nothing to act on.
 *
 * `blocked` and `misconfigured` are OUR faults, and telling someone to check their extensions for
 * either of them sends them to debug a machine that is working. `unreachable` is the only one where
 * that advice is right.
 */
type LoadFailure = 'blocked' | 'misconfigured' | 'unreachable';

/**
 * Client-side auth gate for the sign-in / sign-up pages.
 *
 * We deliberately do NOT use Clerk's <SignedIn>/<SignedOut> here: those resolve auth state on the
 * SERVER via auth(), which requires clerkMiddleware, and this app runs no Clerk middleware (it can't
 * get the secret into the Edge runtime, see middleware.ts). Rendering them server-side throws
 * "auth() was called but Clerk can't detect usage of clerkMiddleware()", a server-side exception on
 * the whole page. useAuth() reads the browser's Clerk instance instead, so it works with no
 * middleware and never touches server auth, no SSR throw.
 *
 * Behavior mirrors the intended loop guard: show the sign-in/up form only when signed out; when Clerk
 * reports the visitor already signed in on an auth page (they were bounced here), render AuthBridge to
 * recover instead of letting the form silently redirect back into a loop.
 */
export function AuthFormGate({ children }: { children: React.ReactNode }) {
  const { isLoaded, isSignedIn } = useAuth();
  const pathname = usePathname();
  const [timedOut, setTimedOut] = useState(false);
  const [policyBlocked, setPolicyBlocked] = useState(false);

  // The instance this BUILD was compiled against. Next inlines NEXT_PUBLIC_* at build time, so an
  // empty value here means the web service built without the key, which no amount of reloading or
  // network debugging on the visitor's side will fix.
  const clerkHost = clerkFrontendApiHost(process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY);

  // `isLoaded` stays false forever if Clerk's script never runs, and the only symptom is this
  // component's spinner. That is exactly what a CSP missing the production Clerk origin produced: a
  // sign-in page that span indefinitely with nothing on it to say why, and no server-side signal at
  // all. A spinner with no terminal state is not a loading state, it is a silent failure.
  useEffect(() => {
    if (isLoaded) return;
    const t = setTimeout(() => setTimedOut(true), LOAD_TIMEOUT_MS);
    return () => clearTimeout(t);
  }, [isLoaded]);

  // A CSP block is the one cause with NO other evidence anywhere: no server log, no failed health
  // check, nothing on the page. Its only trace is a violation in the browser console, which is why
  // it once cost a live hour. The browser will tell us directly if we ask.
  //
  // Registered as early as this component can manage. clerk-js is fetched by ClerkProvider after
  // hydration, so the listener is normally in place first; if a violation does land before it, we
  // fall through to the generic message rather than claiming the wrong cause.
  useEffect(() => {
    if (isLoaded) return;
    const onViolation = (e: SecurityPolicyViolationEvent) => {
      const blocked = String(e.blockedURI || '');
      if (blocked.includes('clerk') || (clerkHost && blocked.includes(clerkHost))) {
        setPolicyBlocked(true);
      }
    };
    document.addEventListener('securitypolicyviolation', onViolation);
    return () => document.removeEventListener('securitypolicyviolation', onViolation);
  }, [isLoaded, clerkHost]);

  if (!isLoaded) {
    if (timedOut) {
      const failure: LoadFailure = policyBlocked ? 'blocked' : !clerkHost ? 'misconfigured' : 'unreachable';
      return (
        <div className="rounded-md border border-warn/35 bg-warn/[0.07] px-4 py-3 flex items-start gap-2.5">
          <TriangleAlert size={15} className="mt-0.5 shrink-0 text-warn" aria-hidden />
          <div className="min-w-0">
            <p className="text-sm text-fg mb-1">The sign-in form could not load.</p>
            <p className="text-xs text-fg-dim leading-relaxed">
              {failure === 'blocked'
                ? 'A browser security policy blocked the sign-in script from loading. That is a fault '
                  + 'in how this site is configured, not something you can fix.'
                : failure === 'misconfigured'
                  ? 'This site was built without its authentication settings, so the sign-in form '
                    + 'cannot start. That is a fault on our side and reloading will not help.'
                  : 'The authentication service did not answer. Its address below may be failing to '
                    + 'resolve, which is usually a DNS or network problem and can be on either side. '
                    + 'Reload the page, and if it keeps happening try another network before '
                    + 'suspecting an extension blocking third-party scripts.'}
              {' Your account and your investigations are unaffected.'}
            </p>
            {/* The host is public (it is in the page's own CSP header and every Clerk request), and
                naming it is the difference between a reader guessing and a reader being able to
                check one thing. Omitted when we never had one, since there is nothing to name. */}
            {clerkHost && failure !== 'misconfigured' && (
              <p className="mt-1.5 font-mono text-2xs text-fg-faint break-all">{clerkHost}</p>
            )}
            {failure !== 'misconfigured' && (
              <button
                type="button"
                onClick={() => window.location.reload()}
                className="btn-slab mt-3 h-8 px-3 rounded-md text-xs font-medium text-fg-dim"
              >
                Reload
              </button>
            )}
          </div>
        </div>
      );
    }
    return (
      <div className="flex justify-center py-10" aria-busy>
        <Loader2 size={20} className="animate-spin text-accent" />
      </div>
    );
  }
  // Only engage the loop recovery on the BASE auth path. Clerk runs multi-step flows under sub-routes
  //. /sign-up/continue (collect required fields), /sign-in/sso-callback (OAuth return),
  // /sign-in/factor-two (MFA), email/phone verification, and on those the child <SignIn>/<SignUp>
  // MUST render to finish the flow. Hijacking a sub-route with AuthBridge would strand the user
  // mid-signup. So the recovery only triggers when the visitor is fully signed in AND sitting on the
  // plain /sign-in or /sign-up entry (the only place the redirect loop can form).
  const onBaseAuthPath = pathname === '/sign-in' || pathname === '/sign-up';
  if (isSignedIn && onBaseAuthPath) return <AuthBridge />;
  return <>{children}</>;
}
