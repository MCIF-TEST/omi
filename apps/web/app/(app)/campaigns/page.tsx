import Link from 'next/link';
import {
  Megaphone, Network, Sparkles, AlertTriangle, ShieldCheck, Clock,
} from 'lucide-react';
import { Card, CardLabel, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import {
  type CampaignsResponse,
  type CampaignSummary,
  type CampaignSort,
  isCorroborated,
} from '@/lib/api';
import { apiServer } from '@/lib/api-server';
import { timeAgo } from '@/lib/format';

export const metadata = { title: 'Narratives. OMISPHERE' };
export const dynamic = 'force-dynamic';

const SORTS: { value: CampaignSort; label: string }[] = [
  { value: 'recent',     label: 'Most recent' },
  { value: 'score',      label: 'Highest score' },
  { value: 'size',       label: 'Largest' },
  { value: 'recurrence', label: 'Most recurring' },
];

const MIN_SCORE_FILTERS = [
  { value: 0.0,  label: 'All observations' },
  { value: 0.5,  label: 'Score ≥ 0.50 (gated)' },
  { value: 0.75, label: 'Score ≥ 0.75' },
] as const;

interface PageProps {
  searchParams?: {
    sort?: string;
    min_score?: string;
    platform?: string;
    recurring?: string;
  };
}

function parseSort(s: string | undefined): CampaignSort {
  return (SORTS.find((o) => o.value === s)?.value) ?? 'recent';
}

function parseMinScore(s: string | undefined): number {
  const n = Number(s);
  if (!Number.isFinite(n) || n < 0 || n > 1) return 0.5;
  return n;
}

// Persistent per-campaign hue. Navigate coordination by colour, not just label.
function clusterIndex(key: string): number {
  let h = 0;
  for (let i = 0; i < key.length; i++) h = (h * 31 + key.charCodeAt(i)) >>> 0;
  return (h % 8) + 1;
}

const SELECT_CLS =
  'h-9 rounded-md bg-bg-elev-2 border border-border-2 text-sm px-2.5 text-fg ' +
  'focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent/25 transition-colors';

export default async function CampaignsPage({ searchParams }: PageProps) {
  const sort = parseSort(searchParams?.sort);
  const min_score = parseMinScore(searchParams?.min_score);
  const platform = (searchParams?.platform || '').trim() || null;
  const recurring_only = searchParams?.recurring === '1';

  const qs = new URLSearchParams({ sort, min_score: String(min_score), limit: '60' });
  if (platform) qs.set('platform', platform);
  if (recurring_only) qs.set('recurring_only', 'true');

  let data: CampaignsResponse;
  try {
    data = await apiServer<CampaignsResponse>(`/v1/campaigns?${qs.toString()}`);
  } catch {
    data = { campaigns: [], total: 0 };
  }

  const total = data.total;
  const items = data.campaigns;
  const recurring = items.filter((c) => c.status === 'recurring').length;
  const uncorroborated = items.filter((c) => !isCorroborated(c.methods)).length;

  return (
    <div className="space-y-6 animate-fade-up">
      {/* Header */}
      <header className="aurora relative overflow-hidden rounded-2xl border border-border-1 bg-bg-elev px-6 py-6 md:px-7">
        <span className="absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-accent/50 to-transparent" />
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div className="min-w-0">
            <span className="section-label">Coordination · Narratives</span>
            <h1 className="display text-2xl font-semibold tracking-tight mt-3">
              Coordinated account groups
            </h1>
            <p className="text-sm text-fg-dim mt-1.5 max-w-2xl leading-relaxed">
              Durable clusters of accounts acting together across scans.
              <span className="text-fg-dim"> Observations, not verdicts.</span> Every
              score carries its evidence; uncorroborated clusters are capped at MODERATE.
            </p>
          </div>
          <span className="shrink-0 font-mono text-2xs text-fg-mute uppercase tracking-wider px-2.5 py-1 border border-border-2 rounded-full tabular">
            {total} total
          </span>
        </div>
      </header>

      {/* Filters */}
      <Card>
        <form className="flex flex-wrap items-end gap-4" action="" method="get">
          <FilterField label="Sort">
            <select name="sort" defaultValue={sort} className={SELECT_CLS}>
              {SORTS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
            </select>
          </FilterField>
          <FilterField label="Min score">
            <select name="min_score" defaultValue={String(min_score)} className={SELECT_CLS}>
              {MIN_SCORE_FILTERS.map((o) => (
                <option key={o.value} value={String(o.value)}>{o.label}</option>
              ))}
            </select>
          </FilterField>
          <FilterField label="Platform">
            <input
              type="text"
              name="platform"
              defaultValue={platform ?? ''}
              placeholder="any"
              className={`${SELECT_CLS} w-28 placeholder:text-fg-faint`}
            />
          </FilterField>
          <label className="flex items-center gap-2 h-9 text-sm text-fg-dim cursor-pointer">
            <input type="checkbox" name="recurring" value="1" defaultChecked={recurring_only} className="accent-accent" />
            Recurring only
          </label>
          <Button type="submit" size="sm" className="h-9">Apply filters</Button>
        </form>
      </Card>

      {/* Summary row */}
      {items.length > 0 && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          <StatBlock label="Shown" value={items.length} icon={<Megaphone size={13} />} />
          <StatBlock label="Recurring" value={recurring} tone={recurring > 0 ? 'elevated' : 'mute'} icon={<Clock size={13} />} />
          <StatBlock label="Uncorroborated" value={uncorroborated} tone={uncorroborated > 0 ? 'moderate' : 'mute'} icon={<AlertTriangle size={13} />} />
          <StatBlock label="Discriminative" value={items.length - uncorroborated} tone="ok" icon={<ShieldCheck size={13} />} />
        </div>
      )}

      {/* List / empty */}
      {items.length === 0 ? (
        <Card className="text-center py-12">
          <div className="w-12 h-12 mx-auto mb-4 rounded-xl border border-border-2 bg-bg-elev-2 flex items-center justify-center text-accent">
            <Megaphone size={20} strokeWidth={1.5} />
          </div>
          <CardTitle className="mb-1.5">No narratives at this filter</CardTitle>
          <p className="text-sm text-fg-dim max-w-lg mx-auto leading-relaxed">
            Campaigns are captured during scans when a corroboration-gated coordination
            cluster of ≥3 accounts is detected (score ≥ 0.50). Widen the filter, or run
            more scans on platforms where coordination is observed.
          </p>
        </Card>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
          {items.map((c, i) => <CampaignCard key={c.campaign_key} campaign={c} rank={i + 1} />)}
        </div>
      )}
    </div>
  );
}

function CampaignCard({ campaign: c, rank }: { campaign: CampaignSummary; rank: number }) {
  const score_pct = Math.round(c.max_coordination_score * 100);
  const corroborated = isCorroborated(c.methods);
  const evidenceText = c.hashtags[0] ?? c.mentions[0] ?? c.methods.slice(0, 2).join('+');
  const cluster = clusterIndex(c.campaign_key);

  return (
    <Link href={`/campaigns/${c.campaign_key}`} className="block group">
      <article className="h-full bg-bg-elev border border-border-1 rounded-xl p-5 card-interactive">
        {/* Top row */}
        <div className="flex items-center justify-between mb-3 gap-2">
          <div className="flex items-center gap-2 flex-wrap min-w-0">
            <span className="cluster-dot" style={{ ['--c' as string]: `var(--cluster-${cluster})` }} />
            <span className="font-mono text-2xs text-fg-faint tabular">#{rank}</span>
            {c.campaign_key.startsWith('feat_') && (
              <span
                title="A real, disclosed influence operation seeded as a worked example, not one of your scans."
                className="inline-flex items-center font-mono text-2xs tracking-wider uppercase px-1.5 py-0.5 rounded-full border border-accent/40 bg-accent/10 text-accent"
              >
                example
              </span>
            )}
            <StatusPill status={c.status} />
            {!corroborated && (
              <span
                title="Only one supporting detector fired. Capped at MODERATE under the corroboration gate"
                className="inline-flex items-center gap-1 font-mono text-2xs tracking-wider uppercase px-1.5 py-0.5 rounded-full border border-tier-moderate/40 bg-tier-moderate/10 text-tier-moderate"
              >
                <AlertTriangle size={10} />
                supporting only
              </span>
            )}
            <span className="font-mono text-2xs tracking-wider uppercase px-1.5 py-0.5 rounded-full border border-border-2 text-fg-mute">
              {c.platform}
            </span>
          </div>
          <span className="font-mono text-2xs text-fg-mute shrink-0">{timeAgo(c.last_seen_at)}</span>
        </div>

        <p className="text-sm text-fg leading-relaxed mb-4 line-clamp-2 min-h-[2.5rem]">
          <span className="font-semibold tabular">{c.member_count}</span> accounts ·{' '}
          <span className="text-fg-dim">{evidenceText || 'coordination'}</span>
        </p>

        {/* Score bar, the headline (max, not current) */}
        <div className="mb-4">
          <div className="flex items-center justify-between font-mono text-2xs mb-1.5">
            <span className="text-fg-mute uppercase tracking-wider">Max coordination</span>
            <span className="text-fg tabular">{score_pct}%</span>
          </div>
          <div className="h-1.5 bg-bg-elev-3 rounded-full overflow-hidden">
            <div
              className={`h-full rounded-full transition-all ${barClassFor(c.max_coordination_score, corroborated)}`}
              style={{ width: `${Math.min(100, score_pct)}%` }}
            />
          </div>
        </div>

        {/* Sub-metrics */}
        <div className="grid grid-cols-4 gap-2">
          <MiniStat label="Members" value={c.member_count} icon={<Network size={10} />} />
          <MiniStat label="Seen" value={`${c.observation_count}×`} tone={c.observation_count > 1 ? 'ok' : 'mute'} icon={<Clock size={10} />} />
          <MiniStat label="Methods" value={c.methods.length} icon={<Sparkles size={10} />} />
          <MiniStat label="Conf." value={`${Math.round(c.confidence * 100)}%`} tone={c.confidence >= 0.7 ? 'ok' : c.confidence >= 0.4 ? 'moderate' : 'mute'} />
        </div>
      </article>
    </Link>
  );
}

function StatusPill({ status }: { status: 'observed' | 'recurring' }) {
  if (status === 'recurring') {
    return (
      <span className="inline-flex items-center gap-1 font-mono text-2xs tracking-wider uppercase px-1.5 py-0.5 rounded-full border border-accent/40 bg-accent/10 text-accent">
        <Clock size={10} />
        recurring
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1 font-mono text-2xs tracking-wider uppercase px-1.5 py-0.5 rounded-full border border-border-2 text-fg-mute">
      observed
    </span>
  );
}

function barClassFor(score: number, corroborated: boolean): string {
  if (!corroborated) return 'bg-tier-moderate';
  if (score >= 0.75) return 'bg-tier-high';
  if (score >= 0.5)  return 'bg-tier-elevated';
  return 'bg-tier-moderate';
}

function FilterField({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="flex flex-col gap-1.5">
      <span className="font-mono text-2xs uppercase tracking-wider text-fg-mute">{label}</span>
      {children}
    </label>
  );
}

function StatBlock({
  label, value, tone = 'mute', icon,
}: {
  label: string;
  value: number | string;
  tone?: 'mute' | 'moderate' | 'elevated' | 'high' | 'ok';
  icon?: React.ReactNode;
}) {
  const toneClass = {
    mute: 'text-fg', moderate: 'text-tier-moderate', elevated: 'text-tier-elevated',
    high: 'text-tier-high', ok: 'text-accent',
  }[tone];
  return (
    <div className="bg-bg-elev border border-border-1 rounded-xl px-4 py-3 card-interactive">
      <div className="font-mono text-2xs uppercase tracking-wider text-fg-mute flex items-center gap-1.5">
        {icon}
        {label}
      </div>
      <div className={`stat-value mt-1.5 text-xl font-semibold ${toneClass}`}>{value}</div>
    </div>
  );
}

function MiniStat({
  label, value, tone = 'mute', icon,
}: {
  label: string;
  value: number | string;
  tone?: 'mute' | 'moderate' | 'elevated' | 'high' | 'ok';
  icon?: React.ReactNode;
}) {
  const toneClass = {
    mute: 'text-fg-dim', moderate: 'text-tier-moderate', elevated: 'text-tier-elevated',
    high: 'text-tier-high', ok: 'text-accent',
  }[tone];
  return (
    <div className="surface-inset px-2 py-1.5">
      <div className="font-mono text-[0.55rem] uppercase tracking-wider text-fg-faint flex items-center gap-1">
        {icon}
        {label}
      </div>
      <div className={`mt-0.5 text-sm font-medium tabular ${toneClass}`}>{value}</div>
    </div>
  );
}
