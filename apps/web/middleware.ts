import { NextResponse, type NextRequest } from 'next/server';

import {
  AGENT_PAGES,
  AGENT_PAGE_BY_PATH,
  AGENT_PAGE_BY_MARKDOWN_PATH,
  markdownPath,
} from './lib/agent-content';
import { MARKDOWN_TYPE, VARY, prefersMarkdown } from './lib/accept-markdown';
import { clerkOriginsFor } from './lib/clerk-origin';

/**
 * Security headers + CSP nonces + lightweight edge rate limiting + referral cookie.
 *
 * No Clerk in middleware, on purpose (see history). Clerk runs client-side only;
 * route protection is in app/(app)/layout.tsx via FastAPI session verification.
 */

const REF_RE = /^[A-Za-z0-9_-]{4,16}$/;

/** Shared static security headers (also mirrored in next.config for static assets). */
export const SECURITY_HEADERS: Record<string, string> = {
  'Strict-Transport-Security': 'max-age=63072000; includeSubDomains; preload',
  'X-Frame-Options': 'DENY',
  'X-Content-Type-Options': 'nosniff',
  'Referrer-Policy': 'strict-origin-when-cross-origin',
  'Permissions-Policy':
    'camera=(), microphone=(), geolocation=(), payment=(), usb=(), interest-cohort=(), accelerometer=(), gyroscope=(), magnetometer=()',
  // same-origin-allow-popups: Clerk/OAuth may open auth windows; pure same-origin can break them.
  'Cross-Origin-Opener-Policy': 'same-origin-allow-popups',
  'Cross-Origin-Resource-Policy': 'same-site',
  // Modern best practice: disable legacy XSS auditor (CSP is the real control).
  'X-XSS-Protection': '0',
};

/**
 * Build a restrictive CSP. Next.js App Router injects flight scripts; when we set `x-nonce`
 * on the request, Next applies that nonce to its inline scripts so we can avoid 'unsafe-inline'.
 * Clerk loads from its CDN without our nonce. Listed explicitly in script-src.
 */
/**
 * The Clerk origins THIS deployment actually talks to, derived from the publishable key.
 *
 * This is not a nicety. A **development** Clerk instance serves clerk-js and its Frontend API from
 * `<slug>.clerk.accounts.dev`, which the static wildcards below cover. A **production** instance
 * serves both from the customer's own subdomain, here `clerk.omisphere.online`, and a subdomain is a
 * different origin, so `'self'` does not cover it and neither does `https://*.clerk.com`.
 *
 * Switching to the pk_live key with only the static hosts allowlisted therefore blocked the Clerk
 * script outright, and the failure looked nothing like a CSP problem: `useAuth().isLoaded` simply
 * never turned true, so `AuthFormGate` held its loading spinner and /sign-in span forever with no
 * error on the page. Deriving the host from the key means the policy follows the instance instead of
 * having to be remembered on the day the keys change.
 *
 * A publishable key is `pk_(test|live)_<base64(frontend_api_host + '$')>`, the same decode
 * `app/core/clerk_auth._issuer` does on the API side.
 */
export function clerkOrigins(): string[] {
  // The decode lives in lib/clerk-origin.ts because AuthFormGate needs the same answer, to name the
  // service that failed to answer. A malformed key widens nothing: it yields no origins rather than
  // a string concatenated into a directive.
  return clerkOriginsFor(process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY);
}

export function buildContentSecurityPolicy(nonce: string): string {
  // The instance this deployment is actually configured for, first, then the static development
  // hosts (kept so a pk_test preview deploy keeps working).
  const instance = clerkOrigins().join(' ');
  const clerkScript = [
    instance,
    'https://*.clerk.accounts.dev',
    'https://clerk.accounts.dev',
    'https://*.clerk.com',
    'https://clerk.com',
    'https://challenges.cloudflare.com',
  ].filter(Boolean).join(' ');
  const clerkConnect = [
    instance,
    'https://*.clerk.accounts.dev',
    'https://api.clerk.com',
    'https://clerk-telemetry.com',
    'https://*.clerk.com',
    'https://challenges.cloudflare.com',
  ].filter(Boolean).join(' ');
  // Stripe Checkout is a top-level redirect (not embedded); connect kept for future Elements.
  const stripe = 'https://js.stripe.com https://api.stripe.com https://hooks.stripe.com';

  return [
    "default-src 'self'",
    // Nonce covers Next.js flight + any nonced app scripts. No 'unsafe-inline' / 'unsafe-eval'.
    `script-src 'self' 'nonce-${nonce}' ${clerkScript}`,
    // Clerk + Tailwind inject styles; 'unsafe-inline' for style is far less risky than for scripts.
    "style-src 'self' 'unsafe-inline'",
    `img-src 'self' data: blob: https://img.clerk.com https://*.clerk.com https://*.clerk.accounts.dev${instance ? ` ${instance}` : ''}`,
    "font-src 'self' data:",
    // The analyst runs server-side on the API, so the BROWSER never reaches the model
    // vendor. Allowing it here widened the policy for nothing.
    `connect-src 'self' ${clerkConnect} ${stripe}`,
    `frame-src 'self' https://challenges.cloudflare.com https://*.clerk.accounts.dev https://js.stripe.com https://hooks.stripe.com${instance ? ` ${instance}` : ''}`,
    "worker-src 'self' blob:",
    "object-src 'none'",
    "base-uri 'self'",
    `form-action 'self' https://*.clerk.accounts.dev https://clerk.com${instance ? ` ${instance}` : ''}`,
    "frame-ancestors 'none'",
    'upgrade-insecure-requests',
  ].join('; ');
}

