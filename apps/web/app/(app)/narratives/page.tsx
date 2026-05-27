import Link from 'next/link';
import { Users, TrendingUp, ArrowRight, ShieldAlert, Shield, AlertTriangle, Flame } from 'lucide-react';
import { Card, CardLabel, CardTitle } from '@/components/ui/card';
import { TierBadge } from '@/components/shared/tier-badge';
import { type NarrativesResponse, type NarrativeOut } from '@/lib/api';
import { apiServer } from '@/lib/api-server';
import { timeAgo } from '@/lib/format';

export const metadata = { title: 'Narratives — OMISPHERE' };
export const dynamic = 'force-dynamic';

const WINDOWS = [1, 7, 30, 90] as const;

const RISK_CONFIG = {
  likely_coordinated: {
    label: 'Likely coordinated',
    icon: <Flame size={11} />,
    cls: 'text-tier-high border-tier-high/40 bg-tier-high/10',
  },
  suspicious: {
    label: 'Suspicious',
    icon: <ShieldAlert size={11} />,
    cls: 'text-tier-elevated border-tier-elevated/40 bg-tier-elevated/10',
  },
  mixed: {
    label: 'Mixed',
    icon: <AlertTriangle size={11} />,
    cls: 'text-tier-moderate border-tier-moderate/40 bg-tier-moderate/10',
  },
  organic: {
    label: 'Organic',
    icon: <Shield size={11} />,
    cls: 'text-tier-low border-tier-low/40 bg-tier-low/10',
  },
  unknown: {
    label: 'Unscored',
    icon: null,
    cls: 'text-fg-mute border-border-2',
  },
};

export default async function NarrativesPage({
  searchParams,
}: {
  searchParams: { window?: string };
}) {
  const window_days = Math.max(1, Math.min(90, parseInt(searchParams.window || '7', 10) || 7));
  let data: NarrativesResponse;
  try {
    data = await apiServer<NarrativesResponse>(`/v1/narratives?window_days=${window_days}&limit=30`);
  } catch {
    data = { window_days, embedder: 'unknown', narratives: [] };
  }

  const sorted = [...data.narratives].sort(
    (a, b) =>
      b.recent_members * (0.5 + b.spread_ratio) -
      a.recent_members * (0.5 + a.spread_ratio),
  );

  const suspiciousCount = sorted.filter(
    (n) => n.risk_label === 'suspicious' || n.risk_label === 'likely_coordinated',
  ).length;

  return (
    <div className="space-y-6">
      {/* Header */}
      <header className="flex items-end justify-between gap-4 flex-wrap">
        <div>
          <p className="font-mono text-2xs tracking-[0.18em] text-fg-mute uppercase mb-1">
            Narrative observatory
          </p>
          <h1 className="text-2xl font-semibold text-fg tracking-tight">
            Spreading narratives
          </h1>
          <p className="mt-1 text-sm text-fg-dim max-w-2xl">
            Semantic clusters of comments — same topic, same framing — across all
            scanned videos. Risk scores flag clusters amplified by inauthentic accounts.
          </p>
        </div>
        {/* Window selector */}
        <div className="flex items-center gap-2">
          <span className="font-mono text-2xs tracking-[0.18em] text-fg-mute uppercase">Window</span>
          {WINDOWS.map((d) => (
            <Link
              key={d}
              href={`/narratives?window=${d}`}
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

      {/* Summary row */}
      {data.narratives.length > 0 && (
        <div className="flex items-center gap-6 font-mono text-2xs text-fg-mute uppercase tracking-wider">
          <span>{data.narratives.length} clusters</span>
          <span>·</span>
          <span>Embedder <span className="text-accent">{data.embedder}</span></span>
          {suspiciousCount > 0 && (
            <>
              <span>·</span>
              <span className="text-tier-elevated">
                {suspiciousCount} suspicious
              </span>
            </>
          )}
        </div>
      )}

      {/* Empty state */}
      {sorted.length === 0 ? (
        <Card>
          <CardLabel>No narratives in this window</CardLabel>
          <CardTitle>The observatory is empty</CardTitle>
          <p className="text-sm text-fg-dim max-w-lg">
            Narratives build from scanned comments. Run more scans — every
            comment longer than 18 characters gets clustered into the
            cross-corpus narrative store. Try widening the time window.
          </p>
        </Card>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
          {sorted.map((n, i) => (
            <NarrativeCard key={n.id} narrative={n} rank={i + 1} />
          ))}
        </div>
      )}
    </div>
  );
}

function NarrativeCard({ narrative: n, rank }: { narrative: NarrativeOut; rank: number }) {
  const risk = RISK_CONFIG[n.risk_label as keyof typeof RISK_CONFIG] ?? RISK_CONFIG.unknown;
  const inauth_pct = Math.round(n.inauthenticity_score * 100);
  const spread_pct = Math.round(n.spread_ratio * 100);

  return (
    <Link href={`/narratives/${n.id}`} className="block group">
      <article className="h-full bg-bg-elev border border-border-1 rounded-md p-5 hover:border-border-hot group-hover:bg-bg-elev-2/30 transition-colors">
        {/* Top row: rank + risk badge + time */}
        <div className="flex items-center justify-between mb-3 gap-2">
          <div className="flex items-center gap-2">
            <span className="font-mono text-2xs text-fg-faint">#{rank}</span>
            <span className={`inline-flex items-center gap-1 font-mono text-2xs tracking-wider uppercase px-2 py-0.5 rounded-sm border ${risk.cls}`}>
              {risk.icon}{risk.label}
            </span>
            {n.platforms.slice(0, 2).map((p) => (
              <span key={p} className="font-mono text-2xs tracking-wider uppercase px-1.5 py-0.5 rounded-sm border border-border-2 text-fg-mute">
                {p}
              </span>
            ))}
          </div>
          <span className="font-mono text-2xs text-fg-mute shrink-0">
            {timeAgo(n.last_seen_at)}
          </span>
        </div>

        {/* Sample text */}
        <p className="text-sm text-fg leading-relaxed mb-4 line-clamp-2 min-h-[2.5rem]">
          &ldquo;{n.sample_text || '(no sample)'}&rdquo;
        </p>

        {/* Stats row */}
        <div className="grid grid-cols-4 gap-2 mb-3">
          <StatMini label="Recent" value={n.recent_members} />
          <StatMini label="Authors" value={n.distinct_authors} icon={<Users size={9} />} />
          <StatMini label="Total" value={n.member_count} />
          <StatMini
            label="Inauth."
            value={`${inauth_pct}%`}
            highlight={inauth_pct >= 35}
          />
        </div>

        {/* Spread bar */}
        <div className="flex items-center gap-2">
          <div className="flex-1 h-1 bg-border-1 rounded-full overflow-hidden">
            <div
              className="h-full rounded-full bg-accent transition-all"
              style={{ width: `${Math.min(100, spread_pct)}%` }}
            />
          </div>
          <span className="font-mono text-2xs text-fg-mute shrink-0 w-16 text-right">
            {spread_pct}% spread
          </span>
          <ArrowRight size={12} className="text-fg-faint group-hover:text-accent transition-colors shrink-0" />
        </div>
      </article>
    </Link>
  );
}

function StatMini({
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
        {icon}{label}
      </div>
      <div className={`font-mono text-sm font-medium ${highlight ? 'text-tier-elevated' : 'text-fg'}`}>
        {value}
      </div>
    </div>
  );
}
