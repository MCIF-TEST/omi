/**
 * The Clerk instance this deployment talks to, derived from the publishable key.
 *
 * A publishable key is `pk_(test|live)_<base64(frontend_api_host + '$')>`, the same decode
 * `app/core/clerk_auth._issuer` performs on the API side. Two places need the answer, for opposite
 * reasons, and both used to be wrong at the same time during one live outage:
 *
 * * `middleware.ts` needs the ORIGINS, to allowlist them in the CSP. A production instance serves
 *   clerk-js and its Frontend API from the customer's own subdomain, which `'self'` does not cover
 *   and neither does `https://*.clerk.com`.
 * * `AuthFormGate` needs the HOST, to say which service failed to answer when the sign-in form does
 *   not load, and to tell a policy block apart from a network failure.
 *
 * It lives here rather than in `middleware.ts` so the client component can use it without pulling an
 * Edge middleware module into the browser bundle. Pure, no environment access: the caller supplies
 * the key, because middleware reads it from `process.env` at the edge while the gate reads the value
 * Next inlined at build time, and those are not the same read.
 */

/** A plain hostname. Anything else is a malformed key and must widen nothing. */
const HOSTNAME_RE = /^[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)+$/i;

/**
 * The Frontend API host the key names, or `null` if the key is absent or malformed.
 *
 * Returning `null` rather than throwing matters: this feeds a security header on one side and a
 * customer-facing sentence on the other, and neither may fail the request over a bad string.
 */
export function clerkFrontendApiHost(pk: string | undefined | null): string | null {
  const key = (pk || '').trim();
  const m = /^pk_(?:test|live)_(.+)$/.exec(key);
  if (!m) return null;
  let host: string;
  try {
    // Clerk strips the base64 padding from the key, and `atob` (unlike Python's b64decode, which the
    // API side uses) rejects a string whose length is not a multiple of four. Pad EXACTLY, never
    // with a fixed '==': the live key's payload is 31 characters and needs one '=', so the naive
    // version threw and the caller silently got nothing at all.
    const raw = m[1];
    host = atob(raw + '='.repeat((4 - (raw.length % 4)) % 4)).replace(/\$$/, '').replace(/\/$/, '');
  } catch {
    return null;
  }
  return HOSTNAME_RE.test(host) ? host : null;
}

/**
 * Every origin this deployment's Clerk instance is reached at.
 *
 * Includes the Account Portal at `accounts.<domain>` when the Frontend API is `clerk.<domain>`:
 * OAuth and email-link flows hand off to it, so it is a navigation and form-action target as well.
 */
export function clerkOriginsFor(pk: string | undefined | null): string[] {
  const host = clerkFrontendApiHost(pk);
  if (!host) return [];
  const origins = [`https://${host}`];
  if (host.startsWith('clerk.')) origins.push(`https://accounts.${host.slice('clerk.'.length)}`);
  return origins;
}
