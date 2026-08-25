import type { Metadata } from 'next';
import { headers } from 'next/headers';

import { StructuredData } from '@/components/shared/structured-data';
import { AGENT_PAGE_BY_PATH, markdownPath } from '@/lib/agent-content';
import { env } from '@/lib/env';
import { Inter, JetBrains_Mono, Archivo } from 'next/font/google';
import { ClerkClientProvider } from '@/components/shared/clerk-provider';
import './globals.css';

/**
 * Self-hosted fonts via next/font (eliminates external stylesheets + SRI findings
 * for Google Fonts / rsms.me Inter). Subsets are downloaded at build time.
 */
const inter = Inter({
  subsets: ['latin'],
  display: 'swap',
  variable: '--font-inter',
  // Optical sizing / tabular figures are set in CSS font-feature-settings.
});

const jetbrainsMono = JetBrains_Mono({
  subsets: ['latin'],
  display: 'swap',
  variable: '--font-mono',
  weight: ['400', '500', '600'],
});

/**
 * Front-page display voice. Archivo is a grotesque cut for signage and headlines: narrower than
 * Inter, closed apertures, a much heavier top weight. Set tight and large it reads institutional
 * and a little severe, which is the register this product wants, and it is nobody's default, which
 * is most of the point.
 *
 * Loaded as a variable font (one file covers 400 to 800) and scoped to the pre-login page via
 * `.font-hero`. The signed-in app keeps Inter throughout: the two sides of the login boundary
 * should still read as one product, so the split is display-only and never reaches body copy.
 */
const archivo = Archivo({
  subsets: ['latin'],
  display: 'swap',
  variable: '--font-archivo',
});

// Space Grotesk (the old `--font-display-alt` marketing voice) is no longer loaded: the pre-login
// page now uses the app's own `.display` (Inter) so both sides of the login boundary read as one
// product. `.display-alt` in globals.css still falls back to `var(--font-display)`, so any stray
// usage degrades to Inter instead of breaking, and no visitor downloads a font nothing renders.

/**
 * Built per request rather than declared statically, for two reasons that both need the path.
 *
 * `canonical` was hardcoded to `/`, so every page that did not set its own told search engines it
 * was a duplicate of the home page. That is the single most effective way to keep a site out of an
 * index, and it was doing it to the marketing pages the brand query depends on.
 *
 * `alternates.types` emits `<link rel="alternate" type="text/markdown">`, which is how an agent
 * discovers the markdown rendering of the page it is already reading without having to guess a URL
 * or re-request with a different Accept header.
 *
 * This does not cost the static optimisation: the layout already reads `headers()` for the CSP
 * nonce, so it was per-request before this.
 */
function currentPath(): string {
  const raw = headers().get('x-pathname') ?? '/';
  return raw.replace(/\/+$/, '') || '/';
}

export function generateMetadata(): Metadata {
  const path = currentPath();
  const page = AGENT_PAGE_BY_PATH[path];
  return {
    ...BASE_METADATA,
    alternates: {
      canonical: path,
      // Only where a markdown rendering actually exists. Pointing at a `.md` address we do not
      // serve would be a 404 advertised in the head of a working page.
      ...(page ? { types: { 'text/markdown': markdownPath(page.path) } } : {}),
    },
  };
}

const BASE_METADATA: Metadata = {
  // A TEMPLATE, so every page carries the brand.
  //
  // The audit's finding was that a clean search for the brand did not return this domain. Part of
  // that is off-platform (links, mentions, time to index) and cannot be fixed from here. What CAN
  // be fixed from here is that the brand appeared in exactly one page title, so no other page was
  // a candidate for a brand query. Every page now ends in the brand.
  title: {
    default: 'OMISPHERE · Social Authenticity Intelligence',
    template: '%s · OMISPHERE',
  },
  description:
    'OMISPHERE detects bots, bought engagement, and AI-written replies in social media comment '
    + 'sections. Paste a post link, pick the accounts to analyse, and get a score for each one with '
    + 'the evidence behind it.',
  applicationName: 'OMISPHERE',
  // The canonical apex. A brand query that resolves to a redirect chain, or to two hosts serving
  // the same content, splits whatever authority the domain has earned between them.
  metadataBase: new URL(env.PUBLIC_BASE_URL),
  keywords: [
    'OMISPHERE', 'bot detection', 'coordinated inauthentic behaviour',
    'comment section analysis', 'engagement authenticity', 'astroturfing detection',
  ],
  openGraph: {
    type: 'website',
    siteName: 'OMISPHERE',
    title: 'OMISPHERE · Social Authenticity Intelligence',
    description:
      'Detect bots, bought engagement and AI-written replies in any comment section.',
    url: env.PUBLIC_BASE_URL,
  },
  twitter: {
    card: 'summary_large_image',
    title: 'OMISPHERE · Social Authenticity Intelligence',
    description:
      'Detect bots, bought engagement and AI-written replies in any comment section.',
  },
  // Indexable by default. This was `index: false, follow: false` site-wide, left over from the private
  // beta, which meant every page, including the marketing pages, told search engines to ignore it.
  // Any traffic spend against that captures nothing durable: no branded search, no organic entry, no
  // compounding content.
  //
  // Non-public surfaces opt OUT individually rather than the whole site opting in: the signed-in app
  // ((app)/layout.tsx), the auth screens, and the tokenised share route (/r/), which is
  // unlisted-link-shareable and must never appear in an index. See also app/robots.ts.
  robots: { index: true, follow: true },
};

export const viewport = {
  width: 'device-width',
  initialScale: 1,
  themeColor: '#010203',
  viewportFit: 'cover' as const,
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  // Nonce set by middleware for CSP; Next.js attaches it to its own inline scripts.
  const nonce = headers().get('x-nonce') ?? undefined;

  return (
    <html
      lang="en"
      className={`${inter.variable} ${jetbrainsMono.variable} ${archivo.variable}`}
    >
      {/* No external <link rel="stylesheet">. Fonts are self-hosted via next/font. */}
      <body className={`font-sans ${inter.className}`} data-csp-nonce={nonce || undefined}>
        {/* Inside <body> deliberately: schema.org JSON-LD is valid there and Next hoisting of a
            bare <script> from outside <body> is ambiguous enough to be worth not relying on. */}
        {/* Scripting off means the reveal animation never runs, and its resting state is
            opacity 0. Without this the page renders complete markup that a human cannot see.
            Inline style is allowed by the CSP (`style-src 'self' 'unsafe-inline'`), and a nonce
            cannot be used here because the browser evaluates <noscript> content by parsing it. */}
        <noscript>
          <style>{'.reveal-pending{opacity:1!important;transform:none!important}'}</style>
        </noscript>
        <StructuredData nonce={nonce} />
        {/* Clerk lives entirely on the client (see ClerkClientProvider) because this app runs no
            clerkMiddleware; nothing on the server ever calls Clerk's auth(). */}
        <ClerkClientProvider>{children}</ClerkClientProvider>
      </body>
    </html>
  );
}
