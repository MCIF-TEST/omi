'use client';

import { useState, useEffect } from 'react';
import {
  Eye, EyeOff, Download, ChevronDown,
} from 'lucide-react';
import { apiClient, type WatchlistOut, type WatchlistsResponse } from '@/lib/api';

interface Props {
  externalId: string;
  platform: string;
  handle: string;
  /** csvRows() returns the CSV body — pulled from the server-rendered history table. */
  csvRows: () => string;
}

export function AccountActions({ externalId, platform, handle, csvRows }: Props) {
  const [watch, setWatch] = useState<{ loading: boolean; existing: WatchlistOut | null }>({
    loading: true,
    existing: null,
  });
  const [exportOpen, setExportOpen] = useState(false);

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
        <div className="flex items-center gap-2 font-mono text-2xs tracking-wider uppercase text-fg-mute min-w-0">
          <span className="px-1.5 py-0.5 rounded-sm border border-border-2 text-fg-dim">
            {platform}
          </span>
          <span className="truncate max-w-[280px]">{handle || externalId}</span>
        </div>

        <div className="flex items-center gap-2 flex-wrap">
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
        </div>
      </div>
    </div>
  );
}
