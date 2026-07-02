import { NextResponse, type NextRequest } from 'next/server';

/**
 * Gate authenticated routes — /(app)/* group — by checking for the
 * omi_session cookie. We don't decode it here (that would need the
 * session secret); we just check it exists. The FastAPI service is the
 * final authority and will reject invalid sessions.
 *
 * Marketing + auth routes pass through unauthenticated.
 *
 * Deliberately ONE-DIRECTIONAL: cookie existence may only ever gate
 * (redirect toward /login), never assert authentication. Bouncing
 * /login -> /dashboard off mere cookie existence contradicted the app
 * layout's validated check whenever the session was stale (server DB
 * reset, rotated session secret, expired uid) and produced an infinite
 * 307 loop (/login <-> /dashboard, ERR_TOO_MANY_REDIRECTS) that locked
 * users out of the login form entirely. The "already logged in" redirect
 * now lives on the login/signup pages, which validate the session
 * against the API before redirecting.
 */
export function middleware(req: NextRequest) {
  const { pathname } = req.nextUrl;
  const hasSession = req.cookies.has('omi_session');

  const isAppRoute = /^\/(dashboard|investigate|investigations|accounts|graph|narratives|content|channels|monitoring|search|bulk|reports|settings)(\/|$)/.test(pathname);
  if (isAppRoute && !hasSession) {
    const url = req.nextUrl.clone();
    url.pathname = '/login';
    url.searchParams.set('next', pathname);
    return NextResponse.redirect(url);
  }
  return NextResponse.next();
}

export const config = {
  matcher: [
    // Run middleware on everything except next internals, static files,
    // and the API rewrite (which is just a passthrough to FastAPI).
    '/((?!_next/|api/|favicon.ico|.*\\..*).*)',
  ],
};
