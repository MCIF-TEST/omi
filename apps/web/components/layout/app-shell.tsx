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
