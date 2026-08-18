'use client';

import { useCallback } from 'react';
import { Activity, Bell, Eye, Loader2, RefreshCw } from 'lucide-react';
import { Card, CardLabel, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { apiClient, type AlertsResponse, type FeedResponse, type WatchlistsResponse } from '@/lib/api';
import { cn } from '@/lib/cn';
import { usePolling } from '@/lib/use-polling';
import { timeAgo } from '@/lib/format';
import { WatchlistForm } from './watchlist-form';
import { WatchlistRow } from './watchlist-row';
import { ConsoleHeader, SECTION_INDEX } from '@/components/shared/console-header';

const FEED_INTERVAL = 30_000;     // 30s
const ALERTS_INTERVAL = 60_000;   // 60s
const WATCHLIST_INTERVAL = 120_000;

export function MonitoringClient() {
  const feed = usePolling<FeedResponse>(
    useCallback(() => apiClient<FeedResponse>('/v1/monitoring/feed?hours=24&limit=30'), []),
    FEED_INTERVAL,
  );
  const alerts = usePolling<AlertsResponse>(
    useCallback(() => apiClient<AlertsResponse>('/v1/monitoring/alerts?limit=50'), []),
    ALERTS_INTERVAL,
  );
  const watchlists = usePolling<WatchlistsResponse>(
    useCallback(() => apiClient<WatchlistsResponse>('/v1/watchlists'), []),
    WATCHLIST_INTERVAL,
  );

  return (
    <div className="space-y-8">
      <ConsoleHeader
        index={SECTION_INDEX['/monitoring']}
        eyebrow="Operations · Live intelligence"
        title="Monitoring"
        lede="Narrative spikes, high-tier surges, and watchlist alerts. Polls every 30 seconds while this tab is open; pauses when you switch away."
        readout={
          // Lamp first, then the word, matching the sidebar rack and the health
          // pill. Refreshing is work in flight, so it gets the work lamp; idle
          // is steady green, not a pulsing dot.
          <span className="inline-flex items-center gap-2">
            <span className={feed.loading ? 'led led-work' : 'led led-ok'} />
            <span className="meta meta-hi">{feed.loading ? 'Refreshing' : 'Live'}</span>
          </span>
        }
      />

      {/* Live anomaly feed */}
      <Card>
        <div className="flex items-center justify-between mb-2 gap-2">
          <CardLabel className="m-0 flex items-center gap-1.5">
            <Activity size={11} /> Live anomaly feed
          </CardLabel>
          <Button variant="ghost" size="sm" onClick={() => feed.refresh()}>
            <RefreshCw size={12} /> Refresh
          </Button>
        </div>
        {(feed.data?.items?.length ?? 0) === 0 ? (
          <p className="text-sm text-fg-dim">
            No anomalies in the last 24 hours. The detector pass runs every 5
            minutes when enabled on the server. Spikes and surges appear here
            as they&apos;re detected.
          </p>
        ) : (
          <ul className="divide-y divide-border-1 -mx-2">
            {feed.data!.items.map((a) => (
              <li key={a.id} className="px-2 py-3">
                <div className="flex items-baseline gap-3 mb-1 flex-wrap">
                  <span className={cn(
                    'font-mono text-2xs tracking-wider uppercase',
                    a.severity === 'high' ? 'text-danger'
                      : a.severity === 'elevated' ? 'text-warn' : 'text-accent-text',
                  )}>
                    {a.kind.replace(/_/g, ' ')}
                  </span>
                  <span className="font-mono text-2xs tracking-wider uppercase text-fg-mute">
                    {a.severity}
                  </span>
                  <span className="font-mono text-2xs tracking-wider uppercase text-fg-mute ml-auto">
                    {timeAgo(a.created_at)}
                  </span>
                </div>
                <p className="text-sm text-fg leading-relaxed">{a.message}</p>
              </li>
            ))}
          </ul>
        )}
      </Card>

      {/* Your alerts */}
      <Card>
        <div className="flex items-center justify-between mb-2 gap-2">
          <CardLabel className="m-0 flex items-center gap-1.5">
            <Bell size={11} /> Your alerts
            {alerts.data?.unread_count ? (
              <span className="ml-2 px-1.5 rounded-sm bg-danger/15 text-danger font-mono text-2xs tabular">
                {alerts.data.unread_count} unread
              </span>
            ) : null}
          </CardLabel>
          <Button variant="ghost" size="sm" onClick={() => alerts.refresh()}>
            <RefreshCw size={12} /> Refresh
          </Button>
        </div>
        {(alerts.data?.alerts?.length ?? 0) === 0 ? (
          <p className="text-sm text-fg-dim">
            No alerts yet. Add a watchlist below; you&apos;ll get notified when a
            watched channel&apos;s tier changes or crosses your threshold.
          </p>
        ) : (
          <ul className="divide-y divide-border-1 -mx-2">
            {alerts.data!.alerts.map((a) => (
              <li
                key={a.id}
                className={`px-2 py-3 ${a.read_at ? 'opacity-60' : ''}`}
              >
                <div className="flex items-baseline gap-3 mb-1 flex-wrap">
                  <span className={cn(
                    'font-mono text-2xs tracking-wider uppercase',
                    a.severity === 'high' ? 'text-danger'
                      : a.severity === 'elevated' ? 'text-warn' : 'text-accent-text',
                  )}>
                    {a.kind.replace(/_/g, ' ')}
                  </span>
                  <span className="font-mono text-2xs tracking-wider uppercase text-fg-mute">
                    {a.severity}
                  </span>
                  <span className="font-mono text-2xs tracking-wider uppercase text-fg-mute ml-auto">
                    {timeAgo(a.created_at)}
                  </span>
                </div>
                <p className="text-sm text-fg leading-relaxed">{a.message}</p>
                {!a.read_at && (
                  <Button
                    variant="ghost"
                    size="sm"
                    className="mt-2"
                    onClick={async () => {
                      await apiClient(`/v1/monitoring/alerts/${a.id}/read`, { method: 'POST' });
                      alerts.refresh();
                    }}
                  >
                    Mark read
                  </Button>
                )}
              </li>
            ))}
          </ul>
        )}
      </Card>

      {/* Watchlists */}
      <Card>
        <CardLabel className="flex items-center gap-1.5 mb-3">
          <Eye size={11} /> Watchlists
        </CardLabel>
        <WatchlistForm onAdded={() => watchlists.refresh()} />
        <div className="mt-6">
          {(watchlists.data?.watchlists?.length ?? 0) === 0 ? (
            <p className="text-sm text-fg-dim">
              No watchlists yet. Add a YouTube channel or X account above.
              OMISPHERE tracks its tier and pings you when it changes.
            </p>
          ) : (
            <ul className="divide-y divide-border-1 -mx-2">
              {watchlists.data!.watchlists.map((w) => (
                <WatchlistRow key={w.id} w={w} onChange={() => watchlists.refresh()} />
              ))}
            </ul>
          )}
        </div>
      </Card>
    </div>
  );
}
