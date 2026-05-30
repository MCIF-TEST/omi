import { NextResponse, type NextRequest } from 'next/server';

/**
 * Gate authenticated routes — /(app)/* group — by checking for the
 * omi_session cookie. We don't decode it here (that would need the
 * session secret); we just check it exists. The FastAPI service is the
 * final authority and will reject invalid sessions.
 *
 * Marketing + auth routes pass through unauthenticated.
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
  // If a logged-in user hits /login or /signup, send them to /dashboard.
  if ((pathname === '/login' || pathname === '/signup') && hasSession) {
    const url = req.nextUrl.clone();
    url.pathname = '/dashboard';
    url.search = '';
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
