/**
 * Campaign member identity helpers.
 *
 * Some campaign sources — notably platform state-actor disclosure archives —
 * ANONYMIZE low-follower accounts by hashing their handles before release. The
 * fixture stores that hash in both `account_external_id` and `handle`, so a
 * naive `handle || account_external_id` render shows the hash as if it were a
 * username. We must not present a hash as a handle.
 *
 * Detection is deliberately conservative so it can NEVER hide a real handle:
 * a member is treated as anonymized only when there is no distinct human handle
 * AND the identifier itself looks like a disclosure hash (base64 characters or
 * implausibly long) — never a normal @handle, a numeric id, or a YouTube
 * `UC…` channel id.
 */

/** True when the raw identifier looks like an anonymized disclosure hash. */
function looksLikeDisclosureHash(value: string): boolean {
  if (!value) return false;
  // base64 padding/alphabet chars never appear in real handles/ids
  if (/[=+/]/.test(value)) return true;
  // handles, numeric ids, and UC… channel ids are all <= ~30 chars
  return value.length > 35;
}

/** A campaign member whose real identity was anonymized at the source. */
export function isAnonymizedMember(
  handle: string | null | undefined,
  externalId: string,
): boolean {
  // A real, distinct human handle → never anonymized.
  if (handle && handle !== externalId) return false;
  // No distinct handle: anonymized only if the identifier is a disclosure hash.
  return looksLikeDisclosureHash(externalId);
}

/** Does any member in the list have an anonymized identity? */
export function hasAnonymizedMembers(
  members: { handle: string | null; account_external_id: string }[],
): boolean {
  return members.some((m) => isAnonymizedMember(m.handle, m.account_external_id));
}

/** The provenance note shown when a campaign contains anonymized members. */
export const ANONYMIZED_PROVENANCE_NOTE =
  'Some source disclosure archives anonymize account identities before release. ' +
  'Membership is derived from behavioral evidence and source disclosures.';
