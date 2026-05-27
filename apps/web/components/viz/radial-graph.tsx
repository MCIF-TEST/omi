'use client';

import { useMemo, useState } from 'react';
import { type GraphEdge, type GraphNode, type Tier } from '@/lib/api';

/**
 * Radial SVG graph view. Focal account at center, neighbors arrayed
 * around it in concentric rings sorted by tie-strength. Nodes colored
 * by Louvain community; ring assignment is BFS-based (1-hop inner, 2+
 * hop outer).
 *
 * Phase 5 will swap this for a Cytoscape canvas with force-directed
 * layout. For now this is intentionally light: zero dependencies, no
 * physics, deterministic placement.
 */

interface Props {
  focal: string;
  nodes: GraphNode[];
  edges: GraphEdge[];
  onSelect?: (node: GraphNode) => void;
}

const COMMUNITY_COLORS = [
  '#22d3ee', '#a78bfa', '#f472b6', '#fb923c',
  '#facc15', '#34d399', '#60a5fa', '#f87171',
];

const TIER_HALO: Record<Tier, string> = {
  low:      'rgba(16, 185, 129, 0.30)',
  moderate: 'rgba(245, 158, 11, 0.40)',
  elevated: 'rgba(251, 146, 60, 0.55)',
  high:     'rgba(239, 68, 68, 0.65)',
};

export function RadialGraph({ focal, nodes, edges, onSelect }: Props) {
  const [hoverId, setHoverId] = useState<string | null>(null);

  const layout = useMemo(() => {
    return computeLayout(focal, nodes, edges);
  }, [focal, nodes, edges]);

  if (nodes.length === 0) {
    return (
      <div className="text-center py-16 text-fg-mute font-mono text-2xs tracking-[0.18em] uppercase">
        No coordination edges yet for this account.
      </div>
    );
  }

  const { positions, ringSize } = layout;
  const W = 720;
  const H = Math.max(560, ringSize.outer * 2 + 80);
  const cx = W / 2;
  const cy = H / 2;

  return (
    <div className="relative">
      <svg
        viewBox={`0 0 ${W} ${H}`}
        width="100%"
        height={H}
        className="bg-bg-deep rounded-md border border-border-1"
        role="img"
        aria-label="Coordination network"
      >
        {/* Concentric guide rings */}
        <circle cx={cx} cy={cy} r={ringSize.inner} fill="none" stroke="var(--border)" strokeDasharray="2 4" />
        <circle cx={cx} cy={cy} r={ringSize.outer} fill="none" stroke="var(--border)" strokeDasharray="2 4" />

        {/* Edges */}
        {edges.map((e, i) => {
          const pa = positions[e.a];
          const pb = positions[e.b];
          if (!pa || !pb) return null;
          const dim = hoverId && hoverId !== e.a && hoverId !== e.b ? 0.18 : 1;
          return (
            <line
              key={i}
              x1={cx + pa.x}
              y1={cy + pa.y}
              x2={cx + pb.x}
              y2={cy + pb.y}
              stroke={`rgba(168, 184, 216, ${0.15 + e.strength * 0.6})`}
              strokeWidth={0.6 + e.strength * 2.5}
              strokeOpacity={dim}
            />
          );
        })}

        {/* Nodes */}
        {nodes.map((n) => {
          const p = positions[n.external_id];
          if (!p) return null;
          const isFocal = n.external_id === focal;
          const r = isFocal ? 16 : 9;
          const fill = COMMUNITY_COLORS[n.community_id % COMMUNITY_COLORS.length];
          const halo = n.tier ? TIER_HALO[n.tier] : 'rgba(168, 184, 216, 0.2)';
          const hovered = hoverId === n.external_id;
          return (
            <g
              key={n.external_id}
              transform={`translate(${cx + p.x}, ${cy + p.y})`}
              style={{ cursor: 'pointer' }}
              onMouseEnter={() => setHoverId(n.external_id)}
              onMouseLeave={() => setHoverId(null)}
              onClick={() => onSelect?.(n)}
            >
              {/* tier halo */}
              <circle r={r + 6} fill={halo} />
              <circle
                r={r}
                fill={fill}
                stroke={isFocal ? 'var(--accent-2)' : 'var(--bg-deep)'}
                strokeWidth={isFocal ? 2 : 1.5}
              />
              {(isFocal || hovered) && (
                <text
                  y={r + 16}
                  textAnchor="middle"
                  fill="var(--text)"
                  fontSize={12}
                  fontFamily="JetBrains Mono, monospace"
                >
                  {truncate(n.handle, 22)}
                </text>
              )}
            </g>
          );
        })}
      </svg>

      {/* Legend */}
      <div className="mt-3 flex flex-wrap gap-x-4 gap-y-2 font-mono text-2xs uppercase tracking-wider text-fg-mute">
        <LegendDot color={COMMUNITY_COLORS[0]} label="community 0" />
        <LegendDot color={COMMUNITY_COLORS[1]} label="community 1" />
        <LegendDot color={COMMUNITY_COLORS[2]} label="community 2" />
        <span className="mx-2">·</span>
        <span><span className="inline-block w-3 h-3 rounded-full mr-1 align-middle" style={{ background: TIER_HALO.high }} /> high tier halo</span>
        <span><span className="inline-block w-3 h-3 rounded-full mr-1 align-middle" style={{ background: TIER_HALO.elevated }} /> elevated</span>
        <span>edge thickness = coordination strength</span>
      </div>
    </div>
  );
}

