import { redirect } from 'next/navigation';
import { getCurrentUser } from '@/lib/auth';
import { AppShell } from '@/components/layout/app-shell';
import { CommandPalette } from '@/components/shared/command-palette';
import { AuthBridgeReset } from '@/components/shared/auth-bridge';

export default async function AppLayout({ children }: { children: React.ReactNode }) {
  const user = await getCurrentUser();
  if (!user) redirect('/sign-in');
  return (
    <>
      {/* Reaching here means the SERVER verified the session — clear any auth-recovery flag so a later
          unrelated bounce starts fresh instead of jumping to the manual "stuck" controls. */}
      <AuthBridgeReset />
      <AppShell user={user}>{children}</AppShell>
      <CommandPalette />
    </>
  );
}
