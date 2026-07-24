/**
 * Server-only HTTP client for the omi FastAPI service.
 *
 * MUST NOT be imported by client components — uses `next/headers` which
 * is server-only. Browser code calls `apiClient` from './api' instead.
 *
 * Split out from `lib/api.ts` so that file stays bundleable for client
 * components without dragging `next/headers` into the browser graph.
 */

// Server-only — imports `next/headers`. Must never be imported from a
// client component; the bundler will throw a build error if you try
// (which is how we caught the original `lib/api.ts` bug).

import { cookies } from 'next/headers';
import { ApiError, _parse } from './api';
import { env } from './env';

export async function apiServer<T>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  // Auth: forward the Clerk session token as a Bearer so FastAPI can verify + resolve the user.
  // FastAPI verifies the JWT against Clerk's public JWKS (RS256) — no Clerk secret needed here.
  //
  // We read the token straight from the `__session` cookie Clerk stores on the app's own domain,
  // and DO NOT call Clerk's server-side auth(). This app intentionally runs no clerkMiddleware (it
  // can't get the secret into the Edge runtime), and auth() throws "clerkMiddleware() was not
  // detected" whenever it runs without that middleware — a server-side exception that would take the
  // page down. The cookie carries the same JWT auth() would return, so reading it directly is both
  // sufficient and immune to the middleware requirement. (`__session`, or a suffixed
  // `__session_<hash>` on a dev instance with suffixed cookies.)
  const jar = cookies();
  let bearer: string | undefined;
  const all = jar.getAll();
  const sessionCookie =
    all.find((c) => c.name === '__session') ??
    all.find((c) => c.name.startsWith('__session_'));
  if (sessionCookie?.value) bearer = `Bearer ${sessionCookie.value}`;

  const cookieHeader = all.map((c) => `${c.name}=${c.value}`).join('; ');

  const res = await fetch(`${env.API_ORIGIN}${path}`, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      ...(bearer ? { authorization: bearer } : {}),
      ...(cookieHeader ? { cookie: cookieHeader } : {}),
      ...init.headers,
    },
    cache: 'no-store',
  });
  return _parse<T>(res);
}

// Re-export ApiError for server callers that want everything from one module.
export { ApiError };
