import { describe, expect, it } from 'vitest';

import { edgeOpacity, edgeWidth, layoutGraph, nodeRadius, type LayoutNode } from './graph-layout';

const n = (external_id: string, community_id = 0, degree = 0): LayoutNode =>
  ({ external_id, community_id, degree });

describe('layoutGraph', () => {
  it('places every node exactly once', () => {
    const nodes = [n('a', 1, 2), n('b', 1, 1), n('c', 2, 1), n('d'), n('e')];
    const out = layoutGraph(nodes);
    expect(out.nodes).toHaveLength(5);
    expect(new Set(out.nodes.map((p) => p.external_id)).size).toBe(5);
  });

  it('is deterministic, because a node moving is a signal the data changed', () => {
    const nodes = [n('a', 1, 3), n('b', 1, 1), n('c', 2, 1), n('d')];
    expect(layoutGraph(nodes)).toEqual(layoutGraph(nodes));
  });

  it('does not depend on the order the API returned members in', () => {
    const nodes = [n('a', 1, 3), n('b', 1, 1), n('c', 2, 1), n('d')];
    const a = layoutGraph(nodes);
    const b = layoutGraph([...nodes].reverse());
    const key = (r: ReturnType<typeof layoutGraph>) =>
      [...r.nodes].sort((x, y) => x.external_id.localeCompare(y.external_id))
        .map((p) => `${p.external_id}:${p.x.toFixed(3)},${p.y.toFixed(3)}`);
    expect(key(a)).toEqual(key(b));
  });

  describe('the unconnected band', () => {
    it('is the common case and gets its own strip, not the clustered field', () => {
      const out = layoutGraph([n('a'), n('b'), n('c')]);
      expect(out.clusters).toHaveLength(0);
      expect(out.unconnectedBandY).not.toBeNull();
      expect(out.nodes.every((p) => p.cluster_index === -1)).toBe(true);
      // All in the band, which sits below the (empty) clustered field.
      expect(out.nodes.every((p) => p.y >= (out.unconnectedBandY as number))).toBe(true);
    });

    it('is absent when everything is connected', () => {
      const out = layoutGraph([n('a', 1, 1), n('b', 1, 1)]);
      expect(out.unconnectedBandY).toBeNull();
    });

    it('separates unconnected nodes from a real cluster', () => {
      const out = layoutGraph([n('a', 1, 1), n('b', 1, 1), n('lonely')]);
      const lonely = out.nodes.find((p) => p.external_id === 'lonely')!;
      const clustered = out.nodes.filter((p) => p.external_id !== 'lonely');
      expect(lonely.cluster_index).toBe(-1);
      expect(clustered.every((p) => p.y < lonely.y)).toBe(true);
    });
  });

  describe('clusters', () => {
    it('centres a single operation rather than pushing it onto a ring of one', () => {
      const out = layoutGraph([n('a', 1, 2), n('b', 1, 1), n('c', 1, 1)], { width: 600, height: 400 });
      expect(out.clusters).toHaveLength(1);
      expect(out.clusters[0].cx).toBeCloseTo(300, 1);
    });

    it('keeps two operations apart', () => {
      const nodes = [n('a1', 1, 1), n('a2', 1, 1), n('b1', 2, 1), n('b2', 2, 1)];
      const out = layoutGraph(nodes);
      expect(out.clusters).toHaveLength(2);
      const [c1, c2] = out.clusters;
      const gap = Math.hypot(c1.cx - c2.cx, c1.cy - c2.cy);
      expect(gap).toBeGreaterThan(c1.r);
    });

    it('orders clusters largest first so the biggest operation reads first', () => {
      const nodes = [n('s', 2, 1), n('t', 2, 1), n('a', 1, 1), n('b', 1, 1), n('c', 1, 1)];
      const out = layoutGraph(nodes);
      expect(out.clusters[0].size).toBe(3);
      expect(out.clusters[0].cluster_index).toBe(0);
    });

    it('puts the most connected member at the middle of its cluster', () => {
      const nodes = [n('weak', 1, 1), n('hub', 1, 9), n('other', 1, 1)];
      const out = layoutGraph(nodes, { width: 600, height: 400 });
      const c = out.clusters[0];
      const d = (id: string) => {
        const p = out.nodes.find((x) => x.external_id === id)!;
        return Math.hypot(p.x - c.cx, p.y - c.cy);
      };
      expect(d('hub')).toBeLessThan(d('weak'));
      expect(d('hub')).toBeLessThan(d('other'));
    });
  });

  it('handles an empty graph without producing NaN', () => {
    const out = layoutGraph([]);
    expect(out.nodes).toHaveLength(0);
    expect(out.clusters).toHaveLength(0);
    expect(Number.isFinite(out.height)).toBe(true);
  });

  it('never emits a non-finite coordinate', () => {
    const many = Array.from({ length: 120 }, (_, i) => n(`x${i}`, (i % 5) + 1, i % 4));
    const out = layoutGraph(many, { width: 400, height: 300 });
    expect(out.nodes.every((p) => Number.isFinite(p.x) && Number.isFinite(p.y))).toBe(true);
  });
});

describe('nodeRadius', () => {
  it('scales with the real score', () => {
    expect(nodeRadius(90)).toBeGreaterThan(nodeRadius(20));
  });

  it('does not draw an unscored node as the smallest one', () => {
    // null means the score was never captured. A confidently tiny node would say the opposite: that
    // this account was measured and came back clean.
    expect(nodeRadius(null)).toBeGreaterThan(nodeRadius(0));
    expect(nodeRadius(undefined)).toBe(nodeRadius(null));
  });

  it('clamps out-of-range input', () => {
    expect(nodeRadius(-40)).toBe(nodeRadius(0));
    expect(nodeRadius(900)).toBe(nodeRadius(100));
  });
});

describe('edge rendering', () => {
  it('draws a stronger link heavier and more opaque', () => {
    expect(edgeWidth(0.99)).toBeGreaterThan(edgeWidth(0.5));
    expect(edgeOpacity(0.99)).toBeGreaterThan(edgeOpacity(0.5));
  });

  it('keeps a weak-but-real link visible', () => {
    // Every edge on screen cleared the detector's bar, so none of them should fade into the ground.
    expect(edgeOpacity(0)).toBeGreaterThan(0.2);
  });
});
