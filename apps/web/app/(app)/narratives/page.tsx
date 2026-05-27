import Link from 'next/link';
import {
  Users,
  ArrowRight,
  ShieldAlert,
  Shield,
  AlertTriangle,
  Flame,
  Radio,
  Activity,
  Crosshair,
} from 'lucide-react';
import { Card, CardLabel, CardTitle } from '@/components/ui/card';
import {
  type NarrativesResponse,
  type NarrativeOut,
  type RiskTier,
} from '@/lib/api';
import { apiServer } from '@/lib/api-server';
import { timeAgo } from '@/lib/format';

export const metadata = { title: 'Narrative intelligence — OMISPHERE' };
export const dynamic = 'force-dynamic';

const WINDOWS = [1, 7, 30, 90] as const;
const RISK_FILTERS = [
  { value: 'low', label: 'All clusters' },
  { value: 'moderate', label: 'Moderate+' },
  { value: 'high', label: 'High+' },
  { value: 'extreme', label: 'Extreme only' },
] as const;

const RISK_CONFIG: Record<
  RiskTier,
  {
    label: string;
    icon: React.ReactNode;
    cls: string;
    barCls: string;
  }
> = {
  extreme: {
    label: 'Extreme',
    icon: <Flame size={11} />,
    cls: 'text-tier-high border-tier-high/40 bg-tier-high/10',
    barCls: 'bg-tier-high',
  },
  high: {
    label: 'High',
    icon: <ShieldAlert size={11} />,
    cls: 'text-tier-elevated border-tier-elevated/40 bg-tier-elevated/10',
    barCls: 'bg-tier-elevated',
  },
  moderate: {
    label: 'Moderate',
    icon: <AlertTriangle size={11} />,
    cls: 'text-tier-moderate border-tier-moderate/40 bg-tier-moderate/10',
    barCls: 'bg-tier-moderate',
  },
  low: {
    label: 'Low',
    icon: <Shield size={11} />,
    cls: 'text-tier-low border-tier-low/40 bg-tier-low/10',
    barCls: 'bg-tier-low',
  },
};

