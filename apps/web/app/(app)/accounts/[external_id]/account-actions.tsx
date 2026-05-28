'use client';

import { useState, useEffect } from 'react';
import {
  Zap, RefreshCw, AlertTriangle, CheckCircle2, X,
  Eye, EyeOff, Download, ChevronDown,
} from 'lucide-react';
import { apiClient, ApiError, type AccountScanOut, type WatchlistOut, type WatchlistsResponse } from '@/lib/api';

type ScanState =
  | { kind: 'idle' }
  | { kind: 'loading'; stage: string }
  | { kind: 'success'; result: AccountScanOut }
  | { kind: 'error'; message: string };

interface Props {
  externalId: string;
  platform: string;
  handle: string;
  /** csvRows() returns the CSV body — pulled from the server-rendered history table. */
  csvRows: () => string;
}

export function AccountActions({ externalId, platform, handle, csvRows }: Props) {
  const [scan, setScan] = useState<ScanState>({ kind: 'idle' });
  const [watch, setWatch] = useState<{ loading: boolean; existing: WatchlistOut | null }>({
    loading: true,
    existing: null,
  });
  const [exportOpen, setExportOpen] = useState(false);

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

  /* ── RESCAN ── */
  async function handleRescan() {
    // Stage 1: kick off
    setScan({ kind: 'loading', stage: 'Resolving channel…' });

    // Animated progress hint — purely cosmetic, drives the eye
    const stages = [
      'Resolving channel…',
      'Fetching profile metadata…',
      'Pulling recent comments…',
      'Running detector pipeline…',
      'Computing coordination signals…',
    ];
    let i = 0;
    const tick = setInterval(() => {
      i = Math.min(i + 1, stages.length - 1);
      setScan((s) => (s.kind === 'loading' ? { kind: 'loading', stage: stages[i] } : s));
    }, 4000);

    try {
      const data = await apiClient<AccountScanOut>(`/v1/scan/${platform}/account`, {
        method: 'POST',
        body: JSON.stringify({
          account_url_or_handle: externalId,
          force_refresh: true,
        }),
      });
      clearInterval(tick);
      setScan({ kind: 'success', result: data });
      // Full reload after a short pause so the user reads the result
      // and so the new scan row definitely appears in the history table.
      setTimeout(() => {
        window.location.reload();
      }, 1800);
    } catch (err) {
      clearInterval(tick);
      const msg =
        err instanceof ApiError
          ? err.status === 402
            ? 'Out of credits — visit Settings to subscribe.'
            : err.status === 401
            ? 'Session expired — please log in again.'
            : err.status === 404
            ? `Channel ${externalId} could not be found on ${platform}.`
            : err.message
          : 'Network error. Check your connection and try again.';
      setScan({ kind: 'error', message: msg });
    }
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
        <div className="mt-3 flex items-center gap-2 px-3 py-2 rounded-sm bg-accent/10 border border-accent/30">
          <RefreshCw size={12} className="text-accent animate-spin shrink-0" />
          <span className="font-mono text-2xs text-accent uppercase tracking-wider">
            {scan.stage}
          </span>
          <span className="ml-auto font-mono text-2xs text-fg-mute">
            stay on this page · ~15-30s
          </span>
        </div>
      )}

      {scan.kind === 'success' && (
        <div className="mt-3 flex items-center gap-2 px-3 py-2 rounded-sm bg-tier-low/10 border border-tier-low/40">
          <CheckCircle2 size={12} className="text-tier-low shrink-0" />
          <span className="font-mono text-2xs text-tier-low uppercase tracking-wider">
            Updated · {Math.round(scan.result.overall_probability * 100)}% · {scan.result.tier} tier · refreshing page…
          </span>
        </div>
      )}

      {scan.kind === 'error' && (
        <div className="mt-3 flex items-start gap-2 px-3 py-2 rounded-sm bg-tier-high/10 border border-tier-high/40">
          <AlertTriangle size={12} className="text-tier-high shrink-0 mt-0.5" />
          <span className="font-mono text-2xs text-tier-high flex-1">{scan.message}</span>
          <button
            type="button"
            onClick={handleRescan}
            className="font-mono text-2xs text-accent hover:text-accent-2 uppercase tracking-wider"
          >
            Try again
          </button>
          <button
            type="button"
            onClick={() => setScan({ kind: 'idle' })}
            className="text-fg-mute hover:text-fg"
            aria-label="Dismiss"
          >
            <X size={11} />
          </button>
        </div>
      )}
    </div>
  );
}
