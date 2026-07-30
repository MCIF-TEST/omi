'use client';

import { useEffect } from 'react';

/** Where the pending claim token lives between the sign-up form and /welcome. */
export const CLAIM_STORAGE_KEY = 'omi.pendingClaim';

/**
 * Mirror the funnel's share token into sessionStorage the moment the sign-up page renders.
 *
 * Clerk's `fallbackRedirectUrl` handles the simple case, but a real sign-up can bounce through
 * /sign-up/continue, an email verification step, or an OAuth round trip before it lands, and a query
 * param does not survive all of those reliably. This is the backstop: /welcome reads the URL first
 * and falls back to this, so the report the visitor came from still ends up in their archive.
 *
 * sessionStorage rather than localStorage on purpose: the intent belongs to this tab and this visit,
 * and a stale token surviving in a browser for weeks would silently claim a report during some
 * unrelated future signup. Renders nothing.
 */
export function RememberClaim({ token }: { token: string }) {
  useEffect(() => {
    if (!token) return;
    try {
      sessionStorage.setItem(CLAIM_STORAGE_KEY, token);
    } catch {
      /* private mode or a full quota. The URL carrier still covers the common path. */
    }
  }, [token]);
  return null;
}