function LegendDot({ color, label }: { color: string; label: string }) {
  return (
    <span>
      <span
        className="inline-block w-3 h-3 rounded-full mr-1 align-middle"
        style={{ background: color }}
      />
      {label}
    </span>
  );
}

function truncate(s: string, n: number) {
  return s.length <= n ? s : s.slice(0, n - 1) + '…';
}

// ---------------------------------------------------------------------------
// Layout computation — deterministic radial placement
// ---------------------------------------------------------------------------

interface LayoutResult {
  positions: Record<string, { x: number; y: number }>;
  ringSize: { inner: number; outer: number };
}

function computeLayout(
  focal: string, nodes: GraphNode[], edges: GraphEdge[],
): LayoutResult {
  // Build adjacency to BFS hop distance from focal
  const adj: Record<string, string[]> = {};
  for (const e of edges) {
    (adj[e.a] ||= []).push(e.b);
    (adj[e.b] ||= []).push(e.a);
  }
  const hop: Record<string, number> = { [focal]: 0 };
  const queue: string[] = [focal];
  while (queue.length) {
    const cur = queue.shift()!;
    for (const nb of adj[cur] || []) {
      if (!(nb in hop)) {
        hop[nb] = hop[cur] + 1;
        queue.push(nb);
      }
    }
  }
  const ring1 = nodes.filter((n) => hop[n.external_id] === 1);
  const ring2 = nodes.filter((n) => hop[n.external_id] >= 2);
  const orphans = nodes.filter((n) => !(n.external_id in hop) && n.external_id !== focal);

  // Place focal at center, ring1 inner radius, ring2 outer radius
  const inner = 130;
  const outer = inner + 110 + Math.min(60, ring2.length * 3);

  // Order ring1 by total incident edge strength (descending) for a tidy spread
  const edgeStrength: Record<string, number> = {};
  for (const e of edges) {
    edgeStrength[e.a] = (edgeStrength[e.a] || 0) + e.strength;
    edgeStrength[e.b] = (edgeStrength[e.b] || 0) + e.strength;
  }
  ring1.sort((a, b) => (edgeStrength[b.external_id] || 0) - (edgeStrength[a.external_id] || 0));
  ring2.sort((a, b) => a.community_id - b.community_id);

  const positions: Record<string, { x: number; y: number }> = {
    [focal]: { x: 0, y: 0 },
  };
  placeOnRing(ring1, inner, positions);
  placeOnRing(ring2, outer, positions);
  placeOnRing(orphans, outer + 50, positions);

  return { positions, ringSize: { inner, outer } };
}

function placeOnRing(
  ring: { external_id: string }[],
  r: number,
  out: Record<string, { x: number; y: number }>,
) {
  if (ring.length === 0) return;
  for (let i = 0; i < ring.length; i++) {
    const angle = (i / ring.length) * Math.PI * 2 - Math.PI / 2;
    out[ring[i].external_id] = {
      x: Math.cos(angle) * r,
      y: Math.sin(angle) * r,
    };
  }
}
