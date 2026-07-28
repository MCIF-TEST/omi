'use client';

import { ClerkProvider } from '@clerk/nextjs';

// Client-only Clerk provider.
//
// WHY a client boundary: this app runs NO clerkMiddleware (it can't get the secret into the Edge
// runtime. See middleware.ts). Clerk's App Router integration assumes middleware, and its
// server-side pieces (auth(), the server ClerkProvider's dynamic state, <SignedIn>/<SignedOut>) throw
// "clerkMiddleware() was not detected" when it's missing. Rendering ClerkProvider inside a client
// component keeps ALL of Clerk on the client: the provider, useAuth(), <SignIn>/<SignUp>, and
// <UserButton> work from the browser Clerk instance, and nothing on the server ever calls Clerk. The
// server authenticates independently by forwarding the __session cookie to FastAPI (JWKS-verified),
// so it never needs Clerk's server helpers.
//
// The publishable key is a NEXT_PUBLIC_ var (inlined into the client bundle at build). When it's
// absent, render children ungated so the app still works.
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
    card: 'bg-transparent shadow-none border-0',
    rootBox: 'w-full',
    headerTitle: 'hidden',
    headerSubtitle: 'hidden',
    formButtonPrimary:
      'bg-[#3B82F6] hover:bg-[#2d6edf] text-white font-semibold normal-case shadow-none',
    socialButtonsBlockButton:
      'border border-[#31425e] bg-[#0f1828] hover:bg-[#18263d] hover:border-[#3c4f70] text-[#f8fafc] normal-case',
    socialButtonsBlockButtonText: 'text-[#f8fafc] font-medium',
    dividerLine: 'bg-[#24344f]',
    dividerText: 'text-[#64748b] font-mono text-xs tracking-wider uppercase',
    formFieldLabel: 'text-[#cbd5e1]',
    formFieldInput: 'bg-[#0f1828] border border-[#24344f] focus:border-[#3B82F6] text-[#f8fafc]',
    footer: 'hidden',
    footerAction: 'hidden',
    identityPreviewEditButton: 'text-[#5b9dff]',
    formResendCodeLink: 'text-[#5b9dff]',
    otpCodeFieldInput: 'bg-[#0f1828] border border-[#24344f] text-[#f8fafc]',
  },
};

export function ClerkClientProvider({ children }: { children: React.ReactNode }) {
  const pk = process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY;
  if (!pk) return <>{children}</>;
  return (
    <ClerkProvider publishableKey={pk} appearance={clerkAppearance}>
      {children}
    </ClerkProvider>
  );
}
