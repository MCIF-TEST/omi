'use client';

import Link from 'next/link';
import { useState, useEffect } from 'react';
import {
  TrendingUp,
  TrendingDown,
  Minus,
  Users,
  MessageCircle,
  AlertTriangle,
  Shield,
  ShieldAlert,
  Flame,
  RefreshCw,
} from 'lucide-react';
import { type BatchDiffResponse, type ContentCommentOut, ApiError, apiClient } from '@/lib/api';
import { timeAgo } from '@/lib/format';

const RISK_CONFIG: Record<string, { label: string; icon: React.ReactNode; cls: string }> = {
  extreme:  { label: 'Extreme',  icon: <Flame size={10} />,        cls: 'text-tier-high border-tier-high/40 bg-tier-high/10' },
  high:     { label: 'High',     icon: <ShieldAlert size={10} />,  cls: 'text-tier-elevated border-tier-elevated/40 bg-tier-elevated/10' },
  elevated: { label: 'High',     icon: <ShieldAlert size={10} />,  cls: 'text-tier-elevated border-tier-elevated/40 bg-tier-elevated/10' },
  moderate: { label: 'Moderate', icon: <AlertTriangle size={10} />, cls: 'text-tier-moderate border-tier-moderate/40 bg-tier-moderate/10' },
  low:      { label: 'Low',      icon: <Shield size={10} />,       cls: 'text-tier-low border-tier-low/40 bg-tier-low/10' },
};

function riskConfig(tier: string) {
  return RISK_CONFIG[tier] ?? RISK_CONFIG.low;
}

interface Props {
  platform: string;
  contentId: string;
  totalBatches: number;
}

