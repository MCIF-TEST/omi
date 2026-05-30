'use client';

import { useState } from 'react';
import { MousePointerClick, ArrowRight } from 'lucide-react';
import { type AccountSubgraphResponse, type GraphNode, type Tier } from '@/lib/api';
import { RadialGraph } from '@/components/viz/radial-graph';
import { ScoreRing } from '@/components/shared/score-ring';
import { TierBadge } from '@/components/shared/tier-badge';

/**
 * Client wrapper around the SVG graph. Manages selection state and the
 * inline detail panel.
 */
export function RadialGraphIsland({ data }: { data: AccountSubgraphResponse }) {
  const [selected, setSelected] = useState<GraphNode | null>(null);
  return (
    <div className="grid grid-cols-1 lg:grid-cols-[1fr_300px] gap-4">
      <RadialGraph
        focal={data.focal}
        nodes={data.nodes}
        edges={data.edges}
        onSelect={(n) => setSelected(n)}
      />
      <aside className="relative overflow-hidden bg-bg-elev border border-border-1 rounded-2xl p-5 shadow-card min-h-[280px]">
        {selected ? (
          <div className="animate-fade-up">
            <div className="relative">
              <div className="font-mono text-2xs tracking-[0.2em] text-accent-2 uppercase mb-4">
                Selected node
              </div>

              <div className="flex items-center gap-4 mb-4">
                <ScoreRing
                  value={selected.last_score ?? 0}
                  tier={(selected.tier as Tier) ?? null}
                  size={68}
                  stroke={6}
                />
                <div className="min-w-0">
                  <div className="text-sm text-fg font-semibold break-words leading-tight">
                    {selected.handle}
                  </div>
                  {selected.display_name && (
                    <div className="text-xs text-fg-dim mt-0.5 truncate">{selected.display_name}</div>
                  )}
                  {selected.tier && (
                    <div className="mt-1.5">
                      <TierBadge tier={selected.tier as Tier} size="sm" />
                    </div>
                  )}
                </div>
              </div>

              <div className="font-mono text-2xs text-fg-faint mb-4 break-all bg-bg rounded-lg border border-border-1 px-2.5 py-1.5">
                {selected.external_id}
              </div>

              <dl className="space-y-px rounded-lg overflow-hidden border border-border-1">
                <Row label="Tier"  value={selected.tier ?? '—'} />
                <Row label="Score" value={selected.last_score != null ? `${Math.round(selected.last_score * 100)}%` : '—'} />
                <Row label="Community" value={`#${selected.community_id}`} />
              </dl>

              <a
                href={`/accounts/${encodeURIComponent(selected.external_id)}?platform=youtube`}
                className="group mt-4 inline-flex items-center gap-1.5 text-2xs font-mono uppercase tracking-wider text-accent hover:text-accent-2 transition-colors"
              >
                Open full history
                <ArrowRight size={12} className="group-hover:translate-x-0.5 transition-transform" />
              </a>
            </div>
          </div>
        ) : (
          <div className="flex flex-col items-center justify-center text-center gap-3 h-full py-10">
            <div className="w-11 h-11 rounded-2xl border border-border-2 bg-bg-elev-2 flex items-center justify-center text-fg-mute">
              <MousePointerClick size={18} />
            </div>
            <p className="text-xs text-fg-mute leading-relaxed max-w-[24ch]">
              Click any node to inspect its tier, score, and community assignment.
            </p>
          </div>
        )}
      </aside>
    </div>
  );
}

function Row({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex justify-between gap-2 bg-bg px-3 py-2">
      <dt className="font-mono text-2xs tracking-[0.16em] text-fg-mute uppercase">{label}</dt>
      <dd className="text-fg text-sm font-mono">{value}</dd>
    </div>
  );
}
