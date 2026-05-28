'use client';

import { useState, useEffect, useRef } from 'react';
import Link from 'next/link';
import {
  Zap, RefreshCw, AlertTriangle, CheckCircle2, X,
  Eye, EyeOff, Download, ChevronDown, ExternalLink,
} from 'lucide-react';
import {
  apiClient, ApiError,
  type AccountScanOut, type AccountHistoryResponse,
  type WatchlistOut, type WatchlistsResponse,
} from '@/lib/api';

type ScanState =
  | { kind: 'idle' }
  | { kind: 'loading'; stage: string; elapsedSeconds: number }
  | { kind: 'success'; result: AccountScanOut | { tier: string; overall_probability: number } }
  | { kind: 'error'; title: string; detail: string; canRetry: boolean };

interface Props {
  externalId: string;
  platform: string;
  handle: string;
  /** csvRows() returns the CSV body — pulled from the server-rendered history table. */
  csvRows: () => string;
}

/** Build a YouTube channel URL from a UC… ID so we can fall back to /investigate. */
function workspaceUrl(platform: string, externalId: string): string {
  if (platform === 'youtube' && externalId.startsWith('UC')) {
    return `/investigate?url=${encodeURIComponent(`https://www.youtube.com/channel/${externalId}`)}`;
  }
  return `/investigate?url=${encodeURIComponent(externalId)}`;
}

