'use client';

import { useState } from 'react';
import { Zap, RefreshCw, AlertTriangle, CheckCircle2, X } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { apiClient, ApiError } from '@/lib/api';

interface Props {
  inputUrl: string;
}

type State =
  | { kind: 'idle' }
  | { kind: 'loading' }
  | { kind: 'success' }
  | { kind: 'error'; message: string };

/**
 * In-place rescan for a saved investigation. POSTs the original input URL
 * back to /v1/scan/link, then full-reloads the page so the latest data
 * shows up — we don't navigate to /investigate anymore.
 */
export function RescanInvestigationButton({ inputUrl }: Props) {
  const [state, setState] = useState<State>({ kind: 'idle' });

  async function handleClick() {
    setState({ kind: 'loading' });
    try {
      await apiClient<unknown>('/v1/scan/link', {
        method: 'POST',
        body: JSON.stringify({ url: inputUrl, max_commenters: 25 }),
      });
      setState({ kind: 'success' });
      setTimeout(() => window.location.reload(), 1000);
    } catch (err) {
      const msg =
        err instanceof ApiError
          ? err.status === 402
            ? 'Out of credits — visit Settings to subscribe.'
            : err.message
          : 'Network error. Try again.';
      setState({ kind: 'error', message: msg });
    }
  }

  if (state.kind === 'loading') {
    return (
      <Button disabled type="button" variant="secondary">
        <RefreshCw size={14} className="animate-spin" />
        Re-scanning…
      </Button>
    );
  }

  if (state.kind === 'success') {
    return (
      <Button disabled type="button" className="!bg-tier-low/10 !border-tier-low !text-tier-low">
        <CheckCircle2 size={14} />
        Updated · reloading…
      </Button>
    );
  }

  if (state.kind === 'error') {
    return (
      <div className="inline-flex items-center gap-2">
        <Button onClick={handleClick} type="button" variant="danger">
          <AlertTriangle size={14} />
          Retry
        </Button>
        <span className="font-mono text-2xs text-tier-high max-w-xs">{state.message}</span>
        <button
          type="button"
          onClick={() => setState({ kind: 'idle' })}
          className="text-fg-mute hover:text-fg"
          aria-label="Dismiss"
        >
          <X size={11} />
        </button>
      </div>
    );
  }

  return (
    <Button onClick={handleClick} type="button">
      <Zap size={14} />
      Re-scan
    </Button>
  );
}
