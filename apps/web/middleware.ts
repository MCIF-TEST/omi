import { clerkMiddleware } from '@clerk/nextjs/server';
import { NextResponse, type NextRequest } from 'next/server';

/**
 * Clerk middleware — context only, secret NOT required.
 *
 * ROOT-CAUSE NOTE (why this file looks the way it does):
 * Next.js compiles middleware into the Edge runtime. It inlines `NEXT_PUBLIC_*` env vars into that
 * bundle, but it deliberately does NOT inline server secrets — `process.env.CLERK_SECRET_KEY` stays a
 * runtime lookup that the Edge sandbox only satisfies for keys threaded in at BUILD time. So the Clerk
 * SECRET can never be relied on inside middleware, and a `clerkMiddleware` that needs it (e.g. via
 * `auth.protect()`, which forces a secret-backed handshake) throws "Missing secretKey" at runtime and
 * 500s every request — even when the key is correctly set on the host.
 *
 * The fix is architectural, not a band-aid: middleware does NOT enforce protection and does NOT need
 * the secret. Route protection is enforced server-side in `app/(app)/layout.tsx`
 * (getCurrentUser → redirect), which runs in the Node runtime where the secret and the FastAPI
 * verifier are always available. This middleware only populates Clerk's request context (so
 * `auth()`/`getToken()` can work in server components when the session is valid) and refreshes the
 * session cookie when the secret happens to be present. Keys are resolved at request time from
 * runtime env, and any Clerk error degrades to letting the request through — the server layer still
 * verifies every protected page. Result: the site can never be taken down by an Edge secret gap.
 */
const PUBLISHABLE_KEY = process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY;

const clerkHandler = clerkMiddleware(
  // No auth.protect() here — protection lives in the (app) server layout (see note above). We only
  // want Clerk's context populated for the session-read (networkless via JWKS) + optional refresh.
  () => {},
  // Resolve keys per-request from runtime env. secretKey is optional: reading a valid session works
  // networklessly with just the publishable key; the secret only enables the refresh handshake.
  () => ({
    publishableKey: process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY,
    secretKey: process.env.CLERK_SECRET_KEY,
  }),
);

export default async function middleware(req: NextRequest, ev: any) {
  // Clerk not configured → never gate, never call into Clerk.
  if (!PUBLISHABLE_KEY) return NextResponse.next();
  try {
    return await clerkHandler(req, ev);
  } catch {
    // A missing-secret handshake (or any Edge-runtime Clerk error) must not 500 the site. The
    // server layout re-verifies via FastAPI/JWKS on every protected route, so it is safe to proceed.
    return NextResponse.next();
  }
}

export const config = {
  matcher: [
    // Everything except Next internals, static files, and the FastAPI /api rewrite…
    '/((?!_next/|api/|favicon.ico|.*\\..*).*)',
    // …plus Clerk's auto-proxy path.
    '/__clerk/:path*',
  ],
};
