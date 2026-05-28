'use client';

import { useState, useEffect, useRef } from 'react';
import Link from 'next/link';
import { Zap, RefreshCw, AlertTriangle, CheckCircle2, X, ExternalLink } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { apiClient, ApiError } from '@/lib/api';

interface Props {
  inputUrl: string;
}

type State =
  | { kind: 'idle' }
  | { kind: 'loading'; elapsedSeconds: number }
  | { kind: 'success' }
  | { kind: 'error'; title: string; detail: string; canRetry: boolean };

/**
 * In-place rescan for a saved investigation. POSTs the original input URL
 * back to /v1/scan/link, then full-reloads the page. Hardened against
 * timeouts, 5xx, and cold-start failures: shows a real error with a
 * fallback link into the scan workspace.
 */
export function RescanInvestigationButton({ inputUrl }: Props) {
  const [state, setState] = useState<State>({ kind: 'idle' });
  const cleanupRef = useRef<() => void>(() => {});

  useEffect(() => () => cleanupRef.current(), []);

  async function handleClick() {
    cleanupRef.current();
    const startedAt = Date.now();
    setState({ kind: 'loading', elapsedSeconds: 0 });

    const tick = setInterval(() => {
      setState((s) =>
        s.kind === 'loading'
          ? { ...s, elapsedSeconds: Math.round((Date.now() - startedAt) / 1000) }
          : s,
      );
    }, 1000);

    const controller = new AbortController();
    // Comprehensive scans take time — give it 3 minutes before we give up.
    const abortTimer = setTimeout(() => controller.abort(), 180_000);

    cleanupRef.current = () => {
      clearInterval(tick);
      clearTimeout(abortTimer);
      controller.abort();
    };

    try {
      await apiClient<unknown>('/v1/scan/link', {
        method: 'POST',
        body: JSON.stringify({ url: inputUrl, max_commenters: 25 }),
        signal: controller.signal,
      });
      cleanupRef.current();
      setState({ kind: 'success' });
      setTimeout(() => window.location.reload(), 800);
    } catch (err) {
      cleanupRef.current();
      if (err instanceof DOMException && err.name === 'AbortError') {
        setState({
          kind: 'error',
          title: 'Scan timed out',
          detail:
            'The browser request hit our 3-minute limit. The scan may still be running on the server — refresh in a minute to check, or open the workspace to monitor live.',
          canRetry: true,
        });
        return;
      }
      setState(toErrorState(err));
    }
  }

  if (state.kind === 'loading') {
    return (
      <div className="inline-flex items-center gap-2">
        <Button disabled type="button" variant="secondary">
          <RefreshCw size={14} className="animate-spin" />
          Re-scanning… {state.elapsedSeconds}s
        </Button>
        {state.elapsedSeconds >= 30 && (
          <span className="font-mono text-2xs text-fg-mute max-w-[260px]">
            Comprehensive scans can take 30-90 s. Stay on this page.
          </span>
        )}
      </div>
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
      <div className="flex flex-col gap-2 max-w-md">
        <div className="flex items-start gap-2 px-3 py-2 rounded-sm bg-tier-high/10 border border-tier-high/40">
          <AlertTriangle size={12} className="text-tier-high shrink-0 mt-0.5" />
          <div className="flex-1 min-w-0">
            <div className="font-mono text-2xs text-tier-high uppercase tracking-wider mb-1">
              {state.title}
            </div>
            <div className="text-xs text-fg-dim leading-relaxed">{state.detail}</div>
            <div className="mt-2 flex items-center gap-3 flex-wrap">
              {state.canRetry && (
                <button
                  type="button"
                  onClick={handleClick}
                  className="font-mono text-2xs text-accent hover:text-accent-2 uppercase tracking-wider"
                >
                  Try again
                </button>
              )}
              <button
                type="button"
                onClick={() => window.location.reload()}
                className="font-mono text-2xs text-fg-dim hover:text-fg uppercase tracking-wider"
              >
                Reload page
              </button>
              <Link
                href={`/investigate?url=${encodeURIComponent(inputUrl)}`}
                className="inline-flex items-center gap-1 font-mono text-2xs text-fg-dim hover:text-fg uppercase tracking-wider"
              >
                Open in workspace <ExternalLink size={10} />
              </Link>
            </div>
          </div>
          <button
            type="button"
            onClick={() => setState({ kind: 'idle' })}
            className="text-fg-mute hover:text-fg shrink-0"
            aria-label="Dismiss"
          >
            <X size={11} />
          </button>
        </div>
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

function toErrorState(err: unknown): State {
  if (err instanceof ApiError) {
    const detail = err.message || 'No detail returned.';
    switch (err.status) {
      case 401:
        return {
          kind: 'error',
          title: 'Session expired',
          detail: 'Your session timed out. Log in again and re-try.',
          canRetry: false,
        };
      case 402:
        return {
          kind: 'error',
          title: 'Out of credits',
          detail: 'You have no scan credits left. Visit Settings → Billing to top up.',
          canRetry: false,
        };
      case 400:
        return {
          kind: 'error',
          title: 'Unrecognized URL',
          detail,
          canRetry: false,
        };
      case 429:
        return {
          kind: 'error',
          title: 'Rate limited',
          detail: 'Too many scans recently. Wait a minute, then retry.',
          canRetry: true,
        };
      case 503:
        return {
          kind: 'error',
          title: 'Scan service unavailable',
          detail: detail.includes('YouTube API key')
            ? 'The API server is missing OMI_YOUTUBE_API_KEY. Set it on the api service in Render and redeploy.'
            : detail,
          canRetry: false,
        };
      case 502:
      case 504:
        return {
          kind: 'error',
          title: 'Gateway timeout',
          detail: 'The scan took longer than the proxy allows. It may still be running — reload in 30 s to check.',
          canRetry: true,
        };
      default:
        return {
          kind: 'error',
          title: `Server error (${err.status})`,
          detail,
          canRetry: true,
        };
    }
  }
  if (err instanceof TypeError) {
    return {
      kind: 'error',
      title: 'Network error',
      detail: 'Could not reach the API. On Render free tier the service may be cold-starting — wait 30 s and try again.',
      canRetry: true,
    };
  }
  return {
    kind: 'error',
    title: 'Unexpected error',
    detail: err instanceof Error ? err.message : String(err),
    canRetry: true,
  };
}
