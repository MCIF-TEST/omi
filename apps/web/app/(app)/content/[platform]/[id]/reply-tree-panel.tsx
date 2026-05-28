'use client';

import { useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import {
  MessageSquare,
  Users,
  ChevronDown,
  ChevronRight,
  Network,
  Filter,
} from 'lucide-react';
import { Card, CardLabel, CardTitle } from '@/components/ui/card';
import { TierBadge } from '@/components/shared/tier-badge';
import {
  apiClient,
  ApiError,
  type ReplyPodOut,
  type ReplyPodsResponse,
  type ReplyTreeNode,
  type ReplyTreeResponse,
  type Tier,
} from '@/lib/api';
import { timeAgo } from '@/lib/format';

// Pod colour palette — keep in sync with the radial-graph community palette so
// users get visual continuity between the two coordination views.
const POD_COLORS = [
  '#22d3ee', '#a78bfa', '#f472b6', '#fb923c',
  '#facc15', '#34d399', '#60a5fa', '#f87171',
];

interface ReplyTreePanelProps {
  platform: string;
  contentId: string;
}

export function ReplyTreePanel({ platform, contentId }: ReplyTreePanelProps) {
  const [tree, setTree] = useState<ReplyTreeResponse | null>(null);
  const [pods, setPods] = useState<ReplyPodsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    Promise.all([
      apiClient<ReplyTreeResponse>(`/v1/content/${platform}/${encodeURIComponent(contentId)}/reply-tree`),
      apiClient<ReplyPodsResponse>(`/v1/content/${platform}/${encodeURIComponent(contentId)}/reply-pods`),
    ])
      .then(([t, p]) => {
        if (cancelled) return;
        setTree(t);
        setPods(p);
      })
      .catch((e) => {
        if (cancelled) return;
        if (e instanceof ApiError && e.status === 404) {
          setTree({ platform, content_id: contentId, total_comments: 0, top_level_count: 0, reply_count: 0, roots: [] });
          setPods({ platform, content_id: contentId, pod_count: 0, pods: [] });
        } else {
          setError(e instanceof ApiError ? e.message : 'Failed to load reply tree');
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [platform, contentId]);

  if (loading) {
    return (
      <Card>
        <CardLabel>Reply intelligence</CardLabel>
        <p className="text-sm text-fg-mute font-mono">Loading reply tree…</p>
      </Card>
    );
  }

  if (error) {
    return (
      <Card>
        <CardLabel>Reply intelligence</CardLabel>
        <p className="text-sm text-danger">{error}</p>
      </Card>
    );
  }

  if (!tree || tree.total_comments === 0) {
    return (
      <Card>
        <CardLabel>Reply intelligence</CardLabel>
        <CardTitle>No threaded data yet</CardTitle>
        <p className="text-sm text-fg-dim">
          Reply structure becomes available after the first comment scan that includes
          threaded replies. Run a scan to populate this view.
        </p>
      </Card>
    );
  }

  return (
    <div className="space-y-5">
      <PodsSummary pods={pods?.pods ?? []} platform={platform} />
      <ReplyTreeBlock tree={tree} pods={pods?.pods ?? []} />
    </div>
  );
}

function PodsSummary({ pods, platform }: { pods: ReplyPodOut[]; platform: string }) {
  if (pods.length === 0) {
    return (
      <Card>
        <div className="flex items-center justify-between gap-3 mb-2 flex-wrap">
          <CardLabel className="m-0">Reply pods</CardLabel>
          <span className="font-mono text-2xs tracking-wider uppercase text-fg-mute">
            None detected
          </span>
        </div>
        <p className="text-sm text-fg-dim">
          No coordinated reply pods found in this video. Pods appear when accounts
          reply to each other or pile onto the same comments in tight windows.
        </p>
      </Card>
    );
  }

  const totalMembers = new Set(pods.flatMap((p) => p.members.map((m) => m.external_id))).size;
  const totalInteractions = pods.reduce((s, p) => s + p.interaction_count, 0);

  return (
    <Card>
      <div className="flex items-center justify-between gap-3 mb-1 flex-wrap">
        <CardLabel className="m-0">
          <Network size={11} className="inline -mt-0.5 mr-1" />
          Reply pods · {pods.length}
        </CardLabel>
        <div className="flex items-center gap-3 font-mono text-2xs text-fg-mute">
          <span><Users size={9} className="inline -mt-0.5 mr-0.5" />{totalMembers} accounts</span>
          <span className="tracking-wider uppercase">{totalInteractions} interactions</span>
        </div>
      </div>
      <p className="text-xs text-fg-mute mb-3">
        Clusters of accounts that systematically reply to each other or co-reply within tight time windows.
      </p>
      <div className="space-y-3">
        {pods.map((pod) => (
          <PodCard key={pod.pod_id} pod={pod} platform={platform} />
        ))}
      </div>
    </Card>
  );
}

function PodCard({ pod, platform }: { pod: ReplyPodOut; platform: string }) {
  const color = POD_COLORS[pod.pod_id % POD_COLORS.length];
  const scorePct = Math.round(pod.score * 100);
  const scoreTone =
    scorePct >= 75 ? 'text-tier-high' :
    scorePct >= 55 ? 'text-tier-elevated' :
    scorePct >= 35 ? 'text-tier-moderate' :
    'text-tier-low';

  return (
    <div className="border border-border-1 rounded-md p-3" style={{ borderLeftColor: color, borderLeftWidth: 3 }}>
      <div className="flex items-center justify-between gap-3 mb-3 flex-wrap">
        <div className="flex items-center gap-2">
          <span
            className="font-mono text-2xs uppercase tracking-wider px-1.5 py-0.5 rounded-sm"
            style={{ backgroundColor: `${color}20`, color }}
          >
            Pod #{pod.pod_id + 1}
          </span>
          <span className="font-mono text-2xs text-fg-mute">
            <Users size={10} className="inline -mt-0.5 mr-1" />
            {pod.members.length} accounts · {pod.interaction_count} interactions
          </span>
        </div>
        <span className={`font-mono text-sm font-semibold tabular-nums ${scoreTone}`}>
          {scorePct}%
        </span>
      </div>

      <div className="flex flex-wrap gap-1.5 mb-2">
        {pod.members.map((m) => (
          <Link
            key={m.external_id}
            href={`/accounts/${encodeURIComponent(m.external_id)}?platform=${platform}`}
            className="inline-flex items-center gap-1.5 bg-bg-elev border border-border-1 hover:border-accent rounded-sm px-2 py-1 text-xs text-fg-dim hover:text-fg transition-colors"
          >
            <span className="truncate max-w-[120px]">{m.handle || m.external_id}</span>
            {m.tier && <TierBadge tier={m.tier as Tier} size="sm" />}
          </Link>
        ))}
      </div>

      {pod.evidence.length > 0 && (
        <ul className="space-y-0.5 mt-2 font-mono text-2xs text-fg-mute">
          {pod.evidence.slice(0, 3).map((ev, i) => (
            <li key={i} className="flex gap-2">
              <span className="text-fg-faint">·</span>
              <span className="truncate">{ev}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function ReplyTreeBlock({ tree, pods }: { tree: ReplyTreeResponse; pods: ReplyPodOut[] }) {
  const [podFilterOn, setPodFilterOn] = useState(false);

  // Build set of root comment IDs that contain at least one pod member.
  const podRootIds = useMemo(() => {
    if (!pods.length) return new Set<string>();
    const podAuthorIds = new Set(pods.flatMap((p) => p.members.map((m) => m.external_id)));
    return new Set(
      tree.roots
        .filter((r) =>
          podAuthorIds.has(r.author_external_id) ||
          r.replies.some((reply) => podAuthorIds.has(reply.author_external_id))
        )
        .map((r) => r.comment_id)
    );
  }, [tree.roots, pods]);

  // Sort roots: pods first (by pod_id ascending), then by reply count desc
  const sortedRoots = useMemo(() => {
    return [...tree.roots].sort((a, b) => {
      const aHasPod = a.replies.some((r) => r.pod_id !== null) || a.pod_id !== null ? 0 : 1;
      const bHasPod = b.replies.some((r) => r.pod_id !== null) || b.pod_id !== null ? 0 : 1;
      if (aHasPod !== bHasPod) return aHasPod - bHasPod;
      return (b.replies.length || 0) - (a.replies.length || 0);
    });
  }, [tree.roots]);

  const displayRoots = podFilterOn
    ? sortedRoots.filter((r) => podRootIds.has(r.comment_id))
    : sortedRoots;

  return (
    <Card>
      <div className="flex items-center justify-between gap-3 mb-3 flex-wrap">
        <CardLabel className="m-0">
          <MessageSquare size={11} className="inline -mt-0.5 mr-1" />
          Reply tree · {tree.total_comments} comments
        </CardLabel>
        <div className="flex items-center gap-3">
          {pods.length > 0 && (
            <button
              type="button"
              onClick={() => setPodFilterOn((v) => !v)}
              className={`inline-flex items-center gap-1 font-mono text-2xs tracking-wider uppercase px-2 py-1 rounded-sm border transition-colors ${
                podFilterOn
                  ? 'border-accent text-accent bg-accent/10'
                  : 'border-border-1 text-fg-mute hover:border-border-hot hover:text-fg'
              }`}
            >
              <Filter size={9} />
              Pod threads only
            </button>
          )}
          <span className="font-mono text-2xs tracking-wider uppercase text-fg-mute">
            {tree.top_level_count} threads · {tree.reply_count} replies
          </span>
        </div>
      </div>
      {podFilterOn && displayRoots.length === 0 && (
        <p className="text-sm text-fg-mute font-mono mb-3">
          No threads with pod activity found.
        </p>
      )}
      <ul className="space-y-1">
        {displayRoots.slice(0, 30).map((root) => (
          <CommentNode key={root.comment_id} node={root} depth={0} />
        ))}
      </ul>
      {!podFilterOn && sortedRoots.length > 30 && (
        <p className="mt-3 font-mono text-2xs text-fg-mute">
          Showing top 30 of {sortedRoots.length} threads.
        </p>
      )}
    </Card>
  );
}

function CommentNode({ node, depth }: { node: ReplyTreeNode; depth: number }) {
  const [expanded, setExpanded] = useState(depth === 0 && node.replies.length > 0 && node.replies.length <= 5);
  const hasReplies = node.replies.length > 0;
  const podColor = node.pod_id !== null ? POD_COLORS[node.pod_id % POD_COLORS.length] : null;

  return (
    <li>
      <div
        className="flex gap-2 p-2 rounded-sm hover:bg-bg-elev/40 transition-colors"
        style={
          podColor
            ? { borderLeft: `2px solid ${podColor}`, paddingLeft: 10 }
            : undefined
        }
      >
        <button
          type="button"
          onClick={() => setExpanded((v) => !v)}
          disabled={!hasReplies}
          className={`shrink-0 mt-0.5 ${
            hasReplies ? 'text-fg-mute hover:text-fg' : 'text-fg-faint cursor-default'
          }`}
          aria-label={expanded ? 'Collapse' : 'Expand'}
        >
          {hasReplies ? (
            expanded ? <ChevronDown size={12} /> : <ChevronRight size={12} />
          ) : (
            <span className="inline-block w-3" />
          )}
        </button>

        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <Link
              href={`/accounts/${encodeURIComponent(node.author_external_id)}?platform=youtube`}
              className="text-xs font-medium text-fg hover:text-accent transition-colors truncate"
            >
              {node.author_handle || node.author_external_id}
            </Link>
            {node.author_tier && <TierBadge tier={node.author_tier as Tier} size="sm" />}
            {podColor && (
              <span
                className="font-mono text-[10px] uppercase tracking-wider px-1 py-0.5 rounded-sm"
                style={{ backgroundColor: `${podColor}25`, color: podColor }}
              >
                Pod #{(node.pod_id ?? 0) + 1}
              </span>
            )}
            <span className="font-mono text-2xs text-fg-mute">{timeAgo(node.posted_at)}</span>
            {node.like_count != null && node.like_count > 0 && (
              <span className="font-mono text-2xs text-fg-mute">♥ {node.like_count}</span>
            )}
          </div>
          <p className="text-xs text-fg-dim mt-0.5 leading-relaxed line-clamp-3">{node.text}</p>
          {hasReplies && (
            <button
              type="button"
              onClick={() => setExpanded((v) => !v)}
              className="font-mono text-2xs text-fg-mute hover:text-accent mt-1 uppercase tracking-wider"
            >
              {expanded ? 'Hide' : 'Show'} {node.replies.length} repl{node.replies.length === 1 ? 'y' : 'ies'}
            </button>
          )}
        </div>
      </div>

      {expanded && hasReplies && (
        <ul className="ml-6 mt-1 pl-3 border-l border-border-1 space-y-1">
          {node.replies.map((child) => (
            <CommentNode key={child.comment_id} node={child} depth={depth + 1} />
          ))}
        </ul>
      )}
    </li>
  );
}
