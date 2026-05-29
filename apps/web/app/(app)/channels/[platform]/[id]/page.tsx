import Link from 'next/link';
import { notFound } from 'next/navigation';
import {
  ArrowLeft,
  User,
  Video,
  Users,
  TrendingUp,
  ExternalLink,
  Activity,
  Repeat,
} from 'lucide-react';
import { Card, CardLabel, CardTitle } from '@/components/ui/card';
import { TierBadge } from '@/components/shared/tier-badge';
import { Sparkline } from '@/components/shared/sparkline';
import { ApiError, type ChannelIntelligenceResponse, type Tier } from '@/lib/api';
import { apiServer } from '@/lib/api-server';
import { timeAgo } from '@/lib/format';

export const dynamic = 'force-dynamic';

export async function generateMetadata({
  params,
}: {
  params: { platform: string; id: string };
}) {
  return { title: `Channel Intelligence — OMISPHERE` };
}

const TIER_CONFIG: Record<string, { label: string; cls: string; barCls: string }> = {
  high:     { label: 'High',     cls: 'text-tier-high',     barCls: 'bg-tier-high' },
  elevated: { label: 'Elevated', cls: 'text-tier-elevated', barCls: 'bg-tier-elevated' },
  moderate: { label: 'Moderate', cls: 'text-tier-moderate', barCls: 'bg-tier-moderate' },
  low:      { label: 'Low',      cls: 'text-tier-low',      barCls: 'bg-tier-low' },
};

function tierCfg(tier: string) {
  return TIER_CONFIG[tier] ?? TIER_CONFIG.low;
}

