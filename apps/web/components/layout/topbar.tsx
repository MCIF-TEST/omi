'use client';

import { useCallback } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { Bell, LogOut, Search, Zap } from 'lucide-react';
import { Logo } from '@/components/shared/logo';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { apiClient, type AlertsResponse, type User } from '@/lib/api';
import { usePolling } from '@/lib/use-polling';
import { ServiceHealthPill } from './service-health';

interface TopbarProps {
  user: User;
  engineStatus?: {
    fingerprints_stored: number;
    total_scans: number;
    youtube_configured: boolean;
    storage_ephemeral?: boolean;
    youtube_quota_used_today?: number;
    youtube_quota_daily_limit?: number;
  };
}

export function Topbar({ user, engineStatus }: TopbarProps) {
  const router = useRouter();
  const credits = user.credits_remaining;
  const creditTone =
    credits === 0 ? 'danger' : credits <= 3 ? 'warn' : 'accent';

  const onLogout = async () => {
    try {
      await apiClient('/v1/auth/logout', { method: 'POST' });
    } catch { /* ignore */ }
    router.refresh();
    router.push('/login');
  };

  // Poll the unread alert count every 60s for the bell badge.
  const alerts = usePolling<AlertsResponse>(
    useCallback(() => apiClient<AlertsResponse>('/v1/monitoring/alerts?unread=true&limit=1'), []),
    60_000,
  );
  const unread = alerts.data?.unread_count ?? 0;

  return (
    <header className="h-14 shrink-0 border-b border-border-1 bg-bg/80 backdrop-blur supports-[backdrop-filter]:bg-bg/60 px-6 flex items-center justify-between gap-6">
      <div className="flex items-center gap-6">
        <Logo />
        <div className="hidden lg:flex items-center gap-3 font-mono text-2xs text-fg-mute tracking-wider uppercase">
          {engineStatus && (
            <>
              <span>FP <span className="text-fg">{engineStatus.fingerprints_stored}</span></span>
              <span>·</span>
              <span>Scans <span className="text-fg">{engineStatus.total_scans}</span></span>
            </>
          )}
        </div>
      </div>

      <div className="flex items-center gap-3">
        {engineStatus && (
          <ServiceHealthPill
            youtubeConfigured={engineStatus.youtube_configured}
            storageEphemeral={Boolean(engineStatus.storage_ephemeral)}
            isAdmin={user.is_admin}
            quotaUsedToday={engineStatus.youtube_quota_used_today}
            quotaDailyLimit={engineStatus.youtube_quota_daily_limit}
          />
        )}
        <Link
          href="/search"
          className="hidden md:inline-flex items-center gap-2 px-2.5 h-7 border border-border-2 rounded-sm font-mono text-2xs tracking-wider uppercase text-fg-mute hover:text-fg-dim hover:border-border-hot transition-colors"
          aria-label="Search accounts"
        >
          <span>Search</span>
          <Search size={11} className="text-fg-mute" />
        </Link>
        <Link
          href="/monitoring"
          className="relative inline-flex items-center justify-center w-8 h-8 rounded-sm border border-border-2 hover:border-border-hot text-fg-dim hover:text-fg transition-colors"
          aria-label={`Alerts (${unread} unread)`}
        >
          <Bell size={14} />
          {unread > 0 && (
            <span className="absolute -top-1.5 -right-1.5 min-w-[16px] h-4 px-1 rounded-full bg-danger text-white text-[10px] leading-4 text-center font-mono">
              {unread > 99 ? '99+' : unread}
            </span>
          )}
        </Link>
        <Badge variant={creditTone}>
          <Zap size={11} />
          {credits} credit{credits === 1 ? '' : 's'}
        </Badge>
        <div className="hidden sm:block font-mono text-2xs text-fg-dim">{user.email}</div>
        <Button variant="ghost" size="sm" onClick={onLogout} aria-label="Log out">
          <LogOut size={14} />
          Logout
        </Button>
      </div>
    </header>
  );
}
