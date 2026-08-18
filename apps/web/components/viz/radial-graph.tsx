'use client';

import { useMemo, useState } from 'react';
import { type GraphEdge, type GraphNode, type Tier } from '@/lib/api';

/**
 * Link-analysis display. Focal account at the centre, neighbours arrayed on
 * labelled concentric rings sorted by tie strength. Node colour is the Louvain
 * community; ring assignment is BFS hop distance (1-hop inner, 2+ outer).
 *
 * Zero dependencies, no physics, deterministic placement.
 *
 * This used to render as a deep-space scene: a warm radial gradient ground, two
 * Gaussian-blur glow filters, glossy spheres with a specular bead, and an
 * animated ripple on the focal node. Every one of those is forbidden by the
 * design language at the top of globals.css (no glow, no gradient fills,
 * elevation by tone and hairline), and together they made the product's most
 * analytical surface its most decorative one. It now reads the way a link chart
 * in an analysis tool reads: flat ground, measured rings, square nodes, tier
 * carried by a ring stroke that survives being screenshotted.
 */

interface Props {
  focal: string;
  nodes: GraphNode[];
  edges: GraphEdge[];
  onSelect?: (node: GraphNode) => void;
}

/**
 * Community identity. These are the design system's own `--cluster-N` values,
 * read off the stylesheet rather than restated here: the palette exists exactly
 * for "persistent categorical hue per cluster" and this component was carrying
 * a private warm array that predated it, so a community was one colour in the
 * graph and a different one everywhere else it appeared.
 */
const COMMUNITY_VARS = [
  'var(--cluster-1)', 'var(--cluster-2)', 'var(--cluster-3)', 'var(--cluster-4)',
  'var(--cluster-5)', 'var(--cluster-6)', 'var(--cluster-7)', 'var(--cluster-8)',
];

/** Tier is a ring around the node, in the tier colour. A stroke stays legible
 *  in a screenshot and at print size; a blurred halo does not. */
