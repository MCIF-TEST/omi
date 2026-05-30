'use client';

import { useState } from 'react';
import { Activity, Search, Zap, Network as NetworkIcon, ChevronDown, ChevronRight, Users, AlertTriangle } from 'lucide-react';
import Link from 'next/link';
import { TierBadge } from '@/components/shared/tier-badge';
import { ScoreRing } from '@/components/shared/score-ring';
import { type ComprehensiveScanResult, type CoordinationCluster } from '@/lib/api';

export function Synthesis({ data }: { data: ComprehensiveScanResult }) {
  const prob = data.overall_probability;
  const v = data.video;
  return (
    <article className="p-6 space-y-6">
      {/* Verdict hero */}
      <header className="relative overflow-hidden rounded-2xl border border-border-1 bg-gradient-to-br from-bg-elev-2/60 to-bg-elev/30 p-5 md:p-6">
        <div className="relative flex items-center gap-5 flex-wrap">
          <ScoreRing value={prob} tier={data.overall_tier} size={96} stroke={8} />
          <div className="flex-1 min-w-[200px]">
            <div className="flex items-center gap-3 mb-2 flex-wrap">
              <span className="font-mono text-2xs tracking-[0.18em] text-fg-mute uppercase">
                Comprehensive verdict
              </span>
              <TierBadge tier={data.overall_tier} size="lg" />
            </div>
            <p className="text-sm text-fg-dim leading-relaxed">{data.summary}</p>
          </div>
        </div>
      </header>

      {/* Stat strip */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <Stat
          icon={<Search size={12} />}
          label="Convergence"
          value={data.cross_links.length}
          sub={`${data.cross_links.filter((l) => l.severity === 'elevated' || l.severity === 'high').length} elevated+`}
        />
        <Stat
          icon={<NetworkIcon size={12} />}
          label="Sources"
          value={data.inputs_provided.length}
          sub={data.inputs_provided.join(' + ') || '—'}
        />
        <Stat
          icon={<Zap size={12} />}
          label="YT quota"
          value={data.quota_used}
          sub="units used"
        />
        {v && (
          <Stat
            icon={<Activity size={12} />}
            label="Commenters"
            value={v.commenter_count}
            sub={`${v.fresh_count} fresh · ${v.cached_count} cached`}
          />
        )}
      </div>

      {/* Coordination summary */}
      {v && (
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
          <SubScan
            label="Coordination"
            prob={v.coordination_score}
            tier={v.coordination_tier}
            sub={`${v.clusters.length} cluster${v.clusters.length === 1 ? '' : 's'}`}
          />
          <SubScan
            label="Thread"
            prob={v.thread_scan.overall_probability}
            tier={v.thread_scan.tier}
            sub="whole corpus"
          />
          <SubScan
            label="Tier distribution"
            customBody={
              <div className="flex gap-2 flex-wrap items-center">
                <DistChip n={v.tier_distribution.high || 0} tone="high" />
                <DistChip n={v.tier_distribution.elevated || 0} tone="elevated" />
                <DistChip n={v.tier_distribution.moderate || 0} tone="moderate" />
                <DistChip n={v.tier_distribution.low || 0} tone="low" />
              </div>
            }
          />
        </div>
      )}

      {/* Coordination rings — the differentiator view */}
      {v && v.clusters.length > 0 && (
        <RingsPanel clusters={v.clusters} commenters={v.commenters ?? []} />
      )}

      {/* Focus account spotlight */}
      {data.focus_account && (
        <section>
          <div className="font-mono text-2xs tracking-[0.18em] text-accent uppercase mb-2">
            Focus account
          </div>
          <div className="bg-bg border border-border-1 rounded-sm p-4">
            <div className="flex items-baseline gap-3 flex-wrap mb-1">
              <span className="text-base font-semibold text-fg">{data.focus_account.handle}</span>
              <TierBadge tier={data.focus_account.tier} />
              {data.focus_account.from_cache && (
                <span className="font-mono text-2xs text-fg-mute uppercase tracking-wider">cached</span>
              )}
            </div>
            <p className="text-sm text-fg-dim mt-2">{data.focus_account.summary}</p>
            {data.focus_account.intent_label && data.focus_account.tier !== 'low' && (
              <p className="mt-2 font-mono text-2xs text-tier-elevated uppercase tracking-wider">
                ▸ {data.focus_account.intent_label}
              </p>
            )}
          </div>
        </section>
      )}

      {/* High-suspicion handles */}
      {v && v.high_suspicion_handles.length > 0 && (
        <section>
          <div className="font-mono text-2xs tracking-[0.18em] text-danger uppercase mb-2">
            High-suspicion commenters · {v.high_suspicion_handles.length}
          </div>
          <div className="flex flex-wrap gap-1.5">
            {v.high_suspicion_handles.slice(0, 30).map((h) => (
              <span
                key={h}
                className="px-2 py-0.5 rounded-sm border border-danger/40 bg-danger/10 text-danger font-mono text-2xs"
              >
                {h}
              </span>
            ))}
          </div>
        </section>
      )}
    </article>
  );
}

// ---------------------------------------------------------------------------
// Coordination rings panel
// ---------------------------------------------------------------------------

const METHOD_LABELS: Record<string, string> = {
  temporal_semantic: 'Timing + semantic',
  co_engagement: 'Co-engagement',
  style_match: 'Writing style match',
  fingerprint_cluster: 'Fingerprint cluster',
  cohort: 'Cohort clustering',
};

interface RingsPanelProps {
  clusters: CoordinationCluster[];
  commenters: any[];
}

function RingsPanel({ clusters, commenters }: RingsPanelProps) {
  // Index commenter handles by external_id for fast lookup
  const handleMap = new Map<string, { handle: string; tier: string }>();
  for (const c of commenters) {
    handleMap.set(c.external_id, { handle: c.handle, tier: c.tier });
  }

  // Sort by score descending
  const sorted = [...clusters].sort((a, b) => b.score - a.score);

  return (
    <section>
      <div className="flex items-center gap-2 mb-3">
        <NetworkIcon size={12} className="text-accent" />
        <span className="font-mono text-2xs tracking-[0.18em] text-accent uppercase">
          Coordination rings · {clusters.length}
        </span>
      </div>
      <div className="space-y-2">
        {sorted.map((cluster, i) => (
          <RingCard
            key={i}
            index={i + 1}
            cluster={cluster}
            handleMap={handleMap}
          />
        ))}
      </div>
    </section>
  );
}

function RingCard({
  index,
  cluster,
  handleMap,
}: {
  index: number;
  cluster: CoordinationCluster;
  handleMap: Map<string, { handle: string; tier: string }>;
}) {
  const [expanded, setExpanded] = useState(false);
  const score = cluster.score;
  const isHighRisk = score >= 0.7;
  const isMedium = score >= 0.4;

  const headerColor = isHighRisk
    ? 'border-danger/40 bg-danger/5'
    : isMedium
      ? 'border-tier-elevated/40 bg-tier-elevated/5'
      : 'border-border-2 bg-bg-elev-2/30';

  const scoreColor = isHighRisk
    ? 'text-danger'
    : isMedium
      ? 'text-tier-elevated'
      : 'text-fg-dim';

  return (
    <div className={`border rounded-xl overflow-hidden transition-colors ${headerColor}`}>
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center justify-between gap-3 px-4 py-3 text-left hover:bg-bg-elev-2/20 transition-colors"
      >
        <div className="flex items-center gap-3 min-w-0">
          <span className="font-mono text-2xs text-fg-mute shrink-0">R{index}</span>
          <span className="font-mono text-2xs tracking-wider uppercase text-fg-dim shrink-0">
            {METHOD_LABELS[cluster.method] ?? cluster.method}
          </span>
          <span className="flex items-center gap-1.5 text-xs text-fg-dim font-mono shrink-0">
            <Users size={10} />
            {cluster.members.length} accounts
          </span>
          {isHighRisk && (
            <span className="flex items-center gap-1 text-danger font-mono text-2xs">
              <AlertTriangle size={10} /> High risk
            </span>
          )}
        </div>
        <div className="flex items-center gap-3 shrink-0">
          <span className={`font-bold font-mono text-base ${scoreColor}`}>
            {Math.round(score * 100)}%
          </span>
          {expanded ? <ChevronDown size={13} className="text-fg-mute" /> : <ChevronRight size={13} className="text-fg-mute" />}
        </div>
      </button>

      {expanded && (
        <div className="px-4 pb-4 space-y-3 border-t border-border-1/50">
          {/* Evidence */}
          {cluster.evidence.length > 0 && (
            <div className="pt-3">
              <div className="font-mono text-2xs tracking-wider uppercase text-fg-mute mb-1.5">Evidence</div>
              <ul className="space-y-1">
                {cluster.evidence.map((e, i) => (
                  <li key={i} className="text-xs text-fg-dim pl-3 border-l border-border-2 leading-relaxed">
                    {e}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Member accounts */}
          <div>
            <div className="font-mono text-2xs tracking-wider uppercase text-fg-mute mb-2">
              Accounts in ring ({cluster.members.length})
            </div>
            <div className="flex flex-wrap gap-1.5">
              {cluster.members.map((id) => {
                const info = handleMap.get(id);
                const handle = info?.handle ?? id;
                const tier = info?.tier ?? 'low';
                return (
                  <Link
                    key={id}
                    href={`/accounts/${encodeURIComponent(id)}?platform=youtube`}
                    className="inline-flex items-center gap-1.5 px-2 py-1 rounded-sm border border-border-2 hover:border-border-hot hover:bg-bg-elev-2/50 transition-colors"
                  >
                    <TierBadge tier={tier as any} size="sm" />
                    <span className="font-mono text-2xs text-fg">{handle}</span>
                  </Link>
                );
              })}
            </div>
          </div>

          {/* Metadata scores */}
          {Object.keys(cluster.metadata).length > 0 && (
            <div>
              <div className="font-mono text-2xs tracking-wider uppercase text-fg-mute mb-1.5">Signal scores</div>
              <div className="grid grid-cols-2 gap-x-4 gap-y-1">
                {Object.entries(cluster.metadata).map(([k, v]) => (
                  <div key={k} className="flex justify-between text-xs font-mono">
                    <span className="text-fg-mute capitalize">{k.replace(/_/g, ' ')}</span>
                    <span className="text-fg-dim">{(v * 100).toFixed(0)}%</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Helper components
// ---------------------------------------------------------------------------

function Stat({ icon, label, value, sub }: {
  icon: React.ReactNode; label: string; value: number | string; sub: string;
}) {
  return (
    <div className="bg-bg border border-border-1 rounded-xl p-3.5 hover:border-border-hot/60 transition-colors">
      <div className="flex items-center justify-between mb-1.5">
        <span className="font-mono text-2xs tracking-[0.16em] text-fg-mute uppercase">{label}</span>
        <span className="text-fg-faint">{icon}</span>
      </div>
      <div className="text-xl font-semibold text-fg mono tracking-tight">{value}</div>
      <div className="text-2xs text-fg-mute font-mono tracking-wider">{sub}</div>
    </div>
  );
}

function SubScan({ label, prob, tier, sub, customBody }: {
  label: string; prob?: number; tier?: any; sub?: string; customBody?: React.ReactNode;
}) {
  return (
    <div className="bg-bg border border-border-1 rounded-xl p-3.5">
      <div className="font-mono text-2xs tracking-[0.16em] text-fg-mute uppercase mb-2">
        {label}
      </div>
      {customBody ?? (
        <>
          <div className="text-xl font-semibold text-fg mono tracking-tight mb-1">
            {prob != null ? `${Math.round(prob * 100)}%` : '—'}
          </div>
          <div className="flex items-center gap-2">
            <TierBadge tier={tier} size="sm" />
            {sub && <span className="text-2xs text-fg-mute font-mono">{sub}</span>}
          </div>
        </>
      )}
    </div>
  );
}

function DistChip({ n, tone }: { n: number; tone: 'high' | 'elevated' | 'moderate' | 'low' }) {
  const bg: Record<typeof tone, string> = {
    high: 'border-tier-high/40 bg-tier-high/10 text-tier-high',
    elevated: 'border-tier-elevated/40 bg-tier-elevated/10 text-tier-elevated',
    moderate: 'border-tier-moderate/40 bg-tier-moderate/10 text-tier-moderate',
    low: 'border-tier-low/40 bg-tier-low/10 text-tier-low',
  };
  return (
    <span className={`px-1.5 py-0.5 rounded-sm border font-mono text-2xs uppercase tracking-wider ${bg[tone]}`}>
      {n} {tone.charAt(0)}
    </span>
  );
}
