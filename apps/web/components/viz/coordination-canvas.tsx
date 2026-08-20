'use client';

/**
 * The coordination canvas for a saved graph.
 *
 * Replaces `RadialGraph` on this surface. That component drew a focal node with BFS hop rings,
 * which imposes a hierarchy a curated set does not have, and pushed almost everything into an
 * `orphans` bucket because coordination edges are sparse by design.
 *
 * WHAT A READER SHOULD BE ABLE TO GET FROM IT, in order:
 *   1. Are any of these accounts linked at all? The unconnected band answers that immediately and
 *      is drawn as a plain row rather than dressed up as a cluster.
 *   2. Is this one operation or several? Separate blobs are separate clusters, from real community
 *      detection over the graph's own edges.
 *   3. Why is that line there? Click it. Every edge carries its posterior, its evidence families
 *      and how many distinct posts it was seen under.
 *
 * Nothing here is estimated. Node size comes from the account's real OMI score, and an account
 * whose score was never captured is drawn HOLLOW rather than small, because a small dot would
 * claim it was measured and came back clean.
 */

import { useMemo, useState } from 'react';

import type { GraphCoordinationEdge, Tier, UserGraphMemberOut } from '@/lib/api';
import {
  edgeOpacity,
  edgeWidth,
  layoutGraph,
  nodeRadius,
  type LayoutNode,
} from '@/lib/graph-layout';

const CLUSTER_VARS = [
  'var(--cluster-1)', 'var(--cluster-2)', 'var(--cluster-3)', 'var(--cluster-4)',
  'var(--cluster-5)', 'var(--cluster-6)', 'var(--cluster-7)', 'var(--cluster-8)',
];

const TIER_STROKE: Record<string, string> = {
  low: 'var(--tier-low)',
  moderate: 'var(--tier-moderate)',
  elevated: 'var(--tier-elevated)',
  high: 'var(--tier-high)',
};

function clusterColor(index: number): string {
  return index < 0 ? 'var(--fg-faint)' : CLUSTER_VARS[index % CLUSTER_VARS.length];
}

export interface CoordinationCanvasProps {
  members: UserGraphMemberOut[];
  edges: GraphCoordinationEdge[];
  selectedId?: string | null;
  onSelectNode?: (member: UserGraphMemberOut) => void;
  onSelectEdge?: (edge: GraphCoordinationEdge) => void;
  height?: number;
}

