'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { RefreshCw, AlertTriangle, CheckCircle2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { apiClient, ApiError, type AccountScanOut } from '@/lib/api';

interface Props {
  externalId: string;
  platform?: string;
  /** Initial idle label — defaults to "Re-scan now". */
  label?: string;
}

export function RescanAccountButton({ externalId, platform = 'youtube', label = 'Re-scan now' }: Props) {
  const router = useRouter();
  const [state, setState] = useState<'idle' | 'loading' | 'success' | 'error'>('idle');
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<AccountScanOut | null>(null);

  async function handleClick() {
    setState('loading');
    setError(null);
    try {
      // Pass the channel ID directly — no need for the user to paste anything.
      const data = await apiClient<AccountScanOut>(`/v1/scan/${platform}/account`, {
        method: 'POST',
        body: JSON.stringify({
          account_url_or_handle: externalId,
          force_refresh: true,
        }),
      });
      setResult(data);
      setState('success');
      // Reload the server-rendered page so the new scan appears in history.
      router.refresh();
      // Reset to idle after a moment so they can rescan again
      setTimeout(() => setState('idle'), 2500);
    } catch (err) {
      const msg = err instanceof ApiError ? err.message : 'Scan failed. Try again in a moment.';
      setError(msg);
      setState('error');
      setTimeout(() => setState('idle'), 4000);
    }
  }

  if (state === 'loading') {
    return (
      <Button disabled>
        <RefreshCw size={14} className="animate-spin" />
        Scanning…
      </Button>
    );
  }

  if (state === 'success' && result) {
    const pct = Math.round(result.overall_probability * 100);
    return (
      <Button disabled className="!bg-tier-low/10 !border-tier-low !text-tier-low">
        <CheckCircle2 size={14} />
        Updated: {pct}% · {result.tier}
      </Button>
    );
  }

  if (state === 'error') {
    return (
      <div className="flex items-center gap-3">
        <Button onClick={handleClick} variant="danger">
          <AlertTriangle size={14} />
          Retry
        </Button>
        <span className="font-mono text-2xs text-tier-high">{error}</span>
      </div>
    );
  }

  return (
    <Button onClick={handleClick}>
      <RefreshCw size={14} />
      {label}
    </Button>
  );
}
