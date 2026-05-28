'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { RefreshCw, AlertTriangle, CheckCircle2, X } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { apiClient, ApiError, type AccountScanOut } from '@/lib/api';

interface Props {
  externalId: string;
  platform?: string;
  /** Initial idle label — defaults to "Re-scan now". */
  label?: string;
}

export function RescanAccountButton({
  externalId,
  platform = 'youtube',
  label = 'Re-scan now',
}: Props) {
  const router = useRouter();
  const [state, setState] = useState<'idle' | 'loading' | 'success' | 'error'>('idle');
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<AccountScanOut | null>(null);

  async function handleClick(e: React.MouseEvent) {
    // Defensive: stop any parent <Link>/<a> from catching this click.
    e.preventDefault();
    e.stopPropagation();
    setState('loading');
    setError(null);
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
      setTimeout(() => setState('idle'), 3000);
    } catch (err) {
      const msg = err instanceof ApiError ? err.message : 'Scan failed. Try again in a moment.';
      setError(msg);
      setState('error');
      // Don't auto-clear errors — user has to dismiss so they actually read it.
    }
  }

  if (state === 'loading') {
    return (
      <div className="inline-flex items-center gap-2">
        <Button disabled type="button">
          <RefreshCw size={14} className="animate-spin" />
          Scanning channel…
        </Button>
        <span className="font-mono text-2xs text-fg-mute">
          fetching latest comments — ~10-30s
        </span>
      </div>
    );
  }

  if (state === 'success' && result) {
    const pct = Math.round(result.overall_probability * 100);
    return (
      <Button disabled type="button" className="!bg-tier-low/10 !border-tier-low !text-tier-low">
        <CheckCircle2 size={14} />
        Updated · {pct}% · {result.tier}
      </Button>
    );
  }

  if (state === 'error') {
    return (
      <div className="inline-flex items-start gap-2 max-w-xl">
        <Button onClick={handleClick} variant="danger" type="button">
          <AlertTriangle size={14} />
          Retry rescan
        </Button>
        <div className="flex items-start gap-1.5 bg-tier-high/10 border border-tier-high/40 rounded-sm px-2 py-1.5">
          <span className="font-mono text-2xs text-tier-high leading-snug">{error}</span>
          <button
            type="button"
            onClick={() => { setState('idle'); setError(null); }}
            className="text-tier-high hover:text-fg shrink-0"
            aria-label="Dismiss error"
          >
            <X size={11} />
          </button>
        </div>
      </div>
    );
  }

  return (
    <Button onClick={handleClick} type="button" title="Re-scan this account using its stored channel ID — no need to paste anything.">
      <RefreshCw size={14} />
      {label}
    </Button>
  );
}
