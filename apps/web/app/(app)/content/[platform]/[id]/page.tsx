import { notFound } from 'next/navigation';
import Link from 'next/link';
import {
  ArrowLeft,
  Shield,
  AlertTriangle,
  ShieldAlert,
  Flame,
  Users,
  Layers,
  MessageCircle,
  ExternalLink,
  Calendar,
  BarChart3,
} from 'lucide-react';
import { Card, CardLabel, CardTitle } from '@/components/ui/card';
import {
  type ContentEntityDetail,
  type CommentBatchOut,
  type ContentCommentOut,
  ApiError,
} from '@/lib/api';
import { apiServer } from '@/lib/api-server';
import { timeAgo } from '@/lib/format';
import { RescanButton } from './rescan-button';
import { DiffPanel } from './diff-panel';

export const dynamic = 'force-dynamic';

export async function generateMetadata({
  params,
}: {
  params: { platform: string; id: string };
}) {
  return { title: `${params.platform}/${params.id} — Content Intelligence` };
}

const RISK_CONFIG: Record<string, { label: string; icon: React.ReactNode; cls: string; barCls: string }> = {
  extreme:  { label: 'Extreme',  icon: <Flame size={10} />,       cls: 'text-tier-high border-tier-high/40 bg-tier-high/10',           barCls: 'bg-tier-high' },
  high:     { label: 'High',     icon: <ShieldAlert size={10} />, cls: 'text-tier-elevated border-tier-elevated/40 bg-tier-elevated/10', barCls: 'bg-tier-elevated' },
  elevated: { label: 'High',     icon: <ShieldAlert size={10} />, cls: 'text-tier-elevated border-tier-elevated/40 bg-tier-elevated/10', barCls: 'bg-tier-elevated' },
  moderate: { label: 'Moderate', icon: <AlertTriangle size={10} />, cls: 'text-tier-moderate border-tier-moderate/40 bg-tier-moderate/10', barCls: 'bg-tier-moderate' },
  low:      { label: 'Low',      icon: <Shield size={10} />,      cls: 'text-tier-low border-tier-low/40 bg-tier-low/10',               barCls: 'bg-tier-low' },
};

function riskConfig(tier: string) {
  return RISK_CONFIG[tier] ?? RISK_CONFIG.low;
}