export default async function NarrativesPage({
  searchParams,
}: {
  searchParams: { window?: string; min?: string };
}) {
  const window_days = Math.max(
    1,
    Math.min(90, parseInt(searchParams.window || '7', 10) || 7),
  );
  const min_risk_tier = (
    ['low', 'moderate', 'high', 'extreme'].includes(searchParams.min || '')
      ? searchParams.min
      : 'moderate'
  ) as RiskTier;

  let data: NarrativesResponse;
  try {
    data = await apiServer<NarrativesResponse>(
      `/v1/narratives?window_days=${window_days}&limit=40&min_risk_tier=${min_risk_tier}`,
    );
  } catch {
    data = { window_days, embedder: 'unknown', narratives: [] };
  }

  const narratives = data.narratives;

  const extreme = narratives.filter((n) => n.risk_tier === 'extreme').length;
  const high = narratives.filter((n) => n.risk_tier === 'high').length;
  const avgCoord =
    narratives.length === 0
      ? 0
      : Math.round(
          (narratives.reduce((s, n) => s + n.coordination_score, 0) /
            narratives.length) *
            100,
        );

  return (
    <div className="space-y-6">
      {/* Header */}
      <header className="flex items-end justify-between gap-4 flex-wrap">
        <div>
          <p className="font-mono text-2xs tracking-[0.18em] text-fg-mute uppercase mb-1">
            Narrative intelligence
          </p>
          <h1 className="text-2xl font-semibold text-fg tracking-tight">
            Coordination & propagation clusters
          </h1>
          <p className="mt-1 text-sm text-fg-dim max-w-2xl">
            Semantic clusters scored across eight independent coordination
            signals. Only moderate-and-above accounts contribute to cluster
            membership — organic discussion is excluded by default.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <span className="font-mono text-2xs tracking-[0.18em] text-fg-mute uppercase">
            Window
          </span>
          {WINDOWS.map((d) => (
            <Link
              key={d}
              href={`/narratives?window=${d}&min=${min_risk_tier}`}
              className={`font-mono text-2xs tracking-wider uppercase px-2.5 py-1.5 rounded-sm border transition-colors ${
                d === window_days
                  ? 'border-accent bg-accent/10 text-accent'
                  : 'border-border-2 text-fg-dim hover:text-fg hover:border-border-hot'
              }`}
            >
              {d}d
            </Link>
          ))}
        </div>
      </header>

      {/* Filter chips */}
      <div className="flex items-center gap-2 flex-wrap">
        <span className="font-mono text-2xs tracking-[0.18em] text-fg-mute uppercase">
          Min risk
        </span>
        {RISK_FILTERS.map((f) => (
          <Link
            key={f.value}
            href={`/narratives?window=${window_days}&min=${f.value}`}
            className={`font-mono text-2xs tracking-wider uppercase px-2.5 py-1.5 rounded-sm border transition-colors ${
              f.value === min_risk_tier
                ? 'border-accent bg-accent/10 text-accent'
                : 'border-border-2 text-fg-dim hover:text-fg hover:border-border-hot'
            }`}
          >
            {f.label}
          </Link>
        ))}
      </div>

      {/* Summary row */}
      {narratives.length > 0 && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          <StatBlock label="Clusters" value={narratives.length} />
          <StatBlock
            label="Extreme"
            value={extreme}
            tone={extreme > 0 ? 'high' : 'mute'}
            icon={<Flame size={12} />}
          />
          <StatBlock
            label="High"
            value={high}
            tone={high > 0 ? 'elevated' : 'mute'}
            icon={<ShieldAlert size={12} />}
          />
          <StatBlock
            label="Avg coordination"
            value={`${avgCoord}%`}
            tone={avgCoord >= 50 ? 'elevated' : avgCoord >= 25 ? 'moderate' : 'mute'}
            icon={<Crosshair size={12} />}
          />
        </div>
      )}

      {/* Empty state */}
      {narratives.length === 0 ? (
        <Card>
          <CardLabel>No qualifying clusters in this window</CardLabel>
          <CardTitle>The observatory is empty</CardTitle>
          <p className="text-sm text-fg-dim max-w-lg">
            With the current filter ({' '}
            <span className="text-accent">{min_risk_tier}+</span> risk over{' '}
            {window_days} days) no clusters meet the coordination threshold.
            Try widening the time window, lowering the risk filter, or running
            more scans — moderate-and-above accounts populate the graph.
          </p>
        </Card>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
          {narratives.map((n, i) => (
            <NarrativeCard key={n.id} narrative={n} rank={i + 1} />
          ))}
        </div>
      )}
    </div>
  );
}

