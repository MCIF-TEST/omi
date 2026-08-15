import { describe, expect, it } from 'vitest';
import { ACCOUNTS_PER_BATCH, ANALYST_BATCH_COUNT, batchStates, batchesFor, displayedBatch } from './analysis-progress';

describe('batchesFor', () => {
  it('matches the API threshold and batch count', () => {
    expect(ACCOUNTS_PER_BATCH).toBe(25);
    expect(ANALYST_BATCH_COUNT).toBe(4);
  });

  it('splits a selection the way the analyst does: a FIXED count, not a slice size', () => {
    // The server divides anything above the threshold into `analyst_batch_count` near-equal
    // batches. Deriving `ceil(accounts / 25)` here promised six passes for a 126-account scan that
    // actually runs four, and the promise is the number a customer watches count down.
    expect(batchesFor(1)).toBe(1);
    expect(batchesFor(25)).toBe(1);
    expect(batchesFor(26)).toBe(4);
    expect(batchesFor(100)).toBe(4);
    expect(batchesFor(126)).toBe(4);
    expect(batchesFor(150)).toBe(4);
  });

  it('never claims zero batches, however odd the input', () => {
    // A denominator of 0 renders "batch 1 of 0", which reads as a broken product.
    expect(batchesFor(0)).toBe(1);
    expect(batchesFor(-5)).toBe(1);
  });
});

describe('displayedBatch', () => {
  it('starts on the first batch', () => {
    expect(displayedBatch(0, 4)).toBe(1);
    expect(displayedBatch(119, 4)).toBe(1);
  });

  it('moves on after 120 seconds so a long first batch does not read as a hang', () => {
    // The whole reason this exists: the first batch can take minutes, and a counter frozen on
    // "1 of 4" is the most common reason a user decides the scan is stuck.
    expect(displayedBatch(120, 4)).toBe(2);
    expect(displayedBatch(240, 4)).toBe(3);
  });

  it('never runs past the last batch', () => {
    // Overshooting would show "batch 7 of 4", which is worse than looking slow.
    expect(displayedBatch(9999, 4)).toBe(4);
    expect(displayedBatch(9999, 1)).toBe(1);
  });

  it('real progress wins when it is ahead of the clock', () => {
    // Three batches genuinely done inside the first two minutes means we are on the fourth,
    // whatever the clock estimate says.
    expect(displayedBatch(10, 6, 3)).toBe(4);
  });

  it('is a position, never a completion count', () => {
    // Guard on the semantics the copy depends on. With nothing finished we are still working ON
    // batch 1, so the number shown is 1, not 0. If this returned `done` instead, the label
    // "Analysing batch N of M" would become a claim that N batches produced results.
    expect(displayedBatch(0, 4, 0)).toBe(1);
  });
});

// ---------------------------------------------------------------------------
// A failed batch is not a finished one.
//
// Live symptom: the strip read "3 OF 4 DONE" directly beside "25 accounts scored". Both numbers
// were correct. `batching.done` counts batches ATTEMPTED, on purpose, so a run containing a failure
// still visibly advances instead of looking hung. But rendering attempts as completions told a
// customer three quarters of their scan was finished when three quarters of it had been TRIED and
// one quarter of it had worked.
// ---------------------------------------------------------------------------
describe('batchStates', () => {
  it('does not count an attempted batch as a completed one', () => {
    // The exact live case: 4 batches, 3 attempted, 1 produced accounts, 2 came back empty.
    const states = batchStates({ total: 4, done: 3, landed: 1, complete: false });
    expect(states).toEqual(['done', 'failed', 'failed', 'running']);
    expect(states.filter((s) => s === 'done')).toHaveLength(1);
  });

  it('uses the per-batch record when it has one, rather than inferring from counts', () => {
    // Counts cannot say WHICH batch failed. Traces can, and here the empty one is not the first.
    const states = batchStates(
      { total: 4, done: 3, landed: 2, complete: false },
      [{ batch: 1, accounts: 25 }, { batch: 2, accounts: 0 }, { batch: 3, accounts: 25 }],
    );
    expect(states).toEqual(['done', 'failed', 'done', 'running']);
  });

  it('shows a healthy run as all done', () => {
    expect(batchStates({ total: 4, done: 4, landed: 4, complete: true }))
      .toEqual(['done', 'done', 'done', 'done']);
  });

  it('marks exactly one batch as running, and only while the run is unfinished', () => {
    expect(batchStates({ total: 4, done: 1, landed: 1, complete: false }))
      .toEqual(['done', 'running', 'pending', 'pending']);
    // Once the run is over nothing is running: an unattempted batch stays pending.
    expect(batchStates({ total: 4, done: 2, landed: 2, complete: true }))
      .toEqual(['done', 'done', 'pending', 'pending']);
  });

  it('treats a missing landed count as "every attempt worked"', () => {
    // Entries written before `landed` existed carry no value, and inventing failures for them would
    // put a warning colour on a scan that was fine.
    expect(batchStates({ total: 3, done: 2, complete: false }))
      .toEqual(['done', 'done', 'running']);
  });

  it('never returns fewer segments than the run has batches', () => {
    expect(batchStates({ total: 0, done: 0, complete: false })).toHaveLength(1);
    expect(batchStates({ total: 4, done: 99, landed: 99, complete: true })).toHaveLength(4);
  });
});
