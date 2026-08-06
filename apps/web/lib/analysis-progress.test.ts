import { describe, expect, it } from 'vitest';
import { ACCOUNTS_PER_BATCH, batchesFor, displayedBatch } from './analysis-progress';

describe('batchesFor', () => {
  it('matches the API batch size', () => {
    expect(ACCOUNTS_PER_BATCH).toBe(25);
  });

  it('splits a selection the way the analyst does', () => {
    expect(batchesFor(1)).toBe(1);
    expect(batchesFor(25)).toBe(1);
    expect(batchesFor(26)).toBe(2);
    expect(batchesFor(100)).toBe(4);
    expect(batchesFor(150)).toBe(6);
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
