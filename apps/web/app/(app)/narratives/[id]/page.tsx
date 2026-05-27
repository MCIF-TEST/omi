import Link from 'next/link';
import { notFound } from 'next/navigation';
import {
  ArrowLeft,
  Users,
  MessageSquare,
  Shield,
  ShieldAlert,
  AlertTriangle,
  Flame,
  Cpu,
  BarChart2,
  ExternalLink,
  RefreshCw,
  Crosshair,
  Activity,
  Radio,
  Zap,
  GitBranch,
  Clock,
} from 'lucide-react';
import { Card, CardLabel, CardTitle } from '@/components/ui/card';
import {
  type NarrativeDetail,
  type NarrativeTopAccount,
  type NarrativeSample,
  type NarrativeSignalBreakdown,
  type NarrativePropagationPoint,
  type NarrativeBurst,
  type NarrativeGraphNode,
  type NarrativeGraphEdge,
  type RiskTier,
  ApiError,
} from '@/lib/api';
import { apiServer } from '@/lib/api-server';
import { timeAgo } from '@/lib/format';

export const dynamic = 'force-dynamic';

export async function generateMetadata({ params }: { params: { id: string } }) {
  return { title: `Narrative #${params.id} — OMISPHERE` };
}

const RISK_CONFIG: Record<
  RiskTier,
  {
    label: string;
    icon: React.ReactNode;
    cls: string;
    barCls: string;
    glowCls: string;
    desc: string;
  }
> = {
  extreme: {
    label: 'Extreme',
    icon: <Flame size={12} />,
    cls: 'text-tier-high border-tier-high/40 bg-tier-high/10',
    barCls: 'bg-tier-high',
    glowCls: 'shadow-[0_0_24px_-8px] shadow-tier-high/60',
    desc: 'Manipulation-network signature: highly coordinated ecosystem with mass synchronization, artificial amplification structure, or bot-farm behaviour.',
  },
  high: {
    label: 'High',
    icon: <ShieldAlert size={12} />,
    cls: 'text-tier-elevated border-tier-elevated/40 bg-tier-elevated/10',
    barCls: 'bg-tier-elevated',
    glowCls: '',
    desc: 'Strong coordination indicators across multiple independent signals — repeated synchronized messaging or abnormal propagation behaviour.',
  },
  moderate: {
    label: 'Moderate',
    icon: <AlertTriangle size={12} />,
    cls: 'text-tier-moderate border-tier-moderate/40 bg-tier-moderate/10',
    barCls: 'bg-tier-moderate',
    glowCls: '',
    desc: 'Repeated suspicious synchronization. Moderate semantic similarity with timing overlap.',
  },
  low: {
    label: 'Low',
    icon: <Shield size={12} />,
    cls: 'text-tier-low border-tier-low/40 bg-tier-low/10',
    barCls: 'bg-tier-low',
    glowCls: '',
    desc: 'Weak signals only — patterns broadly consistent with organic discussion.',
  },
};

const SIGNAL_LABELS: Record<string, { label: string; desc: string }> = {
  inauthenticity: {
    label: 'Inauthenticity',
    desc: 'Fraction of scanned authors at moderate+ tier',
  },
  temporal_burst: {
    label: 'Temporal burst',
    desc: 'Peak-to-mean ratio of hourly comments',
  },
  timing_entropy: {
    label: 'Timing entropy',
    desc: 'How narrow the posting window is',
  },
  repost_overlap: {
    label: 'Repost overlap',
    desc: 'Comments duplicating text across authors',
  },
  cross_parent_spread: {
    label: 'Cross-target spread',
    desc: 'Authors active on multiple parent videos/threads',
  },
  author_concentration: {
    label: 'Author concentration',
    desc: 'Activity concentrated in top 3 accounts',
  },
  persistence: {
    label: 'Persistence',
    desc: 'How long the cluster has remained active',
  },
  semantic_cohesion: {
    label: 'Semantic cohesion',
    desc: 'Comments-per-author tightness',
  },
};

