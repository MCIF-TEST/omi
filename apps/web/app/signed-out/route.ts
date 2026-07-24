import { NextResponse } from 'next/server';

// Clerk sign-out target. Clerk clears its OWN session client-side, but it cannot clear the legacy
// httpOnly `omi_session` cookie (set server-side during the pre-Clerk email/password era). Without
// this, a user who still has that cookie would remain authenticated through the backend's legacy
// fallback AFTER signing out of Clerk. This route deletes the legacy cookie, then sends them home
// fully signed out. It is a no-op for the common case (Clerk-only users have no such cookie).
export const dynamic = 'force-dynamic';

export function GET(request: Request) {
  const res = NextResponse.redirect(new URL('/', request.url));
  res.cookies.set('omi_session', '', { path: '/', maxAge: 0, httpOnly: true, sameSite: 'lax' });
  return res;
}
