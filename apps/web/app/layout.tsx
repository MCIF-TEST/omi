import type { Metadata } from 'next';
import { headers } from 'next/headers';
import { Inter, JetBrains_Mono } from 'next/font/google';
import { ClerkClientProvider } from '@/components/shared/clerk-provider';
import { SITE_DESCRIPTION, SITE_KEYWORDS, SITE_NAME, SITE_TAGLINE, SITE_URL } from '@/lib/seo';
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

// Space Grotesk (the old `--font-display-alt` marketing voice) is no longer loaded: the pre-login
// page now uses the app's own `.display` (Inter) so both sides of the login boundary read as one
// product. `.display-alt` in globals.css still falls back to `var(--font-display)`, so any stray
// usage degrades to Inter instead of breaking, and no visitor downloads a font nothing renders.

export const metadata: Metadata = {
  // Lets every child page use a relative `openGraph.url` / `alternates.canonical` and still resolve to
  // an absolute URL, and is what makes Next auto-resolve the `opengraph-image.tsx` convention file into
  // a full `https://…` URL in the emitted OG/Twitter tags instead of a path a scraper can't fetch.
  metadataBase: new URL(SITE_URL),
  title: { default: `${SITE_NAME} · ${SITE_TAGLINE}`, template: `%s · ${SITE_NAME}` },
  description: SITE_DESCRIPTION,
  applicationName: SITE_NAME,
  // Meta keywords carry ~no ranking weight on their own — Google has ignored the tag for years — but
  // they cost nothing and document, in one place, exactly which queries this site is meant to answer.
  keywords: SITE_KEYWORDS,
  alternates: { canonical: '/' },
  openGraph: {
    type: 'website',
    url: '/',
    siteName: SITE_NAME,
    title: `${SITE_NAME} · ${SITE_TAGLINE}`,
    description: SITE_DESCRIPTION,
  },
  twitter: {
    card: 'summary_large_image',
    title: `${SITE_NAME} · ${SITE_TAGLINE}`,
    description: SITE_DESCRIPTION,
  },
  // Indexable by default. This was `index: false, follow: false` site-wide, left over from the private
  // beta — which meant every page, including the marketing pages, told search engines to ignore it.
  // Any traffic spend against that captures nothing durable: no branded search, no organic entry, no
  // compounding content.
  //
  // Non-public surfaces opt OUT individually rather than the whole site opting in: the signed-in app
  // ((app)/layout.tsx), the auth screens, and the tokenised share routes (/r/, /rc/), which are
  // unlisted-link-shareable and must never appear in an index. See also app/robots.ts.
  robots: { index: true, follow: true },
};

/**
 * Organization + WebSite JSON-LD, site-wide. This is what lets Google attach a knowledge-panel-style
 * identity (name, logo, description) to the brand itself rather than only ever ranking bare page titles,
 * and is a prerequisite for any sitelinks search box / rich brand result.
 */
function organizationJsonLd() {
  return {
    '@context': 'https://schema.org',
    '@graph': [
      {
        '@type': 'Organization',
        '@id': `${SITE_URL}/#organization`,
        name: SITE_NAME,
        url: SITE_URL,
        logo: `${SITE_URL}/opengraph-image`,
        description: SITE_DESCRIPTION,
      },
      {
        '@type': 'WebSite',
        '@id': `${SITE_URL}/#website`,
        url: SITE_URL,
        name: SITE_NAME,
        description: SITE_DESCRIPTION,
        publisher: { '@id': `${SITE_URL}/#organization` },
      },
    ],
  };
}

export const viewport = {
  width: 'device-width',
  initialScale: 1,
  themeColor: '#09111f',
  viewportFit: 'cover' as const,
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  // Nonce set by middleware for CSP; Next.js attaches it to its own inline scripts.
  const nonce = headers().get('x-nonce') ?? undefined;

  return (
    <html
      lang="en"
      className={`${inter.variable} ${jetbrainsMono.variable}`}
    >
      {/* No external <link rel="stylesheet"> — fonts are self-hosted via next/font. */}
      <body className={`font-sans ${inter.className}`} data-csp-nonce={nonce || undefined}>
        {/* CSP here is a nonce allowlist with no 'unsafe-inline' (see middleware.ts), so any inline
            script we add ourselves — Next's own flight scripts get this automatically — needs the same
            nonce or the browser silently drops it. */}
        <script
          type="application/ld+json"
          nonce={nonce}
          dangerouslySetInnerHTML={{ __html: JSON.stringify(organizationJsonLd()) }}
        />
        {/* Clerk lives entirely on the client (see ClerkClientProvider) because this app runs no
            clerkMiddleware; nothing on the server ever calls Clerk's auth(). */}
        <ClerkClientProvider>{children}</ClerkClientProvider>
      </body>
    </html>
  );
}
