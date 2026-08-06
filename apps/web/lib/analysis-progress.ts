/**
 * The pure half of the investigation progress screen, kept out of the component so it can be
 * tested directly (same split as `lib/investigation-export.ts` and `lib/analyst-failure.ts`).
 */

/** Matches `analyst_batch_accounts` on the API. Batches are what the user actually waits on. */
export const ACCOUNTS_PER_BATCH = 25;

/**
 * How long the displayed batch pointer waits before moving itself on.
 *
 * READ THIS BEFORE CHANGING IT. This advance is a FRONT-END ESTIMATE and nothing else. It exists
 * because the first batch can take minutes, and a counter frozen on "batch 1 of 4" for that long
 * reads as a hung scan, which is the most common reason a user reloads and assumes the product is
 * broken.
 *
 * Two things keep it honest, and both are load-bearing:
 *
 * 1. It names the batch being WORKED ON, never a count of batches finished. "Analysing batch 2 of
 *    4" is a statement about position in a queue. "2 of 4 done" would be a claim that results
 *    exist, and that claim would be false. Do not reword the label into a completion count.
 * 2. It only ever runs while there is NO real progress data. The moment the first batch lands, the
 *    progress screen is replaced by the results plus `BatchProgressStrip`, which reports the real
 *    `batching.done` from the server. So the estimate can never contradict a real number, because
 *    the two are never on screen together.
 */
export const BATCH_ADVANCE_SEC = 120;

/** Total batches for a selection of N accounts, which the client can derive without the server. */
export function batchesFor(accounts: number): number {
  return Math.max(1, Math.ceil(Math.max(0, accounts) / ACCOUNTS_PER_BATCH));
}

/**
 * Which batch to say we are on. Real progress always wins; the clock only fills the silence before
 * the first batch lands, and never runs past the last batch.
 */
export function displayedBatch(elapsedSec: number, totalBatches: number, done = 0): number {
  const byClock = 1 + Math.floor(Math.max(0, elapsedSec) / BATCH_ADVANCE_SEC);
  const byProgress = done + 1;
  return Math.min(Math.max(byClock, byProgress, 1), Math.max(1, totalBatches));
}