export function AccountActions({ externalId, platform, handle, csvRows }: Props) {
  const [scan, setScan] = useState<ScanState>({ kind: 'idle' });
  const [watch, setWatch] = useState<{ loading: boolean; existing: WatchlistOut | null }>({
    loading: true,
    existing: null,
  });
  const [exportOpen, setExportOpen] = useState(false);
  const cleanupRef = useRef<() => void>(() => {});

  // Discover whether this account is already on a watchlist
  useEffect(() => {
    apiClient<WatchlistsResponse>('/v1/watchlists')
      .then((r) => {
        const existing = r.watchlists.find(
          (w) => w.kind === 'channel' && w.target_id === externalId,
        );
        setWatch({ loading: false, existing: existing ?? null });
      })
      .catch(() => setWatch({ loading: false, existing: null }));
  }, [externalId]);

  // Cleanup any in-flight timers/aborts on unmount
  useEffect(() => () => cleanupRef.current(), []);

  /* ── RESCAN ──────────────────────────────────────────────────────────
   * Strategy: kick off the scan, then run BOTH:
   *   (a) the POST request itself (we honor the result if it returns)
   *   (b) a poll of /history every 4 s — if a fresh scan row appears,
   *       we declare success even if (a) is still hanging or 502s.
   * That way even a Render-edge timeout or a one-off 5xx can't strand
   * the user as long as the backend did the work.
   * ──────────────────────────────────────────────────────────────────── */
  async function handleRescan() {
    // Tear down any prior attempt
    cleanupRef.current();

    const startedAt = Date.now();
    const baselineLastScan = await readLastScannedAt().catch(() => null);

    setScan({ kind: 'loading', stage: 'Resolving channel…', elapsedSeconds: 0 });

    const stages = [
      'Resolving channel…',
      'Fetching profile metadata…',
      'Pulling recent comments…',
      'Running detector pipeline…',
      'Computing coordination signals…',
      'Still working — large channels take a moment…',
    ];
    let stageIdx = 0;
    const stageTimer = setInterval(() => {
      stageIdx = Math.min(stageIdx + 1, stages.length - 1);
      setScan((s) =>
        s.kind === 'loading'
          ? { ...s, stage: stages[stageIdx], elapsedSeconds: Math.round((Date.now() - startedAt) / 1000) }
          : s,
      );
    }, 4000);

    const controller = new AbortController();
    const abortTimer = setTimeout(() => controller.abort(), 110_000);

    // Bg poll — every 4s look for a newer last_scanned_at than baseline
    let polling = true;
    const pollTimer = setInterval(async () => {
      if (!polling) return;
      const now = await readLastScannedAt().catch(() => null);
      if (now && (!baselineLastScan || now > baselineLastScan)) {
        polling = false;
        controller.abort();
        clearInterval(stageTimer);
        clearInterval(pollTimer);
        clearTimeout(abortTimer);
        setScan({
          kind: 'success',
          result: { tier: 'updated', overall_probability: 0 },
        });
        setTimeout(() => window.location.reload(), 800);
      }
    }, 4000);

    cleanupRef.current = () => {
      polling = false;
      clearInterval(stageTimer);
      clearInterval(pollTimer);
      clearTimeout(abortTimer);
      controller.abort();
    };

    try {
      const data = await apiClient<AccountScanOut>(`/v1/scan/${platform}/account`, {
        method: 'POST',
        body: JSON.stringify({ account_url_or_handle: externalId, force_refresh: true }),
        signal: controller.signal,
      });
      cleanupRef.current();
      setScan({ kind: 'success', result: data });
      setTimeout(() => window.location.reload(), 1500);
    } catch (err) {
      // If the poll already saw a new scan, ignore the request error
      if (!polling) return;
      cleanupRef.current();

      // Aborted because of our timeout? One last poll attempt before giving up.
      if (err instanceof DOMException && err.name === 'AbortError') {
        const now = await readLastScannedAt().catch(() => null);
        if (now && (!baselineLastScan || now > baselineLastScan)) {
          setScan({ kind: 'success', result: { tier: 'updated', overall_probability: 0 } });
          setTimeout(() => window.location.reload(), 800);
          return;
        }
        setScan({
          kind: 'error',
          title: 'Scan is still running',
          detail:
            'The request from your browser timed out, but the scan may complete server-side. Reload in 30 s — if a new entry appears in the history table, it worked.',
          canRetry: true,
        });
        return;
      }

      setScan(toErrorState(err, platform, externalId));
    }
  }

  /** Pull last_scanned_at from /history. Cheap and gives us a polling baseline. */
  async function readLastScannedAt(): Promise<string | null> {
    const r = await apiClient<AccountHistoryResponse>(
      `/v1/accounts/${platform}/${encodeURIComponent(externalId)}/history?limit=1`,
    );
    return r.last_scanned_at ?? r.scans[0]?.scanned_at ?? null;
  }

  /* ── WATCHLIST TOGGLE ── */
  async function handleWatchToggle() {
    if (watch.loading) return;
    setWatch((w) => ({ ...w, loading: true }));
    try {
      if (watch.existing) {
        await apiClient(`/v1/watchlists/${watch.existing.id}`, { method: 'DELETE' });
        setWatch({ loading: false, existing: null });
      } else {
        const created = await apiClient<WatchlistOut>('/v1/watchlists', {
          method: 'POST',
          body: JSON.stringify({
            kind: 'channel',
            target_id: externalId,
            label: handle || externalId,
            alert_threshold_tier: 'elevated',
          }),
        });
        setWatch({ loading: false, existing: created });
      }
    } catch {
      setWatch((w) => ({ ...w, loading: false }));
    }
  }

  /* ── EXPORT ── */
  function downloadCsv() {
    const blob = new Blob([csvRows()], { type: 'text/csv;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${platform}-${externalId}-history.csv`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
    setExportOpen(false);
  }

  function downloadJson() {
    // Pull the data straight off the page via the same endpoint
    apiClient<unknown>(`/v1/accounts/${platform}/${encodeURIComponent(externalId)}/history?limit=1000`)
      .then((data) => {
        const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `${platform}-${externalId}-history.json`;
        document.body.appendChild(a);
        a.click();
        a.remove();
        URL.revokeObjectURL(url);
      })
      .finally(() => setExportOpen(false));
  }

  return (
    <div className="sticky top-0 z-30 -mx-6 px-6 py-3 bg-bg/95 backdrop-blur border-b border-border-1">
      <div className="flex items-center justify-between gap-3 flex-wrap">
        {/* Channel chip */}
        <div className="flex items-center gap-2 font-mono text-2xs tracking-wider uppercase text-fg-mute min-w-0">
          <span className="px-1.5 py-0.5 rounded-sm border border-border-2 text-fg-dim">
            {platform}
          </span>
          <span className="truncate max-w-[280px]">{handle || externalId}</span>
        </div>

        {/* Actions */}
        <div className="flex items-center gap-2 flex-wrap">
          {/* Watchlist toggle */}
          <button
            type="button"
            onClick={handleWatchToggle}
            disabled={watch.loading}
            className={`inline-flex items-center gap-1.5 h-9 px-3 rounded-sm border font-mono text-2xs uppercase tracking-wider transition-colors disabled:opacity-50 ${
              watch.existing
                ? 'border-accent bg-accent/10 text-accent hover:bg-accent/20'
                : 'border-border-2 text-fg-dim hover:text-fg hover:border-border-hot'
            }`}
            title={watch.existing ? 'Stop watching this channel' : 'Get alerts when this channel changes'}
          >
            {watch.existing ? <Eye size={12} /> : <EyeOff size={12} />}
            {watch.existing ? 'Watching' : 'Watch'}
          </button>

          {/* Export dropdown */}
          <div className="relative">
            <button
              type="button"
              onClick={() => setExportOpen((v) => !v)}
              className="inline-flex items-center gap-1.5 h-9 px-3 rounded-sm border border-border-2 text-fg-dim hover:text-fg hover:border-border-hot font-mono text-2xs uppercase tracking-wider transition-colors"
            >
              <Download size={12} />
              Export
              <ChevronDown size={11} className={exportOpen ? 'rotate-180' : ''} />
            </button>
            {exportOpen && (
              <>
                <div className="fixed inset-0 z-40" onClick={() => setExportOpen(false)} />
                <div className="absolute right-0 mt-1 w-40 bg-bg-elev border border-border-2 rounded-sm shadow-lg z-50">
                  <button
                    type="button"
                    onClick={downloadCsv}
                    className="block w-full text-left px-3 py-2 font-mono text-2xs uppercase tracking-wider text-fg-dim hover:bg-bg-elev-2 hover:text-fg"
                  >
                    History as CSV
                  </button>
                  <button
                    type="button"
                    onClick={downloadJson}
                    className="block w-full text-left px-3 py-2 font-mono text-2xs uppercase tracking-wider text-fg-dim hover:bg-bg-elev-2 hover:text-fg border-t border-border-1"
                  >
                    Full JSON
                  </button>
                </div>
              </>
            )}
          </div>

          {/* THE RESCAN BUTTON — primary action */}
          <button
            type="button"
            onClick={handleRescan}
            disabled={scan.kind === 'loading'}
            className="inline-flex items-center gap-1.5 h-9 px-4 rounded-sm bg-accent hover:bg-accent-2 text-bg-deep disabled:opacity-50 disabled:cursor-not-allowed font-mono text-2xs uppercase tracking-wider font-semibold transition-colors"
          >
            {scan.kind === 'loading' ? (
              <><RefreshCw size={12} className="animate-spin" /> Scanning…</>
            ) : (
              <><Zap size={12} /> Re-scan now</>
            )}
          </button>
        </div>
      </div>

      {/* Live status row — appears under the bar when something is happening */}
      {scan.kind === 'loading' && (
        <div className="mt-3 flex items-center gap-2 px-3 py-2 rounded-sm bg-accent/10 border border-accent/30 flex-wrap">
          <RefreshCw size={12} className="text-accent animate-spin shrink-0" />
          <span className="font-mono text-2xs text-accent uppercase tracking-wider">
            {scan.stage}
          </span>
          <span className="ml-auto font-mono text-2xs text-fg-mute">
            {scan.elapsedSeconds}s elapsed · stay on this page
          </span>
          {scan.elapsedSeconds >= 30 && (
            <button
              type="button"
              onClick={() => window.location.reload()}
              className="font-mono text-2xs text-accent hover:text-accent-2 uppercase tracking-wider underline"
            >
              Reload now to check
            </button>
          )}
        </div>
      )}

      {scan.kind === 'success' && (
        <div className="mt-3 flex items-center gap-2 px-3 py-2 rounded-sm bg-tier-low/10 border border-tier-low/40">
          <CheckCircle2 size={12} className="text-tier-low shrink-0" />
          <span className="font-mono text-2xs text-tier-low uppercase tracking-wider">
            {'overall_probability' in scan.result && scan.result.overall_probability > 0
              ? `Updated · ${Math.round(scan.result.overall_probability * 100)}% · ${scan.result.tier} tier · refreshing page…`
              : 'Scan completed · refreshing page…'}
          </span>
        </div>
      )}

      {scan.kind === 'error' && (
        <div className="mt-3 px-3 py-2 rounded-sm bg-tier-high/10 border border-tier-high/40">
          <div className="flex items-start gap-2">
            <AlertTriangle size={12} className="text-tier-high shrink-0 mt-0.5" />
            <div className="flex-1 min-w-0">
              <div className="font-mono text-2xs text-tier-high uppercase tracking-wider mb-1">
                {scan.title}
              </div>
              <div className="text-xs text-fg-dim leading-relaxed">{scan.detail}</div>
              <div className="mt-2 flex items-center gap-3 flex-wrap">
                {scan.canRetry && (
                  <button
                    type="button"
                    onClick={handleRescan}
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
                  href={workspaceUrl(platform, externalId)}
                  className="inline-flex items-center gap-1 font-mono text-2xs text-fg-dim hover:text-fg uppercase tracking-wider"
                >
                  Open in scan workspace <ExternalLink size={10} />
                </Link>
              </div>
            </div>
            <button
              type="button"
              onClick={() => setScan({ kind: 'idle' })}
              className="text-fg-mute hover:text-fg shrink-0"
              aria-label="Dismiss"
            >
              <X size={11} />
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

/** Map any thrown error into the user-facing error state, with actionable copy. */
function toErrorState(err: unknown, platform: string, externalId: string): ScanState {
  if (err instanceof ApiError) {
    const detail = err.message || 'No detail returned.';
    switch (err.status) {
      case 401:
        return {
          kind: 'error',
          title: 'Session expired',
          detail: 'Your session timed out. Log in again and re-try the scan.',
          canRetry: false,
        };
      case 402:
        return {
          kind: 'error',
          title: 'Out of credits',
          detail: 'You have no scan credits left. Visit Settings → Billing to top up or subscribe.',
          canRetry: false,
        };
      case 404:
        return {
          kind: 'error',
          title: 'Channel not found',
          detail: `${platform} could not resolve channel "${externalId}". It may have been deleted, renamed, or made private.`,
          canRetry: false,
        };
      case 429:
        return {
          kind: 'error',
          title: 'Rate limited',
          detail: 'Too many scans in a short window. Wait a minute and try again.',
          canRetry: true,
        };
      case 503:
        return {
          kind: 'error',
          title: 'Scan service unavailable',
          detail: detail.includes('YouTube API key')
            ? 'The API server is missing its YouTube API key (OMI_YOUTUBE_API_KEY). Set that env var on the api service in Render and redeploy.'
            : detail,
          canRetry: false,
        };
      case 502:
      case 504:
        return {
          kind: 'error',
          title: 'Gateway timeout',
          detail: 'The scan took longer than the proxy allows. It may still be running — reload the page in 30 seconds.',
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
      detail: 'Could not reach the API. Check your connection and retry. If you are on Render free tier, the API may be cold-starting — wait 30 s and try again.',
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
