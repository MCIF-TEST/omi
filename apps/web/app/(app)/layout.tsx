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

  // PRE-LAUNCH LOCKDOWN. Everybody who is not an admin goes to the waitlist.
  //
  // `lockdown` comes from the API on the user object rather than from a NEXT_PUBLIC_ env var here,
  // so there is exactly one switch. Two copies would eventually disagree, and both directions are
  // bad: showing the product to somebody the API then refuses, or hiding it from somebody allowed
  // in.
  //
  // This redirect is the COURTESY, not the control. The API refuses the same person on every
  // product route (app/core/lockdown.py), because a signed-in non-admin can call the scan endpoint
  // directly with the cookie their browser already holds and spend real upstream money doing it.
  if (user.lockdown && !user.is_admin) redirect('/coming-soon');
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
