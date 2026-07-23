import { clerkMiddleware, createRouteMatcher } from '@clerk/nextjs/server';

/**
 * Clerk authentication middleware.
 *
 * Protects the authenticated app group — /(app)/* routes — with Clerk: an unauthenticated visitor
 * is redirected to the sign-in page. Marketing + auth routes pass through. The `/api/*` path is the
 * rewrite to the FastAPI service and is deliberately excluded from the matcher — that service does
 * its own auth (it verifies the Clerk session token the browser sends), so Clerk middleware never
 * needs to run on it.
 *
 * Only the PUBLISHABLE key is involved at the edge; the CLERK_SECRET_KEY is read server-side by
 * Clerk and never exposed to the client.
 */
const isAppRoute = createRouteMatcher([
  '/dashboard(.*)', '/investigate(.*)', '/investigations(.*)', '/accounts(.*)', '/graph(.*)',
  '/narratives(.*)', '/content(.*)', '/channels(.*)', '/monitoring(.*)', '/search(.*)',
  '/bulk(.*)', '/reports(.*)', '/settings(.*)',
]);

export default clerkMiddleware(async (auth, req) => {
  if (isAppRoute(req)) {
    await auth.protect();
  }
});

export const config = {
  matcher: [
    // Everything except Next internals, static files, and the FastAPI /api rewrite…
    '/((?!_next/|api/|favicon.ico|.*\\..*).*)',
    // …plus Clerk's auto-proxy path.
    '/__clerk/:path*',
  ],
};
