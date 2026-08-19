/**
 * The pure half of "add this account to one of my graphs", kept out of the component so it can be
 * tested directly (same split as `lib/investigation-export.ts` and `lib/rank-accounts.ts`).
 */

import { type Tier, type UserGraphOut } from './api';

/**
 * Platforms a graph and an account must agree on before one can join the other.
 *
 * THIS IS A CORRECTNESS RULE, NOT A TIDINESS ONE. `POST /v1/graphs/{id}/members` stores the member
 * with the GRAPH's platform, not the account's (`platform=g.platform`), and the coordination-edge
 * query filters on that same value. So an X account added to a YouTube graph is written down as a
 * YouTube account and can never draw an edge to anything: it sits in the graph forever, looking
 * like a finding that failed to connect, when in fact it was mislabelled on the way in.
 *
 * The API cannot catch this — it has no idea what platform the caller thinks the account is on —
 * so the only place to enforce it is where both facts are known, which is here.
 */
export function graphsAcceptingPlatform(
  graphs: readonly UserGraphOut[],
  platform: string | undefined | null,
): UserGraphOut[] {
  const p = normalisePlatform(platform);
  if (!p) return [];
  return graphs.filter((g) => normalisePlatform(g.platform) === p);
}

/** "twitter" and "x" are the same platform under two names; anything else is itself, or nothing. */
export function normalisePlatform(platform: string | undefined | null): string | null {
  const p = (platform ?? '').trim().toLowerCase();
  if (!p || p === 'unknown') return null;
  if (p === 'twitter' || p === 'x') return 'x';
  return p;
}

/** Human name for a platform, for the empty state and the create affordance. */
export function platformLabel(platform: string | undefined | null): string {
  const p = normalisePlatform(platform);
  if (p === 'x') return 'X';
  if (p === 'youtube') return 'YouTube';
  return 'this platform';
}

export interface AddableAccount {
  external_id?: string;
  handle?: string;
  suspicion_tier?: Tier | null;
}

/**
 * Whether this account can be added at all.
 *
 * `external_id` is the identity the graph stores and de-duplicates on, so an account without one
 * cannot be added: an unresolved alias has no identity to attach a membership to, exactly as it has
 * none to attach a public claim to.
 */
export function isAddable(account: AddableAccount, platform: string | undefined | null): boolean {
  return Boolean((account.external_id ?? '').trim()) && normalisePlatform(platform) !== null;
}

/** The request body `POST /v1/graphs/{id}/members` expects, from a per-account row. */
export function memberPayload(account: AddableAccount): {
  external_id: string; handle: string; tier: string | null;
} {
  const externalId = (account.external_id ?? '').trim();
  return {
    external_id: externalId,
    // The API defaults `handle` to the external_id when empty, which renders a numeric id as a name
    // in the graph. Send the handle we already have.
    handle: (account.handle ?? '').trim() || externalId,
    tier: account.suspicion_tier ?? null,
  };
}