const TIER_STROKE: Record<Tier, string> = {
  low:      'var(--tier-low)',
  moderate: 'var(--tier-moderate)',
  elevated: 'var(--tier-elevated)',
  high:     'var(--tier-high)',
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
      <div className="panel tick-frame flex flex-col items-center justify-center gap-3 py-20">
        <div className="w-10 h-10 rounded-[3px] border border-border-2 bg-bg-inset flex items-center justify-center text-fg-faint">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
            <circle cx="12" cy="12" r="3" /><circle cx="5" cy="6" r="2" /><circle cx="19" cy="6" r="2" />
            <circle cx="5" cy="18" r="2" /><circle cx="19" cy="18" r="2" />
            <path d="M7 7l3 3M17 7l-3 3M7 17l3-3M17 17l-3-3" />
          </svg>
        </div>
        <p className="meta text-center">No coordination edges yet for this account</p>
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

  const hoverNode = hoverId ? nodes.find((n) => n.external_id === hoverId) : undefined;

  return (
    <div className="panel overflow-hidden">
      {/* Header bar. A chart with no readout is a picture; a chart that states
          its own node and edge counts, and what the cursor is on, is an
          instrument. The hover slot is reserved at a fixed width so the bar
          does not reflow as the pointer moves across the field. */}
      <div className="panel-head">
        <span className="meta meta-hi">Coordination network</span>
        <span className="flex items-center gap-4 shrink-0">
          <span className="meta tabular">{nodes.length} nodes</span>
          <span className="meta tabular">{edges.length} edges</span>
          <span className="meta meta-on tabular hidden sm:inline-block w-[15ch] text-right truncate">
            {hoverNode ? truncate(hoverNode.handle, 15) : ''}
          </span>
        </span>
      </div>

      <svg
        viewBox={`0 0 ${W} ${H}`}
        width="100%"
        height={H}
        className="block"
        role="img"
        aria-label={`Coordination network: ${nodes.length} accounts, ${edges.length} links`}
      >
        <defs>
          {/* Measurement grid. The ground is flat and near-black; structure is
              the grid, exactly as it is everywhere else in the product. */}
          <pattern id="rg-grid" width="36" height="36" patternUnits="userSpaceOnUse">
            <path d="M36 0H0V36" fill="none" stroke="var(--border)" strokeOpacity="0.28" strokeWidth="1" />
          </pattern>
        </defs>

        <rect x="0" y="0" width={W} height={H} fill="var(--bg-inset)" />
        <rect x="0" y="0" width={W} height={H} fill="url(#rg-grid)" />

        {/* Range rings, labelled. A ring nobody can read the value of is
            decoration; these say which hop they are. */}
        <g fill="none" stroke="var(--border-2)" strokeDasharray="3 5">
          <circle cx={cx} cy={cy} r={ringSize.inner} />
          <circle cx={cx} cy={cy} r={ringSize.outer} />
        </g>
        <g className="meta" fill="var(--text-faint)" fontSize="9" letterSpacing="1.6">
          <text x={cx + 5} y={cy - ringSize.inner - 5}>1 HOP</text>
          <text x={cx + 5} y={cy - ringSize.outer - 5}>2+ HOP</text>
        </g>

        {/* Bearing ticks. Short marks at the ring edge rather than spokes
            running through the whole field: spokes cross every edge in the
            chart and compete with the data for the same lines. */}
        <g stroke="var(--border-2)" strokeWidth="1">
          {Array.from({ length: 12 }).map((_, i) => {
            const a = (i / 12) * Math.PI * 2;
            const r0 = ringSize.outer;
            const r1 = ringSize.outer + (i % 3 === 0 ? 10 : 5);
            return (
              <line key={i}
                x1={cx + Math.cos(a) * r0} y1={cy + Math.sin(a) * r0}
                x2={cx + Math.cos(a) * r1} y2={cy + Math.sin(a) * r1}
              />
            );
          })}
        </g>

        {/* Focal crosshair. A static reticle instead of an animated ripple:
            the centre of a link chart is a fixed reference, and something
            pulsing at the centre of the field reads as an alert. */}
        <g stroke="var(--accent)" strokeOpacity="0.5" strokeWidth="1">
          <line x1={cx - ringSize.outer - 14} y1={cy} x2={cx - 34} y2={cy} />
          <line x1={cx + 34} y1={cy} x2={cx + ringSize.outer + 14} y2={cy} />
          <line x1={cx} y1={cy - ringSize.outer - 14} x2={cx} y2={cy - 34} />
          <line x1={cx} y1={cy + 34} x2={cx} y2={cy + ringSize.outer + 14} />
        </g>

        {/* Edges. Gently bundled toward the centre. */}
        <g>
          {edges.map((e, i) => {
            const pa = positions[e.a];
            const pb = positions[e.b];
            if (!pa || !pb) return null;
            const active = isActive(e.a) && isActive(e.b);
            const traced = Boolean(hoverId) && (hoverId === e.a || hoverId === e.b);
            const ax = cx + pa.x, ay = cy + pa.y;
            const bx = cx + pb.x, by = cy + pb.y;
            // Control point: midpoint pulled 18% toward centre for readable bundling
            const mx = (ax + bx) / 2, my = (ay + by) / 2;
            const qx = mx + (cx - mx) * 0.18;
            const qy = my + (cy - my) * 0.18;
            return (
              <path
                key={i}
                d={`M${ax},${ay} Q${qx},${qy} ${bx},${by}`}
                fill="none"
                stroke={traced ? 'var(--accent-2)' : 'var(--border-hot)'}
                strokeWidth={(0.6 + e.strength * 2.4) * (traced ? 1.6 : 1)}
                strokeOpacity={hoverId ? (active ? (traced ? 0.95 : 0.5) : 0.05) : 0.16 + e.strength * 0.5}
                strokeLinecap="round"
                style={{ transition: 'stroke-opacity 0.2s ease, stroke-width 0.2s ease' }}
              />
            );
          })}
        </g>

        {/* Nodes. Squares, because a link chart is a diagram and a diagram uses
            shapes. Round beads with a highlight read as buttons. */}
        {nodes.map((n) => {
          const p = positions[n.external_id];
          if (!p) return null;
          const isFocal = n.external_id === focal;
          const half = isFocal ? 11 : 6;
          const fill = COMMUNITY_VARS[n.community_id % COMMUNITY_VARS.length];
          const tier = n.tier ? TIER_STROKE[n.tier] : null;
          const hovered = hoverId === n.external_id;
          const active = isActive(n.external_id);
          const tx = cx + p.x, ty = cy + p.y;
          return (
            <g
              key={n.external_id}
              transform={`translate(${tx}, ${ty})`}
              style={{ cursor: 'pointer', opacity: active ? 1 : 0.22, transition: 'opacity 0.2s ease' }}
              onMouseEnter={() => setHoverId(n.external_id)}
              onMouseLeave={() => setHoverId(null)}
              onClick={() => onSelect?.(n)}
            >
              {/* Tier ring. Drawn OUTSIDE the body so community colour and tier
                  are separately readable: they are two different facts about
                  the account and blending them loses one of them. */}
              {tier && (
                <rect
                  x={-half - 4} y={-half - 4}
                  width={(half + 4) * 2} height={(half + 4) * 2}
                  rx="1" fill="none" stroke={tier}
                  strokeWidth={hovered || isFocal ? 2 : 1.5}
                />
              )}
              {/* Selection brackets on the focal node: the corner ticks used
                  everywhere else in the interface, at node scale. */}
              {isFocal && (
                <g stroke="var(--accent)" strokeWidth="1.5" fill="none">
                  {[[-1, -1], [1, -1], [-1, 1], [1, 1]].map(([sx, sy], i) => (
                    <path
                      key={i}
                      d={`M${sx * (half + 10)},${sy * (half + 4)} L${sx * (half + 10)},${sy * (half + 10)} L${sx * (half + 4)},${sy * (half + 10)}`}
                    />
                  ))}
                </g>
              )}
              <rect
                x={-half} y={-half} width={half * 2} height={half * 2}
                rx="1"
                fill={fill}
                stroke={hovered ? 'var(--text)' : 'var(--bg-inset)'}
                strokeWidth={1.5}
                style={{ transition: 'stroke 0.15s ease' }}
              />
              {(isFocal || hovered) && (
                <text
                  y={half + 16}
                  textAnchor="middle"
                  fill="var(--text)"
                  fontSize={11}
                  fontFamily="var(--font-mono), ui-monospace, monospace"
                  style={{ paintOrder: 'stroke', stroke: 'var(--bg-inset)', strokeWidth: 4 }}
                >
                  {truncate(n.handle, 22)}
                </text>
              )}
            </g>
          );
        })}
      </svg>

      {/* Legend. On its own ground under a hairline, so the chart field ends
          where the chart ends. */}
      <div className="border-t border-border-1 bg-bg px-3 py-2.5 flex flex-wrap items-center gap-x-5 gap-y-2">
        <span className="meta">Community</span>
        <LegendSwatch color={COMMUNITY_VARS[0]} label="0" />
        <LegendSwatch color={COMMUNITY_VARS[1]} label="1" />
        <LegendSwatch color={COMMUNITY_VARS[2]} label="2" />
        <span className="w-px h-3 bg-border-2" />
        <span className="meta">Ring</span>
        <LegendRing color={TIER_STROKE.elevated} label="elevated" />
        <LegendRing color={TIER_STROKE.high} label="high" />
        <span className="w-px h-3 bg-border-2" />
        <span className="meta">Edge weight = tie strength</span>
      </div>
    </div>
  );
}

function LegendSwatch({ color, label }: { color: string; label: string }) {
  return (
    <span className="meta meta-on inline-flex items-center gap-1.5">
      <span className="inline-block w-2.5 h-2.5 rounded-[1px]" style={{ background: color }} />
      {label}
    </span>
  );
}

function LegendRing({ color, label }: { color: string; label: string }) {
  return (
    <span className="meta meta-on inline-flex items-center gap-1.5">
      <span
        className="inline-block w-2.5 h-2.5 rounded-[1px] border-[1.5px]"
        style={{ borderColor: color }}
      />
      {label}
    </span>
  );
}

function truncate(s: string, n: number) {
  return s.length <= n ? s : s.slice(0, n - 1) + '…';
}

// ---------------------------------------------------------------------------
// Layout computation. Deterministic radial placement
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
