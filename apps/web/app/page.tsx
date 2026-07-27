import { LandingPage } from './landing-page';

/**
 * The public front door. No user lookup, no API call.
 *
 * This used to be `force-dynamic` and `await getCurrentUser()`, so every anonymous visitor triggered a
 * blocking internal call to FastAPI (`/v1/auth/me`) that hit the database — to answer nothing more than
 * "are you already signed in?". That put the API and the database in the critical path of the one page
 * traffic is bought for, capped its throughput at theirs, and took the marketing site down with the API.
 *
 * The signed-in redirect moved to `middleware.ts`, which checks for a session cookie at the edge with no
 * network call. Cookie presence is not proof of a valid session and does not need to be: a stale cookie
 * lands on `/investigate`, which does the real server-side verification and bounces to sign-in.
 *
 * NOT fully static, and not because of anything here. The root layout reads `headers()` to get the CSP
 * nonce, which opts the whole tree into per-request rendering. That is a deliberate trade — a nonce CSP
 * is worth more than CDN caching — so this page is still rendered per request, just cheaply, with no
 * downstream dependency. Removing `force-dynamic` here keeps that honest: if the nonce requirement ever
 * goes away, this page becomes static with no further change.
 */
export default function Root() {
  return <LandingPage />;
}
