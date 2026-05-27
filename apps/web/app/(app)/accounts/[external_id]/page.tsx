import { notFound } from 'next/navigation';
import Link from 'next/link';
import {
  ArrowLeft, TrendingUp, TrendingDown, Minus, Activity, Calendar,
} from 'lucide-react';
import { Card, CardLabel, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Sparkline } from '@/components/shared/sparkline';
import { ApiError, type AccountHistoryResponse } from '@/lib/api';
import { apiServer } from '@/lib/api-server';
import { pct, timeAgo, tierBg } from '@/lib/format';

interface PageProps {
  params: { external_id: string };
  searchParams: { platform?: string };
}

export const dynamic = 'force-dynamic';

export default async function AccountHistoryPage({ params, searchParams }: PageProps) {
  const platform = searchParams.platform || 'youtube';
  const external_id = decodeURIComponent(params.external_id);

  let history: AccountHistoryResponse;
  try {
    history = await apiServer<AccountHistoryResponse>(
      `/v1/accounts/${platform}/${encodeURIComponent(external_id)}/history`,
    );
  } catch (e) {
    if (e instanceof ApiError && e.status === 404) notFound();
    throw e;
  }

  const latest = history.scans[0]; // newest first
  // Oldest → newest for the sparkline
  const sparkPoints = [...history.scans].reverse().map((s) => s.overall_probability);

  return (
    <div className="space-y-8 max-w-5xl">
      <div>
        <Link
          href="/dashboard"
          className="inline-flex items-center gap-1.5 text-sm text-fg-mute hover:text-fg-dim font-mono tracking-wider uppercase mb-4"
        >
          <ArrowLeft size={14} /> Back
        </Link>
        <p className="font-mono text-2xs tracking-[0.18em] text-fg-mute uppercase mb-1">
          Account · {platform}
        </p>
        <div className="flex items-baseline gap-3">
          <h1 className="text-2xl font-semibold text-fg tracking-tight">{history.handle}</h1>
          {history.display_name && (
            <span className="text-fg-mute">· {history.display_name}</span>
          )}
        </div>
        <p className="mt-1 font-mono text-xs text-fg-faint">{history.external_id}</p>
      </div>

      {/* Trend card + sparkline */}
      <Card>
        <div className="flex items-start justify-between gap-6 flex-wrap">
          <div className="flex-1 min-w-[260px]">
            <CardLabel>Trend over time</CardLabel>
            <div className="flex items-center gap-3 mb-3">
              <TrendIcon dir={history.trend.direction} />
              <CardTitle className="m-0 capitalize">{history.trend.direction}</CardTitle>
              <Badge variant="neutral">{history.trend.sample_size} scans</Badge>
            </div>
            <p className="text-sm text-fg-dim">{history.trend.summary}</p>
            <div className="mt-4 grid grid-cols-3 gap-4 text-2xs font-mono uppercase tracking-wider text-fg-mute">
              <div>
                <div className="mb-0.5">Net change</div>
                <div className="text-fg mono">
                  {history.trend.net_change > 0 ? '+' : ''}
                  {Math.round(history.trend.net_change * 100)}pts
                </div>
              </div>
              <div>
                <div className="mb-0.5">Volatility (σ)</div>
                <div className="text-fg mono">
                  {Math.round(history.trend.volatility * 100)}pts
                </div>
              </div>
              <div>
                <div className="mb-0.5">Slope/scan</div>
                <div className="text-fg mono">
                  {(history.trend.slope * 100).toFixed(1)}pts
                </div>
              </div>
            </div>
          </div>
          <div className="w-full md:w-[260px]">
            <Sparkline points={sparkPoints} tier={latest?.tier} />
            <div className="flex justify-between mt-2 font-mono text-2xs text-fg-mute">
              <span>oldest</span>
              <span>latest</span>
            </div>
          </div>
        </div>
      </Card>

      {/* Latest snapshot */}
      {latest && (
        <Card>
          <CardLabel>Latest scan · {timeAgo(latest.scanned_at)}</CardLabel>
          <div className="flex items-baseline justify-between gap-4 flex-wrap mb-3">
            <span className="text-3xl font-bold tracking-tight mono text-fg">
              {pct(latest.overall_probability)}
            </span>
            <span className={`px-2 py-0.5 rounded-sm border font-mono text-2xs uppercase tracking-wider ${tierBg(latest.tier)}`}>
              {latest.tier} suspicion
            </span>
            <span className="font-mono text-2xs text-fg-mute uppercase tracking-wider">
              confidence {pct(latest.confidence)}
            </span>
          </div>
          <p className="text-sm text-fg-dim">{latest.summary}</p>
        </Card>
      )}

      {/* Scan history table */}
      <Card>
        <CardLabel>History · {history.scans.length} scan{history.scans.length === 1 ? '' : 's'}</CardLabel>
        <div className="overflow-x-auto -mx-2">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left font-mono text-2xs tracking-[0.16em] uppercase text-fg-mute border-b border-border-1">
                <th className="px-2 py-2 font-normal">When</th>
                <th className="px-2 py-2 font-normal">Tier</th>
                <th className="px-2 py-2 font-normal text-right">Probability</th>
                <th className="px-2 py-2 font-normal text-right">Confidence</th>
                <th className="px-2 py-2 font-normal">Summary</th>
              </tr>
            </thead>
            <tbody>
              {history.scans.map((s, i) => (
                <tr key={i} className="border-b border-border-1 last:border-0 hover:bg-bg-elev/50 transition-colors">
                  <td className="px-2 py-3 font-mono text-2xs text-fg-dim whitespace-nowrap">
                    {timeAgo(s.scanned_at)}
                  </td>
                  <td className="px-2 py-3">
                    <span className={`inline-block px-2 py-0.5 rounded-sm border font-mono text-2xs uppercase tracking-wider ${tierBg(s.tier)}`}>
                      {s.tier}
                    </span>
                  </td>
                  <td className="px-2 py-3 mono text-right">{pct(s.overall_probability)}</td>
                  <td className="px-2 py-3 mono text-right text-fg-dim">{pct(s.confidence)}</td>
                  <td className="px-2 py-3 text-fg-dim text-xs leading-relaxed max-w-md">{s.summary}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      {/* Profile snapshot */}
      <Card>
        <CardLabel>Profile snapshot</CardLabel>
        <dl className="grid grid-cols-1 sm:grid-cols-2 gap-x-8 gap-y-3 text-sm">
          <Row label="Followers" value={history.follower_count ?? '—'} />
          <Row
            label="Account created"
            value={
              history.account_created_at
                ? new Date(history.account_created_at).toLocaleDateString()
                : '—'
            }
          />
          <Row
            label="First seen by OMISPHERE"
            value={
              history.first_seen_at
                ? new Date(history.first_seen_at).toLocaleDateString()
                : '—'
            }
          />
          <Row
            label="Last scanned"
            value={
              history.last_scanned_at
                ? timeAgo(history.last_scanned_at)
                : '—'
            }
          />
          {history.bio && (
            <div className="sm:col-span-2">
              <dt className="font-mono text-2xs tracking-[0.16em] text-fg-mute uppercase mb-0.5">Bio</dt>
              <dd className="text-fg text-sm">{history.bio}</dd>
            </div>
          )}
        </dl>
      </Card>

      <div className="flex gap-3">
        <Link href="/investigate">
          <Button>
            <Activity size={14} /> Re-scan this account
          </Button>
        </Link>
      </div>
    </div>
  );
}

function Row({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div>
      <dt className="font-mono text-2xs tracking-[0.16em] text-fg-mute uppercase mb-0.5">
        {label}
      </dt>
      <dd className="text-fg">{value}</dd>
    </div>
  );
}

function TrendIcon({ dir }: { dir: AccountHistoryResponse['trend']['direction'] }) {
  const cls = 'shrink-0';
  switch (dir) {
    case 'rising':   return <TrendingUp size={20} className={`${cls} text-tier-elevated`} />;
    case 'falling':  return <TrendingDown size={20} className={`${cls} text-tier-low`} />;
    case 'volatile': return <Activity size={20} className={`${cls} text-tier-moderate`} />;
    case 'stable':   return <Minus size={20} className={`${cls} text-fg-dim`} />;
    default:         return <Calendar size={20} className={`${cls} text-fg-mute`} />;
  }
}