function NarrativeCard({
  narrative: n,
  rank,
}: {
  narrative: NarrativeOut;
  rank: number;
}) {
  const risk = RISK_CONFIG[n.risk_tier];
  const coord_pct = Math.round(n.coordination_score * 100);
  const manip_pct = Math.round(n.manipulation_probability * 100);
  const sync_pct = Math.round(n.synchronization_intensity * 100);

  return (
    <Link href={`/narratives/${n.id}`} className="block group">
      <article className="h-full bg-bg-elev border border-border-1 rounded-md p-5 hover:border-border-hot group-hover:bg-bg-elev-2/30 transition-colors">
        {/* Top row */}
        <div className="flex items-center justify-between mb-3 gap-2">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="font-mono text-2xs text-fg-faint">#{rank}</span>
            <span
              className={`inline-flex items-center gap-1 font-mono text-2xs tracking-wider uppercase px-2 py-0.5 rounded-sm border ${risk.cls}`}
            >
              {risk.icon}
              {risk.label} risk
            </span>
            {n.cluster_confidence >= 3 && (
              <span className="inline-flex items-center gap-1 font-mono text-2xs tracking-wider uppercase px-1.5 py-0.5 rounded-sm border border-accent/40 bg-accent/10 text-accent">
                <Activity size={10} />
                {n.cluster_confidence}-signal
              </span>
            )}
            {n.platforms.slice(0, 2).map((p) => (
              <span
                key={p}
                className="font-mono text-2xs tracking-wider uppercase px-1.5 py-0.5 rounded-sm border border-border-2 text-fg-mute"
              >
                {p}
              </span>
            ))}
          </div>
          <span className="font-mono text-2xs text-fg-mute shrink-0">
            {timeAgo(n.last_seen_at)}
          </span>
        </div>

        <p className="text-sm text-fg leading-relaxed mb-3 line-clamp-2 min-h-[2.5rem]">
          &ldquo;{n.sample_text || '(no sample)'}&rdquo;
        </p>

        {/* Coordination score bar — the headline */}
        <div className="mb-3">
          <div className="flex items-center justify-between font-mono text-2xs mb-1">
            <span className="text-fg-mute uppercase tracking-wider">
              Coordination
            </span>
            <span className="text-fg tabular-nums">{coord_pct}%</span>
          </div>
          <div className="h-1.5 bg-border-1 rounded-full overflow-hidden">
            <div
              className={`h-full rounded-full transition-all ${risk.barCls}`}
              style={{ width: `${Math.min(100, coord_pct)}%` }}
            />
          </div>
        </div>

        {/* Sub-metrics */}
        <div className="grid grid-cols-4 gap-2 mb-3">
          <MiniStat
            label="Manip."
            value={`${manip_pct}%`}
            highlight={manip_pct >= 45}
          />
          <MiniStat
            label="Sync"
            value={`${sync_pct}%`}
            highlight={sync_pct >= 45}
            icon={<Radio size={9} />}
          />
          <MiniStat
            label="Mod+"
            value={n.qualifying_author_count}
            icon={<Users size={9} />}
            highlight={n.qualifying_author_count >= 5}
          />
          <MiniStat label="Members" value={n.recent_members} />
        </div>

        <div className="flex items-center justify-between font-mono text-2xs">
          <span className="text-fg-mute uppercase tracking-wider">
            {prettyLabel(n.coordination_label)}
          </span>
          <ArrowRight
            size={12}
            className="text-fg-faint group-hover:text-accent transition-colors"
          />
        </div>
      </article>
    </Link>
  );
}

function StatBlock({
  label,
  value,
  tone = 'fg',
  icon,
}: {
  label: string;
  value: string | number;
  tone?: 'fg' | 'mute' | 'moderate' | 'elevated' | 'high';
  icon?: React.ReactNode;
}) {
  const toneCls = {
    fg: 'text-fg',
    mute: 'text-fg-dim',
    moderate: 'text-tier-moderate',
    elevated: 'text-tier-elevated',
    high: 'text-tier-high',
  }[tone];
  return (
    <div className="bg-bg-elev border border-border-1 rounded-md p-3">
      <div className="flex items-center gap-1.5 font-mono text-2xs text-fg-mute uppercase tracking-wider mb-1.5">
        {icon}
        {label}
      </div>
      <div className={`font-mono text-xl font-semibold tabular-nums ${toneCls}`}>
        {value}
      </div>
    </div>
  );
}

function MiniStat({
  label,
  value,
  icon,
  highlight,
}: {
  label: string;
  value: string | number;
  icon?: React.ReactNode;
  highlight?: boolean;
}) {
  return (
    <div>
      <div className="flex items-center gap-0.5 font-mono text-2xs text-fg-mute uppercase tracking-wider mb-0.5">
        {icon}
        {label}
      </div>
      <div
        className={`font-mono text-sm font-medium tabular-nums ${
          highlight ? 'text-tier-elevated' : 'text-fg'
        }`}
      >
        {value}
      </div>
    </div>
  );
}

function prettyLabel(label: string): string {
  return (
    {
      organic: 'organic',
      mixed: 'mixed signal',
      suspicious: 'suspicious',
      coordinated: 'coordinated',
      manipulation_network: 'manipulation network',
      unscored: 'unscored',
    }[label] ?? label
  );
}
