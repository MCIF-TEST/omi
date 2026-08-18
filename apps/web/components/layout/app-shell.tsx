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
  // moment (landing page → first scan) has no detours. Fails open: if
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
      {/* User-visible banner. Everyone sees it, no env-var jargon. */}
      {engineStatus && (
        <ServiceDegradedBanner youtubeConfigured={engineStatus.youtube_configured} />
      )}
      {/* Admin diagnostics. Env-var names, action items. */}
      {engineStatus?.storage_ephemeral && user.is_admin && (
        // A lamp and a labelled severity, not an emoji. An operator banner is
        // the one place in the product that has to read as a machine speaking.
        <div className="bg-danger/15 border-b border-danger/40 px-4 md:px-6 py-2 text-xs font-mono text-danger flex items-start gap-2.5">
          <span className="led led-fail mt-1 shrink-0" />
          <span className="meta text-danger shrink-0 mt-0.5">Fault · Admin</span>
          <span className="min-w-0">
            Database is ephemeral (SQLite). Every redeploy wipes all user accounts and saved
            investigations. Provision Postgres and set{' '}
            <code className="bg-bg/40 px-1 rounded-sm">OMI_DATABASE_URL</code> before going live.
          </span>
        </div>
      )}
      {engineStatus && !engineStatus.youtube_configured && user.is_admin && (
        <div className="bg-warn/15 border-b border-warn/40 px-4 md:px-6 py-2 text-xs font-mono text-warn flex items-start gap-2.5">
          <span className="led led-warn mt-1 shrink-0" />
          <span className="meta text-warn shrink-0 mt-0.5">Degraded · Admin</span>
          <span className="min-w-0">
            YouTube API key not configured. Set{' '}
            <code className="bg-bg/40 px-1 rounded-sm">OMI_YOUTUBE_API_KEY</code>
            {' '}in the API service env to restore scanning.
          </span>
        </div>
      )}
      <div className="flex-1 flex relative z-10">
        <Sidebar isNewUser={isNewUser} isAdmin={user.is_admin} />
        {/* rule-grid: the same 72px measurement field the public pages sit on,
            at ~1.6% opacity. Panels on a measured ground read as instruments on
            a bench; panels on a void read as cards in a feed. It is far too
            faint to be decoration and that is the point. */}
        <main className="flex-1 min-w-0 rule-grid">
          {/* Bottom padding clears the mobile tab bar (+ home-indicator inset). */}
          <div className="max-w-[1440px] mx-auto px-4 py-5 md:px-6 md:py-8 pb-[calc(5.5rem+env(safe-area-inset-bottom))] md:pb-8 animate-fade-up">
            {children}
          </div>
        </main>
      </div>

      {/* Thumb-reachable primary navigation. Phones only. */}
      <MobileNav email={user.email} isNewUser={isNewUser} isAdmin={user.is_admin} />
    </div>
  );
}
