import { notFound } from 'next/navigation';
import Link from 'next/link';
import {
  ArrowLeft, TrendingUp, TrendingDown, Minus, Activity, Calendar,
  Brain, BarChart2, Video, ArrowRight,
} from 'lucide-react';
import { Card, CardLabel, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Sparkline } from '@/components/shared/sparkline';
import { TierBadge } from '@/components/shared/tier-badge';
import { ScoreRing } from '@/components/shared/score-ring';
import { ApiError, type AccountHistoryResponse, type AccountAnalysisResponse, type ChannelIntelligenceResponse, type SignalResult } from '@/lib/api';
import { apiServer } from '@/lib/api-server';
import { pct, timeAgo, tierBg } from '@/lib/format';
import { HistoryRow } from './history-row';
import { AccountActivityPanel } from './activity-panel';
import { AccountActionsClient } from './account-actions-wrapper';
import { LabelWidget } from './label-widget';

interface PageProps {
  params: { external_id: string };
  searchParams: { platform?: string };
}

export const dynamic = 'force-dynamic';

const SIGNAL_LABELS: Record<string, string> = {
  temporal:    'Posting cadence',
  semantic:    'Content repetition',
  ai_writing:  'AI-writing patterns',
  profile:     'Profile metadata',
  voice:       'Personal voice',
  engagement:  'Engagement farming',
  memory:      'Fingerprint match',
  coordination:'Coordination cluster',
};

