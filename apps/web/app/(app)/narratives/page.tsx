import Link from 'next/link';
import {
  Users, ArrowRight, ShieldAlert, Shield, AlertTriangle, Flame,
  Radio, Activity, Crosshair,
} from 'lucide-react';
import { Card, CardTitle } from '@/components/ui/card';
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

const RISK_CONFIG: Record<RiskTier, { label: string; icon: React.ReactNode; cls: string; barCls: string }> = {
  extreme:  { label: 'Extreme',  icon: <Flame size={11} />,        cls: 'text-tier-high border-tier-high/40 bg-tier-high/10',           barCls: 'bg-tier-high' },
  high:     { label: 'High',     icon: <ShieldAlert size={11} />,  cls: 'text-tier-elevated border-tier-elevated/40 bg-tier-elevated/10', barCls: 'bg-tier-elevated' },
  moderate: { label: 'Moderate', icon: <AlertTriangle size={11} />,cls: 'text-tier-moderate border-tier-moderate/40 bg-tier-moderate/10', barCls: 'bg-tier-moderate' },
  low:      { label: 'Low',      icon: <Shield size={11} />,       cls: 'text-tier-low border-tier-low/40 bg-tier-low/10',               barCls: 'bg-tier-low' },
};

function clusterIndex(key: string): number {
  let h = 0;
  for (let i = 0; i < key.length; i++) h = (h * 31 + key.charCodeAt(i)) >>> 0;
  return (h % 8) + 1;
}

const CHIP = 'font-mono text-2xs tracking-wider uppercase px-2.5 py-1.5 rounded-full border transition-colors';
const CHIP_ON = 'border-transparent bg-accent/15 text-accent shadow-[inset_0_0_0_1px_rgba(217,164,74,0.4)]';
const CHIP_OFF = 'border-border-2 text-fg-dim hover:text-fg hover:border-border-hot';

export default async function NarrativesPage({
  searchParams,
}: {
  searchParams: { window?: string; min?: string };
}) {
  const window_days = Math.max(1, Math.min(90, parseInt(searchParams.window || '7', 10) || 7));
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
  const avgCoord = narratives.length === 0 ? 0
    : Math.round((narratives.reduce((s, n) => s + n.coordination_score, 0) / narratives.length) * 100);

  return (
    <div className="space-y-6 animate-fade-up">
      {/* Header */}
      <header className="aurora relative overflow-hidden rounded-2xl border border-border-1 bg-bg-elev px-6 py-6 md:px-7">
        <span className="absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-violet/50 to-transparent" />
        <div className="flex items-end justify-between gap-4 flex-wrap">
          <div className="min-w-0">
            <span className="section-label">Coordination · Narratives</span>
            <h1 className="display text-2xl font-semibold text-fg tracking-tight mt-3">
              How ideas spread
            </h1>
            <p className="mt-1.5 text-sm text-fg-dim max-w-2xl leading-relaxed">
              Semantic clusters of comment text scored across coordination signals.
              Narratives track <span className="text-fg">what is being said</span>;{' '}
              <a href="/campaigns" className="text-accent hover:text-accent-2">Campaigns</a>{' '}
              track <span className="text-fg">who acts together</span>. Only moderate-and-above
              accounts contribute — organic discussion is excluded by default.
            </p>
          </div>
          <div className="flex items-center gap-1.5">
            <span className="font-mono text-2xs tracking-[0.18em] text-fg-mute uppercase mr-1">Window</span>
            {WINDOWS.map((d) => (
              <Link key={d} href={`/narratives?window=${d}&min=${min_risk_tier}`}
                className={`${CHIP} ${d === window_days ? CHIP_ON : CHIP_OFF}`}>
                {d}d
              </Link>
            ))}
          </div>
        </div>
      </header>

      {/* Risk filter chips */}
      <div className="flex items-center gap-2 flex-wrap">
        <span className="font-mono text-2xs tracking-[0.18em] text-fg-mute uppercase">Min risk</span>
        {RISK_FILTERS.map((f) => (
          <Link key={f.value} href={`/narratives?window=${window_days}&min=${f.value}`}
            className={`${CHIP} ${f.value === min_risk_tier ? CHIP_ON : CHIP_OFF}`}>
            {f.label}
          </Link>
        ))}
      </div>

      {/* Summary row */}
      {narratives.length > 0 && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          <StatBlock label="Clusters" value={narratives.length} icon={<Activity size={13} />} />
          <StatBlock label="Extreme" value={extreme} tone={extreme > 0 ? 'high' : 'mute'} icon={<Flame size={13} />} />
          <StatBlock label="High" value={high} tone={high > 0 ? 'elevated' : 'mute'} icon={<ShieldAlert size={13} />} />
          <StatBlock label="Avg coordination" value={`${avgCoord}%`} tone={avgCoord >= 50 ? 'elevated' : avgCoord >= 25 ? 'moderate' : 'mute'} icon={<Crosshair size={13} />} />
        </div>
      )}

      {/* List / empty */}
      {narratives.length === 0 ? (
        <Card className="text-center py-12">
          <div className="w-12 h-12 mx-auto mb-4 rounded-xl border border-border-2 bg-bg-elev-2 flex items-center justify-center text-violet-2">
            <Radio size={20} strokeWidth={1.5} />
          </div>
          <CardTitle className="mb-1.5">No qualifying clusters in this window</CardTitle>
          <p className="text-sm text-fg-dim max-w-lg mx-auto leading-relaxed">
            With <span className="text-accent">{min_risk_tier}+</span> risk over {window_days} days,
            no clusters meet the coordination threshold. Widen the window, lower the risk filter, or
            run more scans — moderate-and-above accounts populate the graph.
          </p>
        </Card>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
          {narratives.map((n, i) => <NarrativeCard key={n.id} narrative={n} rank={i + 1} />)}
        </div>
      )}
    </div>
  );
}

