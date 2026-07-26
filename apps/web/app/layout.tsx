import type { Metadata } from 'next';
import { headers } from 'next/headers';
import { Inter, JetBrains_Mono } from 'next/font/google';
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

// Space Grotesk (the old `--font-display-alt` marketing voice) is no longer loaded: the pre-login
// page now uses the app's own `.display` (Inter) so both sides of the login boundary read as one
// product. `.display-alt` in globals.css still falls back to `var(--font-display)`, so any stray
// usage degrades to Inter instead of breaking, and no visitor downloads a font nothing renders.

export const metadata: Metadata = {
  title: 'OMISPHERE · Social Authenticity Intelligence',
  description:
    'Probabilistic detection of bots, AI engagement, coordinated influence campaigns, and synthetic virality. Powered by the omi detection engine.',
  applicationName: 'OMISPHERE',
  robots: { index: false, follow: false }, // private beta
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
      className={`${inter.variable} ${jetbrainsMono.variable}`}
    >
      {/* No external <link rel="stylesheet"> — fonts are self-hosted via next/font. */}
      <body className={`font-sans ${inter.className}`} data-csp-nonce={nonce || undefined}>
        {/* Clerk lives entirely on the client (see ClerkClientProvider) because this app runs no
            clerkMiddleware; nothing on the server ever calls Clerk's auth(). */}
        <ClerkClientProvider>{children}</ClerkClientProvider>
      </body>
    </html>
  );
}
