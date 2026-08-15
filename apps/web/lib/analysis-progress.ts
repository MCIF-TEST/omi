/**
 * The pure half of the investigation progress screen, kept out of the component so it can be
 * tested directly (same split as `lib/investigation-export.ts` and `lib/analyst-failure.ts`).
 */

/**
 * The THRESHOLD, mirroring `analyst_batch_accounts` on the API: at or below this, the analyst makes
 * one request and there are no batches to wait on.
 *
 * A deployment can lower it (`OMI_ANALYST_BATCH_ACCOUNTS` is 12 in `render.yaml`), which makes a
 * small selection batch sooner than this predicts. That is tolerable and deliberately not wired
 * through as another public env var: this whole module is the estimate shown BEFORE the first batch
 * lands, and real server progress replaces it the moment one does. The number that actually governs
 * a long wait is the count below, and that one is exact.
 */
export const ACCOUNTS_PER_BATCH = 25;

/**
 * How many batches a selection above the threshold becomes. Mirrors `analyst_batch_count` on the
 * API, which is a fixed COUNT rather than a slice size: 100 accounts is four passes of 25, and 126
 * is four passes of 32/32/31/31.
 *
 * It used to be derived as `ceil(accounts / 25)` here, which stopped being true when the server
 * moved to a fixed count: a 126-account scan would have promised six passes and run four.
 */
export const ANALYST_BATCH_COUNT = 4;

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

/**
 * What each batch in a run is actually doing.
 *
 * THE CONTRADICTION THIS FIXES, seen live: the strip read "3 of 4 done" beside "25 accounts
 * scored". Both numbers were correct and together they were a lie. `batching.done` counts batches
 * ATTEMPTED, not batches that produced anything, and it counts attempts on purpose: a run where one
 * batch fails must still visibly advance, or a scan that is working looks hung. But rendering
 * attempts as completions tells a customer that three quarters of their scan is finished when three
 * quarters of it was tried and one quarter of it worked.
 *
 * A failed batch is therefore its own state. `traces` gives the exact answer when it is present (a
 * batch that came back with zero accounts was attempted and produced nothing); without it the split
 * falls back to counts, which is right in aggregate even though it cannot say WHICH batch failed.
 */
export type BatchState = 'done' | 'failed' | 'running' | 'pending';

export function batchStates(
  { total, done, landed, complete }: {
    total: number; done: number; landed?: number; complete?: boolean;
  },
  traces?: ReadonlyArray<{ batch: number; accounts: number }>,
): BatchState[] {
  const n = Math.max(1, total);
  const attempted = Math.min(Math.max(0, done), n);
  const byBatch = new Map((traces ?? []).map((t) => [t.batch, t.accounts]));

  return Array.from({ length: n }, (_, i) => {
    if (byBatch.size > 0 && byBatch.has(i + 1)) {
      return (byBatch.get(i + 1) ?? 0) > 0 ? 'done' : 'failed';
    }
    if (i < attempted) {
      // Attempted, and either it produced nothing or we have no per-batch record. Fall back to the
      // counts: the first `landed` attempts are shown as done and the remainder as failed.
      const ok = Math.min(landed ?? attempted, attempted);
      return i < ok ? 'done' : 'failed';
    }
    // Nothing is running once the run is over: a batch never attempted stays pending.
    return i === attempted && !complete ? 'running' : 'pending';
  });
}

/**
 * 72 -> "1m 12s".
 *
 * Raw seconds stop being readable a couple of minutes in, which is most of the time a progress
 * surface is on screen: "412s" makes a reader do arithmetic to find out whether the scan is going
 * badly. Seconds are zero-padded so the number does not change width as it counts, which otherwise
 * makes the whole line twitch once a second.
 */
export function formatElapsed(sec: number): string {
  const s = Math.max(0, Math.floor(sec));
  return s < 60 ? `${s}s` : `${Math.floor(s / 60)}m ${String(s % 60).padStart(2, '0')}s`;
}

/** Total batches for a selection of N accounts, which the client can derive without the server. */
export function batchesFor(accounts: number): number {
  return Math.max(0, accounts) > ACCOUNTS_PER_BATCH ? ANALYST_BATCH_COUNT : 1;
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