export default async function AccountHistoryPage({ params, searchParams }: PageProps) {
  const platform = searchParams.platform || 'youtube';
  const external_id = decodeURIComponent(params.external_id);

  let history: AccountHistoryResponse;
  try {
    history = await apiServer<AccountHistoryResponse>(
      `/v1/accounts/${platform}/${encodeURIComponent(external_id)}/history?limit=1000`,
    );
  } catch (e) {
    if (e instanceof ApiError && e.status === 404) notFound();
    throw e;
  }

  let analysis: AccountAnalysisResponse | null = null;
  try {
    analysis = await apiServer<AccountAnalysisResponse>(
      `/v1/accounts/${platform}/${encodeURIComponent(external_id)}/analysis`,
    );
  } catch {
    /* analysis is optional */
  }

  // If this account is the author of any scanned content, expose a link to
  // the channel-level intelligence view. Cheap probe — endpoint 404s when
  // there's no data, in which case we hide the link.
  let channel: ChannelIntelligenceResponse | null = null;
  try {
    channel = await apiServer<ChannelIntelligenceResponse>(
      `/v1/channels/${platform}/${encodeURIComponent(external_id)}/intelligence`,
    );
    if (channel.video_count === 0) channel = null;
  } catch {
    channel = null;
  }

  const latest = history.scans[0];
  const sparkPoints = [...history.scans].reverse().map((s) => s.overall_probability);
  const latestSignals = (latest?.signals ?? []).filter((s) => s.confidence > 0);

  // Pre-build CSV body once, server-side, so the export button is instant
  const csvRows = buildCsv(history);

  return (
    <div className="space-y-6 max-w-5xl">
      {/* Sticky action bar — rescan / watch / export — ALWAYS visible */}
      <AccountActionsClient
        externalId={history.external_id}
        platform={platform}
        handle={history.handle}
        csvText={csvRows}
      />

      <div>
        <Link
          href="/dashboard"
          className="inline-flex items-center gap-1.5 text-sm text-fg-mute hover:text-fg transition-colors font-mono tracking-wider uppercase mb-4"
        >
          <ArrowLeft size={14} /> Back
        </Link>

        <header className="relative overflow-hidden rounded-2xl border border-border-1 bg-bg-elev p-6 md:p-7 shadow-card">
          <div className="absolute -top-16 -right-12 w-56 h-56 rounded-full bg-accent/[0.07] blur-3xl pointer-events-none" aria-hidden />
          <div className="absolute inset-0 dot-bg opacity-[0.12] pointer-events-none" aria-hidden />
          <div className="relative flex items-center gap-5 flex-wrap">
            {latest && (
              <ScoreRing value={latest.overall_probability} tier={latest.tier} size={92} stroke={7} />
            )}
            <div className="flex-1 min-w-[200px]">
              <p className="font-mono text-2xs tracking-[0.2em] text-accent-2 uppercase mb-2 flex items-center gap-2">
                <span className="w-1.5 h-1.5 rounded-full bg-accent-2" />
                Account · {platform}
              </p>
              <div className="flex items-baseline gap-3 flex-wrap">
                <h1 className="display text-2xl md:text-3xl font-semibold text-fg tracking-tight">{history.handle}</h1>
                {history.display_name && (
                  <span className="text-fg-mute">· {history.display_name}</span>
                )}
                {latest && <TierBadge tier={latest.tier} size="lg" />}
              </div>
              <p className="mt-1.5 font-mono text-xs text-fg-faint break-all">{history.external_id}</p>
            </div>
          </div>
        </header>
      </div>

      {/* Channel-level intelligence link — only shown when this account owns content */}
      {channel && (
        <Link
          href={`/channels/${platform}/${encodeURIComponent(history.external_id)}`}
          className="block group"
        >
          <div className="flex items-center gap-4 p-4 rounded-xl border border-accent/30 bg-accent/[0.05] hover:border-accent/60 hover:bg-accent/[0.09] hover:shadow-glow-sm transition-all">
            <div className="shrink-0 w-10 h-10 rounded-lg border border-accent/40 bg-bg flex items-center justify-center text-accent">
              <Video size={18} />
            </div>
            <div className="flex-1 min-w-0">
              <p className="font-mono text-2xs tracking-[0.18em] text-accent uppercase mb-0.5">
                Channel intelligence available
              </p>
              <p className="text-sm text-fg">
                {channel.video_count} video{channel.video_count === 1 ? '' : 's'} scanned ·{' '}
                {channel.audience_composition.total_commenters.toLocaleString()} audience interactions ·{' '}
                {Math.round(channel.returning_commenter_ratio * 100)}% returning commenters
              </p>
            </div>
            <ArrowRight size={16} className="text-accent shrink-0 group-hover:translate-x-1 transition-transform" />
          </div>
        </Link>
      )}

      {/* AI Behavioural Analysis */}
      {analysis && (
        <Card>
          <div className="flex items-center gap-2 mb-3">
            <Brain size={14} className="text-accent" />
            <CardLabel className="m-0">AI behavioural analysis</CardLabel>
            <span className="ml-auto font-mono text-2xs text-fg-faint tracking-wider">
              {analysis.provider}
            </span>
          </div>
          <p className="text-sm text-fg leading-relaxed">{analysis.analysis}</p>
        </Card>
      )}

      {/* Latest snapshot + signal breakdown */}
      {latest && (
        <Card>
          <CardLabel>Latest scan · {timeAgo(latest.scanned_at)}</CardLabel>
          <div className="flex items-baseline justify-between gap-4 flex-wrap mb-3">
            <span className="text-3xl font-bold tracking-tight mono text-fg">
              {pct(latest.overall_probability)}
            </span>
            <span className={`px-2.5 py-0.5 rounded-full border font-mono text-2xs uppercase tracking-wider ${tierBg(latest.tier)}`}>
              {latest.tier} suspicion
            </span>
            <span className="font-mono text-2xs text-fg-mute uppercase tracking-wider">
              confidence {pct(latest.confidence)}
            </span>
          </div>
          <p className="mt-3 text-sm text-fg-dim">{latest.summary}</p>

          {latestSignals.length > 0 && (
            <div className="mt-5">
              <div className="flex items-center gap-1.5 font-mono text-2xs tracking-[0.18em] text-accent uppercase mb-3">
                <BarChart2 size={11} />
                Detector breakdown
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                {latestSignals.map((s) => (
                  <SignalCard key={s.name} signal={s} />
                ))}
              </div>
            </div>
          )}
        </Card>
      )}

      {/* Admin-only ground-truth label widget. Renders null for non-admins. */}
      <LabelWidget platform={platform} externalId={history.external_id} />

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

      {/* Account activity — heatmap + searchable comment feed */}
      <AccountActivityPanel platform={platform} externalId={history.external_id} />

      {/* Scan history table — every row expands to show that scan's signals */}
      <Card>
        <div className="flex items-center justify-between gap-3 mb-3 flex-wrap">
          <CardLabel className="m-0">
            Full scan history · {(history.total_scans || history.scans.length).toLocaleString()} scan
            {(history.total_scans || history.scans.length) === 1 ? '' : 's'}
            {history.total_scans > history.scans.length && (
              <span className="ml-2 font-mono text-2xs text-fg-mute normal-case tracking-normal">
                (showing newest {history.scans.length.toLocaleString()})
              </span>
            )}
          </CardLabel>
          <span className="font-mono text-2xs text-fg-mute tracking-wider uppercase">
            Click a row to expand
          </span>
        </div>
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
                <HistoryRow key={`${s.scanned_at}-${i}`} scan={s} />
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      {/* Profile snapshot */}
      <Card>
        <CardLabel>Profile snapshot</CardLabel>
        <dl className="grid grid-cols-1 sm:grid-cols-2 gap-x-8 gap-y-3 text-sm">
          <Row label="Followers" value={history.follower_count?.toLocaleString() ?? '—'} />
          <Row
            label="Account created"
            value={history.account_created_at
              ? new Date(history.account_created_at).toLocaleDateString()
              : '—'}
          />
          <Row
            label="First seen by OMISPHERE"
            value={history.first_seen_at
              ? new Date(history.first_seen_at).toLocaleDateString()
              : '—'}
          />
          <Row
            label="Last scanned"
            value={history.last_scanned_at ? timeAgo(history.last_scanned_at) : '—'}
          />
          {history.bio && (
            <div className="sm:col-span-2">
              <dt className="font-mono text-2xs tracking-[0.16em] text-fg-mute uppercase mb-0.5">Bio</dt>
              <dd className="text-fg text-sm">{history.bio}</dd>
            </div>
          )}
        </dl>
      </Card>
    </div>
  );
}

