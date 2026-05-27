import { type ReactNode } from 'react';
import { Sidebar } from './sidebar';
import { Topbar } from './topbar';
import { type User, type EngineStatus } from '@/lib/api';
import { apiServer } from '@/lib/api-server';

interface AppShellProps {
  user: User;
  children: ReactNode;
}

export async function AppShell({ user, children }: AppShellProps) {
  let engineStatus: EngineStatus | undefined;
  try {
    engineStatus = await apiServer<EngineStatus>('/v1/status');
  } catch {
    /* status is decorative; if it's down, the topbar just hides counters */
  }

  return (
    <div className="min-h-screen flex flex-col bg-bg-deep">
      <Topbar user={user} engineStatus={engineStatus} />
      {engineStatus?.storage_ephemeral && user.is_admin && (
        <div className="bg-danger/15 border-b border-danger/40 px-6 py-2 text-xs font-mono text-danger">
          ⚠ Database is ephemeral (SQLite). Every redeploy will wipe all user
          accounts and saved investigations — provision Postgres and set{' '}
          <code className="bg-bg/40 px-1 rounded-sm">OMI_DATABASE_URL</code> before going live.
        </div>
      )}
      {engineStatus && !engineStatus.youtube_configured && user.is_admin && (
        <div className="bg-warn/15 border-b border-warn/40 px-6 py-2 text-xs font-mono text-warn">
          ⚠ YouTube API key not configured. Scans will fail until{' '}
          <code className="bg-bg/40 px-1 rounded-sm">OMI_YOUTUBE_API_KEY</code>
          {' '}is set in the API environment.
        </div>
      )}
      <div className="flex-1 flex">
        <Sidebar />
        <main className="flex-1 min-w-0">
          <div className="max-w-[1440px] mx-auto px-6 py-8 animate-fade-up">
            {children}
          </div>
        </main>
      </div>
    </div>
  );
}
