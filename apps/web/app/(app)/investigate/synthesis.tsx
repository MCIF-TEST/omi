import { Activity, Search, Zap, Network as NetworkIcon } from 'lucide-react';
import { TierBadge } from '@/components/shared/tier-badge';
import { ProbabilityBar } from '@/components/shared/probability-bar';
import { type ComprehensiveScanResult } from '@/lib/api';

export function Synthesis({ data }: { data: ComprehensiveScanResult }) {
  const prob = data.overall_probability;
  const v = data.video;
  return (
    <article className="p-6 space-y-6">
      <header>
        <div className="flex items-center gap-3 mb-1">
          <span className="font-mono text-2xs tracking-[0.18em] text-fg-mute uppercase">
            Comprehensive Intelligence Verdict
          </span>
        </div>
        <div className="flex items-baseline gap-4 mt-3 mb-3 flex-wrap">
          <span className="text-5xl font-bold mono text-fg tracking-tight">
            {Math.round(prob * 100)}%
          </span>
          <TierBadge tier={data.overall_tier} size="lg" />
        </div>
        <ProbabilityBar value={prob} tier={data.overall_tier} showLabel={false} />
        <p className="mt-4 text-sm text-fg-dim leading-relaxed">{data.summary}</p>
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

function Stat({ icon, label, value, sub }: {
  icon: React.ReactNode; label: string; value: number | string; sub: string;
}) {
  return (
    <div className="bg-bg border border-border-1 rounded-sm p-3">
      <div className="flex items-center justify-between mb-1">
        <span className="font-mono text-2xs tracking-[0.16em] text-fg-mute uppercase">{label}</span>
        <span className="text-fg-mute">{icon}</span>
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
    <div className="bg-bg border border-border-1 rounded-sm p-3">
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
