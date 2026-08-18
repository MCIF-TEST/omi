'use client';

import { useState } from 'react';
import Link from 'next/link';
import { X, ShieldAlert } from 'lucide-react';

interface Props {
  youtubeConfigured: boolean;
  storageEphemeral: boolean;
  isAdmin: boolean;
  quotaUsedToday?: number;
  quotaDailyLimit?: number;
}

/**
 * Compact service-health pill in the topbar.
 *
 * Green when everything is fine; yellow when one capability is degraded;
 * red when scanning won't work at all. Clicking opens a small popover
 * with the human-readable status. Admins get diagnostic detail, regular
 * users get a friendly "scanning is temporarily unavailable" message.
 */
export function ServiceHealthPill({
  youtubeConfigured,
  storageEphemeral,
  isAdmin,
  quotaUsedToday,
  quotaDailyLimit,
}: Props) {
  const [open, setOpen] = useState(false);

  const issues: { severity: 'high' | 'medium'; user: string; admin: string }[] = [];

  if (!youtubeConfigured) {
    issues.push({
      severity: 'high',
      user: 'Scanning is temporarily unavailable. We\'re aware and working on it.',
      admin:
        'OMI_YOUTUBE_API_KEY is not set on the API service. Every scan endpoint returns 503 until it\'s configured.',
    });
  }
  if (storageEphemeral) {
    issues.push({
      severity: 'medium',
      user: 'Your saved investigations may not persist between sessions yet.',
      admin:
        'Database is SQLite on ephemeral disk. Provision Postgres and set OMI_DATABASE_URL before launch, every redeploy wipes user data.',
    });
  }
  // YouTube quota pressure. Only meaningful if YouTube is configured.
  // ≥80% used in last 24h is a yellow warning; ≥95% is a red warning.
  if (youtubeConfigured && quotaUsedToday !== undefined && quotaDailyLimit && quotaDailyLimit > 0) {
    const pct = quotaUsedToday / quotaDailyLimit;
    if (pct >= 0.95) {
      issues.push({
        severity: 'high',
        user: 'Daily scan capacity is nearly exhausted. New scans may be delayed until tomorrow.',
        admin: `YouTube quota at ${Math.round(pct * 100)}% (${quotaUsedToday.toLocaleString()} of ${quotaDailyLimit.toLocaleString()} units used in last 24h). Resets at midnight Pacific.`,
      });
    } else if (pct >= 0.8) {
      issues.push({
        severity: 'medium',
        user: 'Scan capacity is running low for the day. Scans should still work but may be slower.',
        admin: `YouTube quota at ${Math.round(pct * 100)}% (${quotaUsedToday.toLocaleString()} of ${quotaDailyLimit.toLocaleString()} units used in last 24h).`,
      });
    }
  }

  const highest = issues.length === 0
    ? 'ok'
    : issues.some((i) => i.severity === 'high') ? 'high' : 'medium';

  // A lamp and a state word, not an icon and a phrase.
  //
  // Three fixes here. The icons (a tick, a triangle, a shield) are consumer
  // status glyphs, and a console reports state with a lamp. `All systems` was
  // half a sentence, saying nothing about what those systems were doing. And
  // the `high` state pulsed the ENTIRE pill, which on a sticky topbar is a
  // whole control blinking in the corner of the eye for as long as the fault
  // lasts; the lamp blinks, the frame around it holds still.
  const palette = {
    ok:     { btn: 'border-tier-low/40 bg-tier-low/10 text-tier-low hover:bg-tier-low/15', led: 'led-ok', label: 'Nominal' },
    medium: { btn: 'border-tier-moderate/40 bg-tier-moderate/10 text-tier-moderate hover:bg-tier-moderate/15', led: 'led-warn', label: 'Degraded' },
    high:   { btn: 'border-tier-high/40 bg-tier-high/10 text-tier-high hover:bg-tier-high/15', led: 'led-fail animate-pulse-dot', label: 'Offline' },
  }[highest];

  return (
    <div className="relative">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className={`inline-flex items-center gap-1.5 h-7 px-2.5 rounded-sm border font-mono text-2xs uppercase tracking-wider transition-colors ${palette.btn}`}
        aria-label={`Service health: ${palette.label}`}
        aria-expanded={open}
      >
        <span className={`led ${palette.led}`} />
        <span className="hidden sm:inline">{palette.label}</span>
      </button>

      {open && (
        <>
          {/* invisible scrim */}
          <div className="fixed inset-0 z-40" onClick={() => setOpen(false)} />
          {/* shadow-overlay, the product's own token: a tight drop plus a
              hairline. `shadow-xl` is a large soft Tailwind default, which is
              the one elevation move this design language does not use. */}
          <div className="absolute right-0 mt-1 w-80 bg-bg-elev border border-border-2 rounded-sm shadow-overlay z-50 p-3">
            <div className="flex items-center justify-between mb-2">
              <span className="meta meta-hi">Service status</span>
              <button
                type="button"
                onClick={() => setOpen(false)}
                className="text-fg-mute hover:text-fg"
                aria-label="Close"
              >
                <X size={11} />
              </button>
            </div>

            {issues.length === 0 ? (
              <div>
                <div className="flex items-start gap-2.5 mb-3">
                  <span className="led led-ok shrink-0 mt-1.5" />
                  <p className="text-xs text-fg-dim leading-relaxed">
                    All systems operational. Scanning, storage, and detection are healthy.
                  </p>
                </div>
                {isAdmin && quotaDailyLimit && quotaDailyLimit > 0 && quotaUsedToday !== undefined && (
                  <div className="pt-2 border-t border-border-1">
                    <div className="flex items-center justify-between mb-1">
                      <span className="meta">YT quota · last 24h</span>
                      <span className="font-mono text-2xs tabular text-fg">
                        {quotaUsedToday.toLocaleString()} / {quotaDailyLimit.toLocaleString()}
                      </span>
                    </div>
                    <div className="h-1 bg-border-1 rounded-[1px] overflow-hidden">
                      <div
                        className="h-full bg-accent"
                        style={{
                          width: `${Math.min(100, (quotaUsedToday / quotaDailyLimit) * 100)}%`,
                        }}
                      />
                    </div>
                  </div>
                )}
              </div>
            ) : (
              <ul className="space-y-3">
                {issues.map((issue, i) => (
                  <li key={i} className="flex items-start gap-2.5">
                    <span
                      className={`led shrink-0 mt-1.5 ${issue.severity === 'high' ? 'led-fail' : 'led-warn'}`}
                    />
                    <div className="flex-1 min-w-0">
                      <p className="text-xs text-fg leading-relaxed">{issue.user}</p>
                      {isAdmin && (
                        <p className="text-2xs text-fg-mute font-mono mt-1 leading-relaxed">
                          {issue.admin}
                        </p>
                      )}
                    </div>
                  </li>
                ))}
              </ul>
            )}

            {isAdmin && (
              <Link
                href="/v1/status"
                target="_blank"
                rel="noopener noreferrer"
                className="block mt-3 pt-2 border-t border-border-1 meta text-accent hover:text-accent-2"
              >
                View /v1/status →
              </Link>
            )}
          </div>
        </>
      )}
    </div>
  );
}

/**
 * Slim banner that shows under the topbar when scanning is unavailable.
 * Visible to ALL users; the wording is non-technical. Admins also see the
 * existing diagnostic banner from app-shell with env-var details.
 */
export function ServiceDegradedBanner({
  youtubeConfigured,
}: {
  youtubeConfigured: boolean;
}) {
  if (youtubeConfigured) return null;
  return (
    <div className="bg-tier-high/10 border-b border-tier-high/40 px-6 py-2.5 text-xs text-fg flex items-center gap-2.5 justify-center">
      <ShieldAlert size={13} className="text-tier-high shrink-0" />
      <span>
        <span className="font-medium">Scanning is temporarily unavailable.</span>{' '}
        <span className="text-fg-dim">
          Existing investigations remain viewable; new scans will resume shortly.
        </span>
      </span>
    </div>
  );
}