export default async function NarrativeDetailPage({
  params,
}: {
  params: { id: string };
}) {
  let detail: NarrativeDetail | null = null;
  let fetchError: string | null = null;

  try {
    detail = await apiServer<NarrativeDetail>(`/v1/narratives/${params.id}`);
  } catch (err) {
    if (err instanceof ApiError && err.status === 404) {
      notFound();
    }
    fetchError =
      err instanceof ApiError
        ? `API error ${err.status}: ${err.message}`
        : 'Could not load narrative data.';
  }

  if (fetchError || !detail) {
    return (
      <div className="space-y-4">
        <Link
          href="/narratives"
          className="inline-flex items-center gap-1.5 font-mono text-2xs tracking-wider text-fg-dim hover:text-fg uppercase transition-colors"
        >
          <ArrowLeft size={11} />
          Narratives
        </Link>
        <Card>
          <CardLabel className="flex items-center gap-1.5 text-tier-elevated">
            <RefreshCw size={10} />
            Could not load narrative
          </CardLabel>
          <CardTitle>Something went wrong</CardTitle>
          <p className="text-sm text-fg-dim mb-4">
            {fetchError ?? 'The narrative could not be retrieved.'}
          </p>
          <Link
            href="/narratives"
            className="inline-flex items-center gap-1.5 font-mono text-2xs tracking-wider uppercase px-3 py-1.5 rounded-sm border border-border-2 text-fg-dim hover:text-fg hover:border-border-hot transition-colors"
          >
            <ArrowLeft size={11} />
            Back to narratives
          </Link>
        </Card>
      </div>
    );
  }

  const risk = RISK_CONFIG[detail.risk_tier] ?? RISK_CONFIG.low;
  const coord_pct = Math.round(detail.coordination_score * 100);
  const manip_pct = Math.round(detail.manipulation_probability * 100);
  const sync_pct = Math.round(detail.synchronization_intensity * 100);
  const cohesion_pct = Math.round(detail.semantic_cohesion * 100);
  const inauth_pct = Math.round(detail.inauthenticity_score * 100);
  const spread_pct = Math.round(detail.spread_ratio * 100);

  const platformEntries = Object.entries(detail.platform_breakdown).sort(
    ([, a], [, b]) => b - a,
  );
  const platformTotal = Math.max(
    1,
    platformEntries.reduce((s, [, v]) => s + v, 0),
  );

  return (
    <div className="space-y-5">
      {/* Back nav */}
      <Link
        href="/narratives"
        className="inline-flex items-center gap-1.5 font-mono text-2xs tracking-wider text-fg-dim hover:text-fg uppercase transition-colors"
      >
        <ArrowLeft size={11} />
        Narratives
      </Link>

      {/* Header */}
      <header className="space-y-3">
        <div className="flex items-center gap-2 flex-wrap">
          <span
            className={`inline-flex items-center gap-1.5 font-mono text-2xs tracking-wider uppercase px-2.5 py-1 rounded-sm border ${risk.cls}`}
          >
            {risk.icon}
            {risk.label} risk
          </span>
          <span className="inline-flex items-center gap-1.5 font-mono text-2xs tracking-wider uppercase px-2 py-0.5 rounded-sm border border-border-2 text-fg-dim">
            {prettyLabel(detail.coordination_label)}
          </span>
          {detail.cluster_confidence >= 3 && (
            <span className="inline-flex items-center gap-1 font-mono text-2xs tracking-wider uppercase px-2 py-0.5 rounded-sm border border-accent/40 bg-accent/10 text-accent">
              <Activity size={10} />
              {detail.cluster_confidence}-signal cluster
            </span>
          )}
          {detail.platforms.map((p) => (
            <span
              key={p}
              className="font-mono text-2xs tracking-wider uppercase px-2 py-0.5 rounded-sm border border-border-2 text-fg-mute"
            >
              {p}
            </span>
          ))}
          <span className="font-mono text-2xs text-fg-faint ml-auto shrink-0">
            Last seen {timeAgo(detail.last_seen_at)}
          </span>
        </div>

        <h1 className="text-xl font-semibold text-fg tracking-tight leading-snug max-w-3xl">
          {detail.label || `Narrative #${detail.id}`}
        </h1>

        <p className="text-sm text-fg-dim max-w-3xl">{risk.desc}</p>
      </header>

      {/* Headline coordination panel */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <BigStat
          label="Coordination"
          value={`${coord_pct}%`}
          icon={<Crosshair size={14} />}
          barPct={coord_pct}
          barCls={risk.barCls}
          tone={detail.risk_tier}
        />
        <BigStat
          label="Manipulation prob."
          value={`${manip_pct}%`}
          icon={<Zap size={14} />}
          barPct={manip_pct}
          barCls={risk.barCls}
          tone={manip_pct >= 60 ? 'extreme' : manip_pct >= 35 ? 'high' : 'moderate'}
        />
        <BigStat
          label="Synchronization"
          value={`${sync_pct}%`}
          icon={<Radio size={14} />}
          barPct={sync_pct}
          barCls={risk.barCls}
          tone={sync_pct >= 60 ? 'extreme' : sync_pct >= 35 ? 'high' : 'moderate'}
        />
        <BigStat
          label="Semantic cohesion"
          value={`${cohesion_pct}%`}
          icon={<GitBranch size={14} />}
          barPct={cohesion_pct}
          barCls={risk.barCls}
          tone="moderate"
        />
      </div>

      {/* Counts row */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <SmallStat
          label="Mod+ authors"
          value={detail.qualifying_author_count.toLocaleString()}
          icon={<Users size={12} />}
          sub="in cluster"
        />
        <SmallStat
          label="Mod+ comments"
          value={detail.qualifying_member_count.toLocaleString()}
          icon={<MessageSquare size={12} />}
        />
        <SmallStat
          label="Total comments"
          value={detail.member_count.toLocaleString()}
          icon={<MessageSquare size={12} />}
        />
        <SmallStat
          label="Inauthentic"
          value={`${inauth_pct}%`}
          icon={<ShieldAlert size={12} />}
          highlight={inauth_pct >= 35}
          sub="of scanned"
        />
      </div>

      {/* AI Analysis */}
      {detail.ai_analysis && (
        <Card>
          <CardLabel className="flex items-center gap-1.5">
            <Cpu size={10} />
            AI narrative assessment
            {detail.ai_provider && detail.ai_provider !== 'template' && (
              <span className="ml-auto text-fg-faint normal-case tracking-normal">
                {detail.ai_provider}
              </span>
            )}
          </CardLabel>
          <p className="text-sm text-fg leading-relaxed">{detail.ai_analysis}</p>
        </Card>
      )}

      {/* Signal breakdown + Origin window */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-3">
        <Card className="lg:col-span-2 p-5">
          <CardLabel className="flex items-center gap-1.5 mb-4">
            <Activity size={10} />
            Multi-signal coordination breakdown
          </CardLabel>
          {detail.signal_breakdown.length === 0 ? (
            <p className="text-sm text-fg-dim">No signals available.</p>
          ) : (
            <div className="space-y-2.5">
              {detail.signal_breakdown.map((s) => (
                <SignalRow key={s.name} signal={s} riskCls={risk.barCls} />
              ))}
            </div>
          )}
        </Card>

        {/* Origin + platforms */}
        <div className="space-y-3">
          {detail.origin && (
            <Card className="p-5">
              <CardLabel className="flex items-center gap-1.5 mb-3">
                <Clock size={10} />
                Origin window
              </CardLabel>
              <OriginPanel origin={detail.origin} />
            </Card>
          )}
          <Card className="p-5">
            <CardLabel className="mb-3">Platforms</CardLabel>
            {platformEntries.length === 0 ? (
              <p className="text-sm text-fg-dim">No data.</p>
            ) : (
              <div className="space-y-2.5">
                {platformEntries.map(([platform, count]) => {
                  const pct = Math.round((count / platformTotal) * 100);
                  return (
                    <div key={platform}>
                      <div className="flex items-center justify-between mb-1">
                        <span className="font-mono text-2xs text-fg-mute uppercase tracking-wider">
                          {platform}
                        </span>
                        <span className="font-mono text-2xs text-fg tabular-nums">
                          {count.toLocaleString()} · {pct}%
                        </span>
                      </div>
                      <div className="h-1 bg-border-1 rounded-full overflow-hidden">
                        <div
                          className={`h-full rounded-full ${risk.barCls} opacity-50`}
                          style={{ width: `${pct}%` }}
                        />
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </Card>
        </div>
      </div>

      {/* Propagation chart */}
      {detail.propagation.length > 0 && (
        <Card className="p-5">
          <CardLabel className="flex items-center gap-1.5 mb-1">
            <BarChart2 size={10} />
            Propagation timeline
          </CardLabel>
          <p className="font-mono text-2xs text-fg-faint mb-4">
            Comments per hour. Red overlay = moderate+ accounts. Burst markers
            flag spikes &gt; 2.5× rolling baseline.
          </p>
          <PropagationChart
            data={detail.propagation}
            bursts={detail.bursts}
            riskCls={risk.barCls}
          />
        </Card>
      )}

      {/* Coordination subgraph */}
      {detail.graph.nodes.length > 0 && (
        <Card className="p-5">
          <CardLabel className="flex items-center gap-1.5 mb-1">
            <GitBranch size={10} />
            Coordination subgraph
          </CardLabel>
          <p className="font-mono text-2xs text-fg-faint mb-4">
            Moderate+ accounts in this cluster, weighted by cross-cluster
            coordination edges from the global graph.
          </p>
          <CoordinationGraph
            nodes={detail.graph.nodes}
            edges={detail.graph.edges}
          />
        </Card>
      )}

      {/* Top accounts (moderate+) */}
      {detail.top_accounts.length > 0 && (
        <Card className="p-0 overflow-hidden">
          <div className="px-5 pt-5 pb-3 border-b border-border-1">
            <CardLabel className="flex items-center gap-1.5 mb-0">
              <Users size={10} />
              Top moderate+ accounts in this cluster
            </CardLabel>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-bg">
                  <th className="text-left font-mono text-2xs tracking-wider text-fg-mute uppercase px-5 py-2.5">
                    Account
                  </th>
                  <th className="text-left font-mono text-2xs tracking-wider text-fg-mute uppercase px-3 py-2.5">
                    Risk
                  </th>
                  <th className="text-right font-mono text-2xs tracking-wider text-fg-mute uppercase px-3 py-2.5">
                    Comments
                  </th>
                  <th className="text-right font-mono text-2xs tracking-wider text-fg-mute uppercase px-3 py-2.5">
                    Targets
                  </th>
                  <th className="text-left font-mono text-2xs tracking-wider text-fg-mute uppercase px-3 py-2.5 pr-5">
                    Influence
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border-1">
                {detail.top_accounts.map((a) => (
                  <TopAccountRow
                    key={`${a.platform}:${a.external_id}`}
                    account={a}
                  />
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}

      {/* Sample comments */}
      {detail.samples.length > 0 && (
        <div className="space-y-2">
          <div className="font-mono text-2xs tracking-[0.18em] text-fg-mute uppercase flex items-center gap-2">
            <MessageSquare size={10} />
            Sample comments
            <span className="text-fg-faint normal-case tracking-normal">
              {detail.qualifying_member_count > 0
                ? '(from moderate+ accounts)'
                : '(no suspicious authors — showing organic sample)'}
            </span>
          </div>
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-2">
            {detail.samples.map((s, i) => (
              <SampleComment key={i} sample={s} />
            ))}
          </div>
        </div>
      )}

      {/* Footer metadata */}
      <Card className="p-5">
        <CardLabel className="mb-3">Cluster metadata</CardLabel>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 font-mono text-2xs">
          <MetaItem label="First seen" value={formatDate(detail.first_seen_at)} />
          <MetaItem label="Last seen" value={formatDate(detail.last_seen_at)} />
          <MetaItem label="Spread ratio" value={`${spread_pct}%`} />
          <MetaItem label="Cluster ID" value={`#${detail.id}`} />
        </div>
      </Card>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function BigStat({
  label,
  value,
  icon,
  barPct,
  barCls,
  tone,
}: {
  label: string;
  value: string;
  icon?: React.ReactNode;
  barPct: number;
  barCls: string;
  tone: 'low' | 'moderate' | 'high' | 'extreme';
}) {
  const toneTextCls = {
    low: 'text-fg',
    moderate: 'text-tier-moderate',
    high: 'text-tier-elevated',
    extreme: 'text-tier-high',
  }[tone];
  return (
    <div className="bg-bg-elev border border-border-1 rounded-md p-4">
      <div className="flex items-center gap-1.5 font-mono text-2xs text-fg-mute uppercase tracking-wider mb-2">
        {icon}
        {label}
      </div>
      <div
        className={`font-mono text-2xl font-semibold tabular-nums leading-none mb-3 ${toneTextCls}`}
      >
        {value}
      </div>
      <div className="h-1 bg-border-1 rounded-full overflow-hidden">
        <div
          className={`h-full rounded-full ${barCls} transition-all`}
          style={{ width: `${Math.min(100, barPct)}%` }}
        />
      </div>
    </div>
  );
}

function SmallStat({
  label,
  value,
  icon,
  sub,
  highlight,
}: {
  label: string;
  value: string | number;
  icon?: React.ReactNode;
  sub?: string;
  highlight?: boolean;
}) {
  return (
    <div className="bg-bg-elev border border-border-1 rounded-md p-3">
      <div className="flex items-center gap-1.5 font-mono text-2xs text-fg-mute uppercase tracking-wider mb-1.5">
        {icon}
        {label}
      </div>
      <div
        className={`font-mono text-base font-semibold tabular-nums ${
          highlight ? 'text-tier-elevated' : 'text-fg'
        }`}
      >
        {value}
      </div>
      {sub && (
        <div className="font-mono text-2xs text-fg-faint mt-0.5">{sub}</div>
      )}
    </div>
  );
}

function SignalRow({
  signal,
  riskCls,
}: {
  signal: NarrativeSignalBreakdown;
  riskCls: string;
}) {
  const meta = SIGNAL_LABELS[signal.name] ?? {
    label: signal.name,
    desc: '',
  };
  const value_pct = Math.round(signal.value * 100);
  const weight_pct = Math.round(signal.weight * 100);
  const firing = signal.value >= 0.4;
  return (
    <div>
      <div className="flex items-center justify-between gap-2 mb-1">
        <div className="flex items-center gap-2 min-w-0">
          <span
            className={`text-sm font-medium ${firing ? 'text-fg' : 'text-fg-dim'}`}
          >
            {meta.label}
          </span>
          <span className="font-mono text-2xs text-fg-faint">
            ×{weight_pct}%
          </span>
        </div>
        <span
          className={`font-mono text-sm tabular-nums ${firing ? 'text-fg' : 'text-fg-dim'}`}
        >
          {value_pct}%
        </span>
      </div>
      <div className="h-1 bg-border-1 rounded-full overflow-hidden">
        <div
          className={`h-full rounded-full transition-all ${firing ? riskCls : 'bg-border-2'}`}
          style={{ width: `${value_pct}%` }}
        />
      </div>
      {meta.desc && (
        <p className="font-mono text-2xs text-fg-faint mt-1">{meta.desc}</p>
      )}
    </div>
  );
}

function OriginPanel({ origin }: { origin: NonNullable<NarrativeDetail['origin']> }) {
  if (origin.suspicious_first_seen === null) {
    return (
      <div className="space-y-2 font-mono text-2xs">
        <MetaItem label="Narrative emerged" value={formatDateTime(origin.first_seen)} />
        <div className="text-fg-dim mt-2">
          No suspicious amplification detected yet — this cluster is organic so
          far.
        </div>
      </div>
    );
  }
  const lag = origin.lag_hours ?? 0;
  const lagDesc =
    lag < 1
      ? 'amplification began immediately'
      : lag < 24
      ? `${lag.toFixed(1)}h lag — fast amplification onset`
      : `${Math.round(lag / 24)}d lag — narrative seeded then amplified`;
  return (
    <div className="space-y-2 font-mono text-2xs">
      <MetaItem
        label="Narrative emerged"
        value={formatDateTime(origin.first_seen)}
      />
      <MetaItem
        label="Suspicious amplification"
        value={formatDateTime(origin.suspicious_first_seen)}
      />
      <div
        className={`mt-2 text-fg-dim ${lag >= 24 ? 'text-tier-elevated' : ''}`}
      >
        {lagDesc}
      </div>
    </div>
  );
}

function PropagationChart({
  data,
  bursts,
  riskCls,
}: {
  data: NarrativePropagationPoint[];
  bursts: NarrativeBurst[];
  riskCls: string;
}) {
  const max = Math.max(1, ...data.map((p) => p.count));
  const burstSet = new Set(bursts.map((b) => b.bucket_start));
  return (
    <div className="space-y-3">
      <div className="flex items-end gap-px h-28 w-full">
        {data.map((p) => {
          const heightPct = Math.max(2, Math.round((p.count / max) * 100));
          const suspiciousPct =
            p.count === 0 ? 0 : Math.round((p.suspicious_count / p.count) * 100);
          const isBurst = burstSet.has(p.bucket_start);
          return (
            <div
              key={p.bucket_start}
              className="flex-1 group relative min-w-0"
              title={`${p.bucket_start}: ${p.count} comments (${p.suspicious_count} suspicious)`}
            >
              {isBurst && (
                <div className="absolute -top-1 left-1/2 -translate-x-1/2 w-1.5 h-1.5 rounded-full bg-tier-high shadow-[0_0_8px] shadow-tier-high" />
              )}
              <div className="relative w-full" style={{ height: `${heightPct}%` }}>
                {/* Organic base */}
                <div className="absolute inset-0 bg-border-2 group-hover:bg-border-hot rounded-t-sm transition-colors" />
                {/* Suspicious overlay */}
                {suspiciousPct > 0 && (
                  <div
                    className={`absolute bottom-0 left-0 right-0 rounded-t-sm ${riskCls} opacity-80`}
                    style={{ height: `${suspiciousPct}%` }}
                  />
                )}
              </div>
              <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-1 hidden group-hover:flex pointer-events-none z-10">
                <div className="bg-bg-elev border border-border-2 rounded px-2 py-1 font-mono text-2xs text-fg whitespace-nowrap shadow-md">
                  {formatBucket(p.bucket_start)} · {p.count} ({p.suspicious_count} susp)
                </div>
              </div>
            </div>
          );
        })}
      </div>
      <div className="flex items-center justify-between font-mono text-2xs text-fg-mute">
        <span>{formatBucket(data[0]?.bucket_start)}</span>
        <div className="flex items-center gap-3">
          <span className="inline-flex items-center gap-1">
            <span className="w-2 h-2 rounded-sm bg-border-2 inline-block" />
            all comments
          </span>
          <span className="inline-flex items-center gap-1">
            <span className={`w-2 h-2 rounded-sm inline-block ${riskCls}`} />
            moderate+
          </span>
          {bursts.length > 0 && (
            <span className="inline-flex items-center gap-1">
              <span className="w-1.5 h-1.5 rounded-full bg-tier-high inline-block" />
              {bursts.length} burst{bursts.length === 1 ? '' : 's'}
            </span>
          )}
        </div>
        <span>{formatBucket(data[data.length - 1]?.bucket_start)}</span>
      </div>
    </div>
  );
}

function CoordinationGraph({
  nodes,
  edges,
}: {
  nodes: NarrativeGraphNode[];
  edges: NarrativeGraphEdge[];
}) {
  const W = 640;
  const H = 360;
  const cx = W / 2;
  const cy = H / 2;
  const R = Math.min(W, H) / 2 - 30;

  // Radial layout: most influential nodes near the centre.
  const sorted = [...nodes].sort((a, b) => b.influence_score - a.influence_score);
  const positions = new Map<string, { x: number; y: number; r: number }>();
  sorted.forEach((n, i) => {
    const angle = (i / Math.max(1, sorted.length)) * Math.PI * 2;
    // Inner ring for top-3, outer ring for rest.
    const ring = i < 3 ? R * 0.35 : i < 8 ? R * 0.65 : R * 0.92;
    const radius = 6 + n.influence_score * 14;
    positions.set(n.external_id, {
      x: cx + Math.cos(angle) * ring,
      y: cy + Math.sin(angle) * ring,
      r: radius,
    });
  });

  const nodeColor = (n: NarrativeGraphNode): string => {
    switch (n.display_tier) {
      case 'extreme':
        return 'fill-tier-high stroke-tier-high';
      case 'high':
        return 'fill-tier-elevated stroke-tier-elevated';
      case 'moderate':
        return 'fill-tier-moderate stroke-tier-moderate';
      default:
        return 'fill-fg-mute stroke-fg-mute';
    }
  };

  return (
    <div className="w-full overflow-x-auto">
      <svg
        viewBox={`0 0 ${W} ${H}`}
        className="w-full h-auto max-h-[400px] bg-bg rounded-md border border-border-1"
      >
        {/* Edges */}
        {edges.map((e, i) => {
          const a = positions.get(e.a);
          const b = positions.get(e.b);
          if (!a || !b) return null;
          return (
            <line
              key={i}
              x1={a.x}
              y1={a.y}
              x2={b.x}
              y2={b.y}
              className="stroke-accent"
              strokeOpacity={0.15 + e.strength * 0.7}
              strokeWidth={1 + e.strength * 2.5}
            />
          );
        })}
        {/* Nodes */}
        {sorted.map((n) => {
          const pos = positions.get(n.external_id);
          if (!pos) return null;
          return (
            <g key={n.external_id} className="group">
              <circle
                cx={pos.x}
                cy={pos.y}
                r={pos.r}
                className={`${nodeColor(n)} opacity-80 hover:opacity-100 transition-opacity`}
                strokeWidth={1.5}
                fillOpacity={0.4}
              />
              <text
                x={pos.x}
                y={pos.y + pos.r + 11}
                textAnchor="middle"
                className="fill-fg-dim text-[9px] font-mono"
              >
                @{n.handle.length > 14 ? n.handle.slice(0, 13) + '…' : n.handle}
              </text>
            </g>
          );
        })}
      </svg>
      {edges.length === 0 && (
        <p className="font-mono text-2xs text-fg-faint mt-2 text-center">
          No persistent coordination edges yet — these accounts haven&apos;t been
          observed coordinating across multiple scans.
        </p>
      )}
    </div>
  );
}

function TopAccountRow({ account: a }: { account: NarrativeTopAccount }) {
  const tier = (a.display_tier ?? 'unscored') as RiskTier | 'unscored';
  const tierCls =
    {
      extreme: 'text-tier-high border-tier-high/40 bg-tier-high/10',
      high: 'text-tier-elevated border-tier-elevated/40 bg-tier-elevated/10',
      moderate: 'text-tier-moderate border-tier-moderate/40 bg-tier-moderate/10',
      low: 'text-tier-low border-tier-low/40 bg-tier-low/10',
      unscored: 'text-fg-mute border-border-2',
    }[tier] ?? 'text-fg-mute border-border-2';
  const inf_pct = Math.round(a.influence_score * 100);
  return (
    <tr className="hover:bg-bg-elev-2/20 transition-colors">
      <td className="px-5 py-3">
        <Link
          href={`/accounts/${encodeURIComponent(a.external_id)}?platform=${a.platform}&handle=${encodeURIComponent(a.handle)}`}
          className="group inline-flex items-center gap-2 hover:text-accent transition-colors"
        >
          <div>
            <span className="text-sm text-fg group-hover:text-accent font-medium">
              @{a.handle}
            </span>
            {a.display_name && a.display_name !== a.handle && (
              <span className="text-xs text-fg-dim ml-1.5">{a.display_name}</span>
            )}
            <div className="font-mono text-2xs text-fg-faint">{a.platform}</div>
          </div>
          <ExternalLink
            size={11}
            className="text-fg-faint group-hover:text-accent shrink-0"
          />
        </Link>
      </td>
      <td className="px-3 py-3">
        <span
          className={`inline-flex items-center font-mono text-2xs tracking-wider uppercase px-2 py-0.5 rounded-sm border ${tierCls}`}
        >
          {tier}
        </span>
      </td>
      <td className="px-3 py-3 text-right font-mono text-sm tabular-nums text-fg">
        {a.comment_count.toLocaleString()}
      </td>
      <td className="px-3 py-3 text-right font-mono text-sm tabular-nums text-fg">
        {a.distinct_parents}
      </td>
      <td className="px-3 py-3 pr-5">
        <div className="flex items-center gap-2">
          <div className="w-24 h-1 bg-border-1 rounded-full overflow-hidden">
            <div
              className="h-full rounded-full bg-accent"
              style={{ width: `${inf_pct}%` }}
            />
          </div>
          <span className="font-mono text-2xs tabular-nums text-fg-dim w-8 text-right">
            {inf_pct}%
          </span>
        </div>
      </td>
    </tr>
  );
}

function SampleComment({ sample: s }: { sample: NarrativeSample }) {
  return (
    <div className="bg-bg-elev border border-border-1 rounded-md p-4 flex flex-col gap-2">
      <div className="flex items-center justify-between gap-4">
        <div className="flex items-center gap-2 min-w-0">
          <span className="font-mono text-2xs tracking-wider uppercase text-fg-mute shrink-0">
            {s.platform}
          </span>
          {s.handle && (
            <Link
              href={`/accounts/${encodeURIComponent(s.account_external_id)}?platform=${s.platform}&handle=${encodeURIComponent(s.handle)}`}
              className="font-mono text-2xs text-fg-dim hover:text-accent transition-colors truncate"
            >
              @{s.handle}
            </Link>
          )}
        </div>
        <span className="font-mono text-2xs text-fg-faint shrink-0">
          {timeAgo(s.observed_at)}
        </span>
      </div>
      <p className="text-sm text-fg leading-relaxed line-clamp-3">{s.text}</p>
    </div>
  );
}

function MetaItem({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-fg-mute uppercase tracking-wider mb-0.5">{label}</div>
      <div className="text-fg">{value}</div>
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

function formatDate(iso: string | null | undefined): string {
  if (!iso) return '—';
  try {
    return new Date(iso).toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric',
      year: 'numeric',
    });
  } catch {
    return iso;
  }
}

function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return '—';
  try {
    return new Date(iso).toLocaleString('en-US', {
      month: 'short',
      day: 'numeric',
      hour: 'numeric',
      minute: 'numeric',
    });
  } catch {
    return iso;
  }
}

function formatBucket(iso: string | null | undefined): string {
  if (!iso) return '';
  try {
    return new Date(iso).toLocaleString('en-US', {
      month: 'short',
      day: 'numeric',
      hour: 'numeric',
    });
  } catch {
    return iso;
  }
}
