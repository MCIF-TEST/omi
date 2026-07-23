import type { Metadata } from 'next';
import { ClerkProvider } from '@clerk/nextjs';
import './globals.css';

// Clerk's hosted UI, themed to the OmiSphere palette (deep-blue identity, navy-graphite surfaces)
// so sign-in/up feels native. Only the PUBLISHABLE key reaches the browser here — the secret key is
// read server-side by Clerk's middleware/handlers and never ships to the client.
const clerkAppearance = {
  variables: {
    colorPrimary: '#3B82F6',
    colorBackground: '#131E31',
    colorInputBackground: '#0F1828',
    colorText: '#F8FAFC',
    colorTextSecondary: '#94A3B8',
    colorInputText: '#F8FAFC',
    colorDanger: '#EF4444',
    colorSuccess: '#22C55E',
    borderRadius: '0.625rem',
    fontFamily: 'Inter, ui-sans-serif, system-ui, sans-serif',
  },
  elements: {
    // The card lives inside our own auth shell, so drop Clerk's chrome and let the shell frame it.
    card: 'bg-transparent shadow-none border-0',
    rootBox: 'w-full',
    headerTitle: 'hidden',        // our page supplies the heading
    headerSubtitle: 'hidden',
    // Primary action reads as the app's blue lamp button.
    formButtonPrimary:
      'bg-[#3B82F6] hover:bg-[#2d6edf] text-white font-semibold normal-case shadow-none',
    // Social/OAuth buttons: quiet bordered surfaces that light up on hover.
    socialButtonsBlockButton:
      'border border-[#31425e] bg-[#0f1828] hover:bg-[#18263d] hover:border-[#3c4f70] text-[#f8fafc] normal-case',
    socialButtonsBlockButtonText: 'text-[#f8fafc] font-medium',
    dividerLine: 'bg-[#24344f]',
    dividerText: 'text-[#64748b] font-mono text-xs tracking-wider uppercase',
    formFieldLabel: 'text-[#cbd5e1]',
    formFieldInput:
      'bg-[#0f1828] border border-[#24344f] focus:border-[#3B82F6] text-[#f8fafc]',
    footer: 'hidden',             // we render our own switch-mode link
    footerAction: 'hidden',
    identityPreviewEditButton: 'text-[#5b9dff]',
    formResendCodeLink: 'text-[#5b9dff]',
    otpCodeFieldInput: 'bg-[#0f1828] border border-[#24344f] text-[#f8fafc]',
  },
};

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
        {/* Evidence voice — JetBrains Mono (ids, numbers, handles, raw data).
            Loaded globally from the root layout, so the next/font page-scoping
            warning doesn't apply. */}
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
        {/* eslint-disable-next-line @next/next/no-page-custom-font */}
        <link
          rel="stylesheet"
          href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;600&display=swap"
        />
      </head>
      <body className="font-sans">
        <ClerkGate>{children}</ClerkGate>
      </body>
    </html>
  );
}

// Only mount ClerkProvider when a publishable key is configured. Clerk throws hard if the key is
// missing, which would fail the whole static build (marketing pages included) whenever the env var
// isn't set at build time. Gating it keeps the build resilient — with the key present (the normal
// case) Clerk works exactly as before; without it, the app still builds and static pages render.
function ClerkGate({ children }: { children: React.ReactNode }) {
  const pk = process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY;
  if (!pk) return <>{children}</>;
  return (
    <ClerkProvider publishableKey={pk} appearance={clerkAppearance}>
      {children}
    </ClerkProvider>
  );
}
