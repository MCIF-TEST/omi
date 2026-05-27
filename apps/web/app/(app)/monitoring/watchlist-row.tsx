'use client';

import { useState } from 'react';
import Link from 'next/link';
import { X, ExternalLink } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { TierBadge } from '@/components/shared/tier-badge';
import { apiClient, type WatchlistOut, type Tier } from '@/lib/api';
import { timeAgo } from '@/lib/format';

interface Props {
  w: WatchlistOut;
  onChange: () => void;
}

export function WatchlistRow({ w, onChange }: Props) {
  const [pending, setPending] = useState(false);

  const remove = async () => {
    if (!confirm(`Remove "${w.label}" from your watchlist?`)) return;
    setPending(true);
    try {
      await apiClient(`/v1/watchlists/${w.id}`, { method: 'DELETE' });
      onChange();
    } catch {/* no-op */}
    setPending(false);
  };

  return (
    <li className="px-2 py-3 flex items-center justify-between gap-3 flex-wrap">
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-3 mb-1 flex-wrap">
          <span className="font-medium text-fg truncate">{w.label}</span>
          {w.last_seen_tier && <TierBadge tier={w.last_seen_tier as Tier} size="sm" />}
          <span className="font-mono text-2xs text-fg-mute uppercase tracking-wider">
            alert at {w.alert_threshold_tier}+
          </span>
        </div>
        <div className="font-mono text-2xs text-fg-faint">
          {w.target_id} ·{' '}
          {w.last_checked_at
            ? `checked ${timeAgo(w.last_checked_at)}`
            : 'never checked'}
          {w.last_seen_probability != null && (
            <> · {Math.round(w.last_seen_probability * 100)}% last</>
          )}
        </div>
      </div>
      <div className="flex items-center gap-2">
        <Link
          href={`/accounts/${encodeURIComponent(w.target_id)}?platform=youtube`}
          className="inline-flex items-center gap-1 font-mono text-2xs tracking-wider uppercase text-fg-dim hover:text-fg"
        >
          History <ExternalLink size={10} />
        </Link>
        <Button variant="ghost" size="sm" onClick={remove} disabled={pending} aria-label="Remove">
          <X size={12} />
        </Button>
      </div>
    </li>
  );
}