export default async function ContentEntityPage({
  params,
}: {
  params: { platform: string; id: string };
}) {
  let data: ContentEntityDetail;
  try {
    data = await apiServer<ContentEntityDetail>(
      `/v1/content/${params.platform}/${params.id}`,
    );
  } catch (err) {
    if (err instanceof ApiError && err.status === 404) notFound();
    return (
      <Card>
        <CardLabel>Error loading content entity</CardLabel>
        <CardTitle>Something went wrong</CardTitle>
        <p className="text-sm text-fg-dim">
          {err instanceof ApiError ? err.message : 'Unknown error'}
        </p>
      </Card>
    );
  }

  const { entity: e, batches, recent_comments, total_comments, has_continuation } = data;
  const risk = riskConfig(e.latest_risk_tier);
  const coord_pct = Math.round(e.latest_coordination_score * 100);

  // Build tier distribution display
  const tierOrder = ['high', 'elevated', 'moderate', 'low'];
  const tierColors: Record<string, string> = {
    high: 'bg-tier-high',
    elevated: 'bg-tier-elevated',
    moderate: 'bg-tier-moderate',
    low: 'bg-tier-low',
  };
  const tierTotal = Object.values(e.latest_tier_distribution).reduce((s, v) => s + v, 0);

  return (
    <div className="space-y-6">
      {/* Back link */}
      <Link
        href="/content"
        className="inline-flex items-center gap-1.5 font-mono text-2xs tracking-wider uppercase text-fg-mute hover:text-fg transition-colors"
      >
        <ArrowLeft size={12} /> Content database
      </Link>

      {/* Header */}
      <header className="flex items-start gap-4">
        {e.thumbnail_url && (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={e.thumbnail_url}
            alt=""
            className="w-32 h-20 object-cover rounded-md border border-border-1 shrink-0"
          />
        )}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-2 flex-wrap">
            <span className="font-mono text-2xs tracking-wider uppercase px-1.5 py-0.5 rounded-sm border border-border-2 text-fg-mute">
              {e.platform}
            </span>
            <span
              className={`inline-flex items-center gap-1 font-mono text-2xs tracking-wider uppercase px-2 py-0.5 rounded-sm border ${risk.cls}`}
            >
              {risk.icon}
              {risk.label} risk
            </span>
          </div>
          <h1 className="text-xl font-semibold text-fg tracking-tight leading-tight">
            {e.title || e.content_id}
          </h1>
          {e.author_handle && (
            <p className="text-sm text-fg-dim mt-0.5">@{e.author_handle}</p>
          )}
          <div className="flex items-center gap-4 mt-2 flex-wrap">
            {e.canonical_url && (
              <a
                href={e.canonical_url}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1 font-mono text-2xs text-accent hover:underline"
              >
                <ExternalLink size={10} /> View original
              </a>
            )}
            <span className="font-mono text-2xs text-fg-mute">
              <Calendar size={10} className="inline mr-1" />
              First scanned {timeAgo(e.first_scanned_at)}
            </span>
            <span className="font-mono text-2xs text-fg-mute">
              Last updated {timeAgo(e.last_scanned_at)}
            </span>
          </div>
        </div>
      </header>

      {/* Intelligence summary tiles */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <BigStat
          label="Coordination"
          value={`${coord_pct}%`}
          sub={risk.label + ' risk'}
          accent={coord_pct >= 40}
        />
        <BigStat
          label="Batches"
          value={e.total_batches}
          sub={`${e.contributor_count} scanner${e.contributor_count !== 1 ? 's' : ''}`}
          icon={<Layers size={12} />}
        />
        <BigStat
          label="Comments"
          value={e.total_comments_collected.toLocaleString()}
          sub={`${e.total_distinct_authors.toLocaleString()} authors`}
          icon={<MessageCircle size={12} />}
        />
        <BigStat
          label="Unique authors"
          value={e.total_distinct_authors.toLocaleString()}
          sub="across all batches"
          icon={<Users size={12} />}
        />
      </div>

      {/* Tier distribution bar */}
      {tierTotal > 0 && (
        <div className="bg-bg-elev border border-border-1 rounded-md p-4">
          <p className="font-mono text-2xs tracking-[0.18em] text-fg-mute uppercase mb-3">
            Author tier distribution
          </p>
          <div className="flex h-3 rounded-full overflow-hidden gap-px">
            {tierOrder.map((tier) => {
              const count = e.latest_tier_distribution[tier] || 0;
              const pct = tierTotal > 0 ? (count / tierTotal) * 100 : 0;
              if (pct < 0.5) return null;
              return (
                <div
                  key={tier}
                  className={`${tierColors[tier] || 'bg-fg-mute'} transition-all`}
                  style={{ width: `${pct}%` }}
                  title={`${tier}: ${count} (${Math.round(pct)}%)`}
                />
              );
            })}
          </div>
          <div className="flex items-center gap-4 mt-2 flex-wrap">
            {tierOrder.map((tier) => {
              const count = e.latest_tier_distribution[tier] || 0;
              if (count === 0) return null;
              return (
                <span key={tier} className="flex items-center gap-1.5 font-mono text-2xs text-fg-dim">
                  <span className={`w-2 h-2 rounded-full ${tierColors[tier] || 'bg-fg-mute'}`} />
                  {tier}: {count}
                </span>
              );
            })}
          </div>
        </div>
      )}

      {/* Longitudinal evolution chart — only meaningful with 2+ batches */}
      {batches.length >= 2 && <EvolutionChart batches={batches} />}

      {/* What changed since last scan */}
      <DiffPanel platform={e.platform} contentId={e.content_id} totalBatches={e.total_batches} />

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Batch history */}
        <div className="lg:col-span-1 space-y-3">
          <div className="flex items-start justify-between gap-3">
            <p className="font-mono text-2xs tracking-[0.18em] text-fg-mute uppercase pt-1.5">
              Batch history
            </p>
            <RescanButton
              platform={e.platform}
              contentId={e.content_id}
              hasContinuation={has_continuation}
            />
          </div>
          {batches.length === 0 ? (
            <p className="text-sm text-fg-dim">No batches yet.</p>
          ) : (
            <div className="space-y-2">
              {batches.map((b, i) => (
                <BatchRow key={b.id} batch={b} isLatest={i === 0} />
              ))}
            </div>
          )}
        </div>

        {/* Recent comments */}
        <div className="lg:col-span-2 space-y-3">
          <p className="font-mono text-2xs tracking-[0.18em] text-fg-mute uppercase">
            Recent comments
            <span className="ml-2 text-fg-faint">({total_comments.toLocaleString()} total)</span>
          </p>
          {recent_comments.length === 0 ? (
            <p className="text-sm text-fg-dim">No comments stored yet.</p>
          ) : (
            <div className="space-y-2">
              {recent_comments.map((c) => (
                <CommentRow key={c.id} comment={c} platform={e.platform} />
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function EvolutionChart({ batches }: { batches: CommentBatchOut[] }) {
  // Batches come newest-first; reverse for chronological left-to-right plot.
  const ordered = [...batches].reverse();
  const W = 800;
  const H = 180;
  const PADDING = { top: 16, right: 16, bottom: 28, left: 36 };
  const innerW = W - PADDING.left - PADDING.right;
  const innerH = H - PADDING.top - PADDING.bottom;

  const xs = ordered.map((_, i) =>
    ordered.length === 1
      ? PADDING.left + innerW / 2
      : PADDING.left + (i * innerW) / (ordered.length - 1),
  );

  const scoreY = (s: number) => PADDING.top + innerH * (1 - Math.max(0, Math.min(1, s)));
  const maxNew = Math.max(1, ...ordered.map((b) => b.new_comments));
  const barW = Math.max(2, Math.min(20, innerW / ordered.length / 2));

  // Tier→stroke color for the score line segment
  const tierStroke: Record<string, string> = {
    high: '#ef4444',
    extreme: '#ef4444',
    elevated: '#f97316',
    moderate: '#eab308',
    low: '#22c55e',
  };

  // Drift = latest − first (in percentage points)
  const first = ordered[0].coordination_score;
  const last = ordered[ordered.length - 1].coordination_score;
  const driftPct = Math.round((last - first) * 100);
  const driftLabel =
    driftPct > 0 ? `+${driftPct}pp` : driftPct < 0 ? `${driftPct}pp` : '±0pp';
  const driftCls =
    driftPct > 5
      ? 'text-tier-elevated'
      : driftPct < -5
      ? 'text-tier-low'
      : 'text-fg-dim';

  const lineD = xs
    .map((x, i) => `${i === 0 ? 'M' : 'L'} ${x.toFixed(1)} ${scoreY(ordered[i].coordination_score).toFixed(1)}`)
    .join(' ');

  return (
    <div className="bg-bg-elev border border-border-1 rounded-md p-4">
      <div className="flex items-center justify-between mb-3 flex-wrap gap-2">
        <p className="font-mono text-2xs tracking-[0.18em] text-fg-mute uppercase">
          Coordination evolution
          <span className="ml-2 text-fg-faint normal-case tracking-normal">
            ({ordered.length} batches)
          </span>
        </p>
        <div className="flex items-center gap-3 font-mono text-2xs">
          <span className="text-fg-mute uppercase tracking-wider">Drift</span>
          <span className={`tabular-nums font-medium ${driftCls}`}>{driftLabel}</span>
        </div>
      </div>

      <svg
        viewBox={`0 0 ${W} ${H}`}
        className="w-full h-auto"
        preserveAspectRatio="none"
      >
        {/* Grid lines at 25/50/75% */}
        {[0.25, 0.5, 0.75].map((g) => (
          <line
            key={g}
            x1={PADDING.left}
            x2={W - PADDING.right}
            y1={scoreY(g)}
            y2={scoreY(g)}
            stroke="currentColor"
            strokeOpacity={0.08}
            strokeDasharray="2,4"
          />
        ))}
        {/* Y axis labels */}
        {[0, 0.5, 1].map((g) => (
          <text
            key={g}
            x={PADDING.left - 6}
            y={scoreY(g) + 3}
            textAnchor="end"
            className="fill-current"
            fontSize="9"
            opacity={0.4}
            fontFamily="ui-monospace, monospace"
          >
            {Math.round(g * 100)}%
          </text>
        ))}

        {/* New-comments bars (background) */}
        {ordered.map((b, i) => {
          const h = innerH * (b.new_comments / maxNew) * 0.5; // bars fill bottom 50%
          return (
            <rect
              key={`bar-${b.id}`}
              x={xs[i] - barW / 2}
              y={H - PADDING.bottom - h}
              width={barW}
              height={h}
              fill="currentColor"
              opacity={0.12}
              rx={1}
            />
          );
        })}

        {/* Score line */}
        <path
          d={lineD}
          fill="none"
          stroke="currentColor"
          strokeWidth={1.5}
          opacity={0.6}
        />

        {/* Per-batch points colored by risk tier */}
        {ordered.map((b, i) => (
          <g key={`pt-${b.id}`}>
            <circle
              cx={xs[i]}
              cy={scoreY(b.coordination_score)}
              r={4}
              fill={tierStroke[b.risk_tier] || '#9ca3af'}
              stroke="rgb(var(--bg-elev))"
              strokeWidth={1.5}
            >
              <title>
                {new Date(b.fetched_at).toLocaleString()}
                {'\n'}
                Coordination: {Math.round(b.coordination_score * 100)}% ({b.risk_tier})
                {'\n'}
                New: {b.new_comments} · Dupes: {b.duplicates} · Authors: {b.distinct_authors}
              </title>
            </circle>
          </g>
        ))}

        {/* X-axis time labels (first / middle / last) */}
        {[0, Math.floor(ordered.length / 2), ordered.length - 1]
          .filter((v, idx, arr) => arr.indexOf(v) === idx)
          .map((i) => (
            <text
              key={`xl-${i}`}
              x={xs[i]}
              y={H - PADDING.bottom + 14}
              textAnchor="middle"
              className="fill-current"
              fontSize="9"
              opacity={0.4}
              fontFamily="ui-monospace, monospace"
            >
              {shortDate(ordered[i].fetched_at)}
            </text>
          ))}
      </svg>

      <div className="flex items-center gap-4 mt-2 flex-wrap font-mono text-2xs text-fg-mute">
        <span className="flex items-center gap-1.5">
          <span className="inline-block w-3 h-0.5 bg-fg-dim" /> Coordination score
        </span>
        <span className="flex items-center gap-1.5">
          <span className="inline-block w-3 h-2 bg-fg/20 rounded-sm" /> New comments per batch
        </span>
      </div>
    </div>
  );
}

function shortDate(iso: string): string {
  const d = new Date(iso);
  return `${d.getMonth() + 1}/${d.getDate()} ${d.getHours()}:${String(d.getMinutes()).padStart(2, '0')}`;
}

function BigStat({
  label,
  value,
  sub,
  accent,
  icon,
}: {
  label: string;
  value: string | number;
  sub?: string;
  accent?: boolean;
  icon?: React.ReactNode;
}) {
  return (
    <div className="bg-bg-elev border border-border-1 rounded-md p-4">
      <div className="flex items-center gap-1.5 font-mono text-2xs text-fg-mute uppercase tracking-wider mb-2">
        {icon}
        {label}
      </div>
      <div
        className={`font-mono text-2xl font-semibold tabular-nums mb-0.5 ${
          accent ? 'text-tier-elevated' : 'text-fg'
        }`}
      >
        {value}
      </div>
      {sub && <div className="font-mono text-2xs text-fg-mute">{sub}</div>}
    </div>
  );
}

function BatchRow({ batch: b, isLatest }: { batch: CommentBatchOut; isLatest: boolean }) {
  const risk = riskConfig(b.risk_tier);
  const coord_pct = Math.round(b.coordination_score * 100);
  return (
    <div
      className={`bg-bg-elev border rounded-md p-3 ${
        isLatest ? 'border-accent/30' : 'border-border-1'
      }`}
    >
      <div className="flex items-center justify-between mb-1.5">
        <span className="font-mono text-2xs text-fg-dim">{timeAgo(b.fetched_at)}</span>
        <span
          className={`inline-flex items-center gap-0.5 font-mono text-2xs tracking-wider uppercase px-1.5 py-0.5 rounded-sm border ${risk.cls}`}
        >
          {risk.icon}
          {coord_pct}%
        </span>
      </div>
      <div className="grid grid-cols-3 gap-2">
        <div>
          <div className="font-mono text-2xs text-fg-mute uppercase">New</div>
          <div className="font-mono text-sm font-medium text-fg">{b.new_comments}</div>
        </div>
        <div>
          <div className="font-mono text-2xs text-fg-mute uppercase">Dupes</div>
          <div className="font-mono text-sm font-medium text-fg-dim">{b.duplicates}</div>
        </div>
        <div>
          <div className="font-mono text-2xs text-fg-mute uppercase">Authors</div>
          <div className="font-mono text-sm font-medium text-fg">{b.distinct_authors}</div>
        </div>
      </div>
      {b.new_authors > 0 && (
        <p className="font-mono text-2xs text-accent mt-1.5">
          +{b.new_authors} new author{b.new_authors !== 1 ? 's' : ''}
        </p>
      )}
    </div>
  );
}

function CommentRow({
  comment: c,
  platform,
}: {
  comment: ContentCommentOut;
  platform: string;
}) {
  return (
    <div className="bg-bg-elev border border-border-1 rounded-md p-3">
      <div className="flex items-center justify-between mb-1">
        <Link
          href={`/content/authors/${platform}/${encodeURIComponent(c.author_external_id)}`}
          className="font-mono text-2xs text-fg-dim hover:text-accent transition-colors"
        >
          {c.author_handle ? `@${c.author_handle}` : c.author_external_id}
        </Link>
        <span className="font-mono text-2xs text-fg-mute">{timeAgo(c.observed_at)}</span>
      </div>
      <p className="text-sm text-fg leading-relaxed line-clamp-3">{c.text}</p>
      {(c.like_count !== null || c.reply_count !== null) && (
        <div className="flex items-center gap-3 mt-1.5 font-mono text-2xs text-fg-faint">
          {c.like_count !== null && <span>♥ {c.like_count}</span>}
          {c.reply_count !== null && <span>↩ {c.reply_count}</span>}
        </div>
      )}
    </div>
  );
}
