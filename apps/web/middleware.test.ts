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

// ---------------------------------------------------------------------------
// Agent surface: markdown negotiation, the `.md` addresses, and the 404.
//
// These drive the real exported middleware, because the negotiation is only correct in the context
// of the dispatch order around it: a markdown request has to be answered BEFORE the rate limiter
// (an agent must not be refused by a budget meant for page navigations) and a `.md` address has to
// be answered before negotiation (it has one representation and negotiating it would be a lie).
// Testing the predicate alone would prove none of that.
// ---------------------------------------------------------------------------

async function get(path: string, accept?: string) {
  const { NextRequest } = await import('next/server');
  const middleware = (await import('./middleware')).default;
  const req = new NextRequest(new URL(`https://omisphere.online${path}`), {
    headers: accept ? { accept } : {},
  });
  return middleware(req);
}

const AGENT = 'text/markdown';
const HUMAN = 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8';

describe('markdown content negotiation', () => {
  it('serves the page as markdown when an agent asks for it', async () => {
    const res = await get('/pricing', AGENT);
    expect(res.status).toBe(200);
    expect(res.headers.get('content-type')).toBe('text/markdown; charset=utf-8');
    expect(await res.text()).toContain('# ');
  });

  it('names Accept in Vary on the negotiated response', async () => {
    const res = await get('/pricing', AGENT);
    expect(res.headers.get('vary')).toContain('Accept');
  });

  it('leaves a browser navigation alone', async () => {
    const res = await get('/pricing', HUMAN);
    expect(res.headers.get('content-type')).not.toBe('text/markdown; charset=utf-8');
  });

  it('ignores a trailing slash, which agents and humans both send', async () => {
    const res = await get('/pricing/', AGENT);
    expect(res.status).toBe(200);
    expect(res.headers.get('content-type')).toBe('text/markdown; charset=utf-8');
  });

  it('carries the security headers, so the agent path is not a hole in them', async () => {
    const res = await get('/pricing', AGENT);
    expect(res.headers.get('X-Content-Type-Options')).toBe('nosniff');
  });

  it('does not invent a markdown rendering of a private surface', async () => {
    // /investigate is behind auth. Answering it here would publish a document the HTML surface
    // keeps signed in, so it falls through to the ordinary pipeline instead.
    const res = await get('/investigate', AGENT);
    expect(res.headers.get('content-type')).not.toBe('text/markdown; charset=utf-8');
  });
});

describe('the addressable .md URLs', () => {
  it('serves the page body at its own address, with no negotiation involved', async () => {
    const res = await get('/pricing.md', HUMAN);
    expect(res.status).toBe(200);
    expect(res.headers.get('content-type')).toBe('text/markdown; charset=utf-8');
  });

  it('gives the home page a named address', async () => {
    const res = await get('/index.md', HUMAN);
    expect(res.status).toBe(200);
    expect(await res.text()).toContain('# OmiSphere');
  });

  it('does not claim to vary on Accept, because it has one representation', async () => {
    const res = await get('/pricing.md', HUMAN);
    expect(res.headers.get('vary')).toBe('Accept-Encoding');
  });

  it('points back at the page it renders, so the two do not compete in an index', async () => {
    const res = await get('/pricing.md', HUMAN);
    expect(res.headers.get('link')).toContain('rel="canonical"');
  });
});

describe('the agent-recoverable 404', () => {
  it('answers 404, not 200, so a client can tell the page is missing', async () => {
    const res = await get('/no-such-page', AGENT);
    expect(res.status).toBe(404);
  });

  it('says where to look next, in the format that was asked for', async () => {
    const res = await get('/no-such-page', AGENT);
    expect(res.headers.get('content-type')).toBe('text/markdown; charset=utf-8');
    const body = await res.text();
    expect(body).toContain('/pricing');
    expect(body).toContain('/llms.txt');
    expect(body).toContain('/sitemap.xml');
  });

  it('is not cached, because the page may exist tomorrow', async () => {
    const res = await get('/no-such-page', AGENT);
    expect(res.headers.get('cache-control')).toBe('no-store');
  });
});