export function CoordinationCanvas({
  members,
  edges,
  selectedId = null,
  onSelectNode,
  onSelectEdge,
  height = 460,
}: CoordinationCanvasProps) {
  const [hover, setHover] = useState<string | null>(null);

  const layout = useMemo(() => {
    const nodes: LayoutNode[] = members.map((m) => ({
      external_id: m.external_id,
      community_id: m.community_id ?? 0,
      degree: m.degree ?? 0,
    }));
    return layoutGraph(nodes, { width: 720, height });
  }, [members, height]);

  const pos = useMemo(
    () => new Map(layout.nodes.map((p) => [p.external_id, p])),
    [layout],
  );
  const byId = useMemo(
    () => new Map(members.map((m) => [m.external_id, m])),
    [members],
  );

  // Only edges whose BOTH endpoints are on the canvas. A half-drawn line is worse than none.
  const drawable = useMemo(
    () => edges.filter((e) => pos.has(e.a) && pos.has(e.b)),
    [edges, pos],
  );

  const focus = hover ?? selectedId;
  const neighbours = useMemo(() => {
    if (!focus) return null;
    const s = new Set<string>([focus]);
    for (const e of drawable) {
      if (e.a === focus) s.add(e.b);
      if (e.b === focus) s.add(e.a);
    }
    return s;
  }, [focus, drawable]);

  if (members.length === 0) return null;

  const dim = (id: string) => (neighbours && !neighbours.has(id) ? 0.22 : 1);

  return (
    <div className="panel tick-frame overflow-hidden">
      <div className="panel-head">
        <span className="meta meta-hi">Coordination</span>
        <span className="meta tabular">
          {members.length} account{members.length === 1 ? '' : 's'} · {drawable.length} link
          {drawable.length === 1 ? '' : 's'}
        </span>
      </div>
      <div className="panel-body p-0">
        <div className="overflow-x-auto">
          <svg
            viewBox={`0 0 ${layout.width} ${layout.height}`}
            width="100%"
            height={layout.height}
            role="img"
            aria-label={`Coordination graph, ${members.length} accounts, ${drawable.length} links`}
            style={{ display: 'block', minWidth: 420 }}
          >
            {/* Cluster grounds, behind everything. They are what makes "two operations" legible at
                a glance without reading a single label. */}
            {layout.clusters.map((c) => (
              <circle
                key={`hull-${c.community_id}`}
                cx={c.cx}
                cy={c.cy}
                r={c.r}
                fill={clusterColor(c.cluster_index)}
                opacity={0.05}
                stroke={clusterColor(c.cluster_index)}
                strokeOpacity={0.18}
                strokeWidth={1}
              />
            ))}

            {/* Edges. Width and opacity carry the posterior; clicking one asks why it exists. */}
            <g>
              {drawable.map((e) => {
                const a = pos.get(e.a)!;
                const b = pos.get(e.b)!;
                const lit = !neighbours || (neighbours.has(e.a) && neighbours.has(e.b));
                return (
                  <line
                    key={`${e.a}|${e.b}`}
                    x1={a.x}
                    y1={a.y}
                    x2={b.x}
                    y2={b.y}
                    stroke="var(--violet-2, #8f7bf0)"
                    strokeWidth={edgeWidth(e.posterior)}
                    strokeOpacity={lit ? edgeOpacity(e.posterior) : 0.08}
                    style={{ cursor: onSelectEdge ? 'pointer' : undefined }}
                    onClick={() => onSelectEdge?.(e)}
                  >
                    <title>
                      {`P(coordinated) ${(e.posterior * 100).toFixed(1)}% · ` +
                        `${e.families.length} evidence famil${e.families.length === 1 ? 'y' : 'ies'} · ` +
                        `${e.contexts} post${e.contexts === 1 ? '' : 's'}`}
                    </title>
                  </line>
                );
              })}
            </g>

            {/* The unconnected band gets a labelled rule, so "nothing links these" reads as a
                finding rather than as a drawing that failed to lay out. */}
            {layout.unconnectedBandY !== null && (
              <g>
                <line
                  x1={16}
                  y1={layout.unconnectedBandY - 16}
                  x2={layout.width - 16}
                  y2={layout.unconnectedBandY - 16}
                  stroke="var(--border-2, #2c3542)"
                  strokeWidth={1}
                />
                <text
                  x={16}
                  y={layout.unconnectedBandY - 22}
                  fill="var(--fg-faint)"
                  fontSize={9}
                  letterSpacing="0.18em"
                  fontFamily="var(--font-mono, monospace)"
                >
                  NO COORDINATION EVIDENCE
                </text>
              </g>
            )}

            {/* Nodes. Fill = cluster, ring = tier, size = the REAL score. */}
            <g>
              {layout.nodes.map((p) => {
                const m = byId.get(p.external_id);
                if (!m) return null;
                const r = nodeRadius(m.omi_score);
                const unscored = m.omi_score === null || m.omi_score === undefined;
                const isSel = selectedId === p.external_id;
                return (
                  <g
                    key={p.external_id}
                    transform={`translate(${p.x},${p.y})`}
                    opacity={dim(p.external_id)}
                    style={{ cursor: onSelectNode ? 'pointer' : undefined }}
                    onMouseEnter={() => setHover(p.external_id)}
                    onMouseLeave={() => setHover(null)}
                    onClick={() => onSelectNode?.(m)}
                  >
                    <title>
                      {`${m.handle || m.external_id}` +
                        (unscored ? ' · score not captured' : ` · OMI ${m.omi_score}`) +
                        ` · ${m.degree ?? 0} link${(m.degree ?? 0) === 1 ? '' : 's'}`}
                    </title>
                    {/* Tier ring sits OUTSIDE the body, so cluster and tier stay separately
                        readable instead of one overwriting the other. */}
                    {m.tier && (
                      <circle
                        r={r + 3}
                        fill="none"
                        stroke={TIER_STROKE[m.tier as Tier] ?? 'var(--fg-faint)'}
                        strokeWidth={1.5}
                        opacity={0.85}
                      />
                    )}
                    <circle
                      r={r}
                      fill={unscored ? 'none' : clusterColor(p.cluster_index)}
                      stroke={clusterColor(p.cluster_index)}
                      strokeWidth={unscored ? 1.25 : 0}
                      strokeDasharray={unscored ? '2 2' : undefined}
                    />
                    {isSel && (
                      <circle r={r + 7} fill="none" stroke="var(--fg)" strokeWidth={1} opacity={0.9} />
                    )}
                  </g>
                );
              })}
            </g>
          </svg>
        </div>

        <div className="flex flex-wrap items-center gap-x-5 gap-y-1.5 px-3.5 py-2.5 border-t border-border">
          <Key swatch={<span className="inline-block w-2.5 h-2.5 rounded-full bg-[var(--cluster-1)]" />}
               label="cluster" />
          <Key swatch={<span className="inline-block w-2.5 h-2.5 rounded-full border border-dashed border-fg-faint" />}
               label="score not captured" />
          <Key swatch={<span className="inline-block w-2.5 h-2.5 rounded-full border-[1.5px] border-[var(--tier-high)]" />}
               label="ring = tier" />
          <Key swatch={<span className="inline-block w-4 h-px bg-[var(--violet-2,#8f7bf0)]" />}
               label="thicker = stronger evidence" />
        </div>
      </div>
    </div>
  );
}

function Key({ swatch, label }: { swatch: React.ReactNode; label: string }) {
  return (
    <span className="inline-flex items-center gap-1.5">
      {swatch}
      <span className="meta">{label}</span>
    </span>
  );
}