// --- Edge rate limit (best-effort; per isolate). Scanners + abuse get 429. ---
const RATE_WINDOW_MS = 60_000;
const RATE_MAX = 120; // pages per IP per minute
const hits = new Map<string, { count: number; reset: number }>();

function rateLimit(ip: string): { ok: boolean; retryAfter: number } {
  const now = Date.now();
  let row = hits.get(ip);
  if (!row || now >= row.reset) {
    row = { count: 0, reset: now + RATE_WINDOW_MS };
    hits.set(ip, row);
  }
  row.count += 1;
  // Opportunistic cleanup
  if (hits.size > 5_000) {
    for (const [k, v] of hits) {
      if (now >= v.reset) hits.delete(k);
    }
  }
  if (row.count > RATE_MAX) {
    return { ok: false, retryAfter: Math.max(1, Math.ceil((row.reset - now) / 1000)) };
  }
  return { ok: true, retryAfter: 0 };
}

function clientIp(req: NextRequest): string {
  return (
    req.headers.get('x-forwarded-for')?.split(',')[0]?.trim() ||
    req.headers.get('x-real-ip') ||
    'unknown'
  );
}

/**
 * Whether the request carries something that looks like a session.
 *
 * Clerk stores `__session` on the app's own domain, suffixed (`__session_<hash>`) on dev instances;
 * `omi_session` is the legacy cookie path. Presence is all this needs to decide a redirect. See the
 * call site for why verification would be the wrong tool here.
 */
function hasSessionCookie(req: NextRequest): boolean {
  return req.cookies.getAll().some(
    (c) => c.name === '__session' || c.name.startsWith('__session_') || c.name === 'omi_session',
  );
}

/**
 * The addressable markdown rendering of a page, at its own `.md` URL.
 *
 * Answered BEFORE negotiation, because this URL has exactly one representation and negotiating it
 * would be a lie. It exists because the negotiated pair cannot be made cache-safe from inside this
 * app: Next 14 overwrites `Vary` on every app-router HTML response during render, so the HTML half
 * cannot name `Accept`. A single-representation address needs no cache to honour anything.
 */
function markdownDocument(req: NextRequest): NextResponse | null {
  const path = req.nextUrl.pathname.replace(/\/+$/, '') || '/';
  const page = AGENT_PAGE_BY_MARKDOWN_PATH[path];
  if (!page) return null;

  // No `Accept` in Vary here, deliberately: this URL has ONE representation. Naming a request
  // header it does not vary on would tell a cache to store one copy per distinct Accept string,
  // which is a fragmentation of the cache in exchange for nothing.
  return new NextResponse(page.markdown, {
    status: 200,
    headers: {
      'Content-Type': MARKDOWN_TYPE,
      Vary: 'Accept-Encoding',
      'Cache-Control': 'public, max-age=3600, s-maxage=3600',
      Link: `<${page.path}>; rel="canonical"`,
      ...SECURITY_HEADERS,
    },
  });
}

/**
 * acceptmarkdown.com content negotiation.
 *
 * Handled in middleware rather than in each page because it has to cover EVERY public path with one
 * rule, including the 404. Doing it per-route would mean seven places to forget, on a behaviour
 * only machines exercise, so the omission would never be noticed from a browser.
 *
 * Returning the response from here is also what makes `Vary` correct on it: middleware responses
 * are finished before the renderer runs, so nothing overwrites the header the way it does on the
 * HTML variant.
 */
function negotiateMarkdown(req: NextRequest): NextResponse | null {
  const accept = req.headers.get('accept');
  if (!prefersMarkdown(accept)) return null;

  const path = req.nextUrl.pathname.replace(/\/+$/, '') || '/';
  const page = AGENT_PAGE_BY_PATH[path];

  if (page) {
    return new NextResponse(page.markdown, {
      status: 200,
      headers: {
        'Content-Type': MARKDOWN_TYPE,
        Vary: VARY,
        'Cache-Control': 'public, max-age=3600, s-maxage=3600',
        ...SECURITY_HEADERS,
      },
    });
  }

  // A path with no markdown representation. Anything under the private app or a tokenised report
  // falls through to the normal HTML pipeline: those are not public documents and inventing a
  // markdown rendering of them would be publishing something the HTML surface keeps behind auth.
  if (!isPublicPath(path)) return null;

  // A public-shaped path we do not have. This is the agent-recoverable 404: a real 404 status with
  // a body naming where to look next, in the format the client asked for.
  return new NextResponse(notFoundMarkdown(), {
    status: 404,
    headers: {
      'Content-Type': MARKDOWN_TYPE,
      Vary: VARY,
      'Cache-Control': 'no-store',
      ...SECURITY_HEADERS,
    },
  });
}

