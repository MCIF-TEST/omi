import { redirect } from 'next/navigation';
import { getCurrentUser } from '@/lib/auth';
import { LandingPage } from './landing-page';

export const dynamic = 'force-dynamic';

export default async function Root() {
  const user = await getCurrentUser();
  if (user) redirect('/dashboard');
  return <LandingPage />;
}