export function DiffPanel({ platform, contentId, totalBatches }: Props) {
  const [diff, setDiff] = useState<BatchDiffResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (totalBatches < 2) {
      setLoading(false);
      return;
    }
    apiClient<BatchDiffResponse>(`/v1/content/${platform}/${contentId}/diff`)
      .then(setDiff)
      .catch((err) => {
        if (err instanceof ApiError && err.status === 409) {
          // Not enough batches — hide panel
        } else {
          setError(err instanceof ApiError ? err.message : 'Failed to load diff');
        }
      })
      .finally(() => setLoading(false));
  }, [platform, contentId, totalBatches]);

  if (totalBatches < 2) return null;
  if (loading) return <DiffSkeleton />;
  if (error) return null;
  if (!diff) return null;

  const deltaPct = Math.round(diff.coordination_score_delta * 100);
  const fromPct = Math.round(diff.from_batch.coordination_score * 100);
  const toPct = Math.round(diff.to_batch.coordination_score * 100);

  const deltaPositive = deltaPct > 0;
  const deltaNeutral = deltaPct === 0;
  const deltaColor = deltaPositive ? 'text-tier-elevated' : deltaNeutral ? 'text-fg-dim' : 'text-tier-low';
  const DeltaIcon = deltaPositive ? TrendingUp : deltaNeutral ? Minus : TrendingDown;

  const fromRisk = riskConfig(diff.from_batch.risk_tier);
  const toRisk = riskConfig(diff.to_batch.risk_tier);

  return (
    <div className="bg-bg-elev border border-border-1 rounded-md overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-border-1">
        <p className="font-mono text-2xs tracking-[0.18em] text-fg-mute uppercase">
          What changed
          <span className="ml-2 text-fg-faint normal-case tracking-normal">
            batch #{diff.from_batch.id} → #{diff.to_batch.id}
          </span>
        </p>
        <span className="font-mono text-2xs text-fg-faint">
          {timeAgo(diff.from_batch.fetched_at)} → {timeAgo(diff.to_batch.fetched_at)}
        </span>
      </div>

      <div className="p-4 space-y-4">
        {/* Score delta + risk tier */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          {/* Coordination delta */}
          <div className="bg-bg border border-border-1 rounded-md p-3">
            <div className="font-mono text-2xs text-fg-mute uppercase tracking-wider mb-2">
              Coord. shift
            </div>
            <div className={`flex items-center gap-1 font-mono text-2xl font-semibold tabular-nums ${deltaColor}`}>
              <DeltaIcon size={18} />
              {deltaPct > 0 ? '+' : ''}{deltaPct}pp
            </div>
            <div className="font-mono text-2xs text-fg-mute mt-0.5">
              {fromPct}% → {toPct}%
            </div>
          </div>

          {/* Risk tier */}
          <div className="bg-bg border border-border-1 rounded-md p-3">
            <div className="font-mono text-2xs text-fg-mute uppercase tracking-wider mb-2">
              Risk tier
            </div>
            {diff.risk_tier_changed ? (
              <div className="space-y-1">
                <span className={`inline-flex items-center gap-0.5 font-mono text-2xs px-1.5 py-0.5 rounded-sm border ${fromRisk.cls} line-through opacity-60`}>
                  {fromRisk.icon} {fromRisk.label}
                </span>
                <span className={`inline-flex items-center gap-0.5 font-mono text-2xs px-1.5 py-0.5 rounded-sm border ${toRisk.cls}`}>
                  {toRisk.icon} {toRisk.label}
                </span>
              </div>
            ) : (
              <span className={`inline-flex items-center gap-0.5 font-mono text-2xs px-1.5 py-0.5 rounded-sm border ${toRisk.cls}`}>
                {toRisk.icon} {toRisk.label}
              </span>
            )}
          </div>

          {/* New comments */}
          <div className="bg-bg border border-border-1 rounded-md p-3">
            <div className="flex items-center gap-1 font-mono text-2xs text-fg-mute uppercase tracking-wider mb-2">
              <MessageCircle size={10} /> New comments
            </div>
            <div className={`font-mono text-2xl font-semibold tabular-nums ${diff.new_comment_count > 0 ? 'text-fg' : 'text-fg-dim'}`}>
              +{diff.new_comment_count.toLocaleString()}
            </div>
          </div>

          {/* New authors */}
          <div className="bg-bg border border-border-1 rounded-md p-3">
            <div className="flex items-center gap-1 font-mono text-2xs text-fg-mute uppercase tracking-wider mb-2">
              <Users size={10} /> New authors
            </div>
            <div className={`font-mono text-2xl font-semibold tabular-nums ${diff.new_author_count > 0 ? 'text-accent' : 'text-fg-dim'}`}>
              +{diff.new_author_count.toLocaleString()}
            </div>
            {diff.new_authors.length > 0 && (
              <div className="font-mono text-2xs text-fg-mute mt-0.5 truncate">
                {diff.new_authors.slice(0, 3).join(', ')}
                {diff.new_authors.length > 3 && ` +${diff.new_authors.length - 3} more`}
              </div>
            )}
          </div>
        </div>

        {/* Tier distribution delta */}
        {Object.keys(diff.tier_distribution_delta).some((k) => diff.tier_distribution_delta[k] !== 0) && (
          <TierDelta delta={diff.tier_distribution_delta} />
        )}

        {/* Sample new comments */}
        {diff.sample_new_comments.length > 0 && (
          <div>
            <p className="font-mono text-2xs tracking-[0.16em] text-fg-mute uppercase mb-2">
              Sample new comments
            </p>
            <div className="space-y-2">
              {diff.sample_new_comments.map((c) => (
                <NewCommentRow key={c.id} comment={c} platform={platform} />
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function TierDelta({ delta }: { delta: Record<string, number> }) {
  const tiers = ['high', 'elevated', 'moderate', 'low'];
  const cls: Record<string, string> = {
    high: 'text-tier-high',
    elevated: 'text-tier-elevated',
    moderate: 'text-tier-moderate',
    low: 'text-tier-low',
  };
  const entries = tiers.filter((t) => delta[t] !== 0 && delta[t] !== undefined);
  if (entries.length === 0) return null;
  return (
    <div>
      <p className="font-mono text-2xs tracking-[0.16em] text-fg-mute uppercase mb-2">
        Tier distribution shift
      </p>
      <div className="flex items-center gap-3 flex-wrap">
        {entries.map((tier) => {
          const v = delta[tier];
          return (
            <span key={tier} className={`flex items-center gap-1 font-mono text-2xs ${cls[tier] ?? 'text-fg-dim'}`}>
              {tier}: {v > 0 ? '+' : ''}{v}
            </span>
          );
        })}
      </div>
    </div>
  );
}

function NewCommentRow({ comment: c, platform }: { comment: ContentCommentOut; platform: string }) {
  return (
    <div className="bg-bg border border-border-1 rounded-md p-3">
      <div className="flex items-center justify-between mb-1">
        <Link
          href={`/content/authors/${platform}/${encodeURIComponent(c.author_external_id)}`}
          className="font-mono text-2xs text-fg-dim hover:text-accent transition-colors"
        >
          {c.author_handle ? `@${c.author_handle}` : c.author_external_id}
        </Link>
        <span className="font-mono text-2xs text-fg-mute">{timeAgo(c.observed_at)}</span>
      </div>
      <p className="text-sm text-fg leading-relaxed line-clamp-2">{c.text}</p>
    </div>
  );
}

function DiffSkeleton() {
  return (
    <div className="bg-bg-elev border border-border-1 rounded-md p-4 animate-pulse">
      <div className="flex items-center gap-2 mb-4">
        <RefreshCw size={12} className="text-fg-mute animate-spin" />
        <span className="font-mono text-2xs text-fg-mute uppercase tracking-wider">
          Loading diff…
        </span>
      </div>
      <div className="grid grid-cols-4 gap-3">
        {[0, 1, 2, 3].map((i) => (
          <div key={i} className="bg-bg border border-border-1 rounded-md p-3 h-20" />
        ))}
      </div>
    </div>
  );
}
