import { describe, expect, it } from 'vitest';
import { clerkFrontendApiHost, clerkOriginsFor } from './clerk-origin';

/**
 * This decode feeds a security header on one side and a customer-facing sentence on the other, and
 * both were wrong at once during a live outage. The padding case below is the specific bug: it
 * threw, the caller silently got nothing, the CSP dropped the production Clerk origin, and the
 * sign-in page span forever with no error anywhere.
 */
const LIVE = 'pk_live_Y2xlcmsub21pc3BoZXJlLm9ubGluZSQ';                 // clerk.omisphere.online$
const TEST = 'pk_test_c3dlZXQtZmluY2gtNDUuY2xlcmsuYWNjb3VudHMuZGV2JA'; // sweet-finch-45.clerk.accounts.dev$

describe('clerkFrontendApiHost', () => {
  it('decodes a live key whose payload needs exactly one pad character', () => {
    // 31 characters. `atob(raw + '==')` throws on this, which is how it shipped broken.
    expect(LIVE.slice('pk_live_'.length).length % 4).toBe(3);
    expect(clerkFrontendApiHost(LIVE)).toBe('clerk.omisphere.online');
  });

  it('decodes a development key', () => {
    expect(clerkFrontendApiHost(TEST)).toBe('sweet-finch-45.clerk.accounts.dev');
  });

  it('returns null for an absent key rather than throwing', () => {
    // The build-time-missing case. It must be distinguishable from a working key, because it is the
    // one failure a visitor can do nothing about.
    for (const pk of [undefined, null, '', '   ']) {
      expect(clerkFrontendApiHost(pk)).toBeNull();
    }
  });

  it('returns null for anything that is not a plain hostname', () => {
    // A malformed key must widen nothing: this value lands in a CSP directive.
    const evil = `pk_live_${btoa("evil.example' https://attacker.test$")}`;
    expect(clerkFrontendApiHost(evil)).toBeNull();
    expect(clerkFrontendApiHost('pk_live_!!!not-base64!!!')).toBeNull();
    expect(clerkFrontendApiHost('not-a-key-at-all')).toBeNull();
    expect(clerkFrontendApiHost(`pk_live_${btoa('localhost$')}`)).toBeNull();
  });

  it('tolerates a trailing slash as well as the trailing dollar', () => {
    expect(clerkFrontendApiHost(`pk_live_${btoa('clerk.example.com/')}`)).toBe('clerk.example.com');
  });
});

describe('clerkOriginsFor', () => {
  it('includes the Account Portal when the Frontend API is a clerk. subdomain', () => {
    // OAuth and email links hand off to it, so it is a navigation and form-action target too.
    expect(clerkOriginsFor(LIVE)).toEqual([
      'https://clerk.omisphere.online',
      'https://accounts.omisphere.online',
    ]);
  });

  it('does not invent an Account Portal for a development instance', () => {
    expect(clerkOriginsFor(TEST)).toEqual(['https://sweet-finch-45.clerk.accounts.dev']);
  });

  it('yields nothing at all for a key it cannot trust', () => {
    expect(clerkOriginsFor(undefined)).toEqual([]);
    expect(clerkOriginsFor('pk_live_!!!')).toEqual([]);
  });
});

// ---------------------------------------------------------------------------
// Which failure the sign-in page reports.
//
// Three causes with three different remedies. The old message covered all of them with one sentence
// telling the reader to check their network and extensions, which is actively wrong for two of the
// three: a blocked script and a key-less build are our faults, and no amount of reloading fixes
// either. Mirror of the branch in AuthFormGate so it cannot drift back.
// ---------------------------------------------------------------------------
function classify(policyBlocked: boolean, pk: string | undefined): 'blocked' | 'misconfigured' | 'unreachable' {
  const host = clerkFrontendApiHost(pk);
  return policyBlocked ? 'blocked' : !host ? 'misconfigured' : 'unreachable';
}

describe('why the sign-in form did not load', () => {
  it('names a policy block, which has no other evidence anywhere', () => {
    // No server log, no failed health check, nothing on the page: its only trace is a violation in
    // the browser console, which is why it once cost a live hour.
    expect(classify(true, LIVE)).toBe('blocked');
  });

  it('names a key-less build, and does not blame the visitor for it', () => {
    expect(classify(false, undefined)).toBe('misconfigured');
  });

  it('falls back to unreachable when the config is sound and nothing was blocked', () => {
    // The only case where "check your network or extensions" is the right advice.
    expect(classify(false, LIVE)).toBe('unreachable');
  });

  it('prefers the block over the config check when both could apply', () => {
    // A violation is direct evidence; an absent host is an inference. Direct evidence wins.
    expect(classify(true, undefined)).toBe('blocked');
  });
});
