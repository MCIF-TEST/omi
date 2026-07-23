import { SignUp } from '@clerk/nextjs';

export const metadata = { title: 'Create account — OMISPHERE' };

// Clerk-hosted sign-up (Google, Apple, email — whatever is enabled in the Clerk dashboard),
// dropped into the app's centered auth shell. Redirects into the app on success.
export default function SignUpPage() {
  return (
    <div className="flex justify-center">
      <SignUp
        signInUrl="/sign-in"
        fallbackRedirectUrl="/dashboard"
        appearance={{ elements: { rootBox: 'w-full', card: 'shadow-none bg-transparent' } }}
      />
    </div>
  );
}
