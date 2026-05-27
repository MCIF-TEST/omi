'use client';

import { useState } from 'react';
import { type AccountSubgraphResponse, type GraphNode } from '@/lib/api';
import { RadialGraph } from '@/components/viz/radial-graph';

/**
 * Client wrapper around the SVG graph. Manages selection state and the
 * inline detail panel.
 */
export function RadialGraphIsland({ data }: { data: AccountSubgraphResponse }) {
  const [selected, setSelected] = useState<GraphNode | null>(null);
  return (
    <div className="grid grid-cols-1 lg:grid-cols-[1fr_280px] gap-4">
      <RadialGraph
        focal={data.focal}
        nodes={data.nodes}
        edges={data.edges}
        onSelect={(n) => setSelected(n)}
      />
      <aside className="bg-bg border border-border-1 rounded-md p-4">
        {selected ? (
          <>
            <div className="font-mono text-2xs tracking-[0.18em] text-fg-mute uppercase mb-2">
              Selected
            </div>
            <div className="text-sm text-fg font-semibold mb-1 break-words">{selected.handle}</div>
            {selected.display_name && (
              <div className="text-xs text-fg-dim mb-2">{selected.display_name}</div>
            )}
            <div className="font-mono text-2xs text-fg-faint mb-3 break-all">{selected.external_id}</div>
            <dl className="text-xs space-y-2">
              <Row label="Tier"  value={selected.tier ?? '—'} />
              <Row label="Score" value={selected.last_score != null ? `${Math.round(selected.last_score * 100)}%` : '—'} />
              <Row label="Community" value={`#${selected.community_id}`} />
            </dl>
            <a
              href={`/accounts/${encodeURIComponent(selected.external_id)}?platform=youtube`}
              className="mt-3 inline-block text-2xs font-mono uppercase tracking-wider text-accent hover:text-accent-2"
            >
              Open history →
            </a>
          </>
        ) : (
          <div className="text-xs text-fg-mute">
            Click a node to inspect its tier, score, and community assignment.
          </div>
        )}
      </aside>
    </div>
  );
}

function Row({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex justify-between gap-2">
      <dt className="font-mono text-2xs tracking-[0.16em] text-fg-mute uppercase">{label}</dt>
      <dd className="text-fg">{value}</dd>
    </div>
  );
}
