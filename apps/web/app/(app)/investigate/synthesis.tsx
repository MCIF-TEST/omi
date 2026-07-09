'use client';

import { useState } from 'react';
import { Activity, Search, Zap, Network as NetworkIcon, ChevronDown, ChevronRight, Users, AlertTriangle, ShieldCheck, ShieldAlert, Info } from 'lucide-react';
import Link from 'next/link';
import { TierBadge } from '@/components/shared/tier-badge';
import { ScoreRing } from '@/components/shared/score-ring';
import { ConfidenceBand } from '@/components/shared/confidence-band';
import { EvidenceForAgainst } from '@/components/shared/trust-lists';
import { HowToRead } from '@/components/shared/how-to-read';
import { type ComprehensiveScanResult, type CoordinationCluster, isCorroborated } from '@/lib/api';

export function Synthesis({ data }: { data: ComprehensiveScanResult }) {
  const prob = data.overall_probability;
  const v = data.video;
  const conf = _overallConfidence(data);
  const state = _resultState(data, conf);
  return (
    <article className="p-6 space-y-6">
      {/* First-view comprehension aid — the same reading-order guidance the
          public/campaign reports carry, on the user's OWN first result. */}
      <HowToRead storageKey="investigate-synthesis" />
      {/* Verdict hero — the dominant, glanceable unit: gauge + tier + confidence,
          fused. The probability is the visual king; everything below is a sub-score. */}
      <header className="aurora relative overflow-hidden rounded-2xl border border-border-1 bg-bg-elev p-6 md:p-7">
        <span className="absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-accent/50 to-transparent" />
        <div className="relative flex items-center gap-6 flex-wrap md:flex-nowrap">
          <ScoreRing value={prob} tier={data.overall_tier} size={132} stroke={10} className="shrink-0" />
          <div className="flex-1 min-w-[220px]">
            <span className="section-label">Suspicion verdict</span>
            <div className="flex items-center gap-3 mt-2.5 mb-2.5 flex-wrap">
              <TierBadge tier={data.overall_tier} size="lg" />
              <span className="text-sm text-fg-mute">
                {Math.round(prob * 100)}% inauthenticity probability
              </span>
            </div>
            <p className="text-sm text-fg-dim leading-relaxed">{data.summary}</p>
            <div className="mt-4">
              <ConfidenceBand probability={prob} confidence={conf} />
            </div>
          </div>
        </div>
      </header>

      {/* Why this verdict — result-state + evidence-for / weakening. Confidence is
          now fused into the hero above; corroboration + sampling caveats remain. */}
      <VerdictTrustBlock data={data} conf={conf} state={state} />

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
          {/* P3.1.6 — consume the AI Comment Analysis compatibility output when present; the
              probability/tier echo the same engine number, so this never destabilizes the view.
              Falls back to the deterministic thread_scan when Comment Analysis is disabled. */}
          <SubScan
            label="Thread"
            prob={(v.comment_analysis ?? v.thread_scan).overall_probability}
            tier={(v.comment_analysis ?? v.thread_scan).tier}
            sub={v.comment_analysis ? (v.comment_analysis.model_backed ? 'AI · whole corpus' : 'floor · whole corpus') : 'whole corpus'}
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
// Verdict trust block — "Why does Omi believe this, and what would weaken it?"
// Everything here is derived from fields already on the payload (per-commenter
// reasons / weak_signals / confidence, cluster evidence + methods, cross-links).
// The displayed confidence is the mean of the detectors' own confidence — a
// surfacing of existing values, NOT a new scoring system.
// ---------------------------------------------------------------------------

type ResultState = 'coordination_found' | 'organic' | 'insufficient_data' | 'scan_incomplete';

const RESULT_STATE_META: Record<
  ResultState,
  { label: string; tone: string; icon: React.ReactNode; body: string }
> = {
  coordination_found: {
    label: 'Coordination found',
    tone: 'text-tier-elevated border-tier-elevated/40 bg-tier-elevated/[0.07]',
    icon: <ShieldAlert size={14} />,
    body: 'At least one coordinated cluster was detected on this scan. Review the corroboration status and the rings below before treating it as a campaign — coordination is a lead to verify, not a verdict of intent.',
  },
  organic: {
    label: 'Organic — no coordination corroborated',
    tone: 'text-tier-low border-tier-low/40 bg-tier-low/[0.07]',
    icon: <ShieldCheck size={14} />,
    body: 'Omi scanned enough activity and did not find corroborated coordination. This is a substantive "looks organic" result, not a failure — most authentic content lands here.',
  },
  // Distinct from "organic" and from "insufficient data": the scan tried to
  // fetch accounts and a meaningful share FAILED (often a temporary API or
  // quota limit), so coverage is incomplete. Not "clean" — re-run shortly.
  scan_incomplete: {
    label: 'Scan incomplete — some accounts could not be fetched',
    tone: 'text-tier-moderate border-tier-moderate/40 bg-tier-moderate/[0.07]',
    icon: <AlertTriangle size={14} />,
    body: 'Part of this scan could not be completed — a share of the accounts failed to fetch, usually a temporary API or quota limit (when the daily quota is fully spent, scans are refunded and return an error instead). This is NOT a "clean" result: re-run shortly, and check the service-status pill before relying on it.',
  },
  insufficient_data: {
    label: 'Not enough data for a confident read',
    tone: 'text-fg-mute border-border-2 bg-bg-elev/30',
    icon: <Info size={14} />,
    body: 'The accounts scanned cleanly but carry too little history/volume to score confidently — detectors mostly abstained. This is not "clean": widen the scan (more commenters) or add account history before relying on the result.',
  },
};

function _dedupe(items: string[]): string[] {
  const seen = new Set<string>();
  const out: string[] = [];
  for (const s of items) {
    const k = (s || '').trim();
    if (k && !seen.has(k)) { seen.add(k); out.push(k); }
  }
  return out;
}

/** Mean of the detectors' OWN confidence, weighted like the verdict's parts.
 *  Surfacing of existing values — not a new score. */
function _overallConfidence(data: ComprehensiveScanResult): number {
  const parts: { value: number; weight: number }[] = [];
  if (data.focus_account) parts.push({ value: data.focus_account.confidence ?? 0, weight: 1 });
  const commenters = data.video?.commenters ?? [];
  if (commenters.length) {
    const mean = commenters.reduce((s, c) => s + (c.confidence ?? 0), 0) / commenters.length;
    parts.push({ value: mean, weight: 0.8 });
  }
  const cs: any = data.comments_scan;
  if (cs && typeof cs.confidence === 'number') parts.push({ value: cs.confidence, weight: 0.7 });
  const wsum = parts.reduce((s, p) => s + p.weight, 0);
  if (!wsum) return 0;
  return parts.reduce((s, p) => s + p.value * p.weight, 0) / wsum;
}

function _resultState(data: ComprehensiveScanResult, conf: number): ResultState {
  const v = data.video;
  const clusters = v?.clusters ?? [];
  const coordFound =
    clusters.some((c) => c.score >= 0.5) ||
    (v ? v.coordination_tier === 'elevated' || v.coordination_tier === 'high' : false) ||
    data.overall_tier === 'elevated' || data.overall_tier === 'high';
  if (coordFound) return 'coordination_found';

  // Quota-vs-clean: a non-trivial share of fetch FAILURES means the scan was
  // incomplete (likely a transient/quota limit) — not a clean read. Distinct
  // from genuinely-thin data. Uses the per-commenter `error` already on the
  // payload; no new data.
  const commenters = v?.commenters ?? [];
  if (commenters.length >= 3) {
    const errored = commenters.filter((c) => c.error).length;
    if (errored / commenters.length >= 0.3) return 'scan_incomplete';
  }

  const focusDepth = data.focus_account?.history_size ?? 0;
  const scannedEnough = conf >= 0.3 && (commenters.length >= 5 || focusDepth >= 8);
  return scannedEnough ? 'organic' : 'insufficient_data';
}

function _evidenceFor(data: ComprehensiveScanResult): string[] {
  const out: string[] = [];
  const v = data.video;
  for (const c of [...(v?.clusters ?? [])].sort((a, b) => b.score - a.score).slice(0, 3)) {
    if (c.evidence?.[0]) out.push(c.evidence[0]);
  }
  for (const l of (data.cross_links ?? []).filter((x) => x.severity === 'high' || x.severity === 'elevated').slice(0, 2)) {
    if (l.summary) out.push(l.summary);
  }
  for (const r of (data.focus_account?.reasons ?? []).slice(0, 2)) out.push(r);
  for (const c of (v?.commenters ?? []).filter((x) => x.tier === 'moderate' || x.tier === 'elevated' || x.tier === 'high')) {
    for (const r of c.reasons ?? []) out.push(r);
  }
  return _dedupe(out).slice(0, 5);
}

function _evidenceAgainst(data: ComprehensiveScanResult, conf: number, state: ResultState): string[] {
  const out: string[] = [];
  const commenters = data.video?.commenters ?? [];
  for (const c of commenters) for (const w of c.weak_signals ?? []) out.push(w);
  const lowConf = commenters.filter((c) => (c.confidence ?? 0) < 0.4).length;
  if (commenters.length && lowConf > 0) {
    out.push(`${lowConf} of ${commenters.length} commenters had too little history for a confident read — their scores are tentative.`);
  }
  if (state === 'coordination_found') {
    out.push('Even corroborated coordination is not proof of intent: legitimate on-message groups (newsrooms, campaigns, fandoms) can share methods. Verify before concluding.');
  } else {
    out.push('Shared phrasing or timing can reflect a common reaction to the same content rather than coordination — Omi requires corroboration across independent methods before treating it as a campaign.');
  }
  if (conf < 0.3) {
    out.push('Overall confidence is low — limited data backed this scan. Widen the scan or add account history before relying on it.');
  }
  return _dedupe(out).slice(0, 5);
}

function VerdictTrustBlock({ data, conf, state }: {
  data: ComprehensiveScanResult; conf: number; state: ResultState;
}) {
  const meta = RESULT_STATE_META[state];
  const forItems = _evidenceFor(data);
  const againstItems = _evidenceAgainst(data, conf, state);
  const clusters = data.video?.clusters ?? [];
  const methods = clusters.map((c) => c.method);
  const corroborated = clusters.length > 0 ? isCorroborated(methods) : null;

  return (
    <section className="space-y-4">
      {/* Honest result-state banner */}
      <div className={`flex items-start gap-3 rounded-xl border p-4 ${meta.tone}`}>
        <span className="shrink-0 mt-0.5">{meta.icon}</span>
        <div className="min-w-0">
          <div className="font-mono text-2xs uppercase tracking-wider mb-1">{meta.label}</div>
          <p className="text-sm text-fg-dim leading-relaxed">{meta.body}</p>
        </div>
        {corroborated !== null && (
          <span
            title={corroborated
              ? 'A discriminative detector (fingerprint / co-engagement / co-tag) or ≥2 independent methods agree.'
              : 'Only a single non-discriminative detector fired — capped at MODERATE under the corroboration gate.'}
            className={`shrink-0 inline-flex items-center gap-1 font-mono text-2xs uppercase tracking-wider px-2 py-1 rounded-sm border ${
              corroborated
                ? 'border-accent/40 bg-accent/10 text-accent'
                : 'border-tier-moderate/40 bg-tier-moderate/10 text-tier-moderate'
            }`}
          >
            {corroborated ? <ShieldCheck size={11} /> : <AlertTriangle size={11} />}
            {corroborated ? 'corroborated' : 'supporting only'}
          </span>
        )}
      </div>

      {/* M1 — sampling disclosure. The scanned accounts are whatever the
          platform returned (recency/relevance order), not a random draw, so
          findings shouldn't be generalized to the whole audience. */}
      {(data.video?.commenters?.length ?? 0) > 0 && (
        <p className="text-2xs text-fg-faint leading-relaxed">
          Based on the {data.video!.commenters.length} accounts the platform returned for
          this scan{data.next_page_token ? ' (more are available)' : ''}. This is not a
          random sample and may not represent all participants — read it as a close look at
          these accounts, not a measure of the whole audience.
        </p>
      )}

      {/* Why this verdict / what would weaken it */}
      <EvidenceForAgainst
        forItems={forItems}
        againstItems={againstItems}
        forEmpty="No specific suspicion signals fired on this scan."
        againstEmpty="No data-quality caveats surfaced."
      />
    </section>
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
      <div className="stat-value text-xl font-semibold text-fg">{value}</div>
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
          <div className="stat-value text-xl font-semibold text-fg mb-1">
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
