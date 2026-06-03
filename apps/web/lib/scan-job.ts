/**
 * Async single-link scan client — CLIENT-SAFE.
 *
 * Wraps the backend's async job endpoints (`/v1/scan/link/start` +
 * `/v1/scan/link/status/{job_id}`): the whole scan runs on the backend's
 * background pool, so the only client-side fetches are the quick start POST and
 * short status polls — nothing here holds a connection open for the scan's
 * duration, so it can't trip a proxy timeout (the "reaches the last step then
 * shows no result" failure).
 */

import { apiClient, ApiError, type Tier } from './api';

export interface LinkScanJob {
  job_id: string;
  status: 'queued' | 'running' | 'done' | 'failed';
  platform: string;
  url: string;
  investigation_slug: string | null;
  tier: Tier | null;
  overall_probability: number | null;
  error: string | null;
}

/** Thrown by runLinkScanJob when a newer scan supersedes the one being polled. */
export class ScanCancelledError extends Error {
  constructor() {
    super('Scan cancelled');
    this.name = 'ScanCancelledError';
  }
}

const _sleep = (ms: number) => new Promise<void>((r) => setTimeout(r, ms));

/**
 * Start an async link scan and poll until it reaches a terminal state.
 *
 * Resolves with the final job (status 'done' | 'failed'). The initial POST
 * returns in milliseconds and surfaces start-time errors (400/401/402/503…) as
 * ApiError. A transient poll error is tolerated a few times so a blip doesn't
 * abandon a scan that's still running server-side. If `shouldContinue` returns
 * false the run is dropped with a ScanCancelledError (a newer scan replaced it).
 */
export async function runLinkScanJob(
  body: Record<string, unknown>,
  shouldContinue: () => boolean = () => true,
): Promise<LinkScanJob> {
  const job = await apiClient<LinkScanJob>('/v1/scan/link/start', {
    method: 'POST',
    body: JSON.stringify(body),
  });
  if (!shouldContinue()) throw new ScanCancelledError();

  const deadline = Date.now() + 8 * 60 * 1000; // hard cap; backend caps too
  let delay = 1500;
  let pollErrors = 0;
  while (Date.now() < deadline) {
    await _sleep(delay);
    if (!shouldContinue()) throw new ScanCancelledError();
    try {
      const cur = await apiClient<LinkScanJob>(`/v1/scan/link/status/${job.job_id}`);
      pollErrors = 0;
      if (cur.status === 'done' || cur.status === 'failed') return cur;
    } catch (e) {
      // Session loss or a vanished job are terminal; a transient blip is not.
      if (e instanceof ApiError && (e.status === 401 || e.status === 404)) throw e;
      if (++pollErrors > 5) throw e;
    }
    delay = Math.min(delay + 500, 3000);
  }
  throw new ApiError(
    504,
    'The scan is taking longer than expected. It may still be finishing — ' +
      'check your recent investigations in a moment.',
  );
}