export default async function ChannelIntelligencePage({
  params,
}: {
  params: { platform: string; id: string };
}) {
  let data: ChannelIntelligenceResponse;
  try {
    data = await apiServer<ChannelIntelligenceResponse>(
      `/v1/channels/${params.platform}/${encodeURIComponent(params.id)}/intelligence`,
    );
  } catch (err) {
    if (err instanceof ApiError && err.status === 404) notFound();
    return (
      <Card>
        <CardLabel>Error</CardLabel>
        <CardTitle>Could not load channel intelligence</CardTitle>
        <p className="text-sm text-fg-dim">
          {err instanceof ApiError ? err.message : 'Unknown error'}
        </p>
      </Card>
    );
  }

  const comp = data.audience_composition;
  const totalCommenters = comp.total_commenters;
  const tiers = [
    { key: 'high',     label: 'High suspicion',     count: comp.high,     cls: tierCfg('high').cls,     barCls: tierCfg('high').barCls },
    { key: 'elevated', label: 'Elevated suspicion', count: comp.elevated, cls: tierCfg('elevated').cls, barCls: tierCfg('elevated').barCls },
    { key: 'moderate', label: 'Moderate suspicion', count: comp.moderate, cls: tierCfg('moderate').cls, barCls: tierCfg('moderate').barCls },
    { key: 'low',      label: 'Low suspicion',      count: comp.low,      cls: tierCfg('low').cls,      barCls: tierCfg('low').barCls },
  ];

  const avgCoord =
    data.risk_trend.length > 0
      ? data.risk_trend.reduce((s, p) => s + p.coordination_score, 0) / data.risk_trend.length
      : null;

  return (
    <div className="space-y-6 max-w-5xl">
      <Link
        href="/content"
        className="inline-flex items-center gap-1.5 font-mono text-2xs tracking-wider uppercase text-fg-mute hover:text-fg transition-colors"
      >
        <ArrowLeft size={12} /> Content database
      </Link>

      {/* Channel header */}
      <header className="relative overflow-hidden bg-bg-elev border border-border-1 rounded-2xl p-6 shadow-card">
        <div className="absolute -top-16 -right-12 w-56 h-56 rounded-full bg-accent/[0.07] blur-3xl pointer-events-none" aria-hidden />
        <div className="absolute inset-0 dot-bg opacity-[0.12] pointer-events-none" aria-hidden />
        <div className="relative flex items-start gap-4">
          <div className="w-12 h-12 rounded-2xl bg-bg border border-border-2 flex items-center justify-center text-accent-2 shrink-0">
            <User size={20} />
          </div>
          <div className="flex-1 min-w-0">
            <p className="font-mono text-2xs tracking-[0.2em] text-accent-2 uppercase mb-1.5 flex items-center gap-2">
              <span className="w-1.5 h-1.5 rounded-full bg-accent-2" />
              {data.platform} · channel intelligence
            </p>
            <h1 className="display text-2xl md:text-3xl font-semibold text-fg tracking-tight truncate">
              {data.display_name || data.handle}
            </h1>
            {data.display_name && (
              <p className="font-mono text-xs text-fg-faint mt-0.5">
                @{data.handle} · {data.external_id}
              </p>
            )}
            {data.bio && (
              <p className="text-sm text-fg-dim mt-2 line-clamp-2">{data.bio}</p>
            )}
          </div>
          {data.follower_count != null && (
            <div className="shrink-0 text-right">
              <div className="font-mono text-xl font-semibold text-fg tabular-nums">
                {data.follower_count.toLocaleString()}
              </div>
              <div className="font-mono text-2xs text-fg-mute uppercase tracking-wider">subscribers</div>
            </div>
          )}
        </div>

        <div className="relative grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-4 mt-5 pt-5 border-t border-border-1/60">
          <Stat label="Videos scanned" value={data.video_count} icon={<Video size={11} />} />
          <Stat
            label="Total commenters"
            value={totalCommenters.toLocaleString()}
            icon={<Users size={11} />}
          />
          <Stat
            label="Avg coordination"
            value={avgCoord !== null ? `${Math.round(avgCoord * 100)}%` : '—'}
            icon={<TrendingUp size={11} />}
          />
          <Stat
            label="Avg comments/video"
            value={
              data.avg_comments_per_video > 0
                ? Math.round(data.avg_comments_per_video).toLocaleString()
                : '—'
            }
            icon={<Activity size={11} />}
          />
          <Stat
            label="Returning ratio"
            value={
              data.returning_commenter_ratio > 0
                ? `${Math.round(data.returning_commenter_ratio * 100)}%`
                : '—'
            }
            icon={<Repeat size={11} />}
          />
          <Stat
            label="Last scanned"
            value={data.last_scanned_at ? timeAgo(data.last_scanned_at) : '—'}
          />
        </div>
      </header>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Audience composition */}
        <Card>
          <CardLabel className="mb-4">Audience composition</CardLabel>
          {totalCommenters === 0 ? (
            <p className="text-sm text-fg-dim">
              No audience data yet — scan some videos from this channel first.
            </p>
          ) : (
            <div className="space-y-3">
              {tiers.map((t) => {
                const pct = totalCommenters > 0 ? Math.round((t.count / totalCommenters) * 100) : 0;
                return (
                  <div key={t.key}>
                    <div className="flex items-center justify-between font-mono text-2xs mb-1">
                      <span className={`uppercase tracking-wider ${t.cls}`}>{t.label}</span>
                      <span className="text-fg tabular-nums">
                        {pct}% · {t.count.toLocaleString()}
                      </span>
                    </div>
                    <div className="h-2 bg-border-1 rounded-full overflow-hidden">
                      <div
                        className={`h-full rounded-full ${t.barCls} transition-all`}
                        style={{ width: `${pct}%` }}
                      />
                    </div>
                  </div>
                );
              })}
              <p className="text-2xs text-fg-faint mt-3 font-mono">
                Aggregated across {data.video_count} scanned video
                {data.video_count !== 1 ? 's' : ''} ·{' '}
                {totalCommenters.toLocaleString()} total comment interactions
              </p>
            </div>
          )}
        </Card>

        {/* Top repeat commenters */}
        <Card>
          <CardLabel className="mb-4">Top repeat commenters</CardLabel>
          {data.top_commenters.length === 0 ? (
            <p className="text-sm text-fg-dim">
              No cross-video commenter data yet. Scan multiple videos to build this view.
            </p>
          ) : (
            <ul className="divide-y divide-border-1 -mx-2">
              {data.top_commenters.slice(0, 10).map((c) => (
                <li key={c.external_id}>
                  <Link
                    href={`/accounts/${encodeURIComponent(c.external_id)}?platform=${c.platform}`}
                    className="flex items-center justify-between gap-3 py-2 px-2 hover:bg-bg-elev-2/50 rounded-sm transition-colors"
                  >
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="text-sm font-medium text-fg truncate">{c.handle}</span>
                        {c.tier && <TierBadge tier={c.tier as 'low' | 'moderate' | 'elevated' | 'high'} size="sm" />}
                      </div>
                      {c.overall_probability != null && (
                        <p className="font-mono text-2xs text-fg-mute">
                          {Math.round(c.overall_probability * 100)}% bot probability
                        </p>
                      )}
                    </div>
                    <span className="font-mono text-2xs text-fg-mute shrink-0 tabular-nums">
                      {c.video_count} video{c.video_count !== 1 ? 's' : ''}
                    </span>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>

      {/* Risk trend table */}
      {data.risk_trend.length > 0 && (
        <Card>
          <div className="flex items-start justify-between gap-4 flex-wrap mb-4">
            <CardLabel className="m-0">
              Scan history · {data.risk_trend.length} batch{data.risk_trend.length !== 1 ? 'es' : ''}
            </CardLabel>
            {data.risk_trend.length >= 2 && (
              <div className="w-full sm:w-[260px]">
                <Sparkline
                  points={data.risk_trend.map((p) => p.coordination_score)}
                  tier={
                    (data.risk_trend[data.risk_trend.length - 1].risk_tier as Tier) ?? 'low'
                  }
                  height={48}
                />
                <div className="flex justify-between mt-1 font-mono text-2xs text-fg-mute">
                  <span>oldest</span>
                  <span>latest</span>
                </div>
              </div>
            )}
          </div>
          <div className="overflow-x-auto -mx-2">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left font-mono text-2xs tracking-[0.16em] uppercase text-fg-mute border-b border-border-1">
                  <th className="px-2 py-2 font-normal">When</th>
                  <th className="px-2 py-2 font-normal">Video</th>
                  <th className="px-2 py-2 font-normal text-right">Coordination</th>
                  <th className="px-2 py-2 font-normal">Risk</th>
                  <th className="px-2 py-2 font-normal text-right">Comments</th>
                </tr>
              </thead>
              <tbody>
                {data.risk_trend.map((pt, i) => {
                  const rc = tierCfg(pt.risk_tier);
                  return (
                    <tr
                      key={i}
                      className="border-b border-border-1/50 hover:bg-bg-elev/30 transition-colors"
                    >
                      <td className="px-2 py-2 font-mono text-2xs text-fg-mute whitespace-nowrap">
                        {timeAgo(pt.date)}
                      </td>
                      <td className="px-2 py-2">
                        <Link
                          href={`/content/${params.platform}/${pt.content_id}`}
                          className="font-mono text-2xs text-accent hover:underline"
                        >
                          {pt.content_id}
                        </Link>
                      </td>
                      <td className="px-2 py-2 text-right font-mono text-sm tabular-nums">
                        {Math.round(pt.coordination_score * 100)}%
                      </td>
                      <td className="px-2 py-2">
                        <span className={`font-mono text-2xs uppercase tracking-wider ${rc.cls}`}>
                          {rc.label}
                        </span>
                      </td>
                      <td className="px-2 py-2 text-right font-mono text-2xs text-fg-mute tabular-nums">
                        {pt.comment_count}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </Card>
      )}

      {/* Video catalogue */}
      <Card>
        <CardLabel className="mb-4">
          Scanned videos · {data.video_count}
        </CardLabel>
        {data.videos.length === 0 ? (
          <p className="text-sm text-fg-dim">
            No videos found. Scan a video from this channel first.
          </p>
        ) : (
          <div className="space-y-2">
            {data.videos.map((v) => {
              const rc = tierCfg(v.latest_risk_tier);
              const coord_pct = Math.round(v.latest_coordination_score * 100);
              return (
                <Link
                  key={v.content_id}
                  href={`/content/${data.platform}/${v.content_id}`}
                  className="flex items-center gap-3 p-3 rounded-sm border border-border-1 hover:border-border-hot hover:bg-bg-elev-2/30 transition-colors group"
                >
                  {v.thumbnail_url && (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img
                      src={v.thumbnail_url}
                      alt=""
                      className="w-16 h-10 object-cover rounded-sm shrink-0 border border-border-1"
                    />
                  )}
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-fg truncate">
                      {v.title || v.content_id}
                    </p>
                    <div className="flex items-center gap-2 mt-0.5 font-mono text-2xs text-fg-mute flex-wrap">
                      <span>{v.total_comments_collected.toLocaleString()} comments</span>
                      <span>·</span>
                      <span>{v.total_batches} batch{v.total_batches !== 1 ? 'es' : ''}</span>
                      <span>·</span>
                      <span>{timeAgo(v.last_scanned_at)}</span>
                      {v.canonical_url && (
                        <>
                          <span>·</span>
                          <a
                            href={v.canonical_url}
                            target="_blank"
                            rel="noopener noreferrer"
                            onClick={(e) => e.stopPropagation()}
                            className="text-accent hover:underline inline-flex items-center gap-0.5"
                          >
                            <ExternalLink size={9} /> YouTube
                          </a>
                        </>
                      )}
                    </div>
                    <TierDistributionBar dist={v.latest_tier_distribution} />
                  </div>
                  <div className="text-right shrink-0">
                    <div className={`font-mono text-sm font-semibold tabular-nums ${rc.cls}`}>
                      {coord_pct}%
                    </div>
                    <div className={`font-mono text-2xs uppercase tracking-wider ${rc.cls}`}>
                      {rc.label}
                    </div>
                  </div>
                </Link>
              );
            })}
          </div>
        )}
      </Card>
    </div>
  );
}

function TierDistributionBar({ dist }: { dist: Record<string, number> }) {
  const total =
    (dist.high ?? 0) + (dist.elevated ?? 0) + (dist.moderate ?? 0) + (dist.low ?? 0);
  if (total === 0) return null;
  const seg = (count: number) => (count / total) * 100;
  return (
    <div className="mt-1.5 flex h-1 w-full max-w-[280px] rounded-full overflow-hidden bg-border-1">
      {dist.high > 0 && (
        <span
          className="h-full bg-tier-high"
          style={{ width: `${seg(dist.high)}%` }}
          title={`High: ${dist.high}`}
        />
      )}
      {dist.elevated > 0 && (
        <span
          className="h-full bg-tier-elevated"
          style={{ width: `${seg(dist.elevated)}%` }}
          title={`Elevated: ${dist.elevated}`}
        />
      )}
      {dist.moderate > 0 && (
        <span
          className="h-full bg-tier-moderate"
          style={{ width: `${seg(dist.moderate)}%` }}
          title={`Moderate: ${dist.moderate}`}
        />
      )}
      {dist.low > 0 && (
        <span
          className="h-full bg-tier-low"
          style={{ width: `${seg(dist.low)}%` }}
          title={`Low: ${dist.low}`}
        />
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
  value: string | number;
  icon?: React.ReactNode;
}) {
  return (
    <div>
      <div className="flex items-center gap-1 font-mono text-2xs text-fg-mute uppercase tracking-wider mb-0.5">
        {icon}
        {label}
      </div>
      <div className="font-mono text-lg font-semibold tabular-nums text-fg">{value}</div>
    </div>
  );
}
