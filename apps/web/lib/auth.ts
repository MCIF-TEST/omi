/**
 * Server-side auth helpers — resolve the current user from the omi_session
 * cookie by asking FastAPI's /v1/auth/me endpoint.
 *
 * Cached per-request via React's `cache()` so multiple components in the
 * same render don't trigger duplicate API calls.
 */

import { cache } from 'react';
import { ApiError, type User } from './api';
import { apiServer } from './api-server';

export const getCurrentUser = cache(async (): Promise<User | null> => {
  try {
    const u = await apiServer<User | null>('/v1/auth/me');
    return u;
  } catch (e) {
    if (e instanceof ApiError && e.status === 401) return null;
    return null;
  }
});

export async function requireUser(): Promise<User> {
  const u = await getCurrentUser();
  if (!u) {
    // We don't redirect here — let the caller decide. The middleware
    // already handles unauth on protected routes.
    throw new ApiError(401, 'Not authenticated');
  }
  return u;
}
