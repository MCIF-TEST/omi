'use client';

import { useMemo, useState } from 'react';
import { type GraphEdge, type GraphNode, type Tier } from '@/lib/api';

/**
 * Radial SVG graph view. Focal account at center, neighbors arrayed
 * around it in concentric rings sorted by tie-strength. Nodes colored
 * by Louvain community; ring assignment is BFS-based (1-hop inner, 2+
 * hop outer).
 *
 * Zero dependencies, no physics, deterministic placement — but with
 * glow, curved edges, hover-tracing, and a live focal pulse.
 */

interface Props {
  focal: string;
  nodes: GraphNode[];
  edges: GraphEdge[];
  onSelect?: (node: GraphNode) => void;
}

// Brand-aligned community palette
const COMMUNITY_COLORS = [
  '#3b8eff', '#8b5cf6', '#22d3a8', '#f472b6',
  '#fb8c3c', '#facc15', '#6ba9ff', '#a78bfa',
];

const TIER_HALO: Record<Tier, string> = {
  low:      'rgba(34, 211, 168, 0.30)',
  moderate: 'rgba(245, 182, 47, 0.42)',
  elevated: 'rgba(251, 140, 60, 0.55)',
  high:     'rgba(251, 59, 107, 0.65)',
};

export function RadialGraph({ focal, nodes, edges, onSelect }: Props) {
  const [hoverId, setHoverId] = useState<string | null>(null);

  const layout = useMemo(() => computeLayout(focal, nodes, edges), [focal, nodes, edges]);

  // Adjacency for hover-tracing
  const neighbors = useMemo(() => {
    const m: Record<string, Set<string>> = {};
    for (const e of edges) {
      (m[e.a] ||= new Set()).add(e.b);
      (m[e.b] ||= new Set()).add(e.a);
    }
    return m;
  }, [edges]);

  if (nodes.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center gap-3 py-20 rounded-2xl border border-border-1 bg-bg-deep">
        <div className="w-12 h-12 rounded-2xl border border-border-2 bg-bg-elev flex items-center justify-center text-fg-faint">
          <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
            <circle cx="12" cy="12" r="3" /><circle cx="5" cy="6" r="2" /><circle cx="19" cy="6" r="2" />
            <circle cx="5" cy="18" r="2" /><circle cx="19" cy="18" r="2" />
            <path d="M7 7l3 3M17 7l-3 3M7 17l3-3M17 17l-3-3" />
          </svg>
        </div>
        <p className="text-center text-fg-mute font-mono text-2xs tracking-[0.18em] uppercase">
          No coordination edges yet for this account.
        </p>
      </div>
    );
  }

  const { positions, ringSize } = layout;
  const W = 720;
  const H = Math.max(560, ringSize.outer * 2 + 80);
  const cx = W / 2;
  const cy = H / 2;

  const isActive = (id: string) =>
    !hoverId || hoverId === id || neighbors[hoverId]?.has(id);

  return (
    <div className="relative">
      <svg
        viewBox={`0 0 ${W} ${H}`}
        width="100%"
        height={H}
        className="rounded-2xl border border-border-1"
        role="img"
        aria-label="Coordination network"
      >
        <defs>
          {/* Deep-space background */}
          <radialGradient id="rg-bg" cx="50%" cy="50%" r="70%">
            <stop offset="0%"   stopColor="#0a1020" />
            <stop offset="60%"  stopColor="#05070f" />
            <stop offset="100%" stopColor="#030409" />
          </radialGradient>
          {/* Node glow */}
          <filter id="rg-glow" x="-80%" y="-80%" width="260%" height="260%">
            <feGaussianBlur in="SourceGraphic" stdDeviation="4" result="b" />
            <feMerge><feMergeNode in="b" /><feMergeNode in="SourceGraphic" /></feMerge>
          </filter>
          <filter id="rg-glow-focal" x="-120%" y="-120%" width="340%" height="340%">
            <feGaussianBlur in="SourceGraphic" stdDeviation="7" result="b" />
            <feMerge><feMergeNode in="b" /><feMergeNode in="SourceGraphic" /></feMerge>
          </filter>
        </defs>

        {/* Background */}
        <rect x="0" y="0" width={W} height={H} fill="url(#rg-bg)" />

        {/* Concentric guide rings */}
        <circle cx={cx} cy={cy} r={ringSize.inner} fill="none" stroke="rgba(59,142,255,0.14)" strokeDasharray="2 6" />
        <circle cx={cx} cy={cy} r={ringSize.outer} fill="none" stroke="rgba(59,142,255,0.09)" strokeDasharray="2 7" />
        {/* Radial spokes (faint) */}
        <g stroke="rgba(59,142,255,0.05)" strokeWidth="0.5">
          {Array.from({ length: 12 }).map((_, i) => {
            const a = (i / 12) * Math.PI * 2;
            return (
              <line key={i}
                x1={cx} y1={cy}
                x2={cx + Math.cos(a) * ringSize.outer}
                y2={cy + Math.sin(a) * ringSize.outer}
              />
            );
          })}
        </g>

        {/* Edges — curved, bundled toward center */}
        <g>
          {edges.map((e, i) => {
            const pa = positions[e.a];
            const pb = positions[e.b];
            if (!pa || !pb) return null;
            const active = isActive(e.a) && isActive(e.b);
            const traced = hoverId && (hoverId === e.a || hoverId === e.b);
            const ax = cx + pa.x, ay = cy + pa.y;
            const bx = cx + pb.x, by = cy + pb.y;
            // Control point: midpoint pulled 18% toward center for organic bundling
            const mx = (ax + bx) / 2, my = (ay + by) / 2;
            const qx = mx + (cx - mx) * 0.18;
            const qy = my + (cy - my) * 0.18;
            const baseOpacity = hoverId ? (active ? 1 : 0.07) : 1;
            const stroke = traced ? 'rgba(107,169,255,' : 'rgba(120,150,210,';
            return (
              <path
                key={i}
                d={`M${ax},${ay} Q${qx},${qy} ${bx},${by}`}
                fill="none"
                stroke={`${stroke}${(0.14 + e.strength * 0.6).toFixed(2)})`}
                strokeWidth={(0.6 + e.strength * 3) * (traced ? 1.5 : 1)}
                strokeOpacity={baseOpacity}
                strokeLinecap="round"
                style={{ transition: 'stroke-opacity 0.2s ease, stroke-width 0.2s ease' }}
              />
            );
          })}
        </g>

        {/* Nodes */}
        {nodes.map((n) => {
          const p = positions[n.external_id];
          if (!p) return null;
          const isFocal = n.external_id === focal;
          const r = isFocal ? 17 : 9;
          const fill = COMMUNITY_COLORS[n.community_id % COMMUNITY_COLORS.length];
          const halo = n.tier ? TIER_HALO[n.tier] : 'rgba(120, 150, 210, 0.22)';
          const hovered = hoverId === n.external_id;
          const active = isActive(n.external_id);
          const tx = cx + p.x, ty = cy + p.y;
          return (
            <g
              key={n.external_id}
              transform={`translate(${tx}, ${ty})`}
              style={{ cursor: 'pointer', opacity: active ? 1 : 0.25, transition: 'opacity 0.2s ease' }}
              onMouseEnter={() => setHoverId(n.external_id)}
              onMouseLeave={() => setHoverId(null)}
              onClick={() => onSelect?.(n)}
            >
              {/* Focal ripple rings */}
              {isFocal && (
                <>
                  <circle r={r} fill="none" stroke="var(--accent)" strokeWidth="1.5"
                    style={{ transformOrigin: 'center', animation: 'hv-ripple 2.6s ease-out infinite' }} />
                  <circle r={r} fill="none" stroke="var(--accent)" strokeWidth="1"
                    style={{ transformOrigin: 'center', animation: 'hv-ripple 2.6s ease-out infinite', animationDelay: '1.3s' }} />
                </>
              )}
              {/* tier halo */}
              <circle r={r + (hovered ? 9 : 6)} fill={halo} style={{ transition: 'r 0.2s ease' }} />
              {/* node body */}
              <circle
                r={r}
                fill={fill}
                stroke={isFocal ? 'var(--accent-2)' : '#05070f'}
                strokeWidth={isFocal ? 2.5 : 1.5}
                filter={isFocal ? 'url(#rg-glow-focal)' : hovered ? 'url(#rg-glow)' : undefined}
                style={isFocal ? { animation: 'hv-node-pulse 3s ease-in-out infinite' } : undefined}
              />
              {/* inner highlight */}
              <circle r={r * 0.4} cx={-r * 0.25} cy={-r * 0.25} fill="rgba(255,255,255,0.35)" />
              {(isFocal || hovered) && (
                <text
                  y={r + 17}
                  textAnchor="middle"
                  fill="var(--text)"
                  fontSize={12}
                  fontWeight={isFocal ? 600 : 400}
                  fontFamily="JetBrains Mono, monospace"
                  style={{ paintOrder: 'stroke', stroke: '#05070f', strokeWidth: 3 }}
                >
                  {truncate(n.handle, 22)}
                </text>
              )}
            </g>
          );
        })}
      </svg>

      {/* Legend */}
      <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-2 font-mono text-2xs uppercase tracking-wider text-fg-mute">
        <LegendDot color={COMMUNITY_COLORS[0]} label="community 0" />
        <LegendDot color={COMMUNITY_COLORS[1]} label="community 1" />
        <LegendDot color={COMMUNITY_COLORS[2]} label="community 2" />
        <span className="text-border-2">·</span>
        <span><span className="inline-block w-3 h-3 rounded-full mr-1 align-middle" style={{ background: TIER_HALO.high }} /> high halo</span>
        <span><span className="inline-block w-3 h-3 rounded-full mr-1 align-middle" style={{ background: TIER_HALO.elevated }} /> elevated</span>
        <span className="text-border-2">·</span>
        <span>edge = coordination strength</span>
      </div>
    </div>
  );
}

function LegendDot({ color, label }: { color: string; label: string }) {
  return (
    <span>
      <span
        className="inline-block w-3 h-3 rounded-full mr-1 align-middle"
        style={{ background: color, boxShadow: `0 0 6px ${color}99` }}
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
