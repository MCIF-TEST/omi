import Link from 'next/link';
import { redirect } from 'next/navigation';
import {
  ArrowLeft, ArrowRight, Gauge, Users, ShieldCheck, Brain, TrendingUp,
} from 'lucide-react';
import { Card, CardLabel, CardTitle } from '@/components/ui/card';
import { Sparkline } from '@/components/shared/sparkline';
import { TierBadge } from '@/components/shared/tier-badge';
import { apiServer } from '@/lib/api-server';
import { getCurrentUser } from '@/lib/auth';
import {
  type SeedBenchmarkReport,
  type CoordinationBenchmarkReport,
  type RescueBenchmarkReport,
  type MemoryBenchmarkReport,
} from '@/lib/api';

export const metadata = { title: 'Engine Intelligence — OMISPHERE' };
export const dynamic = 'force-dynamic';

const pct = (x: number) => `${Math.round(x * 100)}%`;
type Tone = 'good' | 'warn' | 'bad' | 'neutral';

export default async function EnginePage() {
  const user = await getCurrentUser();
  if (!user || !user.is_admin) {
    redirect('/settings');
  }

  const [seed, coord, rescue, memory] = await Promise.all([
    apiServer<SeedBenchmarkReport>('/v1/intelligence/benchmark').catch(() => null),
    apiServer<CoordinationBenchmarkReport>('/v1/intelligence/benchmark/coordination').catch(() => null),
    apiServer<RescueBenchmarkReport>('/v1/intelligence/benchmark/rescue').catch(() => null),
    apiServer<MemoryBenchmarkReport>('/v1/intelligence/benchmark/memory').catch(() => null),
  ]);

  return (
    <div className="space-y-6 max-w-4xl">
      <div>
        <Link
          href="/settings"
          className="inline-flex items-center gap-1.5 text-sm text-fg-mute hover:text-fg-dim font-mono tracking-wider uppercase mb-4"
        >
          <ArrowLeft size={14} /> Back to settings
        </Link>
        <p className="font-mono text-2xs tracking-[0.18em] text-fg-mute uppercase mb-1 flex items-center gap-2">
          <Gauge size={12} className="text-accent" /> Admin · engine intelligence
        </p>
        <h1 className="text-2xl font-semibold text-fg tracking-tight">Engine intelligence</h1>
        <p className="mt-2 text-sm text-fg-dim max-w-2xl leading-relaxed">
          The engine&apos;s measured quality on curated, version-locked benchmarks —
          the synthetic counterpart to the{' '}
          <Link href="/settings/calibration" className="text-accent hover:underline">
            real-label calibration
          </Link>{' '}
          view. Every number here is enforced by a CI gate: a regression fails the
          build. This is &ldquo;intelligence-grade, continuously improving&rdquo; as a
          tracked number rather than an assertion.
        </p>
      </div>

      {/* 1 — Single-account accuracy */}
      <Card>
        <CardLabel>seed_v1 · single-account accuracy</CardLabel>
        {!seed ? (
          <Unavailable />
        ) : (
          <>
            <CardTitle>How well the engine scores one account at a time</CardTitle>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mt-4">
              <Metric
                label="Tier accuracy"
                value={pct(seed.tier_accuracy)}
                tone={seed.tier_accuracy > seed.majority_class_rate + 0.1 ? 'good'
                  : seed.tier_accuracy > seed.majority_class_rate ? 'warn' : 'bad'}
                sub={`vs ${pct(seed.majority_class_rate)} baseline`}
              />
              <Metric label="Brier score" value={seed.brier_score.toFixed(3)}
                tone={seed.brier_score <= 0.12 ? 'good' : seed.brier_score <= 0.2 ? 'warn' : 'bad'}
                sub="lower is better" />
              <Metric label="Macro F1" value={seed.macro_f1.toFixed(2)}
                tone={seed.macro_f1 >= 0.6 ? 'good' : seed.macro_f1 >= 0.3 ? 'warn' : 'bad'}
                sub="avg across tiers" />
              <Metric label="Cases" value={seed.n_cases} tone="neutral" sub="labeled archetypes" />
            </div>
            <p className="mt-4 text-sm text-fg-dim leading-relaxed">
              The single-account engine is deliberately conservative: it under-flags
              sparse-history accounts rather than risk a false accusation. That is a
              floor, not the product — the rescue and memory benchmarks below show how
              coordination and accumulated history recover that recall.
            </p>
          </>
        )}
      </Card>

      {/* 2 — Coordination detection */}
      <Card>
        <CardLabel>coordination_v1 · cross-account detection</CardLabel>
        {!coord ? (
          <Unavailable />
        ) : (
          <>
            <CardTitle className="flex items-center gap-2">
              <Users size={16} className="text-accent" /> Recovering planted coordination rings
            </CardTitle>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mt-4">
              <Metric label="Cluster recall" value={pct(coord.cluster_recall)}
                tone={rate(coord.cluster_recall)} sub="planted rings found" />
              <Metric label="Member precision" value={pct(coord.member_precision)}
                tone={rate(coord.member_precision)} sub="flagged are bots" />
              <Metric label="Member recall" value={pct(coord.member_recall)}
                tone={rate(coord.member_recall)} sub="bots caught" />
              <Metric label="Clean pass rate" value={pct(coord.clean_pass_rate)}
                tone={rate(coord.clean_pass_rate)} sub="no false rings" />
            </div>
            <p className="mt-4 text-2xs text-fg-mute font-mono tracking-wider uppercase">
              {coord.n_scenarios} scenarios · {coord.n_with_planted} with planted rings · {coord.n_clean} clean controls
            </p>
          </>
        )}
      </Card>

      {/* 3 — Coordination rescue (the bridge) */}
      <Card>
        <CardLabel>coordination_rescue_v1 · within-scan recall rescue</CardLabel>
        {!rescue ? (
          <Unavailable />
        ) : (
          <>
            <CardTitle className="flex items-center gap-2">
              <ShieldCheck size={16} className="text-accent" /> Coordination rescues what single-account scoring misses
            </CardTitle>

            {/* before / after recall */}
            <div className="mt-5 grid grid-cols-1 sm:grid-cols-[1fr_auto_1fr] items-center gap-4">
              <BeforeAfter label="Standalone recall" value={rescue.standalone_bot_recall} tone="bad" />
              <div className="flex flex-col items-center text-accent">
                <TrendingUp size={20} />
                <span className="font-mono text-2xs tracking-wider mt-1">
                  +{pct(rescue.recall_lift)}
                </span>
              </div>
              <BeforeAfter label="With coordination" value={rescue.adjusted_bot_recall} tone="good" />
            </div>

            <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mt-5">
              <Metric label="Rescue rate" value={pct(rescue.rescue_rate)} tone={rate(rescue.rescue_rate)}
                sub={`${rescue.n_rescued}/${rescue.n_rescuable} lifted`} />
              <Metric label="Mean prob lift" value={`+${pct(rescue.mean_prob_lift)}`} tone="good"
                sub="per in-cluster bot" />
              <Metric label="Organic false-lift" value={pct(rescue.organic_false_lift)}
                tone={rescue.organic_false_lift <= 0.05 ? 'good' : 'bad'} sub="clean escalated" />
              <Metric label="Bots / organics" value={`${rescue.n_bots} / ${rescue.n_organic}`} tone="neutral"
                sub="ground truth" />
            </div>
          </>
        )}
      </Card>

      {/* 4 — Memory learning curve */}
      <Card>
        <CardLabel>memory_v1 · across-scan learning</CardLabel>
        {!memory ? (
          <Unavailable />
        ) : (
          <>
            <CardTitle className="flex items-center gap-2">
              <Brain size={16} className="text-accent" /> Becomes smarter as more videos are analyzed
            </CardTitle>

            <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mt-4">
              <Metric label="Cold recall" value={pct(memory.cold_bad_recall)} tone="bad"
                sub="empty store" />
              <Metric label="Warm recall" value={pct(memory.warm_bad_recall)} tone={rate(memory.warm_bad_recall)}
                sub="full store" />
              <Metric label="Learning lift" value={`+${pct(memory.memory_recall_lift)}`} tone="good"
                sub="cold → warm" />
              <Metric label="False-lift / inert" value={`${pct(memory.good_false_lift)} / ${pct(memory.distant_inert_rate)}`}
                tone={memory.good_false_lift <= 0.05 && memory.distant_inert_rate >= 0.99 ? 'good' : 'warn'}
                sub="clean / unmatched" />
            </div>

            <h3 className="mt-5 mb-2 font-mono text-2xs text-fg-mute uppercase tracking-wider">
              Learning curves — adjusted probability vs. reference-store size [{memory.store_sizes.join(', ')}]
            </h3>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              {memory.per_scenario.map((s) => {
                const points = s.learning_curve.map((p) => p.adjusted_probability);
                const warm = s.learning_curve[s.learning_curve.length - 1];
                return (
                  <div key={s.label} className="bg-bg border border-border-1 rounded-xl p-3.5">
                    <div className="flex items-center justify-between mb-1">
                      <span className="font-mono text-2xs text-fg-dim tracking-wider truncate pr-2">
                        {s.label.replace(/_/g, ' ')}
                      </span>
                      <span className={`font-mono text-2xs uppercase tracking-wider ${hoodColor(s.neighborhood)}`}>
                        {s.neighborhood}
                      </span>
                    </div>
                    <Sparkline points={points} tier={warm.adjusted_tier} height={48} />
                    <div className="flex items-center justify-between mt-1.5">
                      <span className="font-mono text-2xs text-fg-mute">
                        {pct(s.standalone_probability)} → {pct(warm.adjusted_probability)}
                      </span>
                      <TierBadge tier={warm.adjusted_tier} size="sm" />
                    </div>
                  </div>
                );
              })}
            </div>
            <p className="mt-4 text-sm text-fg-dim leading-relaxed">
              Each curve is one account scored repeatedly as the fingerprint store
              fills with previously-seen accounts. Bad accounts in a known-bad
              neighborhood climb into a flagged tier; a clean account in a
              previously-cleared neighborhood is nudged <em>down</em>; an account that
              matches nothing stays flat — the memory signal is conservative when it
              has no evidence.
            </p>
          </>
        )}
      </Card>

      {/* Methodology */}
      <Card>
        <CardLabel>Methodology</CardLabel>
        <p className="text-sm text-fg-dim leading-relaxed mb-3">
          These four benchmarks are version-locked synthetic fixtures that drive the
          real production scoring path. Each has a pytest gate that fails CI on
          regression, and the gate constants ratchet up as accuracy improves. Run
          them locally with:
        </p>
        <pre className="bg-bg-elev border border-border-1 rounded-sm px-3 py-2 font-mono text-xs text-fg-dim overflow-x-auto">
{`cd apps/api
python -m pytest tests/test_evaluation_benchmark.py      # seed_v1
python -m pytest tests/test_coordination_benchmark.py    # coordination_v1
python -m pytest tests/test_rescue_benchmark.py          # coordination_rescue_v1
python -m pytest tests/test_memory_benchmark.py          # memory_v1`}
        </pre>
        <Link
          href="/settings/calibration"
          className="mt-4 inline-flex items-center gap-1.5 text-sm text-accent hover:underline font-mono tracking-wider"
        >
          View real-label calibration <ArrowRight size={14} />
        </Link>
      </Card>
    </div>
  );
}

