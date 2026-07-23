import { redirect } from 'next/navigation';

// Auth moved to Clerk. Old /login links now land on the Clerk sign-in page.
export default function LoginRedirect() {
  redirect('/sign-in');
}