/** Whether a path belongs to the public documentary surface, as opposed to the app or a report. */
function isPublicPath(path: string): boolean {
  const PRIVATE = [
    '/api', '/r/', '/rc/', '/investigate', '/investigations', '/settings', '/graph',
    '/monitoring', '/search', '/bulk', '/accounts', '/channels', '/content', '/disputes',
    '/narratives', '/welcome', '/sign-in', '/sign-up', '/_next',
  ];
  return !PRIVATE.some((p) => path === p || path.startsWith(`${p}/`) || path.startsWith(p));
}

function notFoundMarkdown(): string {
  const pages = AGENT_PAGES
    .map((p) => `- [${p.path}](${p.path}): ${p.summary} Markdown: ${markdownPath(p.path)}`)
    .join('\n');
  return `# 404 Not Found

That address does not exist on OmiSphere.

## Pages

${pages}

## Machine-readable

- [/llms.txt](/llms.txt): What this site is, and where to look.
- [/sitemap.xml](/sitemap.xml): Every indexable page.
- [/openapi.json](/openapi.json): The OmiSphere HTTP API specification.
- [/developers](/developers): API reference, error format, rate limits.
`;
}

export default function middleware(req: NextRequest) {
  // Before anything else, including the rate limiter: a markdown request is cheap, cacheable, and
  // must not be refused by a budget meant for page navigations.
  // An explicit `.md` address is one document with no variants, so it is answered first and is
  // never subject to negotiation.
  const document = markdownDocument(req);
  if (document) return document;

  const markdown = negotiateMarkdown(req);
  if (markdown) return markdown;

  // Rate limit page navigations (not every static asset. Matcher already narrows).
  const { ok, retryAfter } = rateLimit(clientIp(req));
  if (!ok) {
    return new NextResponse('Too Many Requests', {
      status: 429,
      headers: {
        'Retry-After': String(retryAfter),
        'Content-Type': 'text/plain; charset=utf-8',
        ...SECURITY_HEADERS,
      },
    });
  }

  // Send an already-signed-in visitor straight to the workspace, so the landing page itself needs no
  // user lookup and can stay static/CDN-cacheable. It previously did this server-side by awaiting
  // /v1/auth/me on every anonymous visit, putting the API and database in the critical path of the
  // page traffic is bought for.
  //
  // Cookie PRESENCE only, no verification, and none needed. This is a convenience redirect, not an
  // access control: /investigate performs the real server-side session check and bounces an invalid
  // cookie to sign-in. Nothing is granted here, so a forged cookie buys an attacker a redirect.
  if (req.nextUrl.pathname === '/' && hasSessionCookie(req)) {
    return NextResponse.redirect(new URL('/investigate', req.url));
  }

  const nonce = Buffer.from(crypto.randomUUID()).toString('base64');
  const csp = buildContentSecurityPolicy(nonce);

  const requestHeaders = new Headers(req.headers);
  requestHeaders.set('x-nonce', nonce);
  // The root layout needs the path to emit `<link rel="alternate" type="text/markdown">` for the
  // page being rendered. A Server Component cannot read the pathname any other way, and the layout
  // is already dynamic for the nonce, so this costs nothing new.
  requestHeaders.set('x-pathname', req.nextUrl.pathname);

  const res = NextResponse.next({
    request: { headers: requestHeaders },
  });

  // Apply security headers on the response (document + navigations).
  for (const [k, v] of Object.entries(SECURITY_HEADERS)) {
    res.headers.set(k, v);
  }
  res.headers.set('Content-Security-Policy', csp);
  // The HTML response is a VARIANT of a negotiated URL, so it should say so. It is set here and
  // Next 14 OVERWRITES it during render (`base-server.js: setVaryHeader` does a bare setHeader with
  // its own RSC values on every app-router response), so the header that reaches the client is
  // Next's. Nothing in this repo can win that, which is why `markdownPath()` exists: the `.md`
  // address is a single-representation URL, so an agent never depends on a cache honouring Vary.
  // Left in place because it IS correct, and because it becomes effective the day the framework
  // stops clobbering it.
  res.headers.set('Vary', VARY);
  // Expose nonce to Server Components via request header (read with headers() in layout).
  res.headers.set('x-nonce', nonce);

  // Referral capture for Clerk sign-up (cannot carry ?ref= through hosted flow).
  const ref = req.nextUrl.searchParams.get('ref');
  if (ref && REF_RE.test(ref) && req.cookies.get('omi_ref')?.value !== ref) {
    res.cookies.set('omi_ref', ref, {
      path: '/',
      maxAge: 60 * 60 * 24 * 30,
      sameSite: 'lax',
      httpOnly: true,
      secure: process.env.NODE_ENV === 'production',
    });
  }

  return res;
}

export const config = {
  // Pages + HTML navigations. Skip static files Next already fingerprints.
  matcher: [
    '/((?!_next/static|_next/image|favicon.ico|.*\\.(?:svg|png|jpg|jpeg|gif|webp|ico|css|js|map|txt|xml|json)$).*)',
  ],
};
