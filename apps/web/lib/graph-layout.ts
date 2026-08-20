/**
 * Deterministic layout for a user-curated coordination graph.
 *
 * WHY NOT THE OLD RADIAL LAYOUT. The previous one picked a `focal` node, BFS'd hop distance from
 * it, and placed ring 1 and ring 2 around it. That shape encodes a hierarchy the data does not
 * have: a saved graph is a set the operator assembled, with no centre. Worse, coordination edges
 * are sparse by design, so in the common case almost every node fell into the `orphans` bucket and
 * the rings were empty. The picture answered a question nobody asked and could not answer the one
 * they did.
 *
 * WHAT THIS DOES INSTEAD. Nodes are grouped by the community the server detected over the graph's
 * own edges, each community is packed into its own cluster, and the clusters are arranged around
 * the canvas. Reading it left to right: separate blobs are separate operations, a big blob is one
 * operation, and the unconnected band is everything with no coordination evidence at all.
 *
 * THE UNCONNECTED BAND IS THE POINT, NOT AN EDGE CASE. Most members of most graphs will have no
 * edges, because coordination evidence is rare and that is the whole product claim. They get their
 * own row along the bottom rather than being scattered into the field as though they were part of
 * a cluster, so "nothing links these" reads as a finding instead of as a broken drawing.
 *
 * DETERMINISTIC ON PURPOSE. No force simulation. The same graph must draw the same way on every
 * render, or a node moving becomes a signal the data changed when it did not. Positions are a pure
 * function of the input, so the canvas is stable across polls, resizes and re-mounts.
 */

export interface LayoutNode {
  external_id: string;
  community_id: number;
  degree: number;
}

export interface PlacedNode {
  external_id: string;
  x: number;
  y: number;
  /** Cluster this node belongs to. 0 is the unconnected band. */
  community_id: number;
  /** Index of the cluster in reading order, for stable colour assignment. -1 for unconnected. */
  cluster_index: number;
}

export interface LayoutResult {
  nodes: PlacedNode[];
  /** One entry per real cluster, for drawing a hull or a label behind the nodes. */
  clusters: { community_id: number; cluster_index: number; cx: number; cy: number; r: number; size: number }[];
  width: number;
  height: number;
  /** Y coordinate where the unconnected band starts, or null when there is nothing in it. */
  unconnectedBandY: number | null;
}

/** Golden angle, for even packing without a simulation. */
const PHI = Math.PI * (3 - Math.sqrt(5));

/** Distance between neighbouring nodes inside a cluster. */
const NODE_PITCH = 26;

/**
 * Pack `n` points into a spiral around (0,0), returning offsets.
 *
 * Phyllotaxis rather than concentric rings: it fills evenly at any count, so a cluster of 3 and a
 * cluster of 30 both look deliberate, and adding one member nudges the packing rather than
 * reflowing it into a different ring structure.
 */
function packOffsets(n: number): { dx: number; dy: number }[] {
  const out: { dx: number; dy: number }[] = [];
  for (let i = 0; i < n; i += 1) {
    const r = NODE_PITCH * 0.62 * Math.sqrt(i + 0.6);
    const a = i * PHI;
    out.push({ dx: r * Math.cos(a), dy: r * Math.sin(a) });
  }
  return out;
}

function clusterRadius(size: number): number {
  return NODE_PITCH * 0.62 * Math.sqrt(size + 0.6) + NODE_PITCH * 0.75;
}

/**
 * Place every node.
 *
 * Clusters are sorted largest first and laid out around a ring sized to fit them, which keeps the
 * biggest operation nearest the centre of attention. Ties break on community id so the arrangement
 * is stable when two clusters are the same size.
 */
