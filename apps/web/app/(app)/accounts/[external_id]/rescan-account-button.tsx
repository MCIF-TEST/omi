'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import {
  RefreshCw,
  AlertTriangle,
  CheckCircle2,
  X,
  Zap,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { apiClient, ApiError, type AccountScanOut } from '@/lib/api';

interface Props {
  externalId: string;
  platform?: string;
  handle?: string;
}

export function RescanAccountButton({
  externalId,
  platform = 'youtube',
  handle,
}: Props) {
  const router = useRouter();
  const [state, setState] = useState<'idle' | 'loading' | 'success' | 'error'>('idle');
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<AccountScanOut | null>(null);

  async function handleClick() {
    setState('loading');
    setError(null);
    setResult(null);
    try {
      const data = await apiClient<AccountScanOut>(`/v1/scan/${platform}/account`, {
        method: 'POST',
        body: JSON.stringify({
          account_url_or_handle: externalId,
          force_refresh: true,
        }),
      });
      setResult(data);
      setState('success');
      router.refresh();
      setTimeout(() => setState('idle'), 5000);
    } catch (err) {
      const msg =
        err instanceof ApiError
          ? err.status === 402
            ? 'Out of credits — visit Settings to subscribe.'
            : err.status === 401
            ? 'Session expired — please log in again.'
            : err.message
          : 'Network error. Check your connection and try again.';
      setError(msg);
      setState('error');
    }
  }

  /* ── Full-width scanning banner ── */
  if (state === 'loading') {
    return (
      <div className="rounded-md border border-accent/40 bg-accent/5 px-5 py-4">
        <div className="flex items-center gap-3 mb-1">
          <RefreshCw size={16} className="text-accent animate-spin shrink-0" />
          <p className="font-mono text-sm font-semibold text-accent uppercase tracking-wider">
            Scanning {handle ? `@${handle}` : 'account'}…
          </p>
        </div>
        <p className="font-mono text-2xs text-fg-dim ml-7">
          Fetching latest channel activity from YouTube — this takes 15–30 seconds.
          Stay on this page.
        </p>
      </div>
    );
  }

  /* ── Success banner ── */
  if (state === 'success' && result) {
    const pct = Math.round(result.overall_probability * 100);
    const tierColor =
      result.tier === 'high' ? 'text-tier-high border-tier-high/40 bg-tier-high/5' :
      result.tier === 'elevated' ? 'text-tier-elevated border-tier-elevated/40 bg-tier-elevated/5' :
      result.tier === 'moderate' ? 'text-tier-moderate border-tier-moderate/40 bg-tier-moderate/5' :
      'text-tier-low border-tier-low/40 bg-tier-low/5';
    return (
      <div className={`rounded-md border px-5 py-4 ${tierColor}`}>
        <div className="flex items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            <CheckCircle2 size={16} className="shrink-0" />
            <div>
              <p className="font-mono text-sm font-semibold uppercase tracking-wider">
                Scan complete · {pct}% inauthentic · {result.tier} tier
              </p>
              <p className="font-mono text-2xs mt-0.5 opacity-75">
                Page is refreshing with latest data…
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={() => setState('idle')}
            className="opacity-60 hover:opacity-100"
            aria-label="Dismiss"
          >
            <X size={14} />
          </button>
        </div>
      </div>
    );
  }

  /* ── Error banner ── */
  if (state === 'error') {
    return (
      <div className="rounded-md border border-tier-high/40 bg-tier-high/5 px-5 py-4">
        <div className="flex items-start justify-between gap-3">
          <div className="flex items-start gap-3">
            <AlertTriangle size={16} className="text-tier-high shrink-0 mt-0.5" />
            <div>
              <p className="font-mono text-sm font-semibold text-tier-high uppercase tracking-wider mb-1">
                Scan failed
              </p>
              <p className="text-sm text-fg-dim">{error}</p>
              <button
                type="button"
                onClick={handleClick}
                className="mt-3 inline-flex items-center gap-1.5 font-mono text-2xs uppercase tracking-wider text-accent hover:text-accent-2 border border-accent/40 hover:border-accent px-2.5 py-1.5 rounded-sm transition-colors"
              >
                <RefreshCw size={11} /> Try again
              </button>
            </div>
          </div>
          <button
            type="button"
            onClick={() => { setState('idle'); setError(null); }}
            className="text-fg-mute hover:text-fg shrink-0"
            aria-label="Dismiss"
          >
            <X size={14} />
          </button>
        </div>
      </div>
    );
  }

  /* ── Idle: single obvious button ── */
  return (
    <Button onClick={handleClick} type="button">
      <Zap size={14} />
      Re-scan this account
    </Button>
  );
}
