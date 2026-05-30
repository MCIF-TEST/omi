'use client';

import Link from 'next/link';
import { useState, useEffect, useMemo } from 'react';
import {
  MessageCircle, Heart, CornerDownRight, ExternalLink,
  RefreshCw, Search as SearchIcon, X,
} from 'lucide-react';
import { Card, CardLabel } from '@/components/ui/card';
import { apiClient, ApiError, type AuthorCommentRow, type AuthorCommentsResponse } from '@/lib/api';
import { timeAgo } from '@/lib/format';
import { PostingHeatmap } from './posting-heatmap';

interface Props {
  platform: string;
  externalId: string;
}

export function AccountActivityPanel({ platform, externalId }: Props) {
  const [data, setData] = useState<AuthorCommentsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [noData, setNoData] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState('');

  useEffect(() => {
    apiClient<AuthorCommentsResponse>(
      `/v1/content/authors/${platform}/${encodeURIComponent(externalId)}/comments?limit=1000`,
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

  const filtered = useMemo(() => {
    if (!data) return [];
    if (!query.trim()) return data.comments;
    const needle = query.trim().toLowerCase();
    return data.comments.filter(
      (r) =>
        r.comment.text.toLowerCase().includes(needle) ||
        (r.entity.title || '').toLowerCase().includes(needle) ||
        (r.entity.content_id || '').toLowerCase().includes(needle),
    );
  }, [data, query]);

  if (loading) {
    return (
      <Card>
        <div className="flex items-center gap-2 text-fg-mute">
          <RefreshCw size={12} className="animate-spin" />
          <span className="font-mono text-2xs uppercase tracking-wider">Loading account activity…</span>
        </div>
      </Card>
    );
  }

  if (noData) {
    return (
      <Card>
        <CardLabel>Account activity</CardLabel>
        <p className="text-sm text-fg-dim">
          No comments by this channel have been ingested into the OMISPHERE content database yet.
          Scan a video they&apos;ve commented on to start building their footprint here.
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

  const totalLikes = data.comments.reduce((s, r) => s + (r.comment.like_count ?? 0), 0);
  const totalReplies = data.comments.reduce((s, r) => s + (r.comment.reply_count ?? 0), 0);
  const distinctEntities = new Set(data.comments.map((r) => r.entity.id)).size;

  return (
    <div className="space-y-4">
      {/* Heatmap up top — visual pattern read */}
      <PostingHeatmap comments={data.comments} />

      <Card>
        <div className="flex items-center justify-between gap-3 mb-4 flex-wrap">
          <CardLabel className="m-0">Account activity · everything this channel has posted</CardLabel>
          <Link
            href={`/content/authors/${platform}/${encodeURIComponent(externalId)}`}
            className="font-mono text-2xs text-accent hover:underline uppercase tracking-wider"
          >
            Cross-content footprint →
          </Link>
        </div>

        {/* Summary stats */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-4">
          <Stat label="Comments tracked" value={data.total.toLocaleString()} icon={<MessageCircle size={11} />} />
          <Stat label="On distinct content" value={distinctEntities.toLocaleString()} icon={<ExternalLink size={11} />} />
          <Stat label="Likes received" value={totalLikes.toLocaleString()} icon={<Heart size={11} />} />
          <Stat label="Replies received" value={totalReplies.toLocaleString()} icon={<CornerDownRight size={11} />} />
        </div>

        {/* Search box */}
        <div className="mb-3">
          <div className="relative max-w-md">
            <SearchIcon
              size={13}
              className="absolute left-3 top-1/2 -translate-y-1/2 text-fg-mute pointer-events-none"
            />
            <input
              aria-label="Search comments"
              type="search"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search their comments…"
              className="w-full pl-9 pr-9 py-2 bg-bg border border-border-1 rounded-sm text-sm text-fg placeholder:text-fg-mute focus:outline-none focus:border-accent transition-colors"
            />
            {query && (
              <button
                type="button"
                onClick={() => setQuery('')}
                className="absolute right-2.5 top-1/2 -translate-y-1/2 text-fg-mute hover:text-fg"
                aria-label="Clear search"
              >
                <X size={13} />
              </button>
            )}
          </div>
          {query && (
            <p className="mt-2 font-mono text-2xs text-fg-mute">
              {filtered.length.toLocaleString()} of {data.comments.length.toLocaleString()} comments match &ldquo;{query}&rdquo;
            </p>
          )}
        </div>

        {data.total > data.comments.length && (
          <p className="font-mono text-2xs text-fg-mute mb-3">
            Showing newest {data.comments.length.toLocaleString()} of {data.total.toLocaleString()} comments
          </p>
        )}

        {/* Comment list */}
        {filtered.length === 0 ? (
          <p className="text-sm text-fg-dim italic py-6 text-center">
            No comments match that search.
          </p>
        ) : (
          <div className="space-y-2 max-h-[700px] overflow-y-auto pr-1">
            {filtered.map((row, i) => (
              <CommentRow key={row.comment.id ?? i} row={row} highlight={query} />
            ))}
          </div>
        )}
      </Card>
    </div>
  );
}

function highlightText(text: string, needle: string) {
  if (!needle.trim()) return text;
  const lower = text.toLowerCase();
  const lowerNeedle = needle.toLowerCase();
  const parts: React.ReactNode[] = [];
  let idx = 0;
  while (idx < text.length) {
    const found = lower.indexOf(lowerNeedle, idx);
    if (found === -1) {
      parts.push(text.slice(idx));
      break;
    }
    if (found > idx) parts.push(text.slice(idx, found));
    parts.push(
      <mark key={`${idx}-h`} className="bg-accent/30 text-fg rounded-sm px-0.5">
        {text.slice(found, found + needle.length)}
      </mark>,
    );
    idx = found + needle.length;
  }
  return <>{parts}</>;
}

function CommentRow({ row, highlight }: { row: AuthorCommentRow; highlight: string }) {
  const c = row.comment;
  const e = row.entity;

  return (
    <div className="bg-bg-elev border border-border-1 rounded-md p-3">
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

      <p className="text-sm text-fg leading-relaxed whitespace-pre-wrap break-words">
        {highlightText(c.text, highlight)}
      </p>

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

function Stat({ label, value, icon }: { label: string; value: string; icon?: React.ReactNode }) {
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
