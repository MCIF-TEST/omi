import { NextResponse, type NextRequest } from 'next/server';

/**
 * No Clerk in middleware — on purpose.
 *
 * WHY: clerkMiddleware performs a server-side "handshake" (e.g. dev-browser setup for development
 * pk_test instances) by redirecting to Clerk's Frontend API and then verifying the returned handshake
 * token. That verification needs CLERK_SECRET_KEY inside the Edge runtime — and Next.js does not
 * reliably expose server secrets to Edge middleware (it inlines only NEXT_PUBLIC_* and threads other
 * keys through inconsistently). When the secret isn't there, the handshake can't complete: the browser
 * gets stuck bouncing through the handshake, the sign-in widget renders blank, and Clerk's client JS
 * throws "a client-side exception" from the half-finished handshake state. Wrapping it in try/catch
 * only hid the incomplete handshake and made it worse.
 *
 * INSTEAD: let Clerk's CLIENT handle its own handshake — it talks to the Frontend API directly from the
 * browser and does not need this middleware. Route protection is enforced server-side in
 * app/(app)/layout.tsx (getCurrentUser → redirect), which runs in the Node runtime and verifies the
 * session by forwarding the Clerk __session cookie to FastAPI (which checks it against Clerk's JWKS).
 * So middleware has no auth job left; it just passes everything through and can never break Clerk or
 * 500 the Edge.
 */
export default function middleware(_req: NextRequest) {
  return NextResponse.next();
}

export const config = {
  // Keep the matcher tight so this no-op doesn't run on static assets or the FastAPI /api rewrite.
  matcher: ['/((?!_next/|api/|favicon.ico|.*\\..*).*)'],
};
