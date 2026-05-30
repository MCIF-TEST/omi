'use client';

import { useMemo, useState } from 'react';
import { Filter } from 'lucide-react';
import { cn } from '@/lib/cn';
import { TierBadge } from '@/components/shared/tier-badge';
import { ProbabilityBar } from '@/components/shared/probability-bar';
import { type CommenterScanResult, type Tier } from '@/lib/api';

interface Props {
  commenters: CommenterScanResult[];
  selectedId: string | null;
  onSelect: (c: CommenterScanResult) => void;
}

const TIER_RANK: Record<Tier, number> = { high: 4, elevated: 3, moderate: 2, low: 1 };
const FILTERS: Array<{ key: 'all' | Tier; label: string }> = [
  { key: 'all', label: 'All' },
  { key: 'high', label: 'High' },
  { key: 'elevated', label: 'Elevated' },
  { key: 'moderate', label: 'Moderate' },
];

export function CommenterList({ commenters, selectedId, onSelect }: Props) {
  const [filter, setFilter] = useState<'all' | Tier>('all');
  const [q, setQ] = useState('');

  const visible = useMemo(() => {
    let list = [...commenters];
    if (filter !== 'all') list = list.filter((c) => c.tier === filter);
    if (q.trim()) {
      const needle = q.trim().toLowerCase();
      list = list.filter((c) => (c.handle || '').toLowerCase().includes(needle));
    }
    list.sort((a, b) => {
      if (!!a.error !== !!b.error) return a.error ? 1 : -1;
      const tr = (TIER_RANK[b.tier] || 0) - (TIER_RANK[a.tier] || 0);
      if (tr) return tr;
      const ap = a.coordination_adjusted_probability ?? a.overall_probability ?? 0;
      const bp = b.coordination_adjusted_probability ?? b.overall_probability ?? 0;
      return bp - ap;
    });
    return list;
  }, [commenters, filter, q]);

  return (
    <div className="flex flex-col h-full">
      <div className="p-3 border-b border-border-1 space-y-2">
        <div className="flex items-center gap-1 flex-wrap">
          {FILTERS.map((f) => {
            const count =
              f.key === 'all'
                ? commenters.length
                : commenters.filter((c) => c.tier === f.key).length;
            return (
              <button
                key={f.key}
                onClick={() => setFilter(f.key)}
                className={cn(
                  'font-mono text-2xs tracking-wider uppercase px-2 py-1 rounded-sm border transition-colors',
                  filter === f.key
                    ? 'border-accent-dim bg-accent/10 text-accent'
                    : 'border-border-2 text-fg-dim hover:text-fg',
                )}
              >
                {f.label} <span className="text-fg-mute">{count}</span>
              </button>
            );
          })}
        </div>
        <div className="relative">
          <Filter size={12} className="absolute left-2 top-1/2 -translate-y-1/2 text-fg-mute" />
          <input
            aria-label="Filter commenters by handle"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="filter by handle…"
            className="w-full h-8 pl-7 pr-2 bg-bg border border-border-2 rounded-sm font-mono text-xs text-fg placeholder:text-fg-mute focus:border-accent-dim focus:outline-none"
          />
        </div>
      </div>
      <div className="flex-1 overflow-y-auto">
        {visible.length === 0 && (
          <div className="px-4 py-8 text-center font-mono text-2xs tracking-wider text-fg-mute uppercase">
            No commenters match.
          </div>
        )}
        {visible.map((c) => {
          const selected = c.external_id === selectedId;
          const adjusted = c.coordination_adjusted_probability;
          const displayProb = adjusted ?? c.overall_probability ?? 0;
          return (
            <button
              key={c.external_id}
              onClick={() => onSelect(c)}
              className={cn(
                'w-full text-left px-3 py-2.5 border-b border-border-1 transition-colors block',
                selected
                  ? 'bg-bg-elev border-l-2 border-l-accent -ml-px pl-[10px]'
                  : 'hover:bg-bg-elev/60 border-l-2 border-l-transparent -ml-px pl-[10px]',
              )}
            >
              <div className="flex items-center justify-between gap-2 mb-1">
                <span className="font-medium text-sm text-fg truncate">
                  {c.handle || c.external_id}
                </span>
                <TierBadge tier={c.tier} size="sm" />
              </div>
              <div className="flex items-center justify-between gap-2">
                <ProbabilityBar
                  value={displayProb}
                  tier={c.tier}
                  size="sm"
                  showLabel={false}
                  className="flex-1"
                />
                <span className="font-mono text-2xs text-fg-dim w-9 text-right">
                  {Math.round(displayProb * 100)}%
                </span>
              </div>
              {c.intent_label && c.tier !== 'low' && (
                <div className="mt-1 font-mono text-2xs text-fg-mute truncate">
                  ▸ {c.intent_label}
                </div>
              )}
            </button>
          );
        })}
      </div>
    </div>
  );
}
