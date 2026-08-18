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
// Clerk renders the sign-in and sign-up forms from its own bundle, so it cannot see our CSS
// variables and every colour has to be handed to it literally. That makes this file the one place
// a palette change silently does not reach: after the ramp moved to near-black, these values still
// painted the form in the old navy (#131E31 panels, #0F1828 inputs) on top of a #010203 page, on
// the two screens the whole funnel ends at.
//
// Kept in sync BY HAND with :root in globals.css. If you change the ramp there, change it here.
const clerkAppearance = {
  variables: {
    colorPrimary: '#3B82F6',        // --accent
    colorBackground: '#0A0D12',     // --bg-elev
    colorInputBackground: '#030406', // --bg-inset
    colorText: '#FFFFFF',           // --text
    colorTextSecondary: '#AAB2BC',  // --text-mute
    colorInputText: '#FFFFFF',
    colorDanger: '#EF4444',
    colorSuccess: '#22C55E',
    borderRadius: '3px',            // matches the tightened Tailwind radius scale
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
      'border border-[#343c4b] bg-[#06080b] hover:bg-[#10141b] hover:border-[#4b5566] text-white normal-case',
    socialButtonsBlockButtonText: 'text-white font-medium',
    dividerLine: 'bg-[#232935]',
    dividerText: 'meta',
    // The mono label voice, the same one `Label` and every panel header uses.
    // Clerk renders into our DOM, so our stylesheet reaches these elements even
    // though Clerk's own bundle cannot see our CSS variables. The form was the
    // one place in the funnel whose field labels read as ordinary sans copy.
    formFieldLabel: 'meta meta-on',
    formFieldInput: 'bg-[#030406] border border-[#232935] focus:border-[#3B82F6] text-white',
    footer: 'hidden',
    footerAction: 'hidden',
    identityPreviewEditButton: 'text-[#5b9dff]',
    formResendCodeLink: 'text-[#5b9dff]',
    otpCodeFieldInput: 'bg-[#030406] border border-[#232935] text-white',
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
