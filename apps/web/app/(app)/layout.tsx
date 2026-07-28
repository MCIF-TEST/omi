import { redirect } from 'next/navigation';
import { getCurrentUser } from '@/lib/auth';
import { AppShell } from '@/components/layout/app-shell';
import { CommandPalette } from '@/components/shared/command-palette';
import { AuthBridgeReset } from '@/components/shared/auth-bridge';

// Private surface (signed-in app): never indexable. The root layout now opts the site IN to indexing (it was
// site-wide noindex, left from the private beta), so anything non-public must opt back OUT here.
export const metadata = { robots: { index: false, follow: false } };

export default async function AppLayout({ children }: { children: React.ReactNode }) {
  const user = await getCurrentUser();
  if (!user) redirect('/sign-in');
  return (
    <>
      {/* Reaching here means the SERVER verified the session. Clear any auth-recovery flag so a later
          unrelated bounce starts fresh instead of jumping to the manual "stuck" controls. */}
      <AuthBridgeReset />
      <AppShell user={user}>{children}</AppShell>
      <CommandPalette />
    </>
  );
}
