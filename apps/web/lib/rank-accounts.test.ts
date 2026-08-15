import { describe, expect, it } from 'vitest';
import { byOmiScoreDesc } from './rank-accounts';

/**
 * The order a customer reads their results in. Worth pinning rather than leaving inline in the
 * panel, because the two edge cases here are both places where a plausible one-line sort quietly
 * says something false about an account.
 */
describe('byOmiScoreDesc', () => {
  it('puts the highest OMI score first', () => {
    const rows = [{ omi_score: 12 }, { omi_score: 88 }, { omi_score: 40 }];
    expect(byOmiScoreDesc(rows).map((r) => r.omi_score)).toEqual([88, 40, 12]);
  });

  it('sorts an unassessed account LAST, not as a zero', () => {
    // A missing score means the analyst never read that account (a floored batch, a row the model
    // skipped). Treating it as 0 would file it among the most exonerated accounts on the page,
    // which is a claim we did not make about it.
    const rows = [{ omi_score: 5 }, { omi_score: undefined }, { omi_score: 60 }];
    expect(byOmiScoreDesc(rows).map((r) => r.omi_score)).toEqual([60, 5, undefined]);
  });

  it('treats null and a non-finite score the same as absent', () => {
    const rows = [{ omi_score: null }, { omi_score: 30 }, { omi_score: NaN }];
    const out = byOmiScoreDesc(rows);
    expect(out[0].omi_score).toBe(30);
    expect(out.length).toBe(3);
  });

  it('keeps tied accounts in their existing order', () => {
    // Stability matters during a live batched run: the list re-renders every time a batch lands,
    // and accounts on the same score must not shuffle between polls.
    const rows = [
      { omi_score: 50, handle: 'a' }, { omi_score: 90, handle: 'b' },
      { omi_score: 50, handle: 'c' }, { omi_score: 50, handle: 'd' },
    ];
    expect(byOmiScoreDesc(rows).map((r) => r.handle)).toEqual(['b', 'a', 'c', 'd']);
  });

  it('does not reorder the array it was given', () => {
    // The panel holds this list in state and the export builds its own rows from the same one.
    // Sorting in place would reorder it under whoever else is holding it.
    const rows = [{ omi_score: 1 }, { omi_score: 99 }];
    const out = byOmiScoreDesc(rows);
    expect(rows.map((r) => r.omi_score)).toEqual([1, 99]);
    expect(out).not.toBe(rows);
  });

  it('handles an empty list', () => {
    expect(byOmiScoreDesc([])).toEqual([]);
  });
});
