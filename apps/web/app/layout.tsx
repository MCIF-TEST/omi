import type { Metadata } from 'next';
import { ClerkClientProvider } from '@/components/shared/clerk-provider';
import './globals.css';

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
  // Extend under the notch / home indicator so our safe-area padding can
  // place the tab bar flush against the device edge.
  viewportFit: 'cover' as const,
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <head>
        {/* Interface + display — Inter (variable, optical). One typeface; the
            scale carries the hierarchy. */}
        <link rel="preconnect" href="https://rsms.me/" />
        <link rel="stylesheet" href="https://rsms.me/inter/inter.css" />
        {/* Evidence voice — JetBrains Mono (ids, numbers, handles, raw data). Display voice on the
            marketing surface — Space Grotesk (a technical grotesk with real character, used via the
            .display-alt class). Both loaded globally here so the next/font page-scoping warning
            doesn't apply. */}
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
        {/* eslint-disable-next-line @next/next/no-page-custom-font */}
        <link
          rel="stylesheet"
          href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;600&family=Space+Grotesk:wght@400;500;600;700&display=swap"
        />
      </head>
      <body className="font-sans">
        {/* Clerk lives entirely on the client (see ClerkClientProvider) because this app runs no
            clerkMiddleware; nothing on the server ever calls Clerk's auth(). */}
        <ClerkClientProvider>{children}</ClerkClientProvider>
      </body>
    </html>
  );
}
