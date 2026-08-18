'use client';

import { useCallback } from 'react';
import Link from 'next/link';
import { Bell } from 'lucide-react';
import { UserButton } from '@clerk/nextjs';
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
    <header className="sticky top-0 z-30 h-14 shrink-0 border-b border-border-1 bg-bg-sidebar px-3 md:px-5 flex items-center gap-2 md:gap-3 min-w-0">

      {/* Persistent feedback. Top-left, on every page, even deep inside an investigation. */}
      <FeedbackButton />

      {/* Brand. Phones have no sidebar, so the wordmark lives here. */}
      <Link href="/investigate" className="md:hidden tap shrink min-w-0 overflow-hidden" aria-label="OMISPHERE home">
        <Logo size="sm" />
      </Link>

      {/* Engine telemetry (desktop). A readout strip: label over figure, one
          framed group, hairline between the fields. These were two separate
          bordered pills, which made two related readings look like two
          unrelated controls, and put a rounded chip in the frame. */}
      {engineStatus && (
        <div className="hidden lg:flex items-stretch shrink-0 border border-border-1 bg-bg-elev rounded-sm divide-x divide-border-1">
          <span className="flex flex-col justify-center px-2.5 py-1">
            <span className="meta leading-none">Fingerprints</span>
            <span className="font-mono text-2xs tabular text-fg-dim leading-none mt-1">
              {engineStatus.fingerprints_stored.toLocaleString()}
            </span>
          </span>
          <span className="flex flex-col justify-center px-2.5 py-1">
            <span className="meta leading-none">Scans</span>
            <span className="font-mono text-2xs tabular text-fg-dim leading-none mt-1">
              {engineStatus.total_scans.toLocaleString()}
            </span>
          </span>
        </div>
      )}

      {/* Command line, the primary verb (search + jump).
          A prompt caret and a mono field, not a rounded search pill with a
          magnifier and an ellipsis. The two say different things about what
          this row is: one is a box you type a query into, the other is the
          line you drive the system from. */}
      <Link
        href="/search"
        className="group hidden md:flex items-center gap-2.5 flex-1 max-w-xl mx-auto h-9 px-3
                   rounded-sm border border-border-2 bg-bg-inset hover:border-accent/60
                   transition-colors"
        aria-label="Search and command"
      >
        <span className="font-mono text-sm text-accent-text leading-none select-none" aria-hidden>&gt;</span>
        <span className="flex-1 meta meta-hi truncate group-hover:text-fg-dim transition-colors">
          Search accounts, narratives, investigations
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
          className="relative hidden sm:inline-flex items-center justify-center w-9 h-9 rounded-sm border border-border-2 bg-bg-elev hover:border-border-hot hover:text-fg-dim text-fg-mute transition-colors"
          aria-label={`Alerts${unread > 0 ? ` (${unread} unread)` : ''}`}
        >
          <Bell size={15} />
          {unread > 0 && (
            // Square counter, seated on the corner. A round red pill on a square
            // control is the one consumer-notification shape in the frame.
            <span className="absolute -top-1.5 -right-1.5 min-w-[16px] h-4 px-1 rounded-[2px] bg-danger text-white text-[10px] leading-4 text-center font-mono tabular">
              {unread > 99 ? '99+' : unread}
            </span>
          )}
        </Link>

        {/* Credits. A labelled figure, not a lightning bolt beside a number.
            The bolt is a games-and-streaks icon and this is the balance that
            decides whether a scan runs; the label also makes the number
            self-explanatory to someone seeing the app for the first time.
            Colour still carries the warning. */}
        <span className="inline-flex items-center gap-1.5 shrink-0" title={`${credits} credits remaining`}>
          <span className="meta hidden sm:inline">Credits</span>
          <span className={cn('font-mono text-xs tabular', creditTone)}>{credits}</span>
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
