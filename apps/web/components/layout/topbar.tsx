'use client';

import { useCallback } from 'react';
import Link from 'next/link';
import { Bell, Search, Zap } from 'lucide-react';
import { UserButton } from '@clerk/nextjs';
import { Button } from '@/components/ui/button';
import { Logo } from '@/components/shared/logo';
import { FeedbackButton } from '@/components/shared/feedback-button';
import { apiClient, type AlertsResponse, type User } from '@/lib/api';
import { cn } from '@/lib/cn';
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
  const credits = user.credits_remaining;
  // Colour still carries the warning (empty / nearly empty / fine); the chip around it does not.
  const creditTone =
    credits === 0 ? 'text-danger' : credits <= 3 ? 'text-warn' : 'text-accent-text';

  const alerts = usePolling<AlertsResponse>(
    useCallback(() => apiClient<AlertsResponse>('/v1/monitoring/alerts?unread=true&limit=1'), []),
    60_000,
  );
  const unread = alerts.data?.unread_count ?? 0;

  return (
    // min-w-0 + gap-2 on phones: this row holds six things, and without a floor on how far it can
    // shrink the last of them (the account button) is simply pushed off the right edge of a 390px
    // screen. Reachable only by panning the page sideways.
    <header className="sticky top-0 z-30 h-14 shrink-0 border-b border-border-1 glass px-3 md:px-5 flex items-center gap-2 md:gap-3 min-w-0">

      {/* Persistent feedback. Top-left, on every page, even deep inside an investigation. */}
      <FeedbackButton />

      {/* Brand. Phones have no sidebar, so the wordmark lives here. */}
      <Link href="/investigate" className="md:hidden tap shrink min-w-0 overflow-hidden" aria-label="OMISPHERE home">
        <Logo size="sm" />
      </Link>

      {/* Engine telemetry (desktop) */}
      <div className="hidden lg:flex items-center gap-2.5 font-mono text-2xs text-fg-mute tracking-wider shrink-0">
        {engineStatus && (
          <>
            <span className="inline-flex items-center gap-1.5 h-7 px-2.5 rounded-md border border-border-1 bg-bg-elev/60">
              <span className="w-1.5 h-1.5 rounded-full bg-tier-low" />
              <span>FP</span>
              <span className="text-fg-dim tabular">{engineStatus.fingerprints_stored.toLocaleString()}</span>
            </span>
            <span className="inline-flex items-center gap-1.5 h-7 px-2.5 rounded-md border border-border-1 bg-bg-elev/60">
              <span>SCANS</span>
              <span className="text-fg-dim tabular">{engineStatus.total_scans.toLocaleString()}</span>
            </span>
          </>
        )}
      </div>

      {/* Command bar, the primary verb (search + jump) */}
      <Link
        href="/search"
        className="group hidden md:flex items-center gap-2.5 flex-1 max-w-xl mx-auto h-9 px-3
                   rounded-lg border border-border-2 bg-bg-elev/70 hover:border-border-hot
                   hover:bg-bg-elev transition-colors"
        aria-label="Search and command"
      >
        <Search size={14} className="text-fg-mute group-hover:text-fg-dim transition-colors" />
        <span className="flex-1 text-sm text-fg-mute truncate">
          Search accounts & narratives…
        </span>
        <span className="kbd">⌘K</span>
      </Link>

      {/* Right cluster */}
      <div className="flex items-center gap-1.5 md:gap-2 ml-auto md:ml-0 shrink-0">
        {/* Service health is diagnostic, and phones already carry a full-width degraded banner
            underneath this bar, so it earns its space on tablets up, not on a 390px row. */}
        {engineStatus && (
          <span className="hidden sm:inline-flex">
            <ServiceHealthPill
              youtubeConfigured={engineStatus.youtube_configured}
              storageEphemeral={Boolean(engineStatus.storage_ephemeral)}
              isAdmin={user.is_admin}
              quotaUsedToday={engineStatus.youtube_quota_used_today}
              quotaDailyLimit={engineStatus.youtube_quota_daily_limit}
            />
          </span>
        )}

        {/* Alerts. Phones reach alerts from the tab bar, so this duplicate is tablet-up. */}
        <Link
          href="/monitoring"
          className="relative hidden sm:inline-flex items-center justify-center w-9 h-9 rounded-lg border border-border-2 bg-bg-elev/60 hover:border-border-hot hover:text-fg-dim text-fg-mute transition-colors"
          aria-label={`Alerts${unread > 0 ? ` (${unread} unread)` : ''}`}
        >
          <Bell size={15} />
          {unread > 0 && (
            <span className="absolute -top-1.5 -right-1.5 min-w-[16px] h-4 px-1 rounded-full bg-danger text-white text-[10px] leading-4 text-center font-mono tabular">
              {unread > 99 ? '99+' : unread}
            </span>
          )}
        </Link>

        {/* Credits */}
        <span className={cn('inline-flex items-center gap-1 font-mono text-2xs tabular', creditTone)}>
          <Zap size={10} />
          {credits}
        </span>

        {/* Email */}
        <span className="hidden xl:block font-mono text-2xs text-fg-mute truncate max-w-[150px]">
          {user.email}
        </span>

        {/* Account. Clerk manages the session (profile, sign out, connected accounts). */}
        <UserButton
          // Route sign-out through /signed-out so the legacy httpOnly omi_session cookie is cleared
          // too (Clerk only clears its own session). Otherwise a legacy-cookie user stays logged in.
          afterSignOutUrl="/signed-out"
          appearance={{ elements: { avatarBox: 'w-8 h-8' } }}
        />
      </div>
    </header>
  );
}
