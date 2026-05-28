'use client';

import Link from 'next/link';
import { useState, useEffect } from 'react';
import {
  MessageCircle,
  Heart,
  CornerDownRight,
  ExternalLink,
  RefreshCw,
} from 'lucide-react';
import { Card, CardLabel } from '@/components/ui/card';
import { apiClient, ApiError, type AuthorCommentRow, type AuthorCommentsResponse } from '@/lib/api';
import { timeAgo } from '@/lib/format';

interface Props {
  platform: string;
  externalId: string;
}

export function AccountActivityPanel({ platform, externalId }: Props) {
  const [data, setData] = useState<AuthorCommentsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [noData, setNoData] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    apiClient<AuthorCommentsResponse>(
      `/v1/content/authors/${platform}/${encodeURIComponent(externalId)}/comments?limit=500`,
    )
      .then(setData)
      .catch((err) => {
        if (err instanceof ApiError && err.status === 404) {
          setNoData(true);
        } else {
          setError(err instanceof ApiError ? err.message : 'Failed to load activity');
        }
      })
      .finally(() => setLoading(false));
  }, [platform, externalId]);

  if (loading) {
    return (
      <Card>
        <div className="flex items-center gap-2 text-fg-mute">
          <RefreshCw size={12} className="animate-spin" />
          <span className="font-mono text-2xs uppercase tracking-wider">Loading activity…</span>
        </div>
      </Card>
    );
  }

  if (noData) {
    return (
      <Card>
        <CardLabel>Account activity</CardLabel>
        <p className="text-sm text-fg-dim">
          No comments by this account have been ingested into the OMISPHERE content database yet.
          Scan a video they&apos;ve commented on to see their footprint here.
        </p>
      </Card>
    );
  }

  if (error || !data) {
    return (
      <Card>
        <CardLabel>Account activity</CardLabel>
        <p className="text-sm text-tier-high">{error ?? 'No data.'}</p>
      </Card>
    );
  }

  const totalLikes = data.comments.reduce(
    (s, r) => s + (r.comment.like_count ?? 0),
    0,
  );
  const totalReplies = data.comments.reduce(
    (s, r) => s + (r.comment.reply_count ?? 0),
    0,
  );
  const distinctEntities = new Set(data.comments.map((r) => r.entity.id)).size;

  return (
    <Card>
      <div className="flex items-center justify-between gap-3 mb-3 flex-wrap">
        <CardLabel className="m-0">Account activity · what this channel has posted</CardLabel>
        <Link
          href={`/content/authors/${platform}/${encodeURIComponent(externalId)}`}
          className="font-mono text-2xs text-accent hover:underline uppercase tracking-wider"
        >
          Footprint view →
        </Link>
      </div>

      {/* Summary stats */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-4">
        <Stat
          label="Comments tracked"
          value={data.total.toLocaleString()}
          icon={<MessageCircle size={11} />}
        />
        <Stat
          label="Across content"
          value={distinctEntities.toLocaleString()}
          icon={<ExternalLink size={11} />}
        />
        <Stat
          label="Total likes received"
          value={totalLikes.toLocaleString()}
          icon={<Heart size={11} />}
        />
        <Stat
          label="Replies to them"
          value={totalReplies.toLocaleString()}
          icon={<CornerDownRight size={11} />}
        />
      </div>

      {data.total > data.comments.length && (
        <p className="font-mono text-2xs text-fg-mute mb-3">
          Showing newest {data.comments.length.toLocaleString()} of {data.total.toLocaleString()} comments
        </p>
      )}

      {/* Comment list */}
      <div className="space-y-2 max-h-[600px] overflow-y-auto pr-1">
        {data.comments.map((row, i) => (
          <CommentRow key={row.comment.id ?? i} row={row} />
        ))}
      </div>
    </Card>
  );
}

function CommentRow({ row }: { row: AuthorCommentRow }) {
  const c = row.comment;
  const e = row.entity;

  return (
    <div className="bg-bg-elev border border-border-1 rounded-md p-3">
      {/* Source content link */}
      <div className="flex items-center justify-between gap-2 mb-1.5 flex-wrap">
        <Link
          href={`/content/${e.platform}/${e.content_id}`}
          className="flex items-center gap-1.5 font-mono text-2xs text-accent hover:underline truncate max-w-[60%]"
        >
          <ExternalLink size={10} className="shrink-0" />
          <span className="truncate">{e.title || e.content_id}</span>
        </Link>
        <span className="font-mono text-2xs text-fg-mute shrink-0">{timeAgo(c.observed_at)}</span>
      </div>

      {/* Comment text */}
      <p className="text-sm text-fg leading-relaxed whitespace-pre-wrap break-words">{c.text}</p>

      {/* Engagement stats */}
      {(c.like_count !== null || c.reply_count !== null) && (
        <div className="flex items-center gap-3 mt-1.5 font-mono text-2xs text-fg-faint">
          {c.like_count !== null && (
            <span className="flex items-center gap-1">
              <Heart size={9} />
              {c.like_count.toLocaleString()}
            </span>
          )}
          {c.reply_count !== null && c.reply_count > 0 && (
            <span className="flex items-center gap-1">
              <CornerDownRight size={9} />
              {c.reply_count.toLocaleString()}
            </span>
          )}
        </div>
      )}
    </div>
  );
}

function Stat({
  label,
  value,
  icon,
}: {
  label: string;
  value: string;
  icon?: React.ReactNode;
}) {
  return (
    <div className="bg-bg border border-border-1 rounded-md p-3">
      <div className="flex items-center gap-1 font-mono text-2xs text-fg-mute uppercase tracking-wider mb-1.5">
        {icon}
        {label}
      </div>
      <div className="font-mono text-base font-medium tabular-nums text-fg">{value}</div>
    </div>
  );
}
