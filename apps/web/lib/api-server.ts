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
  // Forward the user's session cookie so FastAPI can resolve the user.
  const cookieHeader = cookies()
    .getAll()
    .map((c) => `${c.name}=${c.value}`)
    .join('; ');

  const res = await fetch(`${env.API_ORIGIN}${path}`, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      ...(cookieHeader ? { cookie: cookieHeader } : {}),
      ...init.headers,
    },
    cache: 'no-store',
  });
  return _parse<T>(res);
}

// Re-export ApiError for server callers that want everything from one module.
export { ApiError };
