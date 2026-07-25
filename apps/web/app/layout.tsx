import type { Metadata } from 'next';
import { headers } from 'next/headers';
import { Inter, JetBrains_Mono, Space_Grotesk } from 'next/font/google';
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

const spaceGrotesk = Space_Grotesk({
  subsets: ['latin'],
  display: 'swap',
  variable: '--font-display-alt',
  weight: ['400', '500', '600', '700'],
});

export const metadata: Metadata = {
  title: 'OMISPHERE — Social Authenticity Intelligence',
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
      className={`${inter.variable} ${jetbrainsMono.variable} ${spaceGrotesk.variable}`}
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
