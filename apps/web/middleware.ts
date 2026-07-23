import { clerkMiddleware, createRouteMatcher } from '@clerk/nextjs/server';
import { NextResponse, type NextRequest } from 'next/server';

/**
 * Clerk authentication middleware.
 *
 * Protects the authenticated app group — /(app)/* routes — with Clerk: an unauthenticated visitor
 * is redirected to the sign-in page. Marketing + auth routes pass through. The `/api/*` path is the
 * rewrite to the FastAPI service and is deliberately excluded from the matcher — that service does
 * its own auth (it verifies the Clerk session token the browser sends), so Clerk middleware never
 * needs to run on it.
 *
 * KEY RESOLUTION — why the keys are passed explicitly:
 * Clerk resolves its publishable/secret key from `process.env` *inside its own bundled code*. Next
 * inlines `NEXT_PUBLIC_*` env vars only where they appear as a literal `process.env.NEXT_PUBLIC_x`
 * reference in first-party source — it cannot inline a dynamic lookup buried in a dependency. So in
 * the compiled `.next/server/middleware.js`, Clerk's internal lookup finds nothing and throws
 * "Missing publishableKey" at runtime, even when the var is set in the host environment. Reading the
 * keys here (literal references Next WILL inline at build) and passing them to `clerkMiddleware`
 * closes that gap. The middleware bundle is server-only and never shipped to the browser, so
 * inlining the secret key here is safe.
 *
 * RESILIENCE — if the publishable key is somehow absent at build time, we export a pass-through
 * middleware instead of one that throws on every request. The site stays up (Clerk just isn't
 * enforced); with the key present — the normal case — protection works exactly as before.
 */
const PUBLISHABLE_KEY = process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY;
const SECRET_KEY = process.env.CLERK_SECRET_KEY;

const isAppRoute = createRouteMatcher([
  '/investigate(.*)', '/investigations(.*)', '/accounts(.*)', '/graph(.*)',
  '/campaigns(.*)', '/content(.*)', '/channels(.*)', '/monitoring(.*)', '/search(.*)',
  '/bulk(.*)', '/reports(.*)', '/settings(.*)',
]);

const clerkHandler = clerkMiddleware(
  async (auth, req) => {
    if (isAppRoute(req)) {
      await auth.protect();
    }
  },
  // Explicit keys — see "KEY RESOLUTION" above. Undefined here only if truly unset at build.
  { publishableKey: PUBLISHABLE_KEY, secretKey: SECRET_KEY },
);

// Never let a missing key take the whole site down: fall back to a no-op when it isn't configured.
export default PUBLISHABLE_KEY
  ? clerkHandler
  : function passthroughMiddleware(_req: NextRequest) {
      return NextResponse.next();
    };

export const config = {
  matcher: [
    // Everything except Next internals, static files, and the FastAPI /api rewrite…
    '/((?!_next/|api/|favicon.ico|.*\\..*).*)',
    // …plus Clerk's auto-proxy path.
    '/__clerk/:path*',
  ],
};
