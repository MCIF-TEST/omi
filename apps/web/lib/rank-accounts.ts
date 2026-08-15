/**
 * The order the per-account reads are shown in: worst first.
 *
 * The list used to render in BATCH order, which was a consequence of how a scan runs rather than a
 * decision about what a reader wants. It meant the highest-scoring account in an investigation could
 * sit two thirds of the way down a hundred-row list purely because it happened to be selected late,
 * so the finding the customer opened the page for was the thing they had to scroll for. Every other
 * surface in the product already leads with the worst account: the shared report, the markdown
 * export and the CSV all sort this way.
 *
 * Two rules, both inherited from how a score is defined elsewhere in this codebase:
 *
 * * **An unscored account sorts LAST, never as a zero.** A missing `omi_score` means the analyst
 *   never assessed that account (a batch that floored, a row the model skipped), which is not the
 *   same claim as "this account looks like a real person". Treating absence as 0 would file an
 *   unassessed account among the most exonerated ones on the page.
 * * **Ties keep their existing order.** `Array.prototype.sort` is stable per spec, so accounts on
 *   the same score stay in selection order rather than shuffling between polls.
 *
 * Pure and separate from the panel because the panel's job is layout: this is the rule, and a rule
 * worth having is worth pinning.
 */

/** The narrowest shape this needs, so it accepts a full assessment row without importing one. */
export type Rankable = { omi_score?: number | null };

/** A sort key where a missing score is worse than nothing rather than better than everything. */
function rank(row: Rankable): number {
  return typeof row.omi_score === 'number' && Number.isFinite(row.omi_score) ? row.omi_score : -1;
}

/**
 * A new array ordered highest OMI score first.
 *
 * Returns a copy. The input is React state held by the panel and rendered elsewhere (the export
 * builds its own rows from the same list), and sorting it in place would reorder it under whoever
 * else is holding it.
 */
export function byOmiScoreDesc<T extends Rankable>(rows: readonly T[]): T[] {
  return [...rows].sort((a, b) => rank(b) - rank(a));
}
