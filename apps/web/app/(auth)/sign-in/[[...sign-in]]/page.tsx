import { SignIn } from '@clerk/nextjs';

export const metadata = { title: 'Sign in — OMISPHERE' };

// Clerk-hosted sign-in (Google, Apple, email — whatever is enabled in the Clerk dashboard),
// dropped into the app's centered auth shell. Redirects into the app on success.
export default function SignInPage() {
  return (
    <div className="flex justify-center">
      <SignIn
        signUpUrl="/sign-up"
        fallbackRedirectUrl="/dashboard"
        appearance={{ elements: { rootBox: 'w-full', card: 'shadow-none bg-transparent' } }}
      />
    </div>
  );
}
