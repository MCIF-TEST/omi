import type { Metadata } from 'next';
import { headers } from 'next/headers';
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

export const metadata: Metadata = {
  title: 'OMISPHERE · Social Authenticity Intelligence',
  description:
    'Probabilistic detection of bots, bought engagement, and AI-written replies in any comment section. Powered by the omi detection engine.',
  applicationName: 'OMISPHERE',
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
  themeColor: '#09111f',
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
        {/* Clerk lives entirely on the client (see ClerkClientProvider) because this app runs no
            clerkMiddleware; nothing on the server ever calls Clerk's auth(). */}
        <ClerkClientProvider>{children}</ClerkClientProvider>
      </body>
    </html>
  );
}
