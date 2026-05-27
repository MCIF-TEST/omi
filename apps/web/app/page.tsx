import { redirect } from 'next/navigation';
import { getCurrentUser } from '@/lib/auth';

export default async function Root() {
  const user = await getCurrentUser();
  redirect(user ? '/dashboard' : '/login');
}