function buildCsv(h: AccountHistoryResponse): string {
  const header = ['scanned_at', 'tier', 'probability', 'confidence', 'summary'];
  const lines = [header.join(',')];
  for (const s of h.scans) {
    const summary = (s.summary || '').replace(/"/g, '""').replace(/\r?\n/g, ' ');
    lines.push([
      s.scanned_at,
      s.tier,
      s.overall_probability.toFixed(4),
      s.confidence.toFixed(4),
      `"${summary}"`,
    ].join(','));
  }
  return lines.join('\n');
}

function SignalCard({ signal }: { signal: SignalResult }) {
  const prob = signal.probability ?? 0;
  const conf = signal.confidence ?? 0;
  const label = SIGNAL_LABELS[signal.name] ?? signal.name;
  const topEvidence = signal.evidence?.[0];
  const barColor =
    prob >= 0.75 ? 'bg-tier-high' :
    prob >= 0.5  ? 'bg-tier-elevated' :
    prob >= 0.25 ? 'bg-tier-moderate' :
    'bg-tier-low';
  const textColor =
    prob >= 0.75 ? 'text-tier-high' :
    prob >= 0.5  ? 'text-tier-elevated' :
    prob >= 0.25 ? 'text-tier-moderate' :
    'text-tier-low';

  return (
    <div className="bg-bg border border-border-1 rounded-xl p-3.5 hover:border-border-hot/60 transition-colors">
      <div className="flex items-center justify-between gap-2 mb-2">
        <span className="font-mono text-2xs uppercase tracking-wider text-fg-mute">{label}</span>
        <span className={`font-mono font-bold text-sm ${textColor}`}>
          {Math.round(prob * 100)}%
        </span>
      </div>
      <div className="h-1.5 w-full bg-border-1 rounded-full overflow-hidden mb-2">
        <div
          className={`h-full rounded-full ${barColor}`}
          style={{ width: `${Math.round(prob * 100)}%`, opacity: Math.max(0.35, conf) }}
        />
      </div>
      <div className="flex items-center justify-between text-2xs font-mono text-fg-faint">
        <span className="truncate max-w-[180px]">{topEvidence ?? 'No evidence noted.'}</span>
        <span className="shrink-0 ml-2">conf {Math.round(conf * 100)}%</span>
      </div>
    </div>
  );
}

function Row({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div>
      <dt className="font-mono text-2xs tracking-[0.16em] text-fg-mute uppercase mb-0.5">{label}</dt>
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
