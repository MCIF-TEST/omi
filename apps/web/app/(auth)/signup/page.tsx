import { redirect } from 'next/navigation';

// Auth moved to Clerk. Old /signup links now land on the Clerk sign-up page.
export default function SignupRedirect() {
  redirect('/sign-up');
}
