import { describe, it, expect, afterEach } from 'vitest';
import { buildContentSecurityPolicy, clerkOrigins } from './middleware';

const LIVE = 'pk_live_Y2xlcmsub21pc3BoZXJlLm9ubGluZSQ';        // clerk.omisphere.online$
const TEST = 'pk_test_c3dlZXQtZmluY2gtNDUuY2xlcmsuYWNjb3VudHMuZGV2JA'; // sweet-finch-45.clerk.accounts.dev$

function withKey(pk: string | undefined, fn: () => void) {
  const prev = process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY;
  if (pk === undefined) delete process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY;
  else process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY = pk;
  try {
    fn();
  } finally {
    if (prev === undefined) delete process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY;
    else process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY = prev;
  }
}

function directive(csp: string, name: string): string {
  return csp.split('; ').find((d) => d.startsWith(`${name} `)) ?? '';
}

afterEach(() => { /* withKey restores; here so a thrown assertion cannot leak state */ });

describe('clerkOrigins', () => {
  it('derives the production Frontend API origin from the publishable key', () => {
    withKey(LIVE, () => {
      expect(clerkOrigins()).toContain('https://clerk.omisphere.online');
    });
  });

  it('adds the Account Portal origin, which OAuth and email links hand off to', () => {
    withKey(LIVE, () => {
      expect(clerkOrigins()).toContain('https://accounts.omisphere.online');
    });
  });

  it('derives the development instance host too', () => {
    withKey(TEST, () => {
      expect(clerkOrigins()).toEqual(['https://sweet-finch-45.clerk.accounts.dev']);
    });
  });

  it('widens nothing when the key is absent or malformed', () => {
    // A bad key must not concatenate junk into a directive. Better a policy that is too tight, which
    // fails loudly in the console, than one silently opened up by a typo.
    withKey(undefined, () => expect(clerkOrigins()).toEqual([]));
    withKey('', () => expect(clerkOrigins()).toEqual([]));
    withKey('pk_live_', () => expect(clerkOrigins()).toEqual([]));
    withKey('not-a-key', () => expect(clerkOrigins()).toEqual([]));
    withKey('pk_live_' + btoa('not a hostname$'), () => expect(clerkOrigins()).toEqual([]));
    withKey('pk_live_' + btoa('evil.com/path$'), () => expect(clerkOrigins()).toEqual([]));
  });
});

describe('buildContentSecurityPolicy', () => {
  it('allows the production Clerk instance to load its script and call its API', () => {
    // The regression this pins: with only the static *.clerk.accounts.dev / *.clerk.com hosts
    // allowlisted, a pk_live deploy blocked clerk-js outright. `useAuth().isLoaded` never turned
    // true, so /sign-in held its spinner forever with no error anywhere. A subdomain is a separate
    // origin, so neither 'self' nor the wildcards above cover clerk.omisphere.online.
    withKey(LIVE, () => {
      const csp = buildContentSecurityPolicy('abc123');
      expect(directive(csp, 'script-src')).toContain('https://clerk.omisphere.online');
      expect(directive(csp, 'connect-src')).toContain('https://clerk.omisphere.online');
      expect(directive(csp, 'img-src')).toContain('https://clerk.omisphere.online');
      expect(directive(csp, 'frame-src')).toContain('https://clerk.omisphere.online');
      expect(directive(csp, 'form-action')).toContain('https://accounts.omisphere.online');
    });
  });

  it('keeps the development hosts, so a pk_test preview deploy still works', () => {
    withKey(LIVE, () => {
      const csp = buildContentSecurityPolicy('abc123');
      expect(directive(csp, 'script-src')).toContain('https://*.clerk.accounts.dev');
      expect(directive(csp, 'connect-src')).toContain('https://api.clerk.com');
    });
  });

  it('carries the nonce and never falls back to unsafe-inline for scripts', () => {
    withKey(LIVE, () => {
      const csp = buildContentSecurityPolicy('abc123');
      expect(directive(csp, 'script-src')).toContain("'nonce-abc123'");
      expect(directive(csp, 'script-src')).not.toContain('unsafe-inline');
      expect(directive(csp, 'script-src')).not.toContain('unsafe-eval');
    });
  });

  it('emits no stray separators when there is no key to derive from', () => {
    withKey(undefined, () => {
      const csp = buildContentSecurityPolicy('abc123');
      expect(csp).not.toMatch(/\s{2,}/);
      expect(csp).not.toContain('; ;');
      expect(directive(csp, 'default-src')).toBe("default-src 'self'");
    });
  });
});
