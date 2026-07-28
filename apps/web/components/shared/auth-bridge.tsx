'use client';

import { useEffect, useState } from 'react';
import { useAuth, useClerk } from '@clerk/nextjs';
import { Loader2, TriangleAlert } from 'lucide-react';

// The loop-breaker. It renders on an auth page (sign-in / sign-up) ONLY when Clerk reports the visitor
// is already signed in, which means they were bounced here by the app's server-side guard, i.e. Clerk
// and the server disagree about the session (a token that hasn't propagated to the server cookie yet, a
// flaky network mid-handshake, or a dev-instance quirk). Left alone, Clerk's <SignIn> would silently
// redirect back to the app, the app would bounce back here, and the browser would throttle into a blank
// screen. This component makes that impossible: it attempts recovery EXACTLY ONCE automatically, then
// hands the user explicit controls instead of looping.
const FLAG = 'omi.authbridge.attempt';

export function AuthBridge() {
  const { signOut } = useClerk();
  const { getToken, isLoaded } = useAuth();
  const [stuck, setStuck] = useState(false);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!isLoaded) return; // wait for Clerk before deciding anything
    // If we've already tried once this cycle and landed back here, stop auto-retrying. Show controls.
    const prior = typeof sessionStorage !== 'undefined' ? sessionStorage.getItem(FLAG) : null;
    if (prior) {
      setStuck(true);
      return;
    }
    try {
      sessionStorage.setItem(FLAG, String(Date.now()));
    } catch {
      /* ignore */
    }
    // One automatic attempt: make sure Clerk has actually minted a session token (this also lets its
    // __session cookie settle after a flaky handshake), THEN do a FULL navigation to the app so the
    // server re-reads cookies with that session. A client-side route change would not re-run the server
    // guard with fresh cookies. If the server can now resolve the user, they land in the app for good.
    let cancelled = false;
    (async () => {
      try {
        await getToken();
      } catch {
        /* proceed anyway, the reload + server guard is the source of truth */
      }
      if (!cancelled) window.location.assign('/investigate');
    })();
    return () => {
      cancelled = true;
    };
  }, [isLoaded, getToken]);

  const retry = () => {
    setBusy(true);
    try {
      sessionStorage.removeItem(FLAG);
    } catch {
      /* ignore */
    }
    window.location.assign('/investigate');
  };

  const reset = async () => {
    setBusy(true);
    try {
      sessionStorage.removeItem(FLAG);
    } catch {
      /* ignore */
    }
    try {
      await signOut({ redirectUrl: '/sign-in' });
    } catch {
      window.location.assign('/sign-in');
    }
  };

  if (!stuck) {
    // The one-shot auto attempt is in flight. Show a calm "finishing" state, never a bounce.
    return (
      <div className="flex flex-col items-center gap-3 py-8 text-center">
        <Loader2 size={20} className="animate-spin text-accent" />
        <p className="text-sm text-fg-dim">Finishing sign-in…</p>
      </div>
    );
  }

  return (
    <div className="flex flex-col items-center gap-4 py-6 text-center">
      <TriangleAlert size={22} className="text-tier-moderate" />
      <div className="space-y-1.5">
        <h2 className="display text-lg font-semibold text-fg">Almost there</h2>
        <p className="text-sm text-fg-mute max-w-xs">
          You&apos;re signed in, but we couldn&apos;t open your workspace, often a brief network hiccup.
          Try again, or sign out and back in.
        </p>
      </div>
      <div className="flex items-center gap-3">
        <button
          onClick={retry}
          disabled={busy}
          className="inline-flex items-center gap-2 btn-lamp font-semibold px-5 py-2 rounded-lg text-sm disabled:opacity-60"
        >
          {busy ? <Loader2 size={14} className="animate-spin" /> : null}
          Try again
        </button>
        <button
          onClick={reset}
          disabled={busy}
          className="font-mono text-2xs tracking-wider uppercase text-fg-mute hover:text-fg-dim transition-colors disabled:opacity-60"
        >
          Sign out
        </button>
      </div>
    </div>
  );
}

// Cleared once the user is actually inside the app (the server verified them), so a later, unrelated
// bounce starts with a fresh single auto-attempt rather than jumping straight to the manual controls.
export function AuthBridgeReset() {
  useEffect(() => {
    try {
      sessionStorage.removeItem(FLAG);
    } catch {
      /* ignore */
    }
  }, []);
  return null;
}