export function layoutGraph(
  nodes: LayoutNode[],
  opts: { width?: number; height?: number } = {},
): LayoutResult {
  const width = opts.width ?? 720;
  const height = opts.height ?? 480;

  const connected = nodes.filter((n) => n.community_id > 0);
  const unconnected = nodes.filter((n) => n.community_id <= 0);

  // Group the connected ones.
  const byCommunity = new Map<number, LayoutNode[]>();
  for (const n of connected) {
    const list = byCommunity.get(n.community_id) ?? [];
    list.push(n);
    byCommunity.set(n.community_id, list);
  }
  const groups = [...byCommunity.entries()]
    .map(([community_id, members]) => ({ community_id, members }))
    .sort((a, b) => b.members.length - a.members.length || a.community_id - b.community_id);

  // The unconnected band takes a fixed strip at the bottom, so the clustered field never shifts
  // vertically as members are added to or removed from it.
  const bandRows = unconnected.length === 0 ? 0 : Math.ceil(unconnected.length / Math.max(1, Math.floor((width - 40) / NODE_PITCH)));
  const bandHeight = bandRows === 0 ? 0 : bandRows * NODE_PITCH + 34;
  const fieldHeight = Math.max(140, height - bandHeight);
  const cx = width / 2;
  const cy = fieldHeight / 2;

  const placed: PlacedNode[] = [];
  const clusters: LayoutResult['clusters'] = [];

  if (groups.length === 1) {
    // One operation: centre it rather than pushing it out to a ring of one.
    const g = groups[0];
    const offs = packOffsets(g.members.length);
    const ordered = orderWithin(g.members);
    ordered.forEach((n, i) => {
      placed.push({ external_id: n.external_id, x: cx + offs[i].dx, y: cy + offs[i].dy,
                    community_id: n.community_id, cluster_index: 0 });
    });
    clusters.push({ community_id: g.community_id, cluster_index: 0, cx, cy,
                    r: clusterRadius(g.members.length), size: g.members.length });
  } else if (groups.length > 1) {
    // Ring the clusters, sized so the biggest two do not overlap.
    const maxR = Math.max(...groups.map((g) => clusterRadius(g.members.length)));
    const ringR = Math.min(
      Math.max(maxR * 1.6, 90),
      Math.max(60, Math.min(width, fieldHeight) / 2 - maxR - 12),
    );
    groups.forEach((g, gi) => {
      const a = (gi / groups.length) * Math.PI * 2 - Math.PI / 2;
      const gx = cx + ringR * Math.cos(a);
      const gy = cy + ringR * Math.sin(a);
      const offs = packOffsets(g.members.length);
      orderWithin(g.members).forEach((n, i) => {
        placed.push({ external_id: n.external_id, x: gx + offs[i].dx, y: gy + offs[i].dy,
                      community_id: n.community_id, cluster_index: gi });
      });
      clusters.push({ community_id: g.community_id, cluster_index: gi, cx: gx, cy: gy,
                      r: clusterRadius(g.members.length), size: g.members.length });
    });
  }

  // The unconnected band: a plain grid, read left to right, in stable id order.
  let unconnectedBandY: number | null = null;
  if (unconnected.length > 0) {
    const perRow = Math.max(1, Math.floor((width - 40) / NODE_PITCH));
    const bandY = fieldHeight + 24;
    unconnectedBandY = bandY;
    [...unconnected]
      .sort((a, b) => a.external_id.localeCompare(b.external_id))
      .forEach((n, i) => {
        const row = Math.floor(i / perRow);
        const col = i % perRow;
        const rowCount = Math.min(perRow, unconnected.length - row * perRow);
        const rowWidth = (rowCount - 1) * NODE_PITCH;
        placed.push({
          external_id: n.external_id,
          x: width / 2 - rowWidth / 2 + col * NODE_PITCH,
          y: bandY + row * NODE_PITCH,
          community_id: 0,
          cluster_index: -1,
        });
      });
  }

  return { nodes: placed, clusters, width, height: fieldHeight + bandHeight, unconnectedBandY };
}

/**
 * Order a cluster's members so the most connected sit at its centre.
 *
 * The packing spiral starts at the middle, so sorting by degree puts the account holding the
 * cluster together where a reader looks first. Ties break on id, so the order never depends on
 * whatever sequence the API happened to return.
 */
function orderWithin(members: LayoutNode[]): LayoutNode[] {
  return [...members].sort(
    (a, b) => b.degree - a.degree || a.external_id.localeCompare(b.external_id),
  );
}

/**
 * Node radius from the REAL score.
 *
 * `null` is not zero and must not render as the smallest possible dot: it means the score was never
 * captured for this member, and a confidently tiny node would state the opposite of that. Unscored
 * nodes take a fixed middle size and the component draws them hollow.
 */
export function nodeRadius(omiScore: number | null | undefined): number {
  if (omiScore === null || omiScore === undefined) return 6.5;
  const t = Math.max(0, Math.min(100, omiScore)) / 100;
  return 5 + t * 6.5;
}

/** Edge stroke width from the posterior. Kept narrow: this is a hairline instrument, not a web. */
export function edgeWidth(posterior: number): number {
  return 0.75 + Math.max(0, Math.min(1, posterior)) * 2.0;
}

/**
 * Edge opacity from the posterior, with a floor.
 *
 * A link that cleared the detector's bar is worth seeing even at the bottom of the range, so the
 * floor is what stops a real finding fading into the background.
 */
export function edgeOpacity(posterior: number): number {
  return 0.28 + Math.max(0, Math.min(1, posterior)) * 0.52;
}
