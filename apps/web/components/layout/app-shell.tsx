import { type ReactNode } from 'react';
import { Sidebar } from './sidebar';
import { Topbar } from './topbar';
import { MobileNav } from './mobile-nav';
import { ServiceDegradedBanner } from './service-health';
import { type User, type EngineStatus, type InvestigationsListResponse } from '@/lib/api';
import { apiServer } from '@/lib/api-server';

interface AppShellProps {
  user: User;
  children: ReactNode;
}

export async function AppShell({ user, children }: AppShellProps) {
  let engineStatus: EngineStatus | undefined;
  // Pre-activation focus: until the user has run a first investigation, the
  // nav hides the secondary analysis/ops surfaces so the path to the value
  // moment (featured campaign → first scan) has no detours. Fails open: if
  // the probe errors, show the full nav rather than over-hiding.
  let isNewUser = false;
  try {
    const [status, inv] = await Promise.all([
      apiServer<EngineStatus>('/v1/status'),
      apiServer<InvestigationsListResponse>('/v1/investigations?limit=1').catch(
        () => ({ investigations: [{}] } as unknown as InvestigationsListResponse),
      ),
    ]);
    engineStatus = status;
    isNewUser = (inv.investigations ?? []).length === 0;
  } catch {
    /* status is decorative; if it's down, the topbar just hides counters */
  }

  return (
    <div className="min-h-screen flex flex-col bg-bg-deep grain relative">
      <Topbar user={user} engineStatus={engineStatus} />
      {/* User-visible banner — everyone sees it, no env-var jargon. */}
      {engineStatus && (
        <ServiceDegradedBanner youtubeConfigured={engineStatus.youtube_configured} />
      )}
      {/* Admin diagnostics — env-var names, action items. */}
      {engineStatus?.storage_ephemeral && user.is_admin && (
        <div className="bg-danger/15 border-b border-danger/40 px-4 md:px-6 py-2 text-xs font-mono text-danger">
          ⚠ Admin: database is ephemeral (SQLite). Every redeploy wipes all user
          accounts and saved investigations — provision Postgres and set{' '}
          <code className="bg-bg/40 px-1 rounded-sm">OMI_DATABASE_URL</code> before going live.
        </div>
      )}
      {engineStatus && !engineStatus.youtube_configured && user.is_admin && (
        <div className="bg-warn/15 border-b border-warn/40 px-4 md:px-6 py-2 text-xs font-mono text-warn">
          ⚠ Admin: YouTube API key not configured. Set{' '}
          <code className="bg-bg/40 px-1 rounded-sm">OMI_YOUTUBE_API_KEY</code>
          {' '}in the API service env to restore scanning.
        </div>
      )}
      <div className="flex-1 flex relative z-10">
        <Sidebar isNewUser={isNewUser} />
        <main className="flex-1 min-w-0">
          {/* Bottom padding clears the mobile tab bar (+ home-indicator inset). */}
          <div className="max-w-[1440px] mx-auto px-4 py-5 md:px-6 md:py-8 pb-[calc(5.5rem+env(safe-area-inset-bottom))] md:pb-8 animate-fade-up">
            {children}
          </div>
        </main>
      </div>

      {/* Thumb-reachable primary navigation — phones only. */}
      <MobileNav email={user.email} isNewUser={isNewUser} />
    </div>
  );
}