function NarrativeCard({ narrative: n, rank }: { narrative: NarrativeOut; rank: number }) {
  const risk = RISK_CONFIG[n.risk_tier];
  const coord_pct = Math.round(n.coordination_score * 100);
  const manip_pct = Math.round(n.manipulation_probability * 100);
  const sync_pct = Math.round(n.synchronization_intensity * 100);
  const cluster = clusterIndex(String(n.id));

  return (
    <Link href={`/narratives/${n.id}`} className="block group">
      <article className="h-full bg-bg-elev border border-border-1 rounded-xl p-5 card-interactive">
        <div className="flex items-center justify-between mb-3 gap-2">
          <div className="flex items-center gap-2 flex-wrap min-w-0">
            <span className="cluster-dot" style={{ ['--c' as string]: `var(--cluster-${cluster})` }} />
            <span className="font-mono text-2xs text-fg-faint tabular">#{rank}</span>
            <span className={`inline-flex items-center gap-1 font-mono text-2xs tracking-wider uppercase px-2 py-0.5 rounded-full border ${risk.cls}`}>
              {risk.icon}
              {risk.label} risk
            </span>
            {n.cluster_confidence >= 3 && (
              <span className="inline-flex items-center gap-1 font-mono text-2xs tracking-wider uppercase px-1.5 py-0.5 rounded-full border border-accent/40 bg-accent/10 text-accent">
                <Activity size={10} />
                {n.cluster_confidence}-signal
              </span>
            )}
            {n.platforms.slice(0, 2).map((p) => (
              <span key={p} className="font-mono text-2xs tracking-wider uppercase px-1.5 py-0.5 rounded-full border border-border-2 text-fg-mute">
                {p}
              </span>
            ))}
          </div>
          <span className="font-mono text-2xs text-fg-mute shrink-0">{timeAgo(n.last_seen_at)}</span>
        </div>

        <p className="text-sm text-fg leading-relaxed mb-4 line-clamp-2 min-h-[2.5rem]">
          &ldquo;{n.sample_text || '(no sample)'}&rdquo;
        </p>

        {/* Coordination bar — the headline */}
        <div className="mb-4">
          <div className="flex items-center justify-between font-mono text-2xs mb-1.5">
            <span className="text-fg-mute uppercase tracking-wider">Coordination</span>
            <span className="text-fg tabular">{coord_pct}%</span>
          </div>
          <div className="h-1.5 bg-bg-elev-3 rounded-full overflow-hidden">
            <div className={`h-full rounded-full transition-all ${risk.barCls}`} style={{ width: `${Math.min(100, coord_pct)}%` }} />
          </div>
        </div>

        {/* Sub-metrics */}
        <div className="grid grid-cols-4 gap-2 mb-3">
          <MiniStat label="Manip." value={`${manip_pct}%`} highlight={manip_pct >= 45} />
          <MiniStat label="Sync" value={`${sync_pct}%`} highlight={sync_pct >= 45} icon={<Radio size={9} />} />
          <MiniStat label="Mod+" value={n.qualifying_author_count} icon={<Users size={9} />} highlight={n.qualifying_author_count >= 5} />
          <MiniStat label="Members" value={n.recent_members} />
        </div>

        <div className="flex items-center justify-between font-mono text-2xs pt-1">
          <span className="text-fg-mute uppercase tracking-wider">{prettyLabel(n.coordination_label)}</span>
          <ArrowRight size={13} className="text-fg-faint group-hover:text-accent group-hover:translate-x-0.5 transition-all" />
        </div>
      </article>
    </Link>
  );
}

function StatBlock({
  label, value, tone = 'fg', icon,
}: {
  label: string;
  value: string | number;
  tone?: 'fg' | 'mute' | 'moderate' | 'elevated' | 'high';
  icon?: React.ReactNode;
}) {
  const toneCls = {
    fg: 'text-fg', mute: 'text-fg', moderate: 'text-tier-moderate',
    elevated: 'text-tier-elevated', high: 'text-tier-high',
  }[tone];
  return (
    <div className="bg-bg-elev border border-border-1 rounded-xl p-4 card-interactive">
      <div className="flex items-center gap-1.5 font-mono text-2xs text-fg-mute uppercase tracking-wider mb-1.5">
        {icon}
        {label}
      </div>
      <div className={`stat-value text-xl font-semibold ${toneCls}`}>{value}</div>
    </div>
  );
}

function MiniStat({
  label, value, icon, highlight,
}: {
  label: string;
  value: string | number;
  icon?: React.ReactNode;
  highlight?: boolean;
}) {
  return (
    <div className="surface-inset px-2 py-1.5">
      <div className="flex items-center gap-0.5 font-mono text-[0.55rem] text-fg-faint uppercase tracking-wider mb-0.5">
        {icon}
        {label}
      </div>
      <div className={`text-sm font-medium tabular ${highlight ? 'text-tier-elevated' : 'text-fg'}`}>
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
