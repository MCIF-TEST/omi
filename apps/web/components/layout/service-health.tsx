'use client';

import { useState } from 'react';
import Link from 'next/link';
import { AlertTriangle, CheckCircle2, X, ShieldAlert } from 'lucide-react';

interface Props {
  youtubeConfigured: boolean;
  storageEphemeral: boolean;
  isAdmin: boolean;
}

/**
 * Compact service-health pill in the topbar.
 *
 * Green when everything is fine; yellow when one capability is degraded;
 * red when scanning won't work at all. Clicking opens a small popover
 * with the human-readable status — admins get diagnostic detail, regular
 * users get a friendly "scanning is temporarily unavailable" message.
 */
export function ServiceHealthPill({ youtubeConfigured, storageEphemeral, isAdmin }: Props) {
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
        'Database is SQLite on ephemeral disk. Provision Postgres and set OMI_DATABASE_URL before launch — every redeploy wipes user data.',
    });
  }

  const highest = issues.length === 0
    ? 'ok'
    : issues.some((i) => i.severity === 'high') ? 'high' : 'medium';

  const palette = {
    ok: {
      btn: 'border-tier-low/40 bg-tier-low/10 text-tier-low hover:bg-tier-low/15',
      icon: <CheckCircle2 size={11} />,
      label: 'All systems',
    },
    medium: {
      btn: 'border-tier-moderate/40 bg-tier-moderate/10 text-tier-moderate hover:bg-tier-moderate/15',
      icon: <AlertTriangle size={11} />,
      label: 'Degraded',
    },
    high: {
      btn: 'border-tier-high/40 bg-tier-high/10 text-tier-high hover:bg-tier-high/15 animate-pulse-dot',
      icon: <ShieldAlert size={11} />,
      label: 'Service down',
    },
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
        {palette.icon}
        <span className="hidden sm:inline">{palette.label}</span>
      </button>

      {open && (
        <>
          {/* invisible scrim */}
          <div className="fixed inset-0 z-40" onClick={() => setOpen(false)} />
          <div className="absolute right-0 mt-1 w-80 bg-bg-elev border border-border-2 rounded-sm shadow-xl z-50 p-3">
            <div className="flex items-center justify-between mb-2">
              <span className="font-mono text-2xs text-fg-mute uppercase tracking-wider">
                Service status
              </span>
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
              <div className="flex items-start gap-2">
                <CheckCircle2 size={13} className="text-tier-low shrink-0 mt-0.5" />
                <p className="text-xs text-fg-dim leading-relaxed">
                  All systems operational. Scanning, storage, and detection are healthy.
                </p>
              </div>
            ) : (
              <ul className="space-y-3">
                {issues.map((issue, i) => (
                  <li key={i} className="flex items-start gap-2">
                    <AlertTriangle
                      size={13}
                      className={
                        issue.severity === 'high'
                          ? 'text-tier-high shrink-0 mt-0.5'
                          : 'text-tier-moderate shrink-0 mt-0.5'
                      }
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
                className="block mt-3 pt-2 border-t border-border-1 text-2xs font-mono text-accent hover:text-accent-2 uppercase tracking-wider"
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
    <div className="bg-tier-high/10 border-b border-tier-high/40 px-6 py-2.5 text-xs text-fg flex items-center gap-2 justify-center">
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
