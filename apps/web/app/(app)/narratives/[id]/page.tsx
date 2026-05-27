import Link from 'next/link';
import { notFound } from 'next/navigation';
import {
  ArrowLeft,
  Users,
  MessageSquare,
  TrendingUp,
  Shield,
  ShieldAlert,
  AlertTriangle,
  Flame,
  Cpu,
  BarChart2,
  ExternalLink,
  RefreshCw,
} from 'lucide-react';
import { Card, CardLabel, CardTitle } from '@/components/ui/card';
import { TierBadge } from '@/components/shared/tier-badge';
import {
  type NarrativeDetail,
  type NarrativeTopAccount,
  type NarrativeSample,
  type Tier,
  ApiError,
} from '@/lib/api';
import { apiServer } from '@/lib/api-server';
import { timeAgo } from '@/lib/format';

export const dynamic = 'force-dynamic';

export async function generateMetadata({ params }: { params: { id: string } }) {
  return { title: `Narrative #${params.id} — OMISPHERE` };
}

const RISK_CONFIG = {
  likely_coordinated: {
    label: 'Likely coordinated',
    icon: <Flame size={12} />,
    cls: 'text-tier-high border-tier-high/40 bg-tier-high/10',
    desc: 'Strongly elevated inauthenticity signal. A large fraction of authors show bot-like or coordinated behaviours.',
    barCls: 'bg-tier-high',
  },
  suspicious: {
    label: 'Suspicious',
    icon: <ShieldAlert size={12} />,
    cls: 'text-tier-elevated border-tier-elevated/40 bg-tier-elevated/10',
    desc: 'Notable inauthenticity signal. Some amplification by inauthentic accounts is likely.',
    barCls: 'bg-tier-elevated',
  },
  mixed: {
    label: 'Mixed',
    icon: <AlertTriangle size={12} />,
    cls: 'text-tier-moderate border-tier-moderate/40 bg-tier-moderate/10',
    desc: 'Organic and inauthentic engagement appear intermingled in this cluster.',
    barCls: 'bg-tier-moderate',
  },
  organic: {
    label: 'Organic',
    icon: <Shield size={12} />,
    cls: 'text-tier-low border-tier-low/40 bg-tier-low/10',
    desc: 'Authors in this cluster score consistently low for inauthenticity.',
    barCls: 'bg-tier-low',
  },
  unknown: {
    label: 'Unscored',
    icon: null,
    cls: 'text-fg-mute border-border-2 bg-transparent',
    desc: 'Not enough scanned authors to score this cluster.',
    barCls: 'bg-accent',
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
    fetchError = err instanceof ApiError
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

  const risk = RISK_CONFIG[detail.risk_label as keyof typeof RISK_CONFIG] ?? RISK_CONFIG.unknown;
  const inauth_pct = Math.round(detail.inauthenticity_score * 100);
  const spread_pct = Math.round(detail.spread_ratio * 100);

  const activityMax = Math.max(1, ...detail.activity.map((a) => a.count));

  const platformEntries = Object.entries(detail.platform_breakdown).sort(
    ([, a], [, b]) => b - a,
  );
  const platformTotal = Math.max(1, platformEntries.reduce((s, [, v]) => s + v, 0));

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
            {risk.label}
          </span>
          {detail.platforms.map((p) => (
            <span
              key={p}
              className="font-mono text-2xs tracking-wider uppercase px-2 py-1 rounded-sm border border-border-2 text-fg-mute"
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

        <p className="text-sm text-fg-dim">{risk.desc}</p>
      </header>

      {/* Key stats */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <StatCard
          label="Total comments"
          value={detail.member_count.toLocaleString()}
          icon={<MessageSquare size={14} />}
        />
        <StatCard
          label="Distinct authors"
          value={detail.distinct_authors.toLocaleString()}
          icon={<Users size={14} />}
        />
        <StatCard
          label="Spread ratio"
          value={`${spread_pct}%`}
          icon={<TrendingUp size={14} />}
          sub="cross-video spread"
        />
        <StatCard
          label="Inauthentic authors"
          value={`${inauth_pct}%`}
          icon={<ShieldAlert size={14} />}
          highlight={inauth_pct >= 35}
          sub={
            inauth_pct >= 60
              ? 'likely coordinated'
              : inauth_pct >= 35
              ? 'suspicious'
              : inauth_pct >= 15
              ? 'mixed signal'
              : 'low'
          }
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

      {/* Activity chart + Platform breakdown — side by side on wide */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-3">
        {/* Activity chart */}
        <Card className="lg:col-span-2 p-5">
          <CardLabel className="flex items-center gap-1.5 mb-4">
            <BarChart2 size={10} />
            Daily activity (last 30 days)
          </CardLabel>
          {detail.activity.length === 0 ? (
            <p className="text-sm text-fg-dim">No activity data available.</p>
          ) : (
            <ActivityChart data={detail.activity} max={activityMax} riskCls={risk.barCls} />
          )}
        </Card>

        {/* Platform breakdown */}
        <Card className="p-5">
          <CardLabel className="mb-4">Platform breakdown</CardLabel>
          {platformEntries.length === 0 ? (
            <p className="text-sm text-fg-dim">No data.</p>
          ) : (
            <div className="space-y-3">
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
                    <div className="h-1.5 bg-border-1 rounded-full overflow-hidden">
                      <div
                        className={`h-full rounded-full transition-all ${risk.barCls}`}
                        style={{ width: `${pct}%`, opacity: 0.6 }}
                      />
                    </div>
                  </div>
                );
              })}
            </div>
          )}
          <div className="mt-4 pt-4 border-t border-border-1 space-y-1.5">
            <MetaRow label="First seen" value={formatDate(detail.first_seen_at)} />
            <MetaRow label="Last seen" value={formatDate(detail.last_seen_at)} />
            <MetaRow label="Cluster ID" value={`#${detail.id}`} />
          </div>
        </Card>
      </div>

      {/* Top accounts */}
      {detail.top_accounts.length > 0 && (
        <Card className="p-0 overflow-hidden">
          <div className="px-5 pt-5 pb-3 border-b border-border-1">
            <CardLabel className="flex items-center gap-1.5 mb-0">
              <Users size={10} />
              Top authors in this cluster
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
                    Platform
                  </th>
                  <th className="text-right font-mono text-2xs tracking-wider text-fg-mute uppercase px-3 py-2.5">
                    Comments
                  </th>
                  <th className="text-left font-mono text-2xs tracking-wider text-fg-mute uppercase px-3 py-2.5 pr-5">
                    Risk
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border-1">
                {detail.top_accounts.map((a) => (
                  <TopAccountRow key={`${a.platform}:${a.external_id}`} account={a} />
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
            Sample comments from this cluster
          </div>
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-2">
            {detail.samples.map((s, i) => (
              <SampleComment key={i} sample={s} />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function StatCard({
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
    <div className="bg-bg-elev border border-border-1 rounded-md p-4">
      <div className="flex items-center gap-1.5 font-mono text-2xs text-fg-mute uppercase tracking-wider mb-2">
        {icon}
        {label}
      </div>
      <div
        className={`font-mono text-2xl font-semibold tabular-nums leading-none ${
          highlight ? 'text-tier-elevated' : 'text-fg'
        }`}
      >
        {value}
      </div>
      {sub && (
        <div className="font-mono text-2xs text-fg-faint mt-1 uppercase tracking-wider">
          {sub}
        </div>
      )}
    </div>
  );
}

function ActivityChart({
  data,
  max,
  riskCls,
}: {
  data: Array<{ date: string; count: number }>;
  max: number;
  riskCls: string;
}) {
  const recent = data.slice(-30);
  return (
    <div className="flex items-end gap-px h-20 w-full">
      {recent.map((d) => {
        const heightPct = Math.max(3, Math.round((d.count / max) * 100));
        return (
          <div
            key={d.date}
            className="flex-1 group relative min-w-0"
            title={`${d.date}: ${d.count}`}
          >
            <div
              className={`w-full rounded-t-sm transition-colors ${riskCls} opacity-40 group-hover:opacity-80`}
              style={{ height: `${heightPct}%` }}
            />
            <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-1 hidden group-hover:flex flex-col items-center pointer-events-none z-10">
              <div className="bg-bg-elev border border-border-2 rounded px-2 py-1 font-mono text-2xs text-fg whitespace-nowrap shadow-md">
                {d.date}: {d.count}
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}

function TopAccountRow({ account: a }: { account: NarrativeTopAccount }) {
  const tier = a.tier as Tier | null;
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
          </div>
          <ExternalLink size={11} className="text-fg-faint group-hover:text-accent shrink-0" />
        </Link>
      </td>
      <td className="px-3 py-3">
        <span className="font-mono text-2xs tracking-wider uppercase text-fg-mute">
          {a.platform}
        </span>
      </td>
      <td className="px-3 py-3 text-right font-mono text-sm tabular-nums text-fg">
        {a.comment_count.toLocaleString()}
      </td>
      <td className="px-3 py-3 pr-5">
        {tier ? (
          <TierBadge tier={tier} size="sm" />
        ) : (
          <span className="font-mono text-2xs text-fg-faint">—</span>
        )}
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

function MetaRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between font-mono text-2xs">
      <span className="text-fg-mute">{label}</span>
      <span className="text-fg">{value}</span>
    </div>
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
