'use client';

import { useCallback } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { Bell, LogOut, Search, Zap } from 'lucide-react';
import { cn } from '@/lib/cn';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Logo } from '@/components/shared/logo';
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

  const alerts = usePolling<AlertsResponse>(
    useCallback(() => apiClient<AlertsResponse>('/v1/monitoring/alerts?unread=true&limit=1'), []),
    60_000,
  );
  const unread = alerts.data?.unread_count ?? 0;

  return (
    <header className="sticky top-0 z-30 h-14 shrink-0 border-b border-border-1 bg-bg/80 backdrop-blur-md supports-[backdrop-filter]:bg-bg/60 px-4 md:px-5 flex items-center justify-between gap-4">

      {/* Brand — phones have no sidebar, so the wordmark lives here. */}
      <Link href="/dashboard" className="md:hidden tap" aria-label="OMISPHERE home">
        <Logo size="sm" />
      </Link>

      {/* Left: engine stats (desktop) */}
      <div className="hidden lg:flex items-center gap-3 font-mono text-2xs text-fg-mute tracking-wider">
        {engineStatus && (
          <>
            <span className="flex items-center gap-1.5">
              <span className="w-1 h-1 rounded-full bg-tier-low" />
              <span>FP <span className="text-fg-dim">{engineStatus.fingerprints_stored.toLocaleString()}</span></span>
            </span>
            <span className="text-border-2">·</span>
            <span>Scans <span className="text-fg-dim">{engineStatus.total_scans.toLocaleString()}</span></span>
          </>
        )}
      </div>

      {/* Right: actions */}
      <div className="flex items-center gap-2 ml-auto">
        {engineStatus && (
          <ServiceHealthPill
            youtubeConfigured={engineStatus.youtube_configured}
            storageEphemeral={Boolean(engineStatus.storage_ephemeral)}
            isAdmin={user.is_admin}
            quotaUsedToday={engineStatus.youtube_quota_used_today}
            quotaDailyLimit={engineStatus.youtube_quota_daily_limit}
          />
        )}

        {/* Search */}
        <Link
          href="/search"
          className="hidden md:inline-flex items-center gap-2 h-8 px-3 border border-border-2 rounded-sm font-mono text-2xs tracking-wider text-fg-mute hover:text-fg-dim hover:border-border-hot transition-colors"
          aria-label="Search accounts"
        >
          <Search size={11} />
          <span>Search</span>
          <span className="text-fg-faint hidden lg:block">⌘K</span>
        </Link>

        {/* Alerts bell */}
        <Link
          href="/monitoring"
          className="relative inline-flex items-center justify-center w-8 h-8 rounded-sm border border-border-2 hover:border-border-hot text-fg-mute hover:text-fg-dim transition-colors"
          aria-label={`Alerts${unread > 0 ? ` (${unread} unread)` : ''}`}
        >
          <Bell size={14} />
          {unread > 0 && (
            <span className="absolute -top-1.5 -right-1.5 min-w-[16px] h-4 px-1 rounded-full bg-danger text-white text-[10px] leading-4 text-center font-mono">
              {unread > 99 ? '99+' : unread}
            </span>
          )}
        </Link>

        {/* Credit badge */}
        <Badge variant={creditTone}>
          <Zap size={10} />
          {credits}
        </Badge>

        {/* Email */}
        <span className="hidden lg:block font-mono text-2xs text-fg-mute truncate max-w-[160px]">
          {user.email}
        </span>

        {/* Logout */}
        <Button variant="ghost" size="sm" onClick={onLogout} aria-label="Log out" className="gap-1.5">
          <LogOut size={13} />
          <span className="hidden sm:block">Out</span>
        </Button>
      </div>
    </header>
  );
}