function rate(x: number): Tone {
  return x >= 0.8 ? 'good' : x >= 0.5 ? 'warn' : 'bad';
}

function hoodColor(h: string): string {
  return h === 'bad' ? 'text-tier-high' : h === 'good' ? 'text-tier-low' : 'text-fg-faint';
}

function Unavailable() {
  return (
    <p className="text-sm text-fg-dim italic">
      Benchmark unavailable — the scoreboard endpoint did not respond.
    </p>
  );
}

function Metric({
  label, value, tone, sub,
}: { label: string; value: string | number; tone: Tone; sub?: string }) {
  const color = {
    good: 'text-tier-low',
    warn: 'text-tier-moderate',
    bad: 'text-tier-high',
    neutral: 'text-fg',
  }[tone];
  return (
    <div className="bg-bg-elev border border-border-1 rounded-sm p-3">
      <div className="font-mono text-2xs text-fg-mute uppercase tracking-wider mb-1">{label}</div>
      <div className={`font-mono text-2xl font-semibold tabular-nums ${color}`}>{value}</div>
      {sub && <div className="text-2xs text-fg-mute font-mono tracking-wider mt-0.5">{sub}</div>}
    </div>
  );
}

function BeforeAfter({ label, value, tone }: { label: string; value: number; tone: Tone }) {
  const color = tone === 'good' ? 'text-tier-low' : 'text-tier-high';
  return (
    <div className="bg-bg border border-border-1 rounded-xl p-4 text-center">
      <div className="font-mono text-2xs text-fg-mute uppercase tracking-wider mb-1">{label}</div>
      <div className={`font-mono text-3xl font-semibold tabular-nums ${color}`}>{pct(value)}</div>
      <div className="text-2xs text-fg-mute font-mono tracking-wider mt-0.5">bot recall</div>
    </div>
  );
}
