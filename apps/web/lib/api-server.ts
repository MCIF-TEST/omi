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
import { auth } from '@clerk/nextjs/server';
import { ApiError, _parse } from './api';
import { env } from './env';

export async function apiServer<T>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  // Primary auth: forward the Clerk session token as a Bearer so FastAPI can verify + resolve the
  // user. FastAPI verifies the JWT against Clerk's public JWKS (RS256) — no Clerk secret needed here.
  //
  // Two ways to obtain that token, tried in order, so this never depends on the Edge middleware:
  //   1. auth().getToken() — works when clerkMiddleware populated the request context.
  //   2. the `__session` cookie — Clerk stores the session JWT here; readable server-side even when
  //      the middleware degraded (e.g. the secret couldn't reach the Edge runtime). This is what
  //      keeps auth working regardless of the middleware/secret situation.
  const jar = cookies();
  let bearer: string | undefined;
  try {
    const { getToken } = await auth();
    const token = await getToken();
    if (token) bearer = `Bearer ${token}`;
  } catch {
    /* middleware didn't run / not signed in — the __session fallback below covers it */
  }
  if (!bearer) {
    // Clerk stores the session JWT in `__session` (or a suffixed `__session_<hash>` when the instance
    // uses suffixed cookies). Take whichever is present so a dev instance's suffixed cookie also works.
    const all = jar.getAll();
    const sessionCookie =
      all.find((c) => c.name === '__session') ??
      all.find((c) => c.name.startsWith('__session_'));
    if (sessionCookie?.value) bearer = `Bearer ${sessionCookie.value}`;
  }

  const cookieHeader = jar
    .getAll()
    .map((c) => `${c.name}=${c.value}`)
    .join('; ');

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
